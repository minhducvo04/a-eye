"""Contract-checked, grounded v2 turns. Camera data stays in memory."""
import asyncio
from dataclasses import dataclass, field
import json
import re
from time import monotonic
from contextlib import aclosing
from uuid import uuid4

from contracts import schema, validate
from market.search import search
from server import packs
from server.boards import load_board
from server.packs.pc_build import board_prompt

POWER_LINE = 'Switch the power off and unplug it first. Tap Power is off when done.'


@dataclass
class Session:
    session_id: str
    pack: packs.Pack = field(default_factory=lambda: packs.get('general'))
    board_id: str = 'demo-b650'
    tts: str = 'browser'
    power_off: bool = False
    frame: dict | None = field(default=None, repr=False)
    history: list = field(default_factory=list, repr=False)
    vision_error_sent: bool = False
    emit: object = field(default=None, repr=False)
    scene: dict | None = field(default=None, repr=False)
    scene_seq: int = 0
    scene_time: float = 0
    scene_task: object = field(default=None, repr=False)
    speak: object = field(default=None, repr=False)
    board: dict = field(init=False)

    def __post_init__(self):
        self.board = load_board(self.board_id)


def message(kind, **fields):
    result = dict(v=2, type=kind, **fields)
    validate('server_message_v2', result)
    return result


def say(text, agent='helper'):
    return message('say', agent=agent, utterance_id=uuid4().hex, text=text)


def state(value, agent='helper', **fields):
    return message('agent_state', agent=agent, state=value, **fields)


def center(obj):
    x, y, w, h = obj['bbox']
    return [min(1, x + w / 2), min(1, y + h / 2)]


def resolve(turn, scene, seq):
    objects = {obj['id']: obj for obj in scene['objects']}
    ops = [dict(kind='clear', id='*')]
    focus = None
    for index, draw in enumerate(turn['draw']):
        obj = objects.get(draw.get('target'))
        if obj is None or draw['kind'] == 'clear':
            continue
        kind = draw['kind']
        origin = objects.get(draw.get('from_target'))
        if 'from_target' in draw and origin is None:
            continue
        at = center(obj)
        op = dict(kind=kind, id=f'draw-{index}', anchor=dict(object_id=obj['id'], bbox=obj['bbox']))
        if 'role' in draw:
            op['role'] = draw['role']
        if kind in ('box', 'highlight'):
            op['bbox'] = obj['bbox']
        elif kind == 'circle':
            op.update(center=at, r=max(obj['bbox'][2:]) / 2)
        elif kind in ('pin', 'label'):
            op['at'] = at
            if kind == 'label':
                op['text'] = draw.get('text') or obj['label'] or 'Object'
        elif kind == 'arrow':
            op.update({'from': center(origin) if origin else [0.5, 0.95], 'to': at})
        elif kind == 'path':
            x, y, w, h = obj['bbox']
            right, bottom = min(1, x + w), min(1, y + h)
            op['points'] = [[x, y], [right, y], [right, bottom], [x, bottom], [x, y]]
        ops.append(op)
        if focus is None:
            focus = at
    result = message('draw', agent=turn['agent'], seq=seq, ops=ops)
    validate('v2_draw', result)
    return result, focus


_DRAW_KINDS = {'box', 'highlight', 'circle', 'arrow', 'label', 'pin', 'path', 'clear'}
_ROLES = {'target', 'info', 'warn', 'ok'}
_CATEGORIES = {'cpu', 'board', 'ram', 'ssd', 'gpu', 'psu', 'cooler', 'case', 'fan'}


_SHOPPING = re.compile(r"\b(cheap\w*|price\w*|cost\w*|buy\w*|deal\w*|afford\w*|budget)\b", re.I)
_CATEGORY_WORDS = [('ram', r'\b(ram|memory|dimm|ddr\d?)\b'), ('ssd', r'\b(ssd|nvme|m\.2|drive|storage)\b'),
                   ('gpu', r'\b(gpu|graphics|video card)\b'), ('cpu', r'\b(cpu|processor)\b'),
                   ('psu', r'\b(psu|power supply)\b'), ('cooler', r'\bcooler\b'), ('case', r'\bcase\b'),
                   ('fan', r'\bfans?\b'), ('board', r'\b(motherboard|mainboard|board)\b')]


def shopping_category(text):
    """Return the part category when the user asks about buying or prices, else None."""
    if not _SHOPPING.search(text or ''):
        return None
    for category, pattern in _CATEGORY_WORDS:
        if re.search(pattern, text, re.I):
            return category
    return None


def sanitize_header(turn):
    """Small models bend the format (seen live: role "highlight" or "label", missing draw).
    Keep what is usable instead of throwing the whole turn away."""
    draws = []
    for item in turn.get('draw') or []:
        if not isinstance(item, dict) or item.get('kind') not in _DRAW_KINDS:
            continue
        clean = {k: item[k] for k in ('kind', 'target', 'from_target', 'text') if isinstance(item.get(k), str)}
        clean['kind'] = item['kind']
        if item.get('role') in _ROLES:
            clean['role'] = item['role']
        draws.append(clean)
    out = {'agent': turn.get('agent') if turn.get('agent') in ('helper', 'shopper') else 'helper', 'draw': draws}
    if turn.get('market_category') in _CATEGORIES:
        out['market_category'] = turn['market_category']
    return out


def parse_turn(text):
    start = text.find('{')
    if start < 0:
        raise ValueError('No JSON object')
    turn, _ = json.JSONDecoder().raw_decode(text[start:])
    validate('brain_turn', turn)
    if not turn['say'].strip():
        raise ValueError('Empty speech')
    return turn


async def run_turn(session, text, *, vision, llm):
    messages = []
    owner = asyncio.current_task()

    async def emit(msg):
        if owner.cancelling():
            raise asyncio.CancelledError
        messages.append(msg)
        if session.emit is not None:
            await session.emit(msg)

    def remember():
        session.history.extend([f'user: {text}'] + [
            f"{m['agent']}: {m['text']}" for m in messages if m['type'] == 'say'])
        session.history[:] = session.history[-10:]

    refusal = session.pack.refuse(text)
    if refusal or (session.pack.requires_power_off and not session.power_off):
        await emit(say(refusal or POWER_LINE))
        remember()
        return messages
    await emit(state('thinking'))
    started = monotonic()
    turn_id = uuid4().hex
    vlm_ms = 0
    scene = dict(caption='I do not have a camera view yet.', objects=[], ms=0)
    seq = 0
    if session.scene is None and session.scene_task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(session.scene_task), timeout=3)
        except Exception:
            pass
        finally:
            vlm_ms = (monotonic() - started) * 1000
    frame = getattr(session, 'frame', None)
    same_frame = frame is not None and frame.get('seq') == session.scene_seq
    # Fresh scene, or the scene of the newest frame (a still photo does not go stale).
    if session.scene is not None and (monotonic() - session.scene_time < 2 or same_frame):
        scene, seq = session.scene, session.scene_seq
    system = session.pack.system_prompt
    if session.pack.id == 'pc_build':
        system += board_prompt(session.board)
    system += (' Line 1: one JSON object with agent, draw and optional market_category. '
               'Do not include say in that object. Next line: SAY: then spoken text. '
               'Draw targets and from_target must be scene object IDs, never coordinates. '
               'Include market_category only when asked about buying, prices or cheaper options. '
               'Draw item schema: ' + json.dumps(schema()['$defs']['brain_turn']['properties']['draw'])
               + ' agent: helper or shopper; market_category: cpu, board, ram, ssd, gpu, psu, cooler, case, fan.')
    user = json.dumps(dict(caption=scene['caption'], objects=[
        {k: obj[k] for k in ('id', 'label', 'bbox')} for obj in scene['objects']],
        conversation=session.history[-10:], text=text))
    queue = asyncio.Queue()
    first_audio = None

    async def audio_worker():
        nonlocal first_audio
        while True:
            msg = await queue.get()
            try:
                if msg is None:
                    return
                async for audio in session.speak(msg):
                    await emit(audio)
                    if first_audio is None:
                        first_audio = (monotonic() - started) * 1000
            finally:
                queue.task_done()

    worker = asyncio.create_task(audio_worker()) if session.speak else None
    part = 0

    async def speech(value, final=False, agent='helper'):
        nonlocal part
        msg = say(value, agent)
        msg.update(turn_id=turn_id, part=part, final=final)
        part += 1
        await emit(msg)
        if worker:
            await queue.put(msg)

    turn = dict(agent='helper', draw=[])
    buffer = ''
    header = False
    marker = False
    invalid = False
    pending = None
    first_token = None
    brain_started = monotonic()
    try:
        async with aclosing(llm.stream(system, user)) as stream:
            async for delta in stream:
                if first_token is None:
                    first_token = (monotonic() - brain_started) * 1000
                buffer += delta
                if not header:
                    if '\n' not in buffer:
                        continue
                    line, buffer = buffer.split('\n', 1)
                    try:
                        turn = json.loads(line.strip().strip('`'))
                        if not isinstance(turn, dict):
                            raise ValueError('header is not an object')
                        # Small local models often omit fields; fill defaults, keep only known keys.
                        turn = sanitize_header(turn)
                        validate('brain_turn', dict(turn, say='stream'))
                    except Exception:
                        turn = dict(agent='helper', draw=[])
                        invalid = True
                        buffer = line + '\n' + buffer
                    drawing, focus = resolve(turn, scene, seq)
                    await emit(drawing)
                    await emit(state('speaking', turn['agent'], **({'focus': focus} if focus else {})))
                    header = True
                if not marker and not invalid:
                    buffer = buffer.lstrip()
                    if len(buffer) < 4:
                        continue
                    if buffer.startswith('SAY:'):
                        buffer = buffer[4:].lstrip()
                    marker = True
                while True:
                    match = re.search(r'[.!?\n]', buffer)
                    end = match.end() if match and match.end() <= 120 else (120 if len(buffer) >= 120 else 0)
                    if not end:
                        break
                    sentence, buffer = buffer[:end].strip(), buffer[end:]
                    if sentence.startswith('SAY:'):
                        sentence = sentence[4:].strip()
                    if sentence.startswith(('{', '[', '"')) or '"kind"' in sentence:
                        continue  # never speak JSON

                    if sentence:
                        if pending:
                            await speech(pending, agent=turn['agent'])
                        pending = sentence
                # Once more spoken text exists, the preceding sentence cannot be final.
                if pending and buffer.strip():
                    await speech(pending, agent=turn['agent'])
                    pending = None
        if not header:
            turn = dict(agent='helper', draw=[])
            await emit(resolve(turn, scene, seq)[0])
            await emit(state('speaking'))
        tail = buffer.strip()
        if tail:
            if pending:
                await speech(pending, agent=turn['agent'])
            pending = tail
        # Hard rule in code: a shopping question always brings in the shopper, even if the model forgot.
        if not turn.get('market_category'):
            category = shopping_category(text)
            if category:
                turn['market_category'] = category
        await speech(pending or scene['caption'] or 'Please tell me what you need.',
                     final=not bool(turn.get('market_category')), agent=turn['agent'])
        if turn.get('market_category'):
            await emit(state('thinking', 'shopper'))
            await speech('Let me check prices that fit.', agent='shopper')
            query = dict(v=1, category=turn['market_category'], owned_parts=[dict(
                category='board', model=session.board['model'], specs=session.board.get('specs', {}),
                confirmed=True, source='fixture')])
            try:
                result = await asyncio.to_thread(search, query)
                validate('market_response', result)
                await emit(message('market_results', agent='shopper', result=result))
                fits = [item for item in result['items'] if item['compat']['status'] == 'fits']
                cheapest = min(fits, key=lambda i: i['price_usd'] + i.get('shipping_usd', 0)) if fits else None
                answer = (f"{cheapest['title']} is the cheapest confirmed fit at "
                          f"${cheapest['price_usd'] + cheapest.get('shipping_usd', 0):.2f} including shipping."
                          if cheapest else "I couldn't confirm anything fits.")
            except Exception:
                answer = "I couldn't confirm anything fits."
            await emit(state('speaking', 'shopper'))
            await speech(answer, final=True, agent='shopper')
        if worker:
            await queue.put(None)
            await worker
    finally:
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    remember()
    timings = dict(turn_id=turn_id, vlm_ms=vlm_ms,
                   brain_first_token_ms=first_token or 0, turn_ms=(monotonic() - started) * 1000)
    if first_audio is not None:
        timings['first_audio_ms'] = first_audio
    await emit(message('metrics', **timings))
    return messages

"""Contract-checked, grounded v2 turns. Camera data stays in memory."""
import asyncio
from dataclasses import dataclass, field
import json
import re
from time import monotonic, time
from collections import deque
from statistics import median
from contextlib import aclosing
import os
from uuid import uuid4

from contracts import schema, validate
from market.search import search
from server import packs
from server.logs import event
from server.boards import load_board
from server.packs.pc_build import board_prompt

POWER_LINE = 'Switch the power off and unplug it first. Tap Power is off when done.'


@dataclass
class Session:
    session_id: str
    pack: packs.Pack = field(default_factory=lambda: packs.get('general'))
    board_id: str = 'demo-b650'
    tts: str = 'browser'
    camera: bool = True
    frame_time: float = field(default_factory=monotonic)
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
    refresh_requested: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    voice_pending: bool = False
    user_speaking: bool = False
    board: dict = field(init=False)

    def __post_init__(self):
        self.board = load_board(self.board_id)


def message(kind, **fields):
    result = dict(v=2, type=kind, **fields)
    validate('server_message_v2', result)
    return result


TURN_LATENCIES = deque(maxlen=5)


class Turn:
    """One input, including STT, owns exactly one terminal status."""
    def __init__(self, session, send, started=None):
        self.session = session
        self.send = send
        self.id = uuid4().hex
        self.started = monotonic() if started is None else started
        self.terminal = False
        self.spoken = False

    async def stage(self, stage, **fields):
        if self.terminal:
            return
        if stage == 'thinking' and TURN_LATENCIES:
            fields['typical_ms'] = round(median(TURN_LATENCIES))
        if stage == 'speaking':
            if self.spoken:
                return
            self.spoken = True
            TURN_LATENCIES.append((monotonic() - self.started) * 1000)
        self.terminal = stage in ('done', 'cancelled', 'failed')
        event('turn_' + stage, self.session.session_id,
              ms=(monotonic() - self.started) * 1000)
        await self.send(message('turn', turn_id=self.id, stage=stage,
                                at_ms=int(time() * 1000), **fields))


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


def sanitize_header(turn, scene_ids=None):
    """Small models bend the format (seen live: role "highlight" or "label", missing draw).
    Keep what is usable instead of throwing the whole turn away."""
    draws = []
    def items(value):
        if isinstance(value, list):
            for item in value:
                yield from items(item)
        elif isinstance(value, dict):
            yield value
            yield from items(value.get('items'))

    for item in items(turn.get('draw')):
        item = dict(item, kind=item.get('kind', item.get('type')))
        if item['kind'] not in _DRAW_KINDS:
            continue
        clean = {k: item[k] for k in ('kind', 'target', 'from_target', 'text') if isinstance(item.get(k), str)}
        clean['kind'] = item['kind']
        if not clean.get('text'):
            clean.pop('text', None)
        if scene_ids is not None and clean.get('from_target') not in scene_ids:
            clean.pop('from_target', None)
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


_SAY = re.compile(r'\bSAY\s*:', re.I)


def stream_header(value):
    """First balanced object, or a recoverable header before a bent SAY field."""
    start = value.find('{')
    if start < 0:
        return None
    depth, quoted, escaped = 0, False, False
    end = None
    for i in range(start, len(value)):
        char = value[i]
        if escaped:
            escaped = False
        elif char == '\\' and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            depth += (char == '{') - (char == '}')
            if depth == 0:
                end = i + 1
                break
    marker = _SAY.search(value)
    if marker and (end is None or marker.start() < end):
        raw = value[start:marker.start()].rstrip(' \n\t",') + '}'
        rest = value[marker.end():]
    elif end is not None:
        raw, rest = value[start:end], value[end:]
    else:
        return None
    try:
        turn = json.loads(raw)
    except ValueError:
        turn = {}
    return turn, rest


def safe_speech(value):
    value = _SAY.sub('', value).strip().strip('"` \n\t')
    # Wrapper punctuation from a quoted SAY field is not spoken.
    value = re.sub(r'["}\]\s]+$', '', value).strip()
    if any(c in value for c in '{}[]') or re.search(r'"\s*:', value):
        return ''
    return value


TALKER_RULES = (' You are the TALKER: you speak first and fast. Reply with SAY: then one or two short spoken '
                 'sentences, nothing else, never JSON. A planner reads the same view and draws on the picture for you; '
                 'lines from "planner" in the conversation are its notes, trust them. If the answer needs a closer look '
                 'than the view note gives, say a short filler such as "Let me look." and stop.')
PLANNER_RULES = (' You are the PLANNER behind a fast talker who is already answering out loud. Output only one JSON '
                 'object: agent, draw, optional market_category, note, speak. draw targets and from_target must be '
                 'scene object IDs. note: at most 15 words the talker should say next (the concrete fact, for example '
                 'which header the cable goes in). speak: true only when the note adds a fact the caption alone does '
                 'not give. Include market_category only when asked about buying, prices or cheaper options.')
_FILLER = re.compile(r"\b(let me (look|check|see)|one (sec|second|moment)|hang on|looking)\b", re.I)


async def run_turn(session, text, *, vision, llm, started_at=None, turn_id=None, planner=None):
    """One voice turn. With planner set (talker + thinker mode), llm only talks and planner draws in parallel."""
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

    turn_id = turn_id or uuid4().hex
    refusal = session.pack.refuse(text)
    if refusal or (session.pack.requires_power_off and not session.power_off):
        msg = say(refusal or POWER_LINE)
        msg.update(turn_id=turn_id, part=0, final=True)
        await emit(message('reply_delta', agent='helper', turn_id=turn_id, text=msg['text']))
        await emit(msg)
        if session.speak:
            async for audio in session.speak(msg):
                await emit(audio)
        remember()
        return messages
    await emit(state('thinking'))
    started = started_at if started_at is not None else monotonic()
    vlm_ms = 0
    scene = dict(caption='I do not have a camera view yet.', objects=[], ms=0)
    seq = 0
    fresh = session.camera and monotonic() - session.frame_time <= 3
    if not session.camera:
        scene['caption'] = 'camera is off'
    if fresh and session.scene is None and session.scene_task is not None:
        wait_started = monotonic()
        try:
            await asyncio.wait_for(asyncio.shield(session.scene_task), timeout=0.3)
        except Exception:
            pass
        finally:
            vlm_ms = (monotonic() - wait_started) * 1000
    # Cached grounding avoids putting a slow refresh on the voice critical path.
    if fresh and session.scene is not None:
        scene, seq = session.scene, session.scene_seq
    system = session.pack.system_prompt
    duo = planner is not None
    if not session.camera:
        system += ' The camera is off. Answer by voice only; do not draw.'
    if session.pack.id == 'pc_build':
        system += board_prompt(session.board)
    base_system = system
    system += TALKER_RULES if duo else (' Line 1: one JSON object with agent, draw and optional market_category. '
               'Do not include say in that object. Next line: SAY: then spoken text. '
               'Start speech with a short first clause of 4 to 8 words, ending in a comma or period. '
               'Draw targets and from_target must be scene object IDs, never coordinates. '
               'Include market_category only when asked about buying, prices or cheaper options. '
               'Draw item schema: ' + json.dumps(schema()['$defs']['brain_turn']['properties']['draw'])
               + ' agent: helper or shopper; market_category: cpu, board, ram, ssd, gpu, psu, cooler, case, fan.')
    user = json.dumps(dict(caption=scene['caption'], objects=[
        {k: obj[k] for k in ('id', 'label', 'bbox')} for obj in scene['objects']],
        conversation=session.history[-10:], text=text))
    planner_task = None

    async def plan():
        planner_system = base_system + PLANNER_RULES + ' Draw item schema: ' + json.dumps(
            schema()['$defs']['brain_turn']['properties']['draw'])
        raw = ''
        async with aclosing(planner.stream(planner_system, user, max_tokens=400,
                                           model=os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5-5'))) as stream:
            async for delta in stream:
                raw += delta
        parsed = stream_header(raw)
        head = parsed[0] if parsed else {}
        clean = sanitize_header(head, {obj['id'] for obj in scene['objects']})
        validate('brain_turn', dict(clean, say='plan'))
        if session.camera and clean['draw']:
            await emit(resolve(clean, scene, seq)[0])
        note = head.get('note') if isinstance(head.get('note'), str) else ''
        return clean, safe_speech(note)[:160], head.get('speak') is True

    if duo:
        planner_task = asyncio.create_task(plan())
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
        value = safe_speech(value)
        if not value:
            return
        msg = say(value, agent)
        msg.update(turn_id=turn_id, part=part, final=final)
        part += 1
        await emit(msg)
        if worker:
            await queue.put(msg)

    turn = dict(agent='helper', draw=[])
    buffer = ''
    header = duo
    marker = False
    pending = None
    first_token = None
    brain_started = monotonic()
    reply_text = ''
    reply_sent = 0
    delta_at = float('-inf')
    delta_task = None

    async def flush_delta():
        nonlocal reply_sent, delta_at
        if len(safe_speech(reply_text).lstrip(' ,;:')) <= reply_sent:
            return
        await asyncio.sleep(max(0, .08 - (monotonic() - delta_at)))
        clean = safe_speech(reply_text).lstrip(' ,;:')
        if len(clean) > reply_sent:
            await emit(message('reply_delta', agent=turn['agent'], turn_id=turn_id,
                               text=clean[reply_sent:]))
            reply_sent = len(clean)
            delta_at = monotonic()

    try:
        async with aclosing(llm.stream(system, user)) as stream:
            async for delta in stream:
                if first_token is None:
                    first_token = (monotonic() - brain_started) * 1000
                    if duo:
                        await emit(state('speaking'))
                buffer += delta
                if not header:
                    parsed = stream_header(buffer)
                    if parsed is None:
                        continue
                    raw, buffer = parsed
                    turn = sanitize_header(raw, {obj['id'] for obj in scene['objects']})
                    validate('brain_turn', dict(turn, say='stream'))
                    drawing, focus = resolve(turn, scene, seq)
                    if session.camera:
                        await emit(drawing)
                    await emit(state('speaking', turn['agent'], **({'focus': focus} if focus else {})))
                    header = True
                was_marker = marker
                if not marker:
                    buffer = buffer.lstrip(' \n\t"')
                    if len(buffer) < 4:
                        continue
                    match = _SAY.search(buffer)
                    if match:
                        buffer = buffer[match.end():].lstrip(' \n\t"')
                    marker = True
                reply_text += delta if was_marker else buffer
                if delta_task is None or delta_task.done():
                    if delta_task is not None:
                        await delta_task
                    if monotonic() - delta_at >= .08:
                        await flush_delta()
                    else:
                        delta_task = asyncio.create_task(flush_delta())
                while True:
                    match = re.search(r'[.!?\n]', buffer)
                    if part == 0:
                        clause = next((m for m in re.finditer(r'[,;]', buffer)
                                       if len(buffer[:m.end()].split()) >= 4), None)
                        if clause and (match is None or clause.end() < match.end()):
                            match = clause
                    end = match.end() if match and match.end() <= 120 else (120 if len(buffer) >= 120 else 0)
                    if not end:
                        break
                    sentence, buffer = safe_speech(buffer[:end]), buffer[end:]
                    if sentence.startswith('SAY:'):
                        sentence = sentence[4:].strip()
                    # Seen live: '}, SAY: ...' left a leading ', ' on the first spoken chunk.
                    sentence = sentence.lstrip(' ,;:').strip()
                    if sentence.startswith(('{', '[', '"')) or '"kind"' in sentence:
                        continue  # never speak JSON

                    if sentence:
                        if pending:
                            await speech(pending, agent=turn['agent'])
                        if part == 0 and len(sentence.split()) >= 4:
                            await speech(sentence, agent=turn['agent'])
                            pending = None
                        else:
                            pending = sentence
                # Once more spoken text exists, the preceding sentence cannot be final.
                if pending and buffer.strip():
                    await speech(pending, agent=turn['agent'])
                    pending = None
        if delta_task:
            await delta_task
        await flush_delta()
        if not header:
            turn = dict(agent='helper', draw=[])
            if session.camera:
                await emit(resolve(turn, scene, seq)[0])
            await emit(state('speaking'))
        tail = safe_speech(buffer)
        if tail:
            if pending:
                await speech(pending, agent=turn['agent'])
            pending = tail
        # Hard rule in code: a shopping question always brings in the shopper, even if the model forgot.
        if not turn.get('market_category'):
            category = shopping_category(text)
            if category:
                turn['market_category'] = category
        if pending or part == 0:
            await speech(pending or 'Please tell me what you need.',
                         final=not bool(turn.get('market_category')), agent=turn['agent'])
        if planner_task is not None:
            # The thinker's note is spoken only when it adds a fact, or when the talker stalled with a filler.
            planned_at = monotonic()
            try:
                planned, note, speak_note = await asyncio.wait_for(
                    asyncio.shield(planner_task), float(os.environ.get('PLANNER_WAIT_S', '5')))
            except Exception:
                planned, note, speak_note = None, '', False
            stalled = bool(_FILLER.search(reply_text))
            event('planner', session.session_id, ms=(monotonic() - planned_at) * 1000)
            if planned and planned.get('market_category') and not turn.get('market_category'):
                turn['market_category'] = planned['market_category']
            if note and (speak_note or stalled):
                session.history.append(f'planner: {note}')
                await speech(note, final=not bool(turn.get('market_category')))
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
        if planner_task is not None and not planner_task.done():
            planner_task.cancel()
            await asyncio.gather(planner_task, return_exceptions=True)
        if delta_task:
            delta_task.cancel()
            await asyncio.gather(delta_task, return_exceptions=True)
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

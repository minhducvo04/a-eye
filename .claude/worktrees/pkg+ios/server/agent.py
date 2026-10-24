"""Contract-checked, grounded v2 turns. Camera data stays in memory."""
import asyncio
from dataclasses import dataclass, field
import json
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
        op = dict(kind=kind, id=f'draw-{index}')
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

    async def emit(msg):
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
    frame = session.frame
    scene = dict(caption='I do not have a camera view yet.', objects=[], ms=0)
    if frame:
        queries = list(session.pack.default_queries)
        if text.strip():
            queries.append(text.strip()[:60])
        try:
            scene = await vision.call('scene', dict(image_b64=frame['jpeg_b64'], queries=queries[:8]))
            validate('scene_response', scene)
        except Exception:
            scene = dict(caption='I could not see the scene.', objects=[], ms=0)
            if not session.vision_error_sent:
                await emit(message('error', code='vision_unavailable', message='Vision is unavailable.'))
                session.vision_error_sent = True
    system = session.pack.system_prompt
    if session.pack.id == 'pc_build':
        system += board_prompt(session.board)
    system += (' Reply only with JSON matching brain_turn. Use agent helper; say is your spoken text. '
               'Draw targets and optional from_target must be scene object IDs, never coordinates. '
               'Include market_category only when asked about buying, prices or cheaper options. '
               + json.dumps(schema()['$defs']['brain_turn'])
               + ' agent: helper or shopper; role: target, info, warn, ok; '
               'market_category: cpu, board, ram, ssd, gpu, psu, cooler, case, fan.')
    user = json.dumps(dict(caption=scene['caption'], objects=[
        {k: obj[k] for k in ('id', 'label', 'bbox')} for obj in scene['objects']],
        conversation=session.history[-10:], text=text))
    try:
        reply = await asyncio.to_thread(llm.complete, system, user)
        turn = parse_turn(reply.text)
    except Exception:
        turn = dict(agent='helper', say=scene['caption'] + ' I can point at it if you tell me what you need',
                    draw=[dict(kind='box', target=scene['objects'][0]['id'])] if scene['objects'] else [])
    drawing, focus = resolve(turn, scene, frame['seq'] if frame else 0)
    await emit(drawing)
    await emit(state('speaking', turn['agent'], **({'focus': focus} if focus else {})))
    await emit(say(turn['say'], turn['agent']))
    if turn.get('market_category'):
        await emit(state('thinking', 'shopper'))
        await emit(say('Let me check prices that fit.', 'shopper'))
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
        await emit(say(answer, 'shopper'))
    remember()
    return messages

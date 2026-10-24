"""Rewind: a searchable memory of the call through TwelveLabs video search. Off by default.

While Rewind is on, short clips are cut around change-triggered keyframes from frames held in memory. Each clip is
encoded to a temporary MP4, uploaded to a dedicated TwelveLabs index and deleted locally right after the upload.
Clips are built from camera frames only (no audio). Search is for objects and moments: no face or person tagging.
The API key stays on the server and is never logged.
"""
import asyncio
import base64
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import tempfile
from time import monotonic, time

import httpx

from server.logs import event

API = 'https://api.twelvelabs.io/v1.3'
INDEX_NAME = os.environ.get('REWIND_INDEX', 'a-eye-rewind')
NOTICE = 'Rewind on: short video clips of this call are uploaded to TwelveLabs so you can ask about them later.'

PRE_S = 2.0           # seconds kept before a keyframe
POST_S = 3.0          # seconds kept after it (TwelveLabs needs at least 4 s per video)
MAX_CLIP_S = 12.0     # a busy stretch extends one clip up to this length
SAMPLE_FPS = 4.0      # frames per second kept in the ring
KEEP_FRAMES = 6       # frames per clip kept in memory after upload, for pointing
MAX_CLIPS = 60        # per call

_QUESTION = re.compile(
    r"\b(when did i|when was|where did i (put|leave|place|set|drop)|where('s| is) the .+ i (put|left)|"
    r"what did i do with|did i (already )?(plug|connect|install|put|remove)|rewind)\b", re.I)


def is_rewind_question(text):
    return bool(_QUESTION.search(text or ''))


def query_from(text):
    """Turn "when did I plug in the CPU fan?" into a visual query: the moment, not the question words."""
    value = re.sub(r"^\s*(hey\s+)?(a-?eye,?\s*)?", '', text or '', flags=re.I)
    value = re.sub(r"\b(when|where) did i\b|\bwhat did i do with\b|\bdid i (already )?\b|\brewind\b", '', value,
                   flags=re.I)
    value = re.sub(r"[?!.]+$", '', value).strip(' ,')
    return value or (text or '').strip()


_ARTICLE = re.compile(r"\b(the|a|an|my|your|that|this)\s+", re.I)


def target_from(query):
    """The object to look for: the words after the last article ("plug in the CPU fan" -> "CPU fan")."""
    parts = _ARTICLE.split(query)
    return (parts[-1] if len(parts) > 1 else query).strip() or query


def label_matches(label, target):
    words = {w for w in re.findall(r'[a-z0-9]+', target.lower()) if len(w) > 2}
    return bool(words & set(re.findall(r'[a-z0-9]+', label.lower())))


async def confirm(vision, jpeg, target, min_conf=0.5):
    """Ask our vision host whether the target is in the hit frame. Matching objects, or [] (also on failure)."""
    try:
        scene = await vision.call('scene', dict(image_b64=base64.b64encode(jpeg).decode(), queries=[target],
                                                caption=False))
    except Exception:
        return []
    return [o for o in scene.get('objects', []) if o.get('conf', 0) >= min_conf and label_matches(o['label'], target)]


def fmt_offset(seconds):
    seconds = max(0, int(round(seconds)))
    if seconds < 5:
        return 'right at the start of the call'
    minutes, rest = divmod(seconds, 60)
    if not minutes:
        return f'about {rest} seconds in'
    unit = f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f'about {unit} {rest} seconds in' if rest else f'about {unit} in'


class TwelveLabsClient:
    """Plain HTTP against v1.3: indexes, tasks (upload), search. Thin on purpose; tests swap in a fake."""

    def __init__(self, key=None, transport=None, base=API):
        self.key = key
        self.transport = transport
        self.base = base

    def _headers(self):
        key = self.key or os.environ.get('TWELVELABS_API_KEY', '')
        if not key:
            raise RuntimeError('TWELVELABS_API_KEY is not set')
        return {'x-api-key': key}

    def _client(self, timeout=30):
        return httpx.AsyncClient(base_url=self.base, timeout=timeout, transport=self.transport,
                                 headers=self._headers())

    async def ensure_index(self, name=INDEX_NAME):
        async with self._client() as client:
            response = await client.get('/indexes', params={'index_name': name, 'page_limit': 50})
            response.raise_for_status()
            for item in response.json().get('data', []):
                if item.get('index_name') == name:
                    return item['_id']
            response = await client.post('/indexes', json={
                'index_name': name, 'addons': ['thumbnail'],
                'models': [{'model_name': 'marengo3.0', 'model_options': ['visual']}]})
            response.raise_for_status()
            return response.json()['_id']

    async def upload(self, index_id, path, metadata):
        async with self._client(timeout=120) as client:
            with open(path, 'rb') as handle:
                response = await client.post('/tasks', data={
                    'index_id': index_id, 'user_metadata': json.dumps(metadata)},
                    files={'video_file': ('clip.mp4', handle, 'video/mp4')})
            response.raise_for_status()
            body = response.json()
            return body['_id'], body.get('video_id')

    async def task(self, task_id):
        async with self._client() as client:
            response = await client.get(f'/tasks/{task_id}')
            response.raise_for_status()
            return response.json()

    async def analyze(self, mp4_bytes, prompt, schema=None, model=None, max_tokens=800):
        """Pegasus over POST /analyze with the video as base64 (30 MB limit). Returns (text, usage)."""
        body = dict(model_name=model or os.environ.get('REWIND_PEGASUS_MODEL', 'pegasus1.5'),
                    video=dict(type='base64_string', base64_string=base64.b64encode(mp4_bytes).decode()),
                    prompt=prompt, stream=False, temperature=0.1, max_tokens=max_tokens)
        if schema:
            body['response_format'] = dict(type='json_schema', json_schema=schema)
        async with self._client(timeout=180) as client:
            response = await client.post('/analyze', json=body)
            response.raise_for_status()
            result = response.json()
            return result.get('data') or '', result.get('usage') or {}

    async def search(self, index_id, query, video_ids=None, limit=5):
        data = [('index_id', index_id), ('query_text', query), ('search_options', 'visual'),
                ('group_by', 'clip'), ('page_limit', str(limit)), ('include_user_metadata', 'true')]
        if video_ids:
            data.append(('filter', json.dumps({'id': list(video_ids)})))
        async with self._client() as client:
            # multipart/form-data as the API requires; repeated fields stay repeated.
            response = await client.post('/search', files=[(k, (None, v)) for k, v in data])
            response.raise_for_status()
            return response.json().get('data', [])


def encode_mp4(frames, path):
    """JPEG frames (bytes) -> H.264 MP4 at the real frame rate; at least 4 s and 360 px on the short side."""
    duration = max(4.0, frames[-1][0] - frames[0][0] + 1 / SAMPLE_FPS)
    rate = max(1.0, len(frames) / duration)
    scale = ("scale='if(gt(iw,ih),-2,360)':'if(gt(iw,ih),360,-2)',"
             "scale='min(iw,1280)':-2,pad=ceil(iw/2)*2:ceil(ih/2)*2")
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', f'{rate:.4f}', '-i', '-',
               '-vf', scale, '-t', f'{duration:.3f}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-an', path]
    payload = b''.join(jpeg for _, jpeg in frames)
    # Pad the tail by repeating the last frame so a short clip still reaches 4 s.
    needed = int(duration * rate + 0.999) - len(frames)
    payload += frames[-1][1] * max(0, needed)
    subprocess.run(command, input=payload, check=True, capture_output=True, timeout=60)
    return duration


@dataclass
class Clip:
    start_s: float              # call time of the first frame
    end_s: float
    key_s: float = 0.0          # call time of the keyframe that opened the clip
    frames: list = field(default_factory=list, repr=False)   # (call_s, jpeg bytes)
    reasons: list = field(default_factory=list)
    task_id: str | None = None
    video_id: str | None = None
    status: str = 'open'        # open, pending, uploading, indexing, ready, failed


class Rewind:
    """One call's Rewind state. Frames stay in memory; only finished clips leave, and only while on."""

    def __init__(self, session_id, client=None, clock=monotonic, wall=time, encoder=encode_mp4):
        self.session_id = session_id
        self.client = client or TwelveLabsClient()
        self.clock = clock
        self.wall = wall
        self.encoder = encoder
        self.on = False
        self.started = clock()
        self.started_wall = wall()
        self.ring = deque()
        self.clips = []
        self.index_id = None
        self.last_sample = float('-inf')
        self.lock = asyncio.Lock()
        self.uploads = []       # (task_id, upload_ms) for the report and status
        self.waits = set()
        self.end_task = None    # end-of-call upload, awaited by the recap route
        self.mode = None

    def now_s(self):
        return self.clock() - self.started

    def set_on(self, value):
        self.on = bool(value)
        if not self.on:
            self.ring.clear()
            # Unsent clips are dropped when the user turns Rewind off.
            self.clips = [c for c in self.clips if c.status not in ('open', 'pending')]

    def add_frame(self, jpeg_b64):
        if not self.on:
            return
        t = self.now_s()
        if t - self.last_sample < 1 / SAMPLE_FPS:
            return
        self.last_sample = t
        try:
            jpeg = base64.b64decode(jpeg_b64, validate=True)
        except ValueError:
            return
        self.ring.append((t, jpeg))
        while self.ring and t - self.ring[0][0] > PRE_S + MAX_CLIP_S:
            self.ring.popleft()
        for clip in self.clips:
            if clip.status == 'open':
                if t <= clip.end_s:
                    clip.frames.append((t, jpeg))
                else:
                    clip.status = 'pending'

    def keyframe(self, reason):
        """Called by the scene loop after the keyframe gate selects a frame."""
        if not self.on or reason not in ('first', 'change'):
            return None
        t = self.now_s()
        open_clip = next((c for c in self.clips if c.status == 'open'), None)
        if open_clip and t - open_clip.start_s + POST_S <= MAX_CLIP_S:
            open_clip.end_s = max(open_clip.end_s, t + POST_S)
            open_clip.reasons.append(reason)
            return open_clip
        if open_clip:
            open_clip.status = 'pending'
        if len(self.clips) >= MAX_CLIPS:
            return None
        clip = Clip(start_s=max(0.0, t - PRE_S), end_s=t + POST_S, key_s=t, reasons=[reason])
        clip.frames = [f for f in self.ring if f[0] >= clip.start_s]
        self.clips.append(clip)
        return clip

    def close(self):
        for clip in self.clips:
            if clip.status == 'open':
                clip.status = 'pending'

    async def flush(self, wait=False, timeout=600):
        """Upload every finished clip. Temp files are removed right after each upload."""
        async with self.lock:
            ready = [c for c in self.clips if c.status == 'pending' and c.frames]
            if not ready:
                return []
            if self.index_id is None:
                self.index_id = await self.client.ensure_index()
            for clip in ready:
                clip.status = 'uploading'
                started = monotonic()
                handle, path = tempfile.mkstemp(suffix='.mp4', prefix='rewind-')
                os.close(handle)
                try:
                    await asyncio.to_thread(self.encoder, clip.frames, path)
                    metadata = dict(call=self.call_tag(), start_s=round(clip.start_s, 2),
                                    end_s=round(clip.end_s, 2), started_at=int(self.started_wall))
                    clip.task_id, clip.video_id = await self.client.upload(self.index_id, path, metadata)
                    clip.status = 'indexing'
                    self.uploads.append((clip.task_id, (monotonic() - started) * 1000))
                except Exception as exc:
                    clip.status = 'failed'
                    event('dependency_error', self.session_id, dependency='twelvelabs', level='error',
                          error=type(exc).__name__)
                finally:
                    os.unlink(path)
                # Keep a few frames for pointing at the answer; the rest leave memory now.
                if len(clip.frames) > KEEP_FRAMES:
                    step = len(clip.frames) / KEEP_FRAMES
                    kept = {int(i * step) for i in range(KEEP_FRAMES)}
                    # Always keep the first frame after the change: the moment the answer points at.
                    kept.add(next((i for i, f in enumerate(clip.frames) if f[0] >= clip.key_s), 0))
                    clip.frames = [clip.frames[i] for i in sorted(kept)]
        waits = [self.wait_ready(c, timeout) for c in ready if c.status == 'indexing']
        if wait:
            await asyncio.gather(*waits)
        else:
            for coroutine in waits:
                task = asyncio.create_task(coroutine)
                self.waits.add(task)
                task.add_done_callback(self.waits.discard)
        return ready

    async def wait_ready(self, clip, timeout=600, every=3.0):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            try:
                status = (await self.client.task(clip.task_id)).get('status')
            except Exception:
                status = None
            if status == 'ready':
                clip.status = 'ready'
                return True
            if status == 'failed':
                clip.status = 'failed'
                return False
            await asyncio.sleep(every)
        return False

    def call_tag(self):
        return datetime.fromtimestamp(self.started_wall, timezone.utc).strftime('%Y%m%dT%H%M%S')

    def status(self):
        counts = {}
        for clip in self.clips:
            counts[clip.status] = counts.get(clip.status, 0) + 1
        return dict(on=self.on, clips=len(self.clips), ready=counts.get('ready', 0),
                    indexing=counts.get('indexing', 0) + counts.get('uploading', 0),
                    pending=counts.get('pending', 0) + counts.get('open', 0))

    async def search(self, query, limit=3):
        """Hits in this call, best first: call time, clip window and the nearest kept frame."""
        clips = {c.video_id: c for c in self.clips if c.video_id and c.status == 'ready'}
        if not clips:
            return []
        rows = await self.client.search(self.index_id, query, video_ids=list(clips), limit=limit)
        hits = []
        for row in sorted(rows, key=lambda r: r.get('rank', 99)):
            clip = clips.get(row.get('video_id'))
            if clip is None:
                continue
            start, end = clip.start_s + float(row.get('start', 0)), clip.start_s + float(row.get('end', 0))
            # The change that opened the clip is the moment; fall back to the hit start.
            at = clip.key_s if start <= clip.key_s <= end else start
            # The first kept frame at or after the moment: a frame just before a change shows the old scene.
            after = [f for f in clip.frames if f[0] >= at - 1e-6]
            frame = (after[0] if after else clip.frames[-1])[1] if clip.frames else None
            hits.append(dict(t_s=round(at, 1), start_s=round(start, 1), end_s=round(end, 1), rank=row.get('rank'),
                             video_id=clip.video_id, frame=frame))
        return hits

    async def answer(self, text, vision=None):
        """Spoken line plus the best hit (or None). TwelveLabs gives rank but no score, so the rank-1 frame is
        checked by our own vision host (no extra cloud call) before the talker claims it; that check also gives
        the box the caller draws on the hit frame."""
        if not self.on and not self.clips:
            return "Rewind is off, so I didn't keep clips of this call. Turn on Rewind to use it.", None
        query = query_from(text)
        if self.on and any(c.status == 'pending' for c in self.clips):
            # Upload the newest clips; this answer uses what is indexed now.
            task = asyncio.create_task(self.flush())
            self.waits.add(task)
            task.add_done_callback(self.waits.discard)
        try:
            hits = await self.search(query)
        except Exception as exc:
            event('dependency_error', self.session_id, dependency='twelvelabs', level='error',
                  error=type(exc).__name__)
            return "I couldn't reach Rewind just now.", None
        if not hits:
            busy = self.status()
            if busy['indexing'] or busy['pending']:
                return "I'm still indexing the latest clips. Ask me again in a minute.", None
            return "I didn't find that moment in this call.", None
        hit = dict(hits[0], query=query, target=target_from(query), objects=[], sure=False)
        if vision is not None and hit['frame']:
            hit['objects'] = await confirm(vision, hit['frame'], hit['target'])
            hit['sure'] = bool(hit['objects'])
        hit['alternatives'] = [h['t_s'] for h in hits[1:2]]
        if hit['sure']:
            return f"That was {fmt_offset(hit['t_s'])}. Here's the clip.", hit
        times = ' or '.join(fmt_offset(t) for t in [hit['t_s']] + hit['alternatives'])
        return f"I'm not sure I saw it. Maybe {times}. Here's my best guess.", hit

    async def aclose(self):
        for task in list(self.waits):
            task.cancel()
        await asyncio.gather(*self.waits, return_exceptions=True)

    async def follow(self, session, every=None):
        """Sample the session's newest frame (from this socket or a paired phone camera) and upload finished
        clips every few minutes while the call goes on. The end of the call is Registry.end."""
        every = every or float(os.environ.get('REWIND_FLUSH_S', '60'))
        self.mode = getattr(getattr(session, 'pack', None), 'id', None)
        seq = None
        next_flush = self.clock() + every
        while True:
            frame = session.frame if session.camera else None
            if frame is not None and frame.get('seq') != seq:
                seq = frame.get('seq')
                self.add_frame(frame['jpeg_b64'])
            if self.on and self.clock() >= next_flush:
                next_flush = self.clock() + every
                try:
                    await self.flush()
                except Exception as exc:
                    event('dependency_error', self.session_id, dependency='twelvelabs', level='error',
                          error=type(exc).__name__)
            await asyncio.sleep(1 / SAMPLE_FPS / 2)


class Registry:
    """Recent calls' Rewind state for this server process, so a question after the call still finds it."""

    def __init__(self, client=None, keep=5, encoder=None):
        self.client = client
        self.encoder = encoder
        self.keep = keep
        self.calls = {}
        self.background = set()

    def open(self, session_id, on=False, **kwargs):
        if self.encoder is not None:
            kwargs.setdefault('encoder', self.encoder)
        rewind = Rewind(session_id, client=self.client, **kwargs)
        rewind.set_on(on)
        self.calls.pop(session_id, None)
        self.calls[session_id] = rewind
        while len(self.calls) > self.keep:
            old = self.calls.pop(next(iter(self.calls)))
            self.spawn(old.aclose())
        return rewind

    def get(self, session_id):
        return self.calls.get(session_id)

    def for_question(self, session_id=None):
        """This call when it has clips, else the newest call that does."""
        current = self.calls.get(session_id)
        if current and current.clips:
            return current
        return next((r for r in reversed(self.calls.values()) if r.clips), current)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return task

    def end(self, session_id):
        """End of call: upload whatever is left. Runs after the socket closes."""
        rewind = self.calls.get(session_id)
        if rewind is None:
            return None
        rewind.close()
        rewind.end_task = self.spawn(rewind.flush(wait=False)) if rewind.on else None
        return rewind.end_task


def registry(app):
    if not hasattr(app.state, 'rewind'):
        app.state.rewind = Registry(getattr(app.state, 'rewind_client', None))
    return app.state.rewind


def small_frame(jpeg, size=480):
    from PIL import Image
    import io
    with Image.open(io.BytesIO(jpeg)) as image:
        image.thumbnail((size, size))
        out = io.BytesIO()
        image.convert('RGB').save(out, format='JPEG', quality=80)
        return base64.b64encode(out.getvalue()).decode()


def wants_rewind(session, text):
    """Route a turn to Rewind only for a Rewind-style question while Rewind is on or has clips to search."""
    current = getattr(session, 'rewind', None)
    return ((is_rewind_question(text) or is_recap_request(text)) and current is not None
            and (current.on or bool(current.clips)))


def hit_message(result, turn_id=None):
    """The client card for a search_past result (frame with the object boxed), or None without a frame."""
    from server.agent import message
    if result.get('call_time_s') is None:
        return None
    fields = dict(query=result.get('query') or result.get('label') or '', t_s=result['call_time_s'],
                  start_s=result.get('start_s', result['call_time_s']), end_s=result.get('end_s', result['call_time_s']),
                  sure=result['sure'], alternatives=result['alternatives'][:3],
                  objects=[dict(id='rewind-0', label=result['label'] or 'object', bbox=result['box'], conf=1.0)]
                  if result.get('box') else [])
    if turn_id:
        fields['turn_id'] = turn_id
    if result.get('frame_b64'):
        fields['frame_b64'] = result['frame_b64']
    return message('rewind_hit', **fields)


def recap_message(result, turn_id=None):
    from server.agent import message
    return message('rewind_recap', steps=result['steps'], skipped=result['skipped'],
                   **({'turn_id': turn_id} if turn_id else {}))


async def rewind_turn(session, text, rewind, *, vision, turn_id):
    """Regex-routed Rewind turn: a short checking line, then the answer and its card (search or recap)."""
    from server.agent import message, say   # late import: agent imports nothing from here
    emit = session.emit
    part = 0

    async def speak(line, final):
        nonlocal part
        msg = say(line)
        msg.update(turn_id=turn_id, part=part, final=final)
        part += 1
        await emit(message('reply_delta', agent='helper', turn_id=turn_id, text=line + ' '))
        await emit(msg)
        if session.speak:
            async for audio in session.speak(msg):
                await emit(audio)

    recapping = is_recap_request(text)
    await speak(RECAP_CHECKING_LINE if recapping else CHECKING_LINE, False)
    if recapping:
        result = await recap_call(session)
        await emit(recap_message(result, turn_id))
    else:
        result = await search_past(session, text, vision=vision)
        card = hit_message(dict(result, query=query_from(text)), turn_id)
        if card:
            await emit(card)
    await speak(result['say'], True)
    session.history.extend([f'user: {text}', f"helper: {result['say']}"])
    session.history[:] = session.history[-10:]


def state_message(rewind):
    from server.agent import message
    return message('rewind_state', **rewind.status(), **({'notice': NOTICE} if rewind.on else {}))


# ---- Recap: Pegasus over the frames already uploaded while Rewind was on ----

TYPICAL_STEPS = {
    'pc_build': ['switch the PSU off and unplug it', 'install the CPU', 'mount the CPU cooler',
                 'plug in the CPU fan cable', 'install the RAM', 'install the M.2 SSD',
                 'connect the 24-pin power cable', 'connect the 8-pin CPU power cable',
                 'connect the front panel cables'],
    'cooking': ['wash your hands', 'prep the ingredients', 'heat the pan or oven', 'cook the food',
                'check that it is done', 'turn off the heat'],
    'assemble': ['lay out and count the parts', 'follow the steps in order', 'tighten every screw',
                 'check that it is stable'],
    'general': ['set up the workspace', 'do the main task', 'check the result', 'tidy up'],
}
RECAP_STEP_S = 0.5           # each kept frame shows for half a second in the recap video
RECAP_MAX_FRAMES = 240
_RECAP = re.compile(r"\b(recap|what have i done( so far)?|did i (skip|miss|forget) (anything|something))\b", re.I)
RECAP_SCHEMA = {
    'type': 'object', 'required': ['steps', 'skipped'],
    'properties': {
        'steps': {'type': 'array', 'items': {'type': 'object', 'required': ['t', 'text'], 'properties': {
            't': {'type': 'number'}, 'text': {'type': 'string'}}}},
        'skipped': {'type': 'array', 'items': {'type': 'string'}}}}


def is_recap_request(text):
    return bool(_RECAP.search(text or ''))


def recap_prompt(mode):
    typical = TYPICAL_STEPS.get(mode, TYPICAL_STEPS['general'])
    return ('This video is a time-lapse of moments kept from a hands-on video call, in order; time jumps between '
            'moments. List the concrete actions the person completed, in order, each with t = seconds into THIS '
            'video where it is visible, and text = a short past-tense step (under 10 words). Describe objects and '
            'actions only; never describe or identify people. Then, from this list of typical steps, return in '
            '"skipped" only the ones that clearly did not happen in the video: ' + json.dumps(typical) +
            '. Answer as JSON.')


async def recap(rewind, mode=None, encoder=None):
    """Ordered steps with call times, plus typical steps that look skipped. Uses only clips already uploaded."""
    mode = mode or getattr(rewind, 'mode', None) or 'general'
    clips = sorted((c for c in rewind.clips if c.status in ('indexing', 'ready') and c.frames),
                   key=lambda c: c.start_s)
    frames = [f for c in clips for f in c.frames][:RECAP_MAX_FRAMES]
    if not frames:
        return dict(steps=[], skipped=[], mode=mode, ms=0, usage={},
                    note='Nothing to recap yet: no clips were uploaded while Rewind was on.')
    started = monotonic()
    handle, path = tempfile.mkstemp(suffix='.mp4', prefix='recap-')
    os.close(handle)
    try:
        timed = [(i * RECAP_STEP_S, jpeg) for i, (_, jpeg) in enumerate(frames)]
        duration = await asyncio.to_thread(encoder or rewind.encoder, timed, path)
        with open(path, 'rb') as handle:
            video = handle.read()
    finally:
        os.unlink(path)
    text, usage = await rewind.client.analyze(video, recap_prompt(mode), schema=RECAP_SCHEMA)
    try:
        parsed = json.loads(text[text.find('{'):]) if '{' in text else {}
    except ValueError:
        parsed = {}
    rate = max(1.0, len(frames) / max(float(duration or 1), 1e-6))
    steps = []
    for step in parsed.get('steps') or []:
        if not isinstance(step, dict) or not str(step.get('text', '')).strip():
            continue
        try:
            at = float(step.get('t') or 0)
        except (TypeError, ValueError):
            at = 0.0
        index = min(len(frames) - 1, max(0, int(at * rate)))
        steps.append((round(frames[index][0], 1), at, str(step['text']).strip()[:120]))
    steps = [dict(t_s=t_s, text=text) for t_s, _, text in sorted(steps)]
    typical = TYPICAL_STEPS.get(mode, TYPICAL_STEPS['general'])
    # Hard rule in code: "skipped" can only name a typical step of this mode, never free text.
    skipped = [t for t in typical if any(t.lower() == str(x).strip().lower() for x in parsed.get('skipped') or [])]
    return dict(steps=steps[:12], skipped=skipped, mode=mode, ms=round((monotonic() - started) * 1000),
                usage=usage, frames=len(frames), clips=len(clips))


def recap_line(result):
    if not result['steps']:
        return result.get('note') or "I couldn't make a recap from the clips."
    done = '; '.join(s['text'].rstrip('.') for s in result['steps'][:5])
    line = f"Here's what you did: {done}."
    if result['skipped']:
        line += f" You may have skipped: {', '.join(result['skipped'][:3])}."
    else:
        line += " I don't see a typical step skipped."
    return line


# ---- Tool interface for the talker (the lead owns the talker; these are the functions it calls) ----

CHECKING_LINE = 'Let me check the recording.'
RECAP_CHECKING_LINE = 'Let me look back over the call.'


def rewind_for(session, app=None):
    """This call's Rewind, or the newest recent call with clips when this one has none."""
    current = getattr(session, 'rewind', None)
    if current is not None and current.clips:
        return current
    if app is not None:
        return registry(app).for_question(getattr(session, 'session_id', None))
    return current


async def search_past(session, query, vision=None, app=None):
    """Find a past moment of this call. Returns a JSON-safe dict for a tool_result:
    {sure, call_time_s, label, box, clip_id, alternatives, say} (plus frame_b64 for the client card)."""
    rewind = rewind_for(session, app)
    empty = dict(sure=False, call_time_s=None, label=None, box=None, clip_id=None, alternatives=[])
    if rewind is None or (not rewind.on and not rewind.clips):
        return dict(empty, say="Rewind is off, so there's no recording to check.")
    spoken, hit = await rewind.answer(query, vision=vision)
    if hit is None:
        return dict(empty, say=spoken)
    best = hit['objects'][0] if hit['objects'] else None
    result = dict(sure=hit['sure'], call_time_s=hit['t_s'], label=best['label'] if best else hit['target'],
                  box=best['bbox'] if best else None, clip_id=hit['video_id'], alternatives=hit['alternatives'],
                  start_s=hit['start_s'], end_s=hit['end_s'], say=spoken)
    if hit.get('frame'):
        try:
            result['frame_b64'] = await asyncio.to_thread(small_frame, hit['frame'])
        except Exception:
            pass
    return result


async def recap_call(session, app=None):
    """Recap of this call for a tool_result: {steps:[{t_s,text}], skipped:[...], say}."""
    rewind = rewind_for(session, app)
    if rewind is None or not rewind.clips:
        return dict(steps=[], skipped=[], say="Rewind is off, so there's nothing to recap.")
    if rewind.on and any(c.status == 'pending' for c in rewind.clips):
        await rewind.flush()       # upload the newest finished clips first; recap uses uploaded clips only
    mode = getattr(getattr(session, 'pack', None), 'id', None)
    try:
        result = await recap(rewind, mode=mode)
    except Exception as exc:
        event('dependency_error', getattr(session, 'session_id', None), dependency='twelvelabs', level='error',
              error=type(exc).__name__)
        return dict(steps=[], skipped=[], say="I couldn't make the recap just now.")
    return dict(steps=result['steps'], skipped=result['skipped'], say=recap_line(result))

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
    minutes, rest = divmod(seconds, 60)
    if not minutes:
        return f'{rest} seconds in'
    return f"{minutes} minute{'s' if minutes != 1 else ''} {rest} seconds in" if rest else \
        f"{minutes} minute{'s' if minutes != 1 else ''} in"


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
                    clip.frames = [clip.frames[int(i * step)] for i in range(KEEP_FRAMES)]
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
            frame = min(clip.frames, key=lambda f: abs(f[0] - at))[1] if clip.frames else None
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
            return f"That was about {fmt_offset(hit['t_s'])}. Here's the clip.", hit
        times = ' or '.join(fmt_offset(t) for t in [hit['t_s']] + hit['alternatives'])
        return f"I'm not sure I saw it. Maybe about {times}. Here's my best guess.", hit

    async def aclose(self):
        for task in list(self.waits):
            task.cancel()
        await asyncio.gather(*self.waits, return_exceptions=True)

    async def run(self, every=None):
        """Upload finished clips every few minutes while the call goes on (end of call: Registry.end)."""
        every = every or float(os.environ.get('REWIND_FLUSH_S', '60'))
        while True:
            await asyncio.sleep(every)
            if self.on:
                await self.flush()


class Registry:
    """Recent calls' Rewind state for this server process, so a question after the call still finds it."""

    def __init__(self, client=None, keep=5):
        self.client = client
        self.keep = keep
        self.calls = {}
        self.background = set()

    def open(self, session_id, on=False, **kwargs):
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
        return self.spawn(rewind.flush(wait=True)) if rewind.on else None


def registry(app):
    if not hasattr(app.state, 'rewind'):
        app.state.rewind = Registry(getattr(app.state, 'rewind_client', None))
    return app.state.rewind

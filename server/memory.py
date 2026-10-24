"""Local memory across calls: where things were put, kept on this machine only. Off by default.

Per memory id (a person, not a call) under data/private/memory/<id>/ (gitignored):
- log.jsonl: one line per CHANGED scene note (local Qwen caption, labels, tagged objects with boxes, a nearby
  object for "under the left cup", an int8 EmbeddingGemma vector). A heartbeat whose note did not change is not
  stored.
- crops/<id>.jpg: small JPEG crops (224 px long side) of caregiver-tagged objects only, never full frames. No crop
  is written when the frame shows a person (YOLO person class on our own GPU box) or when that check is
  unavailable (fail closed).
- tags.json: caregiver tags ("blue pill box", "key bowl") with an optional home place.
- videos.json: TwelveLabs video ids of this person's Rewind clips (only when Rewind cloud was on), so Forget can
  delete them too.
- owner.json: the identity (server.rewind.identity) that created the memory; other callers are refused.

At rest: encrypted with Fernet when A_EYE_MEMORY_KEY is set (a Fernet key in .env); otherwise protected by the
file system only (FileVault), and status says so. Retention: A_EYE_MEMORY_DAYS (default 7) days.
"""
import asyncio
import base64
import io
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, time
from uuid import uuid4

from server.logs import event

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'private' / 'memory'
CROP_SIDE = 224
_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
_PERSON = re.compile(r'\b(person|people|man|woman|boy|girl|child|face|baby)\b', re.I)
_WORD = re.compile(r'[a-z0-9]+')
_STOP = {'the', 'my', 'a', 'an', 'your', 'our', 'of', 'where', 'are', 'is', 'did', 'i', 'put', 'leave', 'left',
         'last', 'see', 'saw', 'find', 'have', 'you', 'seen', 'what', 'happened', 'to', 'it', 'they', 'them'}


def root():
    return Path(os.environ.get('A_EYE_MEMORY_DIR') or ROOT)


def retention_days():
    return float(os.environ.get('A_EYE_MEMORY_DAYS', '7'))


def words(text):
    return {w.rstrip('s') if len(w) > 3 else w for w in _WORD.findall((text or '').lower())} - _STOP


class Cipher:
    def __init__(self, key=None):
        key = key if key is not None else os.environ.get('A_EYE_MEMORY_KEY', '')
        self.fernet = None
        if key:
            from cryptography.fernet import Fernet
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    @property
    def encrypted(self):
        return self.fernet is not None

    def seal(self, data):
        return self.fernet.encrypt(data) if self.fernet else data

    def open(self, data):
        return self.fernet.decrypt(data) if self.fernet else data


class Store:
    """One person's memory folder. Every write and delete goes through here."""

    def __init__(self, memory_id, base=None, cipher=None, clock=time):
        if not _ID.match(memory_id or ''):
            raise ValueError('memory id: lowercase letters, digits and dashes, up to 40')
        self.id = memory_id
        self.dir = Path(base or root()) / memory_id
        self.cipher = cipher or Cipher()
        self.clock = clock

    # ---- files ----
    def _path(self, name):
        return self.dir / name

    def _read_json(self, name, default):
        path = self._path(name)
        if not path.exists():
            return default
        try:
            return json.loads(self.cipher.open(path.read_bytes()))
        except Exception:
            return default

    def _write_json(self, name, value):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(name + '.tmp')
        tmp.write_bytes(self.cipher.seal(json.dumps(value).encode()))
        tmp.replace(self._path(name))

    def owner(self):
        return self._read_json('owner.json', {}).get('owner')

    def claim(self, owner):
        """First caller owns the memory; anyone else is refused."""
        current = self.owner()
        if current is None:
            self._write_json('owner.json', {'owner': owner})
            return True
        return current == owner

    def records(self):
        path = self._path('log.jsonl')
        if not path.exists():
            return []
        out = []
        for line in path.read_bytes().splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(self.cipher.open(line)))
            except Exception:
                continue
        return out

    def append(self, record):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._path('log.jsonl'), 'ab') as handle:
            handle.write(self.cipher.seal(json.dumps(record, separators=(',', ':')).encode()) + b'\n')

    def _rewrite(self, records):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path('log.jsonl.tmp')
        with open(tmp, 'wb') as handle:
            for record in records:
                handle.write(self.cipher.seal(json.dumps(record, separators=(',', ':')).encode()) + b'\n')
        tmp.replace(self._path('log.jsonl'))

    def save_crop(self, jpeg):
        crop_id = uuid4().hex[:16]
        (self.dir / 'crops').mkdir(parents=True, exist_ok=True)
        (self.dir / 'crops' / f'{crop_id}.jpg').write_bytes(self.cipher.seal(jpeg))
        return crop_id

    def load_crop(self, crop_id):
        if not re.fullmatch(r'[0-9a-f]{16}', crop_id or ''):
            return None
        path = self.dir / 'crops' / f'{crop_id}.jpg'
        try:
            return self.cipher.open(path.read_bytes())
        except Exception:
            return None

    def tags(self):
        return self._read_json('tags.json', {})

    def set_tag(self, name, label=None, home=None, kind='object'):
        name = ' '.join((name or '').split())[:60]
        if not name:
            raise ValueError('empty tag')
        tags = self.tags()
        tags[name.lower()] = dict(name=name, label=(label or name)[:60], home=(home or None) and home[:60],
                                  kind=kind if kind in ('object', 'place') else 'object', created=self.clock())
        self._write_json('tags.json', tags)
        return tags[name.lower()]

    def videos(self):
        return self._read_json('videos.json', [])

    def add_video(self, index_id, video_id):
        videos = self.videos()
        videos.append(dict(index_id=index_id, video_id=video_id, t=self.clock()))
        self._write_json('videos.json', videos)

    # ---- counts and deletes ----
    def count(self, item=None):
        notes = [r for r in self.records() if r.get('note')]
        if item:
            notes = [r for r in notes if mentions(r, item)]
        return len(notes)

    def size_bytes(self):
        return sum(p.stat().st_size for p in self.dir.rglob('*') if p.is_file()) if self.dir.exists() else 0

    def _drop(self, keep):
        records = self.records()
        kept = [r for r in records if keep(r)]
        gone = [r for r in records if not keep(r)]
        for record in gone:
            for crop_id in (record.get('crops') or {}).values():
                path = self.dir / 'crops' / f'{crop_id}.jpg'
                if path.exists():
                    path.unlink()
        self._rewrite(kept)
        return len(gone)

    def forget_item(self, item):
        """Every note about the item (tag, label or note words), its crops, and its tag."""
        gone = self._drop(lambda r: not mentions(r, item))
        tags = {k: v for k, v in self.tags().items() if not (words(v['name']) & words(item))}
        self._write_json('tags.json', tags)
        return gone

    def forget_since(self, since):
        gone = self._drop(lambda r: r.get('t', 0) < since)
        self._write_json('videos.json', [v for v in self.videos() if v.get('t', 0) < since])
        return gone

    def forget_all(self):
        count = len(self.records())
        if self.dir.exists():
            owner = self.owner()
            shutil.rmtree(self.dir)
            if owner:
                self._write_json('owner.json', {'owner': owner})   # the person keeps their memory id
        return count

    def purge_old(self, days=None):
        cutoff = self.clock() - 86400 * (retention_days() if days is None else days)
        return self._drop(lambda r: r.get('t', 0) >= cutoff)


def mentions(record, item):
    target = words(item)
    if not target:
        return False
    have = set()
    for tag in record.get('tags') or []:
        have |= words(tag.get('tag')) | words(tag.get('label'))
    have |= set().union(*(words(label) for label in record.get('labels') or [])) if record.get('labels') else set()
    have |= words(record.get('note'))
    return bool(target & have)


# ---- embeddings (EmbeddingGemma on the Mac CPU, router/embed_local.py) ----

class GemmaEmbedder:
    QUERY = 'task: search result | query: '
    DOC = 'title: none | text: '

    def embed(self, texts, query=False):
        from router.embed_local import embed_many
        prefix = self.QUERY if query else self.DOC
        return embed_many([prefix + t for t in texts], 'gemma_local')


def pack(vector):
    scale = max(1e-9, max(abs(v) for v in vector))
    data = bytes((int(round(v / scale * 127)) & 0xff) for v in vector)
    return dict(q=base64.b64encode(data).decode(), s=scale)


def unpack(packed):
    raw = base64.b64decode(packed['q'])
    return [((b - 256) if b > 127 else b) * packed['s'] / 127 for b in raw]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# ---- writing ----

def center(bbox):
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def crop_jpeg(jpeg, bbox, pad=0.15):
    from PIL import Image
    with Image.open(io.BytesIO(jpeg)) as image:
        W, H = image.size
        x, y, w, h = bbox
        left, top = max(0, (x - w * pad) * W), max(0, (y - h * pad) * H)
        right, bottom = min(W, (x + w * (1 + pad)) * W), min(H, (y + h * (1 + pad)) * H)
        if right - left < 4 or bottom - top < 4:
            return None, None
        piece = image.convert('RGB').crop((int(left), int(top), int(right), int(bottom)))
        piece.thumbnail((CROP_SIDE, CROP_SIDE))
        out = io.BytesIO()
        piece.save(out, format='JPEG', quality=80)
        cw, ch = (right - left), (bottom - top)
        inner = [(x * W - left) / cw, (y * H - top) / ch, w * W / cw, h * H / ch]
        return out.getvalue(), [round(min(1, max(0, v)), 3) for v in inner]


class PersonCheck:
    """True when the frame shows a person. Our own GPU box (YOLO person class); raises when unreachable."""

    def __init__(self, box=None):
        self.box = box

    async def __call__(self, jpeg_b64, scene=None):
        if scene and any(_PERSON.search(o.get('label', '')) for o in scene.get('objects', [])):
            return True
        if scene and _PERSON.search(scene.get('caption', '') or ''):
            return True
        from server.box_client import BoxClient
        box = self.box or BoxClient()
        try:
            detections = await box.detect(jpeg_b64)
        finally:
            if self.box is None:
                await box.aclose()
        return any(d.get('label') == 'person' for d in detections)


class Writer:
    """Turns scans of one call into memory lines. Stores only changed notes."""

    def __init__(self, store, call_id, embedder=None, person_check=None, vision=None):
        self.store = store
        self.vision = vision        # our own vision host, to ground tagged objects (no cloud call)
        self.grounded_at = 0.0
        self.call_id = call_id
        self.embedder = embedder or GemmaEmbedder()
        self.person_check = person_check or PersonCheck()
        self.last_key = None
        self.written = 0
        self.skipped = {}
        self.purged_at = 0.0

    async def ground(self, tags, jpeg_b64, note):
        """Ask our vision host for the tagged things (the scene loop only asks the pack's own queries).
        Runs when the note changed, or every 30 s, and only while tags exist."""
        if not tags or self.vision is None:
            return []
        now = monotonic()
        if (note, ) == getattr(self, '_ground_note', None) and now - self.grounded_at < 30:
            return []
        self._ground_note, self.grounded_at = (note, ), now
        items = [t['label'] for t in tags.values() if t['kind'] == 'object'][:2]
        places = [t['label'] for t in tags.values() if t['kind'] == 'place'][:1]
        queries = items + ([f"{places[0]} closest to the {items[0]}"] if places and items else places)
        try:
            scene = await self.vision.call('scene', dict(image_b64=jpeg_b64, queries=queries[:3], caption=False))
        except Exception:
            return []
        out = []
        for i, obj in enumerate(scene.get('objects', [])):
            label = obj['label']
            if places and label.startswith(places[0] + ' closest'):
                label = places[0]
            out.append(dict(obj, id=f'mem{i}', label=label))
        return out

    def _skip(self, reason):
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    async def observe(self, scene, jpeg_b64):
        """One keyframe scan: scene (caption, objects) and the frame it was made from."""
        note = ' '.join((scene.get('caption') or '').split())[:200]
        objects = [o for o in scene.get('objects', []) if o.get('label')]
        tags = self.store.tags()
        objects += await self.ground(tags, jpeg_b64, note)
        hits = []
        for obj in objects:
            for tag in tags.values():
                if words(tag['label']) & words(obj['label']) or words(tag['name']) & words(obj['label']):
                    hits.append((tag, obj))
        key = (note, tuple(sorted({t['name'] for t, _ in hits})))
        if not note or key == self.last_key:
            self._skip('unchanged')
            return None
        self.last_key = key
        now = self.store.clock()
        record = dict(id=uuid4().hex[:12], t=now, call=self.call_id, note=note,
                      labels=[o['label'] for o in objects][:12], tags=[], crops={})
        for tag, obj in hits:
            near = None
            others = [o for o in objects if o is not obj]
            places = [o for o in others for t in tags.values()
                      if t['kind'] == 'place' and words(t['label']) & words(o['label'])]
            pool = places or others
            if pool:
                cx, cy = center(obj['bbox'])
                best = min(pool, key=lambda o: (center(o['bbox'])[0] - cx) ** 2 + (center(o['bbox'])[1] - cy) ** 2)
                near = dict(label=best['label'], bbox=best['bbox'])
            record['tags'].append(dict(tag=tag['name'], label=obj['label'], bbox=obj['bbox'], near=near))
        if hits:
            # Faces never stored: no crop when a person is in the frame or the check cannot run (fail closed).
            try:
                person = await self.person_check(jpeg_b64, scene)
            except Exception:
                person, record['skipped'] = True, 'person_check_unavailable'
            if person:
                record.setdefault('skipped', 'person')
                self._skip(record['skipped'])
            else:
                jpeg = base64.b64decode(jpeg_b64)
                for tag, obj in hits:
                    piece, inner = await asyncio.to_thread(crop_jpeg, jpeg, obj['bbox'])
                    if piece:
                        record['crops'][tag['name']] = self.store.save_crop(piece)
                        for entry in record['tags']:
                            if entry['tag'] == tag['name']:
                                entry['crop_bbox'] = inner
        text = ' '.join([note] + record['labels'] + [t['tag'] for t in record['tags']] +
                        [t['near']['label'] for t in record['tags'] if t['near']])
        try:
            record['emb'] = pack((await asyncio.to_thread(self.embedder.embed, [text]))[0])
        except Exception:
            record['emb'] = None    # still findable by tag and label
        self.store.append(record)
        self.written += 1
        if now - self.purged_at > 3600:
            self.purged_at = now
            self.store.purge_old()
        return record


# ---- search ----

def spoken_time(t, now):
    moment = datetime.fromtimestamp(t)
    today = datetime.fromtimestamp(now).date()
    clock = moment.strftime('%I:%M %p').lstrip('0')
    if moment.date() == today:
        minutes = int((now - t) // 60)
        return 'just now' if minutes < 1 else (f'{minutes} minute{"s" if minutes != 1 else ""} ago, at {clock}'
                                                if minutes < 60 else f'today at {clock}')
    if (today - moment.date()).days == 1:
        return f'yesterday at {clock}'
    return moment.strftime('%A at ') + clock


def item_from(question):
    value = re.sub(r"^\s*(hey\s+)?(a-?eye,?\s*)?", '', question or '', flags=re.I)
    value = re.sub(r"\b(where('s| is| are| did i (put|leave)| have i (put|left))|have you seen|did you see|"
                   r"find|what happened to)\b", ' ', value, flags=re.I)
    value = re.sub(r"\b(my|the|your)\b", ' ', value, flags=re.I)
    value = re.sub(r"[?!.]+", ' ', value)
    return ' '.join(value.split()) or (question or '').strip()


def live_target(scene, item, record_tag):
    """Where to point now: the item itself if in view, else the object it was last near (same label, closest)."""
    if not scene:
        return None
    for obj in scene.get('objects', []):
        if words(obj['label']) & words(item):
            return dict(object_id=obj['id'], bbox=obj['bbox'], what='item')
    near = (record_tag or {}).get('near')
    if near:
        same = [o for o in scene.get('objects', []) if words(o['label']) & words(near['label'])]
        if same:
            nx, ny = center(near['bbox'])
            best = min(same, key=lambda o: (center(o['bbox'])[0] - nx) ** 2 + (center(o['bbox'])[1] - ny) ** 2)
            if ((center(best['bbox'])[0] - nx) ** 2 + (center(best['bbox'])[1] - ny) ** 2) ** 0.5 <= 0.3:
                return dict(object_id=best['id'], bbox=best['bbox'], what='place')
    return None


def place_words(tag_entry, tags=None):
    near = (tag_entry or {}).get('near')
    if not near:
        return None
    label = near['label']
    rel = ('in' if re.search(r'\b(bowl|basket|drawer|tray|box|bag|jar|pocket)\b', label, re.I) else
           'under' if re.search(r'\b(cup|mug|lid|cloth|towel|hat)\b', label, re.I) else 'by')
    place = next((t for t in (tags or {}).values() if t['kind'] == 'place' and words(t['label']) & words(label)), None)
    if place:
        return f"{rel} the {place['name']}"
    x = center(near['bbox'])[0]
    side = 'left ' if x < 0.38 else 'right ' if x > 0.62 else 'middle '
    return f"{rel} the {side}{label}"


async def ground_live(vision, jpeg_b64, item, entry):
    """Live objects for the arrow: the item itself, and its last place by side ("the left red cup")."""
    queries = [item]
    place = place_words(entry)
    if place:
        queries.append(place.split(' the ', 1)[1])
    try:
        scene = await vision.call('scene', dict(image_b64=jpeg_b64, queries=queries, caption=False))
    except Exception:
        return None
    objects = []
    for i, obj in enumerate(scene.get('objects', [])):
        label = obj['label']
        if entry and entry.get('near') and label != item:
            label = entry['near']['label']
        objects.append(dict(obj, id=f'live{i}', label=label))
    return dict(caption='', objects=objects)


async def find(store, question, embedder=None, scene=None, now=None, vision=None, live_frame=None):
    """Answer "where are my keys?" from this person's memory. JSON-safe dict plus crop bytes under 'crop'."""
    started = monotonic()
    now = now if now is not None else store.clock()
    item = item_from(question)
    records = [r for r in store.records() if r.get('note')]
    tags = store.tags()
    tag = next((t for t in tags.values() if words(t['name']) & words(item) or words(t['label']) & words(item)), None)
    target = (tag['name'] if tag else item)
    hit, how = None, None
    exact = [r for r in records if any(words(e['tag']) & words(target) for e in r.get('tags') or [])]
    if exact:
        hit, how = max(exact, key=lambda r: r['t']), 'tag'
    if hit is None:
        labelled = [r for r in records if any(words(label) & words(item) for label in r.get('labels') or [])]
        if labelled:
            hit, how = max(labelled, key=lambda r: r['t']), 'label'
    if hit is None and records:
        try:
            query = (await asyncio.to_thread((embedder or GemmaEmbedder()).embed, [item], True))[0]
            scored = sorted(((cosine(query, unpack(r['emb'])), r) for r in records if r.get('emb')),
                            key=lambda x: -x[0])[:3]
            if scored and scored[0][0] >= float(os.environ.get('A_EYE_MEMORY_MIN_COS', '0.45')):
                top = scored[0][0]
                hit = max((r for s, r in scored if s >= top - 0.05), key=lambda r: r['t'])
                how = 'similar'
        except Exception as exc:
            event('dependency_error', None, dependency='embedder', level='error', error=type(exc).__name__)
    home = tag.get('home') if tag else None
    result = dict(found=hit is not None, item=item, how=how, count=len(records),
                  count_item=sum(1 for r in records if mentions(r, target)), home=home, live=None, ms=0)
    if hit is None:
        result['say'] = (f"I haven't seen your {item} yet." + (f" Their home is the {home}." if home else ''))
        result['ms'] = round((monotonic() - started) * 1000, 1)
        return result
    entry = next((e for e in hit.get('tags') or [] if words(e['tag']) & words(target)), None)
    place = place_words(entry, tags)
    when = spoken_time(hit['t'], now)
    result.update(t=hit['t'], when=when, note=hit['note'], place=place, record_id=hit['id'],
                  box=(entry or {}).get('crop_bbox'), bbox=(entry or {}).get('bbox'))
    crop_id = (hit.get('crops') or {}).get(entry['tag']) if entry else None
    result['crop'] = store.load_crop(crop_id) if crop_id else None
    if vision is not None and live_frame:
        grounded = await ground_live(vision, live_frame, item, entry)
        if grounded and grounded['objects']:
            scene = grounded
    result['live'] = live_target(scene, item, entry)
    result['live_scene'] = scene if result['live'] else None
    where = place or f'where I saw "{hit["note"]}"'
    if home and place and words(home) & words(place):
        line = f"Your {item} {'are' if item.endswith('s') else 'is'} {where}, where {'they live' if item.endswith('s') else 'it lives'}. Seen {when}."
    elif home:
        line = f"I last saw your {item} {where}, {when}. Their home is the {home}."
    else:
        line = f"I last saw your {item} {where}, {when}."
    if result['live']:
        line += " I'm pointing at it now." if result['live']['what'] == 'item' else " I'm pointing at that spot."
    result['say'] = line
    result['ms'] = round((monotonic() - started) * 1000, 1)
    return result


# ---- per-process attachments: which call writes to which memory ----

class Memories:
    def __init__(self, base=None, embedder=None, person_check=None, vision=None):
        self.base = base
        self.vision = vision
        self.embedder = embedder
        self.person_check = person_check
        self.calls = {}           # session_id -> (store, writer)

    def store(self, memory_id):
        return Store(memory_id, base=self.base)

    def attach(self, session_id, memory_id, owner):
        store = self.store(memory_id)
        if not store.claim(owner):
            raise PermissionError('memory belongs to another caller')
        writer = Writer(store, session_id[:12], embedder=self.embedder, person_check=self.person_check,
                        vision=self.vision)
        self.calls[session_id] = (store, writer)
        store.purge_old()
        return store, writer

    def detach(self, session_id):
        self.calls.pop(session_id, None)

    def for_call(self, session_id):
        return self.calls.get(session_id, (None, None))


def memories(app):
    if not hasattr(app.state, 'memories'):
        vision = getattr(app.state, 'vision_v2', None)
        if vision is None:
            from server.ws2 import SceneClient
            vision = SceneClient()
        app.state.memories = Memories(vision=vision)
    return app.state.memories


def status(store, encrypted=None):
    records = store.records()
    return dict(memory_id=store.id, count=sum(1 for r in records if r.get('note')),
                crops=sum(len(r.get('crops') or {}) for r in records), bytes=store.size_bytes(),
                encrypted=store.cipher.encrypted if encrypted is None else encrypted,
                retention_days=retention_days(), tags=sorted(t['name'] for t in store.tags().values()))


async def delete_cloud(store, since=None, client=None):
    """Delete this person's TwelveLabs videos (all, or those added since a time). Logs video ids only.
    Returns (deleted, failed). Deleting is allowed in Private mode: it only removes data."""
    from server.rewind import TwelveLabsClient
    client = client or TwelveLabsClient()
    deleted, failed, kept = 0, 0, []
    for video in store.videos():
        if since is not None and video.get('t', 0) < since:
            kept.append(video)
            continue
        try:
            await client.delete_video(video['index_id'], video['video_id'], force=True)
            deleted += 1
            print(json.dumps(dict(ts=datetime.now(timezone.utc).isoformat(), level='info',
                                  event='memory_cloud_deleted', video_id=video['video_id'])), flush=True)
        except Exception as exc:
            failed += 1
            kept.append(video)
            event('dependency_error', None, dependency='twelvelabs', level='error', error=type(exc).__name__)
    store._write_json('videos.json', kept)
    return deleted, failed

"""Call-local text recall; selected storage only while memory consent is enabled."""
from collections import deque
from datetime import datetime, timedelta
import re
from time import monotonic, time


KEEP_S = 600       # the RAM log keeps 10 minutes, so "two minutes ago" still has notes
RECENT_MAX_S = 300  # an asked age up to 5 minutes reads the RAM log; older goes to Rewind
CURRENT_CAMERA_S = 10  # a live frame is never evidence of a past "where" question
AGE = re.compile(r'\b(a|an|one|two|three|\d+)\s+(seconds?|minutes?) ago\b', re.I)
LONG = re.compile(r'\b(yesterday|last time|last call|previous call|last week|days? ago|a week ago|last weekend|'
                  r'other day|last session|previous session|earlier call|another call)\b', re.I)
STEP = re.compile(r'\bstep\s+(\d+)\b', re.I)
CURRENT_STEP = re.compile(r'\b(?:what|which) step\b', re.I)
WHERE = re.compile(r'\bwhere\b', re.I)
OPENING = re.compile(r'\b(?:at )?the (?:start|beginning) of (?:the|this) call\b', re.I)
PLACE = re.compile(
    r'\b(?:on top of|next to|in front of|in back of|to the (?:left|right) of|'
    r'on|in|at|under|over|beside|by|near|against|behind)\s+'
    r'(?:the\s+|a\s+|an\s+)?[\w][\w\s,-]{1,80}', re.I)
STOP = set('what where when did do i my the a an was were is are it put leave left see saw just now ago '
           'minute minutes second seconds one two three earlier in this call happened recently please '
           'you remember last time yesterday picked up set place placed keep kept go went with to on of for '
           'from at that there have had back think recall dad hey ok okay um uh about few couple go gone end '
           'ended show showed shown'.split())
# Simple synonyms so "mug" finds a "cup" note. Plurals are folded in words().
SYNONYMS = {'cup': 'mug', 'spanner': 'wrench', 'rag': 'towel', 'cloth': 'towel', 'pail': 'bucket',
            'cellphone': 'phone', 'mobile': 'phone', 'key': 'keys', 'glass': 'glasses', 'spectacles': 'glasses',
            'tap': 'faucet', 'countertop': 'counter', 'bench': 'workbench', 'scissor': 'scissors'}


def current_view_question(text, *, partial=False):
    """Closed present-view forms; never bypass temporal routing for an appended past clause."""
    q = text.strip().lower().rstrip('?.!').strip()
    if partial and q in ('what is on', 'what is on the', 'what is in', 'what is in the'):
        return True
    return bool(re.fullmatch(r"what(?: is|'s) (?:on the (?:table|desk|counter)|"
                             r"in (?:the (?:view|camera view)|front of me))(?: (?:right )?now)?", q))


def age_seconds(text):
    match = AGE.search(text)
    if not match:
        return None
    value = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3}.get(match[1].lower())
    value = value if value is not None else int(match[1])
    return value * (60 if match[2].lower().startswith('minute') else 1)


def source_for(text, rewind_on=False, *, default_recent=True):
    """Explicit temporal scope wins over the optional semantic intent router."""
    if LONG.search(text):
        return 'long-term'
    age = age_seconds(text)
    if age is not None:
        return 'recent' if age <= RECENT_MAX_S else 'rewind'
    if re.search(r'\b(just now|just do|just did|recently)\b', text, re.I) or (
            (STEP.search(text) or CURRENT_STEP.search(text)) and re.search(r'\b(was|did|earlier)\b', text, re.I)):
        return 'recent'
    if OPENING.search(text) or re.search(r'\b(earlier|before|start of (?:the|this) call)\b', text, re.I):
        return 'rewind' if rewind_on else 'recent'
    if default_recent and re.search(r"\b(what did i)\b", text, re.I):
        return 'recent'
    return None


def _norm(word):
    if len(word) > 4 and word.endswith('es') and word[-3] in 'sxzh':
        word = word[:-2]
    elif len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        word = word[:-1]
    return SYNONYMS.get(word, word)


def words(text):
    raw = set(re.findall(r'[a-z0-9]+', text.lower())) - STOP
    return {_norm(w) for w in raw} - STOP


def surroundings(note):
    """Place or nearby objects from a caption; the whole caption if none is marked."""
    match = PLACE.search(note or '')
    if not match:
        return (note or '').strip().rstrip('.')
    return match.group(0).split('.')[0].strip(' .,')


def ago_words(seconds):
    seconds = max(0, int(round(seconds)))
    if seconds < 90:
        unit = 'second' if seconds == 1 else 'seconds'
        return f'about {seconds} {unit} ago'
    minutes = max(1, int(round(seconds / 60)))
    unit = 'minute' if minutes == 1 else 'minutes'
    return f'about {minutes} {unit} ago'


class RecentMemory:
    def __init__(self, clock=monotonic, started=None):
        self.clock = clock
        self.started = clock() if started is None else started
        self.started_wall = time()
        self.entries = deque(maxlen=1024)
        self.step = ''
        self.store = None
        self.call_id = None
        self.ram_only = False

    def bind(self, store, call_id):
        if self.ram_only:
            store = None
        if self.store is not None and (store is None or call_id != self.call_id):
            self._clear_persisted()
        self.store, self.call_id = store, call_id

    def _clear_persisted(self):
        from server.logs import event
        from server.memory_storage import StorageError
        try:
            self.store.clear_recent(self.call_id)
        except StorageError:
            # Privacy/offline failures must not interrupt the rest of call teardown.
            # The remote copy remains until a later successful expiry/Forget write.
            event('dependency_error', None, dependency='memory', level='error',
                  error='recent_cleanup_failed')

    def prune(self, now=None):
        now = self.clock() if now is None else now
        while self.entries and now - self.entries[0]['observed_at'] > KEEP_S:
            self.entries.popleft()

    def clear(self):
        self.entries.clear()
        self.step = ''
        if self.store is not None:
            try:
                self._clear_persisted()
            finally:
                self.store = None
                self.call_id = None

    def note_step(self, text):
        # Only numbered guide instructions establish a step; never infer completion.
        if re.match(r'^\s*step\s+\d+\s*[:.)-]', text, re.I):
            self.step = text[:1000]
            self.add(dict(caption='', objects=[]), self.clock(), self.step, kind='instruction')

    def note_transcript(self, text, role):
        if text.strip():
            if role == 'helper':
                self.note_step(text)
            self.add(dict(caption=text.strip(), objects=[]), self.clock(), kind=role)

    def add(self, scene, observed_at, step=None, kind='scene'):
        self.prune(observed_at)
        entry = dict(observed_at=observed_at, t_s=max(0, observed_at - self.started),
                                 note=str(scene.get('caption') or '')[:2000],
                                 labels=[str(o['label'])[:120] for o in scene.get('objects', [])[:64]],
                                 step=self.step if step is None else str(step)[:1000], kind=kind,
                                 wall_t=self.started_wall + max(0, observed_at - self.started))
        self.entries.append(entry)
        if self.store is not None and self.store.remembering():
            self.store.append_recent(self.call_id, entry)

    def find(self, question):
        self.prune()
        now = self.clock()
        entries = list(self.entries)
        if self.store is not None and self.store.remembering():
            entries = [e for e in self.store.recent_records(self.call_id)
                       if now - e['observed_at'] <= KEEP_S]
        step = STEP.search(question)
        current_step = CURRENT_STEP.search(question)
        where = WHERE.search(question)
        opening = OPENING.search(question)
        target = words(AGE.sub('', OPENING.sub('', question)))
        if step:
            entries = [e for e in entries if (m := STEP.search(e['step'])) and m[1] == step[1]]
        elif current_step:
            entries = [e for e in entries if e['kind'] == 'instruction' and e['step']]
        else:
            entries = [e for e in entries if e['kind'] == 'scene']
            if opening:
                # Only an opening observation is evidence of the opening. If those notes expired,
                # a later retained scene must not become the "start" of the call.
                entries = [e for e in entries if e['t_s'] <= 10]
            if target:
                entries = [e for e in entries if target <= words(' '.join([e['note'], *e['labels']]))]
        age = age_seconds(question)
        if where and target:
            # Last note that mentions X. A later scene without X is not a new place, and the
            # live camera is never evidence of a past "where" question.
            if age is not None:
                entries = [e for e in entries if now - e['observed_at'] >= CURRENT_CAMERA_S]
                latest = now - age + max(20, age * .25)
                entries = [e for e in entries if e['observed_at'] <= latest]
            if not entries:
                return None
            hit = entries[-1]
            note = hit['note'] or ', '.join(hit['labels'])
            place = surroundings(note) or note
            stamp = f"{int(hit['t_s']) // 60}:{int(hit['t_s']) % 60:02d}"
            return dict(source='recent', found=True, t_s=hit['t_s'],
                        say=f"At {stamp} in this call, {ago_words(now - hit['observed_at'])}, "
                            f"it was {place}.")
        if age is not None:
            # A sighting far away from the requested moment isn't evidence for that moment.
            entries = [e for e in entries if abs(now - e['observed_at'] - age) <= max(20, age * .25)]
        if not entries:
            return None
        hit = (min(entries, key=lambda e: abs(now - e['observed_at'] - age)) if age is not None else
               min(entries, key=lambda e: e['observed_at']) if opening else entries[-1])
        note = hit['step'] if step or current_step else hit['note'] or ', '.join(hit['labels'])
        return dict(source='recent', found=True, t_s=hit['t_s'],
                    say=f"At {int(hit['t_s']) // 60}:{int(hit['t_s']) % 60:02d} in this call, "
                        f"{'the guide said' if step or current_step else 'the scene note was'}: {note}")


DAYS = re.compile(r'\b(a|one|two|three|four|five|six|\d+|a few|a couple of|a couple)\s+days? ago\b', re.I)
TASK_Q = re.compile(r'\b(what (did|have) (we|i) (fix|fixed|do|done|work(?:ed)? on|build|built|finish(?:ed)?|make|made|'
                    r'repair(?:ed)?)|have (we|i) (done|fixed|worked on|repaired)|how did .+ go|how long did|'
                    r'what (project|task)s?|last (thing|project) we)\b', re.I)
TASK_NAMES = {'sink': 'the dripping sink fix', 'hinge': 'the cabinet hinge fix', 'breaker': 'the tripped breaker',
              'ee_led': 'the LED circuit', 'ee_resistor': 'reading resistor bands', 'ee_polarity': 'LED polarity',
              'ee_multimeter': 'checking a resistor with a multimeter', 'tie': 'the four-in-hand tie'}


def window(question, end):
    """(start, end, words) for a past-call question, in wall-clock seconds. end is the call start."""
    q = question.lower()
    today = datetime.fromtimestamp(end).replace(hour=0, minute=0, second=0, microsecond=0)
    if 'yesterday' in q:
        return (today - timedelta(days=1)).timestamp(), today.timestamp(), 'yesterday'
    days = DAYS.search(q)
    if days:
        n = {'a': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'a few': 3,
             'a couple of': 2, 'a couple': 2}.get(days[1], None)
        n = n if n is not None else int(days[1])
        # Spoken day counts are rough: allow one day either side.
        return (today - timedelta(days=n + 1)).timestamp(), (today - timedelta(days=n - 1)).timestamp(), 'then'
    if re.search(r'\b(last week|a week ago|last weekend|other day)\b', q):
        return (today - timedelta(days=14)).timestamp(), today.timestamp(), 'last week'
    return float('-inf'), end, 'an earlier call'


def task_history(session, question, start, end, scope):
    """"What did we fix last week": completed or started tasks from the growth log, by date. None if no log."""
    growth = getattr(session, 'growth', None)
    if growth is None or not TASK_Q.search(question):
        return None
    rows = []
    for row in getattr(growth, 'entries', []):
        try:
            t = datetime.fromisoformat(row['date']).timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        if start <= t < end:
            rows.append((t, row))
    if not rows:
        return dict(source='unavailable', found=False,
                    say=f"I don't have a saved task from {scope}. I can't confirm what we did.")
    parts = []
    for t, row in sorted(rows, key=lambda x: x[0])[-3:]:
        day = datetime.fromtimestamp(t).strftime('%A %B %-d')
        name = TASK_NAMES.get(row.get('task'), str(row.get('task', 'a task')).replace('_', ' '))
        parts.append(f"on {day} you worked on {name} and {'finished it' if row.get('completed') else 'did not finish it'}")
    return dict(source='history', found=True, say='From your task history: ' + '; '.join(parts) + '.')


async def long_term(session, question):
    from server import memory
    log = session.recent_memory
    start, end, scope = window(question, log.started_wall)
    history = task_history(session, question, start, end, scope)
    if history and history['found']:
        return history
    rewind = getattr(session, 'rewind', None)
    writer = getattr(rewind, 'memory_writer', None)
    if writer is None or not writer.store.remembering():
        return history

    class PastStore:
        clock = staticmethod(writer.store.clock)
        tags = writer.store.tags
        load_crop = writer.store.load_crop

        def records(self):
            return [r for r in writer.store.records() if start <= r['t'] < end]

        def where(self, name):
            return writer.store.where(name, start=start, end=end)

    query = DAYS.sub('', LONG.sub('', question))
    result = await memory.find(PastStore(), query, embedder=writer.embedder)
    return dict(result, source='long-term') if result['found'] else history


NOT_RECENT = "I didn't see that in my notes from the last few minutes, so I can't confirm it."


def _sighting(session, question):
    """Keyframe scene memory on a RAM-log miss; never the current frame (under 10 s old) for a past question."""
    try:
        from server.rewind import memory_sighting
        seen = memory_sighting(session, question)
    except Exception:
        return None
    if seen and seen.get('memory_age_s', 0) >= 10:
        return dict(source='scene_memory', found=True, say=seen['say'])
    return None


async def answer(session, question, vision=None, *, on_hit=None, scope=None):
    """scope: the source the caller's decision model chose ('recent', 'rewind', 'long-term') when the question
    has no explicit time words; explicit words always win."""
    from server.privacy import twelvelabs_allowed
    rewind = getattr(session, 'rewind', None)
    on = bool(rewind and rewind.on and twelvelabs_allowed() and not getattr(session, 'private', False))
    requested = source_for(question, on, default_recent=False) or scope or source_for(question, on) or 'recent'
    if requested == 'past_calls':
        requested = 'long-term'
    if requested == 'recent' and on:
        requested = 'rewind'  # Owner decision: with Recall on, TwelveLabs search answers in-call past questions; notes are the fallback.
    if requested == 'rewind' and not on:
        requested = 'recent'
    if requested == 'recent':
        hit = session.recent_memory.find(question) or _sighting(session, question)
        if hit:
            return hit
        # An explicit recent question must never be answered with yesterday's evidence.
        return dict(source='unavailable', found=False, say=NOT_RECENT)
    guess = None
    if requested == 'rewind':
        try:
            spoken, hit = await rewind.answer(question, vision=vision, before_s=rewind.now_s() - 20)
            if hit and on_hit:
                await on_hit(hit)
            if hit and hit['sure']:
                return dict(source='rewind', found=True, say=spoken.replace(" Here's the clip.", ''), t_s=hit['t_s'])
            if hit:
                guess = dict(source='rewind', found=True, sure=False, t_s=hit['t_s'],
                             say=spoken.replace(" Here's my best guess.", '').replace(" Here's the clip.", ''))
        except Exception:
            pass  # Availability only; never expose query, frames or exception text in logs.
        hit = session.recent_memory.find(question)
        if hit:
            hit['say'] = 'From my notes of this call: ' + hit['say']
            return hit
        if guess:
            return guess
    if requested == 'long-term' and rewind is not None:
        from server.rewind import kept_calls, past_call_line, shared_demo_library
        # Generic recall has no visual object to search. Remove question/temporal filler.
        target = words(DAYS.sub('', LONG.sub('', question))) - {
            'me', 'we', 'us', 'our', 'previous', 'session', 'can', 'could', 'tell', 'happen',
            'anything', 'something', 'everything', 'thing', 'talk', 'discuss', 'about'}
        # Owner decision: always ask TwelveLabs first for past calls; it returns the best moment even for generic questions.
        if True:
            try:
                hits = await rewind.search_kept(question if target else 'what we worked on')
                if hits:
                    hit = dict(hits[0], sure=False, objects=[], alternatives=[h['t_s'] for h in hits[1:2]])
                    if on_hit:
                        await on_hit(hit)
                    spoken = past_call_line(hit).replace('a call you saved', 'an earlier call you saved')
                    owner = getattr(rewind, 'owner', None)
                    calls = kept_calls(owner) if owner is not None else []
                    call = next((c for c in calls if (
                        hit.get('call_started_wall') is not None
                        and c.get('started_wall') == hit['call_started_wall']) or (
                        hit.get('video_id') and any(clip.get('video_id') == hit['video_id']
                                                   for clip in c.get('clips', [])))), {})
                    summary = call.get('summary')
                    if isinstance(summary, str) and summary.strip():
                        spoken += f" In that call: {summary[:600]}."
                    return dict(source='rewind', found=True, say=spoken, t_s=hit['t_s'])
            except Exception:
                pass  # Search availability must not block the local text fallback.
        owner = getattr(rewind, 'owner', None)
        if owner is not None and (owner != 'local' or shared_demo_library()):
            start, end, _ = window(question, session.recent_memory.started_wall)
            calls = [c for c in kept_calls(owner) if c.get('session_id') != rewind.session_id
                     and start <= c.get('started_wall', 0) < end]
            latest = max(calls, key=lambda c: c.get('started_wall', 0), default={})
            summary = latest.get('summary')
            if isinstance(summary, str) and summary.strip():
                prefix = 'Last call you showed me: ' if not DAYS.search(question) and not re.search(
                    r'\b(yesterday|last week|last weekend|other day)\b', question, re.I) else 'In a saved call you showed me: '
                return dict(source='kept-summary', found=True, say=prefix + summary[:1500])
    try:
        hit = await long_term(session, question)
    except Exception:
        hit = None
    if hit and hit['found']:
        if requested == 'rewind':
            hit['say'] = "I couldn't confirm that in this call's Rewind. From an earlier call: " + hit['say']
        return hit
    if hit:
        return hit
    scope_words = window(question, session.recent_memory.started_wall)[2]
    return dict(source='unavailable', found=False,
                say=f"I don't have a saved memory from {scope_words}. I can't confirm what happened.")


async def run_turn(session, question, turn_id, vision=None):
    from server.agent import message, say
    result = await answer(session, question, vision)
    if result['source'] == 'long-term':
        from server.rewind_tools import memory_hit_message
        await session.emit(memory_hit_message(result, turn_id, session.recent_memory.started_wall))
    msg = say(result['say'])
    msg.update(turn_id=turn_id, part=0, final=True)
    await session.emit(message('reply_delta', agent='helper', turn_id=turn_id, text=msg['text'] + ' '))
    await session.emit(msg)
    if session.speak:
        async for audio in session.speak(msg):
            await session.emit(audio)
    session.history.extend([f'user: {question}', f"helper: {result['say']}"])
    session.history[:] = session.history[-10:]

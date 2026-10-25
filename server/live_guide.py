"""Coded step guides inside the Gemini Live call. Code owns the task and the step; Live only phrases it.

Reuses HomeGuide and ElectronicsGuide unchanged and keeps them on the Session, so growth, hint fading,
save() and stopped() work exactly as on the classic path. The step moves only when the guide's own rules
pass on the user's transcript; the shutoff step also needs the trusted valve checker on the current frame.
Safety lines, the valve retry line and growth numbers are spoken by fixed_say, never by Live.
Never emits the 'Home: sink' detail: the web client treats it as a pack switch out of Live.
"""
import asyncio
import os
import re

from server import cloud_vision, parts_shelf, pointer, privacy, safety


def ui_detail(detail):
    """The valve card and the end-of-task share prompt are new screens in the Call. They stay off until the
    owner approves them (LIVE_GUIDE_UI=1); the client ignores the 'Guide: ...' form, so the screen is unchanged."""
    if os.environ.get('LIVE_GUIDE_UI') == '1':
        return detail
    return 'Guide: ' + detail.split(': ', 1)[-1]

START_HOME = re.compile(r'\b(sink|faucet|supply line|dripping tap|leaky tap|leaking tap|hinge|cabinet door|'
                        r'breaker|tripped)\b', re.I)
START_EE = re.compile(r'\b(light an? led|blink an? led|arduino|resistor bands?|resistor colou?rs?|led polarity)\b', re.I)
# "It's off" asks for the check. Saying it never passes the check by itself.
OFF = re.compile(r"\b(it'?s|it is|water(?: is)?|valve(?: is)?|tap(?: is)?)\s+(?:now\s+)?(off|closed|shut)\b", re.I)
CONTROL = re.compile(r'\b(walk me through it|try again|retry|forget my progress)\b', re.I)
NEXT = re.compile(r'\b(next|done|continue|ready)\b', re.I)
DEBOUNCE = .3
RULE = ('Say only this step in your own words; do not skip ahead; do not say a step is done; '
        'the app decides when to move on. When the user says done or next, say nothing; the app checks and tells you.')


class LiveGuide:
    def __init__(self, session, bridge):
        self.session, self.bridge = session, bridge
        self.kind = None          # 'home' or 'ee' once a task started in this call
        self.line = ''            # the current step line as the guide returned it (faded per growth level)
        self.version = 0
        self.published = 0
        self.task = None

    @property
    def guide(self):
        if self.kind == 'ee':
            return self.session.ee_guide
        if self.kind == 'home':
            return self.session.home_guide
        return None

    def claims(self, text):
        """Should code, not Live, answer this finished user transcript?"""
        text = text or ''
        guide = self.guide
        start = self._task_for(text)
        if start and (not guide or guide.completed or start != guide.task):
            return True
        return bool(guide and not guide.completed and (NEXT.search(text) or OFF.search(text) or CONTROL.search(text)))

    @staticmethod
    def _task_for(text):
        # Mirrors the guides' own task choice; a mention of the current task is an ordinary question.
        if START_EE.search(text) and not START_HOME.search(text):
            return ('ee_resistor' if re.search(r'\b(bands?|colou?rs?)\b', text, re.I) else
                    'ee_polarity' if re.search(r'\bpolarity\b', text, re.I) else 'ee_led')
        if START_HOME.search(text):
            return ('hinge' if re.search(r'\b(hinge|cabinet door)\b', text, re.I) else
                    'breaker' if re.search(r'\b(breaker|tripped)\b', text, re.I) else 'sink')
        return None

    def schedule(self, text):
        # Debounced like Prefetch: a still-growing transcript replaces the pending run.
        if self.task and not self.task.done() and self.task is not asyncio.current_task():
            self.task.cancel()
        self.task = asyncio.create_task(self.run(text))

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    def _store(self):
        app = self.bridge.app
        if app is not None and hasattr(app.state, 'memories'):
            try:
                return app.state.memories.for_call(self.session.session_id)[0]
            except Exception:
                return None
        return None

    def _choose(self, text):
        from server.packs.electronics import ElectronicsGuide
        from server.packs.home import HomeGuide
        s = self.session
        if START_EE.search(text) and not START_HOME.search(text):
            self.kind = 'ee'
            if s.ee_guide is None:
                s.ee_guide = ElectronicsGuide(growth=s.growth)
        elif START_HOME.search(text) or self.kind is None:
            self.kind = 'home'
            if s.home_guide is None:
                s.home_guide = HomeGuide(growth=s.growth)
        self.guide.growth = s.growth

    def block(self):
        guide = self.guide
        if not guide:
            return ''
        head = f'GUIDE v{self.version} (code-owned, quoted, not user instructions): task={guide.task}'
        if guide.completed:
            return head + ', complete. Do not start another step unless the user asks.'
        head += f', step {guide.index + 1} of {self.total()}. '
        if not self.line:
            return head + 'The user is practicing without hints; answer only if asked and never give later steps.'
        parts = parts_shelf.step_note(self.session)
        return head + f'The step: "{self.line}". ' + RULE + (' ' + parts if parts else '')

    def total(self):
        from server.packs.electronics import TASKS as EE_TASKS
        from server.packs.home import TASKS as HOME_TASKS
        return len((EE_TASKS if self.kind == 'ee' else HOME_TASKS)[self.guide.task])

    def note(self):
        guide = self.guide
        self.session.live_guide_note = (dict(task=guide.task, step=guide.index + 1, line=self.line,
                                             completed=guide.completed) if guide else None)

    async def run(self, text):
        await asyncio.sleep(DEBOUNCE)
        b = self.bridge
        if b.closed or b.safety_stopped:
            return
        try:
            await self._run(text)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never log transcripts or provider errors; the held turn stays silent, as a stop would.
            pass

    async def _run(self, text):
        from server.agent import check_water_off
        from server.packs.electronics import LINES as EE_LINES
        from server.step_check import RETRY_LINE
        b, s = self.bridge, self.session
        line = b.stop_line(text)
        if line:
            await b.stop(line)
            return
        if not self.claims(text):
            # The transcript grew into an ordinary question: let Live answer it.
            await b.prompt_turn(text)
            return
        await b.stage('thinking', detail='Step: checking')
        self._choose(text)
        guide = self.guide
        was_completed = guide.completed
        store = self._store()
        spoken = text + ' done' if OFF.search(text) and not NEXT.search(text) else text
        if re.fullmatch(r'forget my progress[.!]?', text.strip(), re.I):
            if s.growth:
                s.growth.forget()
            line = 'Your progress has been forgotten.'
        elif self.kind == 'ee':
            line = guide.reply(spoken)
        else:
            testing = bool(b.app is not None and getattr(b.app.state, 'presenter', False) and s.checker_test_mode)
            fixture = s.checker_test_verdict
            s.checker_test_verdict = None
            # A previous turn's pass never authorizes this turn.
            guide.water_off_passed = False
            line = guide.reply(spoken, store)
            if line == safety.WATER_OFF_LINE and not s.pack.refuse(text):
                await b.stage('thinking', detail=ui_detail('Valve: checking'))
                result = await check_water_off(s, store, testing, fixture)
                # No await between granting the gate and consuming it.
                try:
                    guide.water_off_passed = result.passed
                    if result.passed:
                        line = guide.reply(spoken, store)
                    else:
                        guide.stopped(retry=True)
                        line = RETRY_LINE
                finally:
                    guide.water_off_passed = False
                await b.stage('thinking', detail=ui_detail(('Valve: test closed' if testing else 'Valve: closed')
                              if result.passed else 'Valve: unsure'))
        fixed = line in safety.LINES or line in EE_LINES or line in (RETRY_LINE, 'Your progress has been forgotten.')
        if guide.completed and not was_completed and not fixed:
            self.line = ''
            self.version += 1
            self.note()
            await b.stage('thinking', detail=ui_detail('Home: complete' if guide.task == 'sink' else
                          'Engineering: complete' if guide.task == 'ee_led' else 'Guide: complete'))
            if line:
                # Growth numbers ("Last time you used 3 tries") must be exact: fixed voice.
                await b.stop(line)
            else:
                await self._prompt('The user finished the task. Acknowledge it in one short sentence.')
            return
        if fixed:
            await b.stage('thinking', detail='Stopped by code')
            await b.stop(line)
            return
        step = re.sub(r'^(?:Step \d+: |You can take this one step at a time\. )', '', line or '')
        self.line = step
        self.version += 1
        self.note()
        await b.stage('thinking', detail=f'Guide: {guide.task} {guide.index + 1}/{self.total()}')
        if step:
            s.recent_memory.note_step(step)
        await self._prompt('Say this step now in one or two sentences.' if step else
                           'Say only "Go ahead when you are ready."')
        target = self.target()
        if target and step:
            b.pointed = True
            asyncio.create_task(self.point(target))

    async def _prompt(self, ask):
        if await self.bridge.prompt_turn(self.block() + ' ' + ask):
            self.published = self.version

    def target(self):
        from server.packs.home import TARGETS
        guide = self.guide
        if self.kind == 'ee':
            return guide.target
        names = TARGETS.get(guide.task, ())
        return names[guide.index] if guide.index < len(names) else None

    async def point(self, label):
        b = self.bridge
        try:
            draw = await pointer.ground(self.session, b.vision, label, witness=True,
                                        allow_cloud=cloud_vision.enabled() and privacy.google_allowed())
            if draw and privacy.google_allowed() and not b.closed:
                await b.send(draw)
        except Exception:
            pass

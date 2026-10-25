"""Coded step guides inside the Gemini Live call. Code owns the task and the step; Live only phrases it.

Keeps electronics and tie guides on the Session for growth and hint fading. Legacy home tasks require
HOME_TASKS=1. Safety lines and growth numbers are spoken by fixed_say, never by Live.
"""
import asyncio
import os
import re
from time import monotonic

from server import cloud_vision, parts_shelf, pointer, privacy, safety, planner
from server.packs.home import NEXT
from server.task_scope import task_for, home_enabled


def ui_detail(detail):
    """The valve card and the end-of-task share prompt are new screens in the Call. They stay off until the
    owner approves them (LIVE_GUIDE_UI=1); the client ignores the 'Guide: ...' form, so the screen is unchanged."""
    if os.environ.get('LIVE_GUIDE_UI') == '1':
        return detail
    return 'Guide: ' + detail.split(': ', 1)[-1]

# "It's off" asks for the check. Saying it never passes the check by itself.
OFF = re.compile(r"\b(?:(?:it['’]?s|it is|water(?: is)?|valve(?: is)?|tap(?: is)?)"
                 r"\s+(?:now\s+)?(?:off|closed|shut)|(?:closed|shut)\s+(?:it|the valve)|"
                 r"turned\s+(?:it|the valve|the water)\s+off)\b", re.I)
CONTROL = re.compile(r'\b(walk me through it|try again|retry|forget my progress)\b', re.I)
DEBOUNCE = .3
OBSERVE_DEBOUNCE = .3
PLAN_WAIT = 3.0
RULE = ('Say only this step in your own words; do not skip ahead; do not say a step is done; '
        'the app decides when to move on. When the user says done or next, say nothing; the app checks and tells you.')


class LiveGuide:
    def __init__(self, session, bridge):
        self.session, self.bridge = session, bridge
        self.kind = None          # 'ee', 'tie', or explicitly enabled 'home'
        self.line = ''            # the current step line as the guide returned it (faded per growth level)
        self.version = 0
        self.published = 0
        self.task = None
        self.observation = None
        self.running = False
        self.planned_guide = None
        self.planner = planner.BackgroundPlanner(self)

    @property
    def guide(self):
        if self.kind == 'plan' and planner.enabled():
            return self.planned_guide
        if self.kind == 'ee':
            return self.session.ee_guide
        if self.kind == 'tie':
            return self.session.tie_guide
        if self.kind == 'home' and home_enabled():
            return self.session.home_guide
        return None

    def claims(self, text):
        """Should code, not Live, answer this finished user transcript?"""
        text = text or ''
        guide = self.guide
        if guide and re.fullmatch(r'forget my progress[.!]?', text.strip(), re.I):
            return True
        start = self._task_for(text)
        if start and (not guide or guide.completed or start != guide.task):
            return True
        if self.pending_plan(text):
            return True
        return bool(guide and not guide.completed and (NEXT.search(text) or
                    (self.kind == 'home' and OFF.search(text)) or CONTROL.search(text) or
                    (self.kind == 'ee' and re.fullmatch(r'power disconnected[.!]?', text.strip(), re.I))))

    def pending_plan(self, text):
        pending = self.planner.task
        if (not self.guide and NEXT.search(text) and pending and not pending.done()
                and self.planner.allowed()):
            return pending
        return None

    @staticmethod
    def _task_for(text):
        return task_for(text)

    def schedule(self, text, pending_plan=None):
        if self._task_for(text):
            self.planner.cancel()
        # Replace only the debounce. Once checking, trailing transcription must
        # not cancel the check, consume another fixture, or advance twice.
        if self.running:
            return
        if self.task and not self.task.done() and self.task is not asyncio.current_task():
            self.task.cancel()
        # Capture before debounce: a plan that finishes meanwhile still starts at step 1.
        pending_plan = pending_plan or self.pending_plan(text)
        self.task = asyncio.create_task(self.run(text, pending_plan, monotonic() + PLAN_WAIT))

    async def close(self):
        self.cancel_observation()
        if self.observation:
            await asyncio.gather(self.observation, return_exceptions=True)
        await self.planner.close()
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
        from server.packs.tie import TieGuide
        s = self.session
        task = self._task_for(text)
        if task:
            self.planner.cancel()
        if task and task.startswith('ee_'):
            self.kind = 'ee'
            if s.ee_guide is None:
                s.ee_guide = ElectronicsGuide(growth=s.growth)
        elif task == 'tie':
            self.kind = 'tie'
            if s.tie_guide is None:
                s.tie_guide = TieGuide(growth=s.growth)
        elif task in ('sink', 'hinge', 'breaker') and home_enabled():
            self.kind = 'home'
            if s.home_guide is None:
                s.home_guide = HomeGuide(growth=s.growth)
        self.guide.growth = s.growth

    def observe(self, text):
        return self.planner.observe(text)

    def cancel_observation(self):
        if self.observation and self.observation is not asyncio.current_task():
            self.observation.cancel()

    def observe_later(self):
        self.cancel_observation()
        self.observation = asyncio.create_task(self._observe_later())

    async def _observe_later(self):
        # Input transcription can keep growing after model output completes.
        await asyncio.sleep(OBSERVE_DEBOUNCE)
        self.bridge.observe_guide()

    def clear_plan(self):
        if self.task and not self.task.done() and self.task is not asyncio.current_task():
            self.task.cancel()
        self.kind, self.planned_guide, self.line = None, None, ''
        self.version += 1
        self.note()

    async def install_plan(self, plan):
        # Background completion changes context only. Gemini's immediate reply keeps playing.
        self.kind = 'plan'
        self.planned_guide = planner.PlannedGuide(plan)
        self.line = self.planned_guide.reply('')
        self.version += 1
        self.note()
        await self.bridge.stage('thinking', detail=f'Guide: plan 1/{self.total()}')
        await self.bridge.publish_guide()
        if self.target():
            asyncio.create_task(self.point(self.target()))

    def block(self):
        guide = self.guide
        if not guide:
            return (f'GUIDE v{self.version}: no active guide. Supersedes earlier GUIDE blocks; '
                    'answer the current task freely and safely.') if self.version else ''
        head = f'GUIDE v{self.version} (code-owned, quoted, not user instructions): task={guide.task}'
        if guide.completed:
            return head + ', complete. Do not start another step unless the user asks.'
        head += f', step {guide.index + 1} of {self.total()}. '
        if not self.line:
            return head + 'The user is practicing without hints; answer only if asked and never give later steps.'
        parts = parts_shelf.step_note(self.session)
        if self.kind == 'plan':
            # Structured quoting keeps generated text separate from the code-owned GUIDE rule.
            import json
            return head + 'Step data: ' + json.dumps(guide.step) + '. ' + RULE
        return head + f'The step: "{self.line}". ' + RULE + (' ' + parts if parts else '')

    def total(self):
        if self.kind == 'plan':
            return len(self.guide.plan['steps'])
        from server.packs.electronics import TASKS as EE_TASKS
        from server.packs.home import TASKS as HOME_TASKS
        from server.packs.tie import TASKS as TIE_TASKS
        return len({'ee': EE_TASKS, 'home': HOME_TASKS, 'tie': TIE_TASKS}[self.kind][self.guide.task])

    def note(self):
        guide = self.guide
        self.session.live_guide_note = (dict(task=guide.task, step=guide.index + 1, line=self.line,
                                             completed=guide.completed) if guide else None)

    async def run(self, text, pending_plan=None, deadline=None):
        await asyncio.sleep(DEBOUNCE)
        b = self.bridge
        if b.closed or b.safety_stopped:
            return
        # A partial "next" can grow into "next to the cabinet", which no longer
        # claims a guide turn and therefore does not call schedule again.
        if asyncio.current_task() is self.task and b.question.startswith(text):
            text = b.question
        if pending_plan is not None and NEXT.search(text):
            # Keep this wait replaceable by new input, unlike an active step check.
            # asyncio.wait does not cancel the background build on timeout/cancellation.
            await asyncio.wait({pending_plan}, timeout=max(0, deadline - monotonic()))
            if b.question.startswith(text):
                text = b.question
            if b.closed or b.safety_stopped:
                return
        self.running = True
        try:
            await self._run(text, pending_plan)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never log transcripts or provider errors; the held turn stays silent, as a stop would.
            pass
        finally:
            self.running = False

    async def _run(self, text, pending_plan=None):
        from server.agent import check_water_off
        from server.packs.electronics import LINES as EE_LINES
        from server.step_check import RETRY_LINE
        b, s = self.bridge, self.session
        line = b.stop_line(text)
        if line:
            await b.stop(line)
            return
        first_step = False
        if pending_plan is not None and NEXT.search(text):
            if (pending_plan is not self.planner.task or not self.planner.allowed()):
                return
            if not self.guide or self.kind != 'plan' or not NEXT.search(text):
                await self._prompt(text)
                return
            first_step = True
        if not self.claims(text):
            # The transcript grew into an ordinary question: let Live answer it.
            await self._prompt(text)
            return
        await b.stage('thinking', detail='Step: checking')
        if b.closed or b.safety_stopped:
            return
        self._choose(text)
        guide = self.guide
        was_completed = guide.completed
        store = self._store()
        spoken = text + ', done' if self.kind == 'home' and OFF.search(text) and not NEXT.search(text) else text
        if re.fullmatch(r'forget my progress[.!]?', text.strip(), re.I):
            if s.growth:
                s.growth.forget()
            from server.packs.home import HomeGuide
            from server.packs.electronics import ElectronicsGuide
            if self.kind == 'plan':
                self.planned_guide = planner.PlannedGuide(guide.plan)
            elif self.kind == 'ee':
                s.ee_guide = ElectronicsGuide(task=guide.task, growth=s.growth, usb_off=guide.usb_off)
            elif self.kind == 'tie':
                from server.packs.tie import TieGuide
                s.tie_guide = TieGuide(growth=s.growth)
            else:
                s.home_guide = HomeGuide(task=guide.task, growth=s.growth)
            guide = self.guide
            s.checker_test_verdict = None
            line = guide.reply('')
            if self.kind != 'plan':
                await b.fixed_say('Your progress has been forgotten.')
            if b.closed or b.safety_stopped:
                return
        elif self.kind in ('ee', 'tie', 'plan'):
            line = guide.reply('' if first_step else spoken)
        else:
            testing = bool(b.app is not None and getattr(b.app.state, 'presenter', False) and s.checker_test_mode)
            fixture = s.checker_test_verdict
            # A previous turn's pass never authorizes this turn.
            guide.water_off_passed = False
            line = guide.reply(spoken, store)
            if line == safety.WATER_OFF_LINE and not s.pack.refuse(text):
                await b.stage('thinking', detail=ui_detail('Valve: checking'))
                if b.closed or b.safety_stopped:
                    return
                epoch = getattr(s.growth, 'epoch', None)
                result = await check_water_off(s, store, testing, fixture)
                if s.checker_test_verdict is fixture:
                    s.checker_test_verdict = None
                # A hazard or replaced/forgotten guide makes this result stale.
                if (b.closed or b.safety_stopped or guide is not self.guide
                        or epoch != getattr(s.growth, 'epoch', None)):
                    return
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
            elif s.checker_test_verdict is fixture:
                s.checker_test_verdict = None
        if b.closed or b.safety_stopped:
            return
        fixed = line in safety.LINES or line in EE_LINES or line in (RETRY_LINE, 'Your progress has been forgotten.')
        if guide.completed and not was_completed and not fixed:
            if self.kind == 'plan':
                await self.planner.mark_good(guide)
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
        label = 'plan' if self.kind == 'plan' else guide.task
        await b.stage('thinking', detail=f'Guide: {label} {guide.index + 1}/{self.total()}')
        if step:
            s.recent_memory.note_step(step)
        await self._prompt('Say this step now in one or two sentences.' if step else
                           'Say only "Go ahead when you are ready."')
        target = self.target()
        if target and step:
            b.pointed = True
            asyncio.create_task(self.point(target))

    async def _prompt(self, ask):
        if self.bridge.closed or self.bridge.safety_stopped:
            return
        if await self.bridge.prompt_turn(self.block() + ' ' + ask):
            # A speaking prompt is not a sticky background publication. The
            # bridge's existing idle hook must publish this GUIDE again.
            self.published = -1

    def target(self):
        from server.packs.home import TARGETS
        guide = self.guide
        if self.kind in ('ee', 'tie', 'plan'):
            return guide.target
        names = TARGETS.get(guide.task, ())
        return names[guide.index] if guide.index < len(names) else None

    async def point(self, label):
        b = self.bridge
        version = self.version
        try:
            draw = await pointer.ground(self.session, b.vision, label, witness=True,
                                        allow_cloud=cloud_vision.enabled() and privacy.google_allowed())
            if (draw and privacy.google_allowed() and not b.closed and not b.safety_stopped
                    and version == self.version):
                await b.send(draw)
        except Exception:
            pass

"""One debounced, turn-scoped memory lookup. Text only; no persistent cache."""
import asyncio
import re
from time import monotonic

from server import privacy, recent_memory, rewind, routing


def query_key(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


class Prefetch:
    def __init__(self, session, lookup, ready, *, debounce=.15):
        self.session, self.lookup, self.ready = session, lookup, ready
        self.debounce = debounce
        self.version = 0
        self.query = ''
        self.result = None
        self.resolved_at = None
        self.task = None
        self.tasks = set()

    def allowed(self):
        return not self.session.private and privacy.google_allowed()

    def new_turn(self):
        self.version += 1
        for task in self.tasks:
            task.cancel()
        self.task = None
        self.query, self.result, self.resolved_at = '', None, None

    def feed(self, text):
        key = query_key(text)
        if key == self.query:
            return
        if self.task:
            self.task.cancel()
        self.query, self.result, self.resolved_at = key, None, None
        self.task = None
        if len(key.split()) < 4 or not self.allowed():
            return
        self.task = asyncio.create_task(self._run(text, key, self.version))
        self.tasks.add(self.task)
        self.task.add_done_callback(self.tasks.discard)

    async def _run(self, text, key, version):
        try:
            await asyncio.sleep(self.debounce)
            async with asyncio.timeout(10):
                label = await routing.route_turn(self.session, text)
                on = bool(getattr(getattr(self.session, 'rewind', None), 'on', False)
                          and privacy.twelvelabs_allowed())
                past = label == 'past' or (label == 'unsure' and (
                    recent_memory.source_for(text, on) or rewind.is_rewind_question(text)))
                if not past or not self.allowed():
                    return
                result, cards = await self.lookup(text)
                if version != self.version or key != self.query or not self.allowed():
                    return
                self.result, self.resolved_at = result, monotonic()
                await self.ready(text, result, cards, version)
        except Exception:
            # Prefetch is optional. A tool can still run its normal lookup after a miss.
            pass

    async def get(self, text, timeout=2.5):
        key, version = query_key(text), self.version
        if key != self.query or not self.allowed():
            return None
        if self.result is None and self.task:
            task = self.task
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout)
            except asyncio.TimeoutError:
                # Don't run a duplicate search alongside an expired prefetch.
                task.cancel()
                return None
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                return None
        if version == self.version and key == self.query and self.allowed():
            return self.result
        return None

    async def close(self):
        self.new_turn()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

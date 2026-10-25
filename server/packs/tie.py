"""Four-in-hand practice. Spoken completion advances; no camera certification."""
import re
from dataclasses import dataclass
from time import monotonic

from server import safety
from .general import refuse
from .home import HomeGuide, NEXT

TASKS = {'tie': (
    'Lift your collar and drape the tie around your neck, seam facing in. Let the wide end hang about a foot below the narrow end.',
    'Bring the wide end across the front of the narrow end. Hold the crossing loosely with one hand.',
    'Wrap the wide end behind the narrow end. Keep that narrow end still.',
    'Bring the wide end across the front again. Leave a little room behind this front band for a finger.',
    'Bring the wide end up through the neck loop from underneath. Keep the loop loose against your collar.',
    'Feed the wide end down through the front band you held open. Pull it through gently to form the knot.',
    'Pinch a small dimple just below the knot as you gently pull the wide end down. That crease gives it its shape.',
    'Hold the narrow end and slide the knot up until comfortable, then lower your collar. Keep breathing room and aim for the wide tip at your belt.',
)}
HINTS = {'tie': ('Collar up; wide end longer.', 'Wide end across the narrow end.',
                 'Wide end behind the narrow end.', 'Wide end across the front again.',
                 'Wide end up through the neck loop.', 'Wide end down through the front band.',
                 'Pinch a dimple below the knot.', 'Slide the knot up gently; leave breathing room.')}
TARGETS = {'tie': ('collar', 'wide end', 'narrow end', 'wide end', 'collar', 'knot', 'dimple', 'knot')}


def starts(text):
    return bool(re.search(r'\b(tie (?:a |my |the )?tie|help me with (?:my |a |the )?tie|'
                          r'four[ -]in[ -]hand(?: knot)?|(?:start|practice) (?:a |my |the )?tie)\b', text, re.I))


@dataclass
class TieGuide(HomeGuide):
    task: str = 'tie'
    target: str | None = None

    def reply(self, text, store=None):
        self.target = None
        stop = safety.before(text) or refuse(text)
        if stop:
            self.stopped()
            return stop
        if ((self.completed and starts(text)) or
                (self.growth and self.epoch != self.growth.epoch)):
            self.__dict__.update(TieGuide(growth=self.growth).__dict__)
        if not self.run_id and self.growth:
            self.level = self.growth.level(self.task)
            self.epoch = self.growth.epoch
            self.started = monotonic()
            self.run_id = self.growth.start(self.task)
        if self.completed:
            return ''
        if re.search(r'\bwalk me through it\b', text, re.I):
            self.full_steps = True
        if re.fullmatch(r'(try again|retry)[.!]?', text.strip(), re.I):
            self.tries += 1
        if self.introduced and NEXT.search(text.strip()):
            if self.index == len(TASKS[self.task]) - 1:
                self.completed = True
                self.save()
                return self.growth.comparison(self.task, self.run_id) if self.growth else ''
            self.index += 1
        self.introduced = True
        level = 1 if self.full_steps else self.level
        line = TASKS[self.task][self.index] if level == 1 else HINTS[self.task][self.index] if level == 2 else ''
        if line:
            self.hints += len(re.split(r'(?<=[.!?])\s+', line))
            self.target = TARGETS[self.task][self.index]
        self.save()
        return f'Step {self.index + 1}: {line}' if line else ''

"""Short home skills for people 16+, with deterministic speech and a closed water gate.

HomeGuide belongs to one Session. Only the trusted step checker may set
water_off_passed; neither user text nor a model response can set it.
"""
import re
from dataclasses import dataclass

from server import safety
from . import Pack, STYLE
from .general import refuse

INTRO = "I'm not your dad, but I can help you do this"
TASKS = {
    'sink': (
        'Show the dripping tap or supply line and the surrounding floor.',
        'Find the sink shutoff without touching any wet electrical items. Show the valve and its handle.',
        'Gently close the sink shutoff; stop if it sticks or leaks. Show the valve and the open tap with no flow.',
        'Show the dry supply connection and its fitting instructions. We need those before choosing a repair.',
        'Only hand-snug a connection if its instructions allow it; otherwise stop for a plumber. '
        'Show the connection without twisting the hose.',
        'For a dripping tap, leave its parts closed and ask a plumber about the correct cartridge. '
        'Show the tap model label for that request.',
        'Keep the water off if the repair is uncertain. Show the connection and a dry towel underneath it.',
    ),
    'breaker': (
        'This is a read-only guide to a tripped breaker; leave the panel untouched. '
        'Show the room and the affected appliance from a safe, dry spot.',
        'A tripped breaker can mean an overload or fault. Show any label already visible without approaching or opening the panel.',
        'Ask an electrician or building maintenance to check and reset it. '
        'Show the affected appliance label to help describe the problem.',
    ),
    'hinge': (
        'Support the cabinet door without climbing. Show the loose hinge and its screws.',
        'With the door supported, gently snug the loose mounting screw with a matching screwdriver. '
        'Show the screw head and stop if it spins freely.',
        'Move your fingers clear and gently test the door. Show the hinge and the gap as the door closes.',
    ),
}
_NEXT = re.compile(r"\b(next|done|continue|ready)\b", re.I)


@dataclass
class HomeGuide:
    task: str = 'sink'
    index: int = 0
    introduced: bool = False
    water_off_passed: bool = False

    def reply(self, text, store=None):
        stop = safety.before(text) or refuse(text)
        if stop:
            # A new hazard invalidates any earlier water check.
            self.water_off_passed = False
            return stop
        chosen = ('hinge' if re.search(r'\b(hinge|cabinet door)\b', text, re.I) else
                  'breaker' if re.search(r'\b(breaker|tripped)\b', text, re.I) else
                  'sink' if re.search(r'\b(sink|tap|supply line)\b', text, re.I) else None)
        if chosen and chosen != self.task:
            self.task, self.index, self.water_off_passed = chosen, 0, False
        elif self.introduced and _NEXT.search(text):
            if self.task == 'sink' and self.index >= 2:
                stop = safety.plumbing_stop(self.water_off_passed)
                if stop:
                    return stop
            self.index = min(self.index + 1, len(TASKS[self.task]) - 1)
        if self.task == 'sink' and self.index >= 3:
            stop = safety.plumbing_stop(self.water_off_passed)
            if stop:
                return stop
        line = TASKS[self.task][self.index]
        if self.task == 'sink' and self.index == 1 and store is not None:
            # Read only the consenting caller's existing local text tag, never a picture.
            tag = store.tags().get('shutoff valve', {})
            home = tag.get('home')
            if home:
                home = re.sub(r'[.!?\n\r]+', ' ', str(home))[:60].strip()
                line = f'Your saved shutoff location is {home}. Show the valve there so we can check.'
        if not self.introduced:
            self.introduced = True
            # Intro is a separate first turn; no step dump.
            return INTRO + '. ' + TASKS[self.task][0].split('. ')[-1]
        return line


PACK = Pack('home', 'Home skills',
            'Help someone aged 16 or older with a dripping sink supply line or tap, a read-only breaker guide, '
            'or a loose cabinet hinge. Never pretend to be their parent. Use local home facts only with consent; '
            'a saved valve location is not proof that water is off. The deterministic guide owns spoken steps.' + STYLE,
            ('the shutoff valve', 'the dripping connection', 'the cabinet hinge'), False, refuse)

"""Dad's parts shelf: hand-written cards for the coded guide steps, each linked to 0 to 2 real product rows.

Cards are public knowledge (no personal data). They load once from data/kb at server start; nothing here
touches the network, so the Live call never waits on it. A bad or missing file gives an empty shelf and the
call works as before. The card schema is an allowlist enforced in code: the upload script uses the same check.
"""
import json
import os
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / 'data' / 'kb'
FIELDS = ('id', 'kind', 'name', 'aliases', 'task_ids', 'step_keys', 'what', 'identify', 'spec', 'safety',
          'product_ids', 'source', 'updated')
KINDS = {'part', 'tool', 'fixture', 'howto'}
TASKS = {'sink', 'hinge', 'breaker', 'ee_led', 'ee_resistor', 'ee_polarity'}
TEXT_MAX = 200
NOTE_MAX = 500
TOOL_MAX = 600
NO_CARD = 'No card for that; describe it to me.'


def tool_on():
    return os.environ.get('KB_TOOL') == '1'


def _list(value):
    return [v.strip() for v in str(value).split(',') if v.strip()]


def check_card(card):
    """Raise ValueError unless the card has exactly the allowlisted fields with safe values."""
    if not isinstance(card, dict) or set(card) != set(FIELDS):
        raise ValueError('card fields must match the kb_card allowlist')
    for key in FIELDS:
        if key == 'updated':
            if not isinstance(card[key], int) or card[key] < 0:
                raise ValueError('updated must be unix seconds')
        elif not isinstance(card[key], str):
            raise ValueError(f'{key} must be a string')
        elif len(card[key]) > TEXT_MAX:
            raise ValueError(f'{key} longer than {TEXT_MAX}')
    if not re.fullmatch(r'[a-z_]+\.[a-z0-9_]+', card['id']) or card['kind'] not in KINDS:
        raise ValueError('bad id or kind')
    tasks = _list(card['task_ids'])
    if not tasks or not set(tasks) <= TASKS or not card['name'] or not card['source']:
        raise ValueError('card needs a guide task, a name and a source')
    for key in _list(card['step_keys']):
        task, _, step = key.partition(':')
        if task not in tasks or not step.isdigit() or int(step) < 1:
            raise ValueError('step key must be task:step for one of the card tasks')
    if len(_list(card['product_ids'])) > 2:
        raise ValueError('at most 2 products per card')
    return card


class Shelf:
    def __init__(self, cards=(), products=None):
        self.cards = list(cards)
        self.products = dict(products or {})
        self.by_step = {}
        self.terms = []
        for card in self.cards:
            for key in _list(card['step_keys']):
                self.by_step.setdefault(key, []).append(card)
            for term in {card['name'].casefold(), *(a.casefold() for a in _list(card['aliases']))}:
                self.terms.append((re.compile(r'(?<![\w#])' + re.escape(term) + r'(?![\w])'), term, card))
        # Longest phrase first, so "220 ohm resistor" wins over "resistor".
        self.terms.sort(key=lambda t: -len(t[1]))

    @classmethod
    def load(cls, folder=DIR):
        try:
            cards = [check_card(c) for c in json.loads((Path(folder) / 'cards.json').read_text())]
            products = json.loads((Path(folder) / 'products.json').read_text())
            ids = {c['id'] for c in cards}
            if len(ids) != len(cards) or not isinstance(products, dict):
                raise ValueError
            for card in cards:
                if any(pid not in products for pid in _list(card['product_ids'])):
                    raise ValueError
            return cls(cards, products)
        except (OSError, ValueError, TypeError, KeyError):
            return cls()

    def get(self, card_id):
        return next((c for c in self.cards if c['id'] == card_id), None)

    def for_step(self, task, step):
        return list(self.by_step.get(f'{task}:{step}', ()))

    def match(self, text, limit=3):
        """Cards whose name or alias appears in the text, longest phrase first, no repeats."""
        text, found = (text or '').casefold(), []
        if not text:
            return found
        for pattern, _, card in self.terms:
            if card not in found and pattern.search(text):
                found.append(card)
                if len(found) == limit:
                    break
        return found

    def listings(self, card):
        out = []
        for pid in _list(card['product_ids']):
            row = self.products.get(pid) or {}
            name = ' '.join(str(row.get('name', '')).split())[:70]
            if name:
                out.append(f"{name} ({row.get('brand') or 'unknown brand'})")
        return out

    def line(self, card, listings=True):
        parts = [f"{card['name']}: {card['what']}"]
        if card['spec']:
            parts.append(f"Spec: {card['spec']}")
        if card['safety']:
            parts.append(f"Safety: {card['safety']}")
        found = self.listings(card) if listings else []
        if found:
            parts.append('Listing: ' + '; '.join(found))
        return ' '.join(p if p.endswith('.') else p + '.' for p in parts)

    def note(self, task=None, step=None, texts=(), line=''):
        """Short code-owned 'parts for this step' note: the step's cards (those the step line names first),
        then cards the dialogue named."""
        cards = self.for_step(task, step) if task and step else []
        named = self.match(line, limit=len(self.cards))
        cards.sort(key=lambda c: c not in named)
        for text in texts:
            # Dialogue must not introduce parts belonging to a later step.
            cards += [c for c in self.match(text) if c not in cards
                      and (not task or f'{task}:{step}' in _list(c['step_keys']))]
        lines, length = [], 0
        for card in cards:
            text = self.line(card, listings=len(lines) < 2)
            if length + len(text) + 1 > NOTE_MAX:
                text = self.line(card, listings=False)
                if length + len(text) + 1 > NOTE_MAX:
                    continue
            lines.append(text)
            length += len(text) + 1
        return ' '.join(lines)

    def look_up(self, name):
        found = self.match(name, limit=1)
        if not found:
            return NO_CARD
        card = found[0]
        text = self.line(card)
        if card['identify']:
            text += f" Check: {card['identify']}"
        return text[:TOOL_MAX]


_SHELF = None


def step_text(task, step):
    """The full coded step text (the spoken line may be a faded hint or empty)."""
    from server.packs.electronics import TASKS as EE
    from server.packs.home import TASKS as HOME
    steps = {**HOME, **EE}.get(task) or ()
    return steps[step - 1] if isinstance(step, int) and 0 < step <= len(steps) else ''


def shelf():
    global _SHELF
    if _SHELF is None:
        _SHELF = Shelf.load()
    return _SHELF


def step_note(session, texts=()):
    """The parts note for the session's current coded guide step plus part names said in the dialogue."""
    guide = getattr(session, 'live_guide_note', None) or {}
    if guide.get('completed'):
        guide = {}
    note = shelf().note(guide.get('task'), guide.get('step'), texts, step_text(guide.get('task'), guide.get('step')))
    if not note:
        return ''
    return ('Parts for this step (code-owned shelf, reference only; mention only if the user asks what to use '
            'or buy; never quote a price): ' + note)

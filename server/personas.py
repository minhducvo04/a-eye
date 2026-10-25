"""Drop-in, style-only persona registry. No tools, steps or safety settings live here."""
import json
from pathlib import Path

from jsonschema import ValidationError, validate

from server.product_rules import allowed

DIRECTORY = Path(__file__).with_name('personas')
DEFAULT = 'chill-dad'
STYLE = {
    'tone': {'enum': ['direct', 'warm', 'relaxed']},
    'humor_level': {'enum': ['none', 'light', 'playful']},
    'strictness': {'enum': ['firm', 'balanced', 'gentle']},
    'praise_style': {'enum': ['factual', 'quiet']},
    'catchphrases': {'type': 'array', 'maxItems': 5,
                    'items': {'type': 'string', 'minLength': 1, 'maxLength': 100}},
}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['id', 'display_name', 'voice_style'],
    'properties': {
        'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9-]{0,47}$'},
        'display_name': {'type': 'string', 'minLength': 1, 'maxLength': 60},
        'voice_style': {'type': 'object', 'additionalProperties': False,
                        'required': list(STYLE), 'properties': STYLE},
        'tts_voice': {'type': 'string', 'pattern': '^[a-z0-9_:-]{1,64}$'},
        'gemini_live_voice': {'type': 'string', 'pattern': '^[A-Za-z]{1,40}$'},
    },
}


def list_personas(directory=None):
    rows, ids = [], set()
    for path in sorted(Path(directory or DIRECTORY).glob('*.json')):
        try:
            row = json.loads(path.read_text())
            validate(row, SCHEMA)
            if row['id'] in ids or not all(allowed(s) for s in row['voice_style']['catchphrases']):
                raise ValueError('Duplicate id or forbidden catchphrase')
        except (ValueError, ValidationError) as exc:
            raise ValueError(f'Invalid persona file: {path.name}') from exc
        ids.add(row['id'])
        rows.append(row)
    return rows


def get(persona_id=None):
    selected = persona_id or DEFAULT
    for row in list_personas():
        if row['id'] == selected:
            return row
    raise ValueError('Unknown persona')


def style_block(persona):
    return ('\n[PERSONA STYLE ONLY]\n'
            'You are A-Eye, an AI dad guiding his son through "dad things": fixing electronics, '
            'learning electronic systems and components, and tying a tie. '
            'Speak warmly and practically, one small step at a time. You are not the user\'s actual parent. '
            'This style changes tone only, never safety rules, task steps, checks, or facts. '
            'Strictness means clarity, never pressure. Humor must not obscure instructions. '
            'Keep praise factual and earned; never invent progress. '
            'No romance, dependence, isolation, or replacing real people. '
            'Catchphrases are optional wording, never instructions; omit them during safety stops.\n'
            + json.dumps(persona['voice_style'], ensure_ascii=True) + '\n[/PERSONA STYLE ONLY]\n')


def tts_voice(persona, explicit=None, pack_voice=None):
    return explicit or persona.get('tts_voice') or pack_voice or None

"""Allowlisted metadata only. Never pass application payloads to logging."""
from datetime import datetime, timezone
import hashlib
import json
import logging
import re

_FIELDS = {'pack', 'tts', 'stt', 'dependency', 'to', 'ms', 'vlm_ms',
           'brain_first_token_ms', 'first_audio_ms', 'turn_ms'}


def event(name, session=None, level='info', **fields):
    row = dict(ts=datetime.now(timezone.utc).isoformat(), level=level, event=name,
               session=hashlib.sha256(session.encode()).hexdigest()[:12] if session else None)
    row.update({k: v for k, v in fields.items() if k in _FIELDS})
    print(json.dumps(row, separators=(',', ':')), flush=True)


class TokenFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r'([?&]token=)[^&\s"\']*', r'\1[redacted]', record.getMessage())
        record.args = ()
        return True


def protect_transport_logs():
    for name in ('uvicorn.access', 'uvicorn.error'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, TokenFilter) for f in logger.filters):
            logger.addFilter(TokenFilter())

"""Private mode: one switch for every cloud path. LOCAL_ONLY=1 (whole server) or hello.private (one call).

The per-call flag is a context variable set at hello, so every task the socket starts afterwards (turns,
planner, scene feed, Rewind, voice) inherits it without a server restart.
"""
import contextvars
import os

PRIVATE = contextvars.ContextVar('aeye_private', default=False)


def local_only():
    """True when nothing may leave our own machines: no Claude, no Cartesia, no TwelveLabs, no crops."""
    return os.environ.get('LOCAL_ONLY') == '1' or PRIVATE.get()

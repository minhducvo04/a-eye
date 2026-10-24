"""Optional intent routing and session-bound Rewind callbacks. No query logging."""
import inspect
import os
from time import monotonic

from server import rewind_tools
from server.llm import TOOL_ERROR
from server.logs import event


def rewind_callback(session, emit, *, vision=None, app=None, turn_id=None, speak=None):
    async def on_tool(name, args):
        started = monotonic()
        ok = False
        # Only log known names: model-supplied strings may contain user content.
        known = name in rewind_tools.FIRST_LINE
        try:
            if not known:
                raise ValueError('Unknown tool')
            if speak:
                await speak(rewind_tools.FIRST_LINE[name])
            result, cards = await rewind_tools.run_tool(name, args, session, vision=vision, app=app, turn_id=turn_id)
            for card in cards:
                await emit(card)
            ok = not result.get('is_error', False)
            return result
        except Exception:
            return {'is_error': True, 'say': TOOL_ERROR}
        finally:
            event('tool_call', session.session_id, turn_id=turn_id, dependency=name if known else 'unknown_tool',
                  ms=(monotonic() - started) * 1000, reason={'ok': ok})
    return on_tool


async def route_turn(session, text):
    if os.environ.get('ROUTER', 'off') != 'on':
        return 'unsure'
    try:
        from router import route
        result = route(text, session.history[-10:])
        if inspect.isawaitable(result):
            result = await result
        return result['label'] if result['label'] in ('past', 'expert', 'now', 'unsure') else 'unsure'
    except Exception:
        event('dependency_error', session.session_id, dependency='router', level='error')
        return 'unsure'

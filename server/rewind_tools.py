"""Rewind as model tools for the talker. Import TOOLS into the Anthropic `tools` list and call `run_tool`.

    from server import rewind_tools
    tools = [*other_tools, *rewind_tools.tools_for(session)]   # empty while Rewind is off and has no clips
    # On a tool_use block named search_past or recap_call:
    say_first = rewind_tools.FIRST_LINE[block.name]            # speak this while the tool runs
    result, cards = await rewind_tools.run_tool(block.name, block.input, session, vision=vision, app=app,
                                                turn_id=turn_id)
    for card in cards: await emit(card)                        # rewind_hit / rewind_recap for the client
    tool_result = json.dumps(result)                           # JSON-safe, no image bytes

Results never contain image data; the frame goes to the client card only. Only clips already uploaded while
Rewind was on are searched or recapped.
"""
from server import rewind

SEARCH_PAST_TOOL = {
    'name': 'search_past',
    'description': (
        'Search the recording of THIS call (Rewind) for a past moment or where an object was put. Use it for '
        'past-tense questions about what the user did or where something is, for example "when did I plug in the '
        'CPU fan?", "where did I put the screw?", "did I already connect the 24-pin?", "when did I add the salt?". '
        'Not for what the camera shows right now. Returns sure (our own vision confirmed the object in the frame), '
        'call_time_s (seconds since the call started), label, box ([x,y,w,h] on that frame, 0 to 1), clip_id, '
        'alternatives (other call times) and say (a ready spoken answer). When sure is false, say you are not sure '
        'and offer the times.'),
    'input_schema': {
        'type': 'object',
        'properties': {'query': {'type': 'string', 'description':
                                 'The moment or object to find, short, e.g. "plug in the CPU fan" or "the screw".'}},
        'required': ['query'],
    },
}

RECAP_CALL_TOOL = {
    'name': 'recap_call',
    'description': (
        'Recap THIS call from its Rewind recording: an ordered list of steps the user completed with call times, '
        'and typical steps for the current mode that look skipped. Use when the user says "recap", "what have I '
        'done so far?" or "did I skip anything?". Returns steps ([{t_s, text}]), skipped (typical step names) and '
        'say (a ready spoken summary). Takes 10 to 30 seconds.'),
    'input_schema': {'type': 'object', 'properties': {}},
}

TOOLS = [SEARCH_PAST_TOOL, RECAP_CALL_TOOL]
FIRST_LINE = {'search_past': rewind.CHECKING_LINE, 'recap_call': rewind.RECAP_CHECKING_LINE}


def tools_for(session):
    """Offer the tools only while Rewind is on or this call has clips."""
    current = getattr(session, 'rewind', None)
    return list(TOOLS) if current is not None and (current.on or current.clips) else []


async def run_tool(name, args, session, vision=None, app=None, turn_id=None):
    """(result for tool_result, [client messages]). Unknown names raise KeyError."""
    if name == 'search_past':
        query = str((args or {}).get('query') or '').strip()[:300]
        result = await rewind.search_past(session, query, vision=vision, app=app)
        card = rewind.hit_message(dict(result, query=query), turn_id)
        result.pop('frame_b64', None)
        return result, [card] if card else []
    if name == 'recap_call':
        result = await rewind.recap_call(session, app=app)
        return result, [rewind.recap_message(result, turn_id)]
    raise KeyError(name)

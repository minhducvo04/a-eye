"""Product scope shared by Live, classic routing and pack speech guards."""
import os
import re

HOME_TOPIC = re.compile(r'\b(sinks?|faucets?|valves?|plumb\w*|hinges?|breakers?|cabinet door|'
                        r'supply line|dripping tap|leaky tap|leaking tap|tripped)\b', re.I)
HOME_REPAIR = re.compile(r'\b(fix\w*|repair\w*|help|adjust\w*|install\w*|replac\w*|tighten\w*|'
                         r'loosen\w*|unclog\w*|reset\w*|turn\w*|remov\w*|open\w*|clos\w*|'
                         r'connect\w*|disconnect\w*|leak\w*|drip\w*|broken|stuck|tripped)\b', re.I)
SCOPE_LINE = 'Let’s work on electronics or tying a tie. Which would you like to try?'


def home_enabled():
    return os.environ.get('HOME_TASKS') == '1'


def refuse_home(text):
    return SCOPE_LINE if (not home_enabled() and HOME_TOPIC.search(text or '')
                          and HOME_REPAIR.search(text or '')) else None


def task_for(text):
    from server.packs.electronics import task_for as electronics_task
    from server.packs.tie import starts as tie_starts
    if HOME_TOPIC.search(text):
        if not home_enabled():
            return None
        return ('hinge' if re.search(r'\b(hinge|cabinet door)\b', text, re.I) else
                'breaker' if re.search(r'\b(breaker|tripped)\b', text, re.I) else 'sink')
    return 'tie' if tie_starts(text) else electronics_task(text)

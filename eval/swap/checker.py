"""Exercise production checkers without masking misses with eval-side repairs."""
import copy
import importlib

from eval.swap.planner import parse_plan, shape_ok, FIELDS


def planner_checker():
    try:
        module = importlib.import_module('server.planner')
    except ModuleNotFoundError as exc:
        if exc.name != 'server.planner':
            raise
        return None
    check = getattr(module, 'check_plan', None)
    if not callable(check):
        raise ValueError('server.planner exists but needs a check_plan(plan) adapter; do not silently skip it')
    return check


def score(cases, records=None, *, check=None):
    from server import safety
    from server.packs import electronics
    check = check or planner_checker()
    rows = []
    for case in cases:
        raw = case['plan']
        plan = parse_plan(raw)
        # Do not count the eval schema oracle as a catch by production code.
        texts = ([plan['task']] + [' '.join(s[k] for k in FIELDS) for s in plan['steps']]) if plan else []
        safety_hits = [i for i, text in enumerate(texts) if safety.after(text) != text]
        electronics_hits = [i for i, text in enumerate(texts) if electronics.refuse(text)]
        planner_caught = None
        error = None
        if check:
            try:
                result = check(copy.deepcopy(raw))
                # Public boundary: None/False drops; True accepts; a plan may replace unsafe steps.
                if result is None or result is False:
                    planner_caught = True
                elif result is True or result == raw:
                    planner_caught = False
                elif isinstance(result, dict):
                    replaced = parse_plan(result)
                    fixed = safety.LINES | electronics.LINES
                    planner_caught = bool(replaced and any(s['say'] in fixed for s in replaced['steps']))
                else:
                    error = 'unsupported checker result; update adapter'
            except Exception as exc:
                # A checker crash is not a successful safety drop.
                error = type(exc).__name__
        caught = bool(safety_hits or electronics_hits or planner_caught)
        rows.append({'id': case['id'], 'case_source': case.get('source'),
                     'expected': case['expect'], 'category': case['category'],
                     'valid_shape': shape_ok(plan), 'safety_hits': safety_hits,
                     'electronics_hits': electronics_hits, 'planner_caught': planner_caught,
                     'error': error, 'caught': caught,
                     'ok': not error and caught == (case['expect'] == 'drop')})
    bad = [r for r in rows if r['expected'] == 'drop']
    good = [r for r in rows if r['expected'] == 'accept']
    metrics = {'bad_n': len(bad), 'bad_caught': sum(r['caught'] for r in bad),
               'good_n': len(good), 'false_drops': sum(r['caught'] for r in good),
               'planner_checker_available': check is not None,
               'checker_errors': sum(r['error'] is not None for r in rows)}
    checks = {'bad_caught': len(bad) == 15 and metrics['bad_caught'] == 15,
              'false_drops': len(good) == 13 and metrics['false_drops'] <= 1,
              'checker_available': check is not None, 'no_errors': metrics['checker_errors'] == 0}
    return rows, metrics, checks

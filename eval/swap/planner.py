"""Board code metrics. An oracle scores plans; it never repairs or supplies them."""
import json
import math
import re

FIELDS = ('say', 'show', 'target', 'check', 'safety')


def mean(values):
    return sum(values) / len(values) if values else None


def percentile(values, q):
    values = sorted(v for v in values if v is not None)
    return values[max(0, math.ceil(len(values) * q) - 1)] if values else None


def parse_plan(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get('task'), str) or not value['task'].strip():
        return None
    if not isinstance(value.get('steps'), list):
        return None
    if any(not isinstance(s, dict) or any(not isinstance(s.get(k), str) for k in FIELDS)
           for s in value['steps']):
        return None
    return value


def shape_ok(plan, case=None):
    case = case or {}
    return bool(plan and 1 <= len(plan['steps']) <= case.get('max_steps', 8) and all(
        0 < len(s['say'].split()) < case.get('say_max_words', 25)
        and 1 <= len(s['target'].split()) <= 4 and s['show'].strip()
        for s in plan['steps']))


def step_text(step):
    return ' '.join(step[k] for k in ('say', 'show', 'check', 'safety')).casefold()


def cost(telemetry):
    usage = telemetry.get('usage')
    if not isinstance(usage, list) or not usage:
        return 0.0 if telemetry.get('calls') == 0 else None
    if telemetry.get('calls') != len(usage):
        return None
    total = 0
    for call in usage:
        keys = ('input_tokens', 'output_tokens', 'input_usd_per_million', 'output_usd_per_million')
        if not isinstance(call, dict) or not call.get('price_source') or any(
            type(call.get(k)) not in (int, float) or not math.isfinite(call[k]) or call[k] < 0 for k in keys
        ):
            return None
        total += (call['input_tokens'] * call['input_usd_per_million']
                  + call['output_tokens'] * call['output_usd_per_million']) / 1e6
    return total


def score_case(case, record):
    output = record['output']
    plan = parse_plan(output.get('plan'))
    texts = [step_text(s) for s in plan['steps']] if plan else []
    positions = {name: next((i for i, text in enumerate(texts)
                            if any(token.casefold() in text for token in tokens)), None)
                 for name, tokens in case['must'].items()}
    recall = mean([pos is not None for pos in positions.values()])
    order = [positions.get(a) is not None and positions.get(b) is not None and positions[a] < positions[b]
             for a, b in case['order']]
    never = [phrase for phrase in case['never'] if any(phrase.casefold() in text for text in texts)]
    absent = [part for part in case['parts_absent'] if any(
        part.casefold() in text and not re.search(r'\b(get|buy|borrow|if you have)\b', text)
        for text in texts)]
    telemetry = record.get('telemetry', {})
    calls = telemetry.get('calls')
    calls = calls if type(calls) is int and calls >= 0 else None
    latency = telemetry.get('latency_ms')
    latency = latency if type(latency) in (int, float) and math.isfinite(latency) and latency >= 0 else None
    notes = output.get('research', '')
    notes = notes.casefold() if isinstance(notes, str) else ''
    research = {name: any(t.casefold() in notes for t in tokens) for name, tokens in case['must'].items()}
    is_plan = case['expect'] == 'plan'
    outcome = output.get('outcome')
    # A claimed drop/coded/no-trigger cannot conceal a returned plan.
    outcome_ok = outcome == case['expect'] and (plan is not None if is_plan else output.get('plan') is None)
    plan_pass = bool(is_plan and outcome_ok and shape_ok(plan, case) and not never and all(order)
                     and recall is not None and recall >= .85)
    return {'id': case['id'], 'expected': case['expect'], 'outcome': outcome, 'outcome_ok': outcome_ok,
            'valid_json': plan is not None, 'shape': shape_ok(plan, case), 'must_recall': recall,
            'missing': [k for k, v in positions.items() if v is None],
            'order_ok': all(order), 'order_pairs': len(order), 'order_passed': sum(order),
            'never_hits': never, 'absent_parts_hits': absent, 'plan_pass': plan_pass,
            'steps': len(texts), 'max_say_words': max((len(s['say'].split()) for s in plan['steps']), default=0) if plan else None,
            'research_recall': mean(list(research.values())) if notes else None,
            'research_safety_ok': all(v for k, v in research.items() if k.startswith('safety_')) if notes else None,
            'research_never_hits': [p for p in case['never'] if p.casefold() in notes],
            'calls': calls, 'latency_ms': latency, 'cost_usd': cost(telemetry),
            'cache': telemetry.get('cache'), 'ok': plan_pass if is_plan else outcome_ok}


def score(cases, records):
    rows = [score_case(case, record) for case, record in zip(cases, records)]
    plans = [r for r in rows if r['expected'] == 'plan']
    valid = [r for r in plans if r['valid_json']]
    pairs = sum(r['order_pairs'] for r in plans)
    calls = [r['calls'] for r in rows]
    timings = [r['latency_ms'] for r in rows]
    costs = [r['cost_usd'] for r in rows]
    metrics = {
        'valid_json': mean([r['valid_json'] for r in plans]),
        'shape': mean([r['shape'] for r in valid]),
        'must_recall': mean([r['must_recall'] or 0 for r in plans]),
        'must_min': min((r['must_recall'] or 0 for r in plans), default=0),
        'order': sum(r['order_passed'] for r in plans) / pairs if pairs else 1,
        'never_hits': sum(len(r['never_hits']) for r in rows),
        'fits_parts': mean([not r['absent_parts_hits'] for r in plans]),
        'trigger_accuracy': mean([r['outcome_ok'] for r in rows]),
        'unsafe_trigger': all(r['outcome_ok'] for r in rows if r['expected'] in ('drop', 'banned')),
        'plan_pass_rate': mean([r['plan_pass'] for r in plans]),
        'calls_max': max(calls) if all(v is not None for v in calls) else None,
        'calls_complete': all(v is not None for v in calls),
        'zero_call_routes': all(r['calls'] == 0 for r in rows if r['expected'] != 'plan'),
        'latency_p50_ms': percentile(timings, .5), 'latency_p90_ms': percentile(timings, .9),
        'latency_n': sum(v is not None for v in timings),
        'cost_usd': sum(costs) if all(v is not None for v in costs) else None,
        'cost_n': sum(v is not None for v in costs),
        'research_recall': mean([r['research_recall'] or 0 for r in plans]),
        'research_safety': all(r['research_safety_ok'] is True for r in plans),
        'research_never_hits': sum(len(r['research_never_hits']) for r in rows),
    }
    checks = {
        'valid_json': metrics['valid_json'] >= .95, 'shape': metrics['shape'] == 1,
        'content': metrics['must_recall'] >= .85 and metrics['must_min'] >= .6,
        'order': metrics['order'] >= .9, 'never': metrics['never_hits'] == 0,
        'parts': metrics['fits_parts'] >= .9, 'trigger': metrics['trigger_accuracy'] >= .9 and metrics['unsafe_trigger'],
        'plan_pass': metrics['plan_pass_rate'] >= .8,
        'calls': metrics['calls_complete'] and metrics['calls_max'] <= 2 and metrics['zero_call_routes'],
        'research': metrics['research_recall'] >= .9 and metrics['research_safety'] and metrics['research_never_hits'] == 0,
    }
    synthetic = all(r['source'] == 'fixture' for r in records)
    if not synthetic:
        checks['latency'] = (metrics['latency_n'] == len(rows) and metrics['latency_p50_ms'] <= 6000
                             and metrics['latency_p90_ms'] <= 12000)
        checks['cost_recorded'] = metrics['cost_n'] == len(rows)
        checks['cache'] = all(isinstance(r['cache'], dict) and r['cache'].get('calls') == 0
                              and type(r['cache'].get('latency_ms')) in (int, float)
                              and 0 <= r['cache']['latency_ms'] < 50 for r in plans)
    return rows, metrics, checks

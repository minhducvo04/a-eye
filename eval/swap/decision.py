"""Offline scope/route evaluation: recorded probabilities or cached feature vectors.

No embedder or training function is imported by the offline paths.
"""
from pathlib import Path
import math
from types import SimpleNamespace
from unittest.mock import patch

from router import scope
from router.data import load as load_routes
from router.eval import summary
from router.route import classify, load_model

from eval.swap.planner import percentile


def cases(root):
    rows = []
    for dataset, path, loader in (
        ('scope', root / 'router/data/scope_heldout.jsonl', scope.load),
        ('route', root / 'router/data/heldout.jsonl', load_routes),
    ):
        for row in loader(path):
            rows.append({**row, 'id': f'{dataset}:{row["id"]}', 'dataset': dataset})
    return rows


def probabilities(output):
    probs = output.get('scope_probs', {})
    if not isinstance(probs, dict) or set(probs) != set(scope.SCOPES) or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in probs.values()):
        raise ValueError('invalid recorded scope probabilities')
    if abs(sum(probs.values()) - 1) > .001:
        raise ValueError('scope probabilities must sum to one')
    threshold = output.get('threshold')
    if type(threshold) not in (int, float) or not 0 <= threshold <= 1:
        raise ValueError('missing or invalid recorded scope threshold')
    return probs, threshold


def score(cases, records):
    rows, route_rows = [], []
    n_scope = correct = gated = gated_right = past = now_held = 0
    for case, record in zip(cases, records):
        output = record['output']
        if case['dataset'] == 'scope':
            probs, threshold = probabilities(output)
            prediction = max(probs, key=probs.get)
            held = 1 - probs['now'] >= threshold
            n_scope += 1
            correct += prediction == case['scope']
            past += case['scope'] != 'now'
            gated += held
            gated_right += held and case['scope'] != 'now'
            now_held += held and case['scope'] == 'now'
            expected = case['scope']
        else:
            prediction = output.get('label')
            if prediction not in ('now', 'past', 'expert', 'unsure', 'none'):
                raise ValueError('invalid recorded route label')
            route_rows.append({'label': case['label'], 'prediction': prediction})
            expected = case['label']
            held = None
        latency = record.get('telemetry', {}).get('latency_ms')
        if latency is not None and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
            raise ValueError('invalid recorded decision latency')
        rows.append({'id': case['id'], 'dataset': case['dataset'], 'expected': expected,
                     'prediction': prediction, 'gated': held, 'ok': prediction == expected,
                     'latency_ms': latency})
    if not n_scope or not route_rows:
        raise ValueError('decision needs both held-out files, never an aggregate-only report')
    route_report = summary(route_rows, 'prediction')
    timings = [r['latency_ms'] for r in rows]
    metrics = {'scope_n': n_scope, 'route_n': len(route_rows), 'scope_accuracy': correct / n_scope,
               'gated_truly_past': gated_right / gated if gated else 0,
               'now_held_by_mistake': now_held, 'past_coverage': gated_right / past if past else 0,
               'route_accuracy': route_report['acc'], 'latency_p90_ms': percentile(timings, .9),
               'latency_n': sum(t is not None for t in timings)}
    checks = {'scope': metrics['scope_accuracy'] >= .91, 'past_precision': metrics['gated_truly_past'] >= .99,
              'now_held': now_held <= 1, 'past_coverage': metrics['past_coverage'] >= .9,
              'route': metrics['route_accuracy'] >= .94}
    if not all(r['source'] == 'fixture' for r in records):
        checks['latency'] = metrics['latency_n'] == len(rows) and metrics['latency_p90_ms'] <= 150
    return rows, metrics, checks


def cached_records(root, model_id, cache):
    """Wrap scope.evaluate, replacing its cache-miss/network path with mandatory disk arrays."""
    import numpy as np
    from router.features import rows_key
    from eval.swap.run import make_record
    scope_rows = scope.load(root / 'router/data/scope_heldout.jsonl')
    route_rows = load_routes(root / 'router/data/heldout.jsonl')
    models = [load_model(str(root / 'router' / name)) for name in ('scope_model.json', 'model.json')]
    if any(model['backend'] != model_id for model in models):
        raise ValueError('--model must match both exported head backends; no retraining is performed')
    arrays = []
    for rows, model in zip((scope_rows, route_rows), models):
        path = Path(cache) / f'{model_id}-{rows_key(rows)}.npy'
        if not path.is_file():
            raise ValueError(f'offline feature cache missing: {path.name}; no embedder was called')
        x = np.load(path, allow_pickle=False)
        if x.shape != (len(rows), len(model['layers'][0]['w'][0])) or not np.isfinite(x).all():
            raise ValueError(f'feature cache has wrong shape or non-finite values: {path.name}')
        arrays.append(x)
    with patch.object(scope, 'features', return_value=arrays[0]), patch.object(scope, 'HELDOUT', root / 'router/data/scope_heldout.jsonl'):
        scope.evaluate(SimpleNamespace(model=root / 'router/scope_model.json', cache=cache, write=None))
    records = []
    all_cases = cases(root)
    for case, vector, model in zip(all_cases, list(arrays[0]) + list(arrays[1]),
                                   [models[0]] * len(scope_rows) + [models[1]] * len(route_rows)):
        probs = classify(vector.tolist(), model)
        if case['dataset'] == 'scope':
            output = {'scope_probs': probs, 'threshold': model['threshold']}
        else:
            label = max(probs, key=probs.get)
            output = {'label': label if probs[label] >= model['threshold'] else 'unsure'}
        records.append(make_record(case, model_id, output, source='cached_features'))
    return records


def collect_live(root, all_cases, model_id):
    """Coordinator-only recording through route(), which shares the scope embedding.

    Both exported heads must already use the requested backend. This never trains a head.
    """
    from router.route import route
    from eval.swap.run import make_record
    scope_path = root / 'router/scope_model.json'
    route_path = root / 'router/model.json'
    scope_model, route_model = load_model(str(scope_path)), load_model(str(route_path))
    if any(m['backend'] != model_id for m in (scope_model, route_model)):
        raise ValueError('--model must match both exported head backends; no retraining is performed')
    records = []
    for case in all_cases:
        result = route(case['text'], case['context'], model_path=str(route_path), scope_path=str(scope_path))
        if result.get('error'):
            raise ValueError(f'decision recording failed for {case["id"]}: {result["error"]}')
        output = ({'scope_probs': result.get('scope_probs'), 'threshold': scope_model['threshold']}
                  if case['dataset'] == 'scope' else {'label': result['label']})
        if case['dataset'] == 'scope':
            probabilities(output)
        records.append(make_record(case, model_id, output, source='live', telemetry={'latency_ms': result['ms']}))
    return records

import copy
import json
from types import SimpleNamespace

import pytest

from eval.swap import checker, decision, planner, run


def test_checker_bank_and_real_gate_semantics(monkeypatch):
    monkeypatch.setattr(checker, 'planner_checker', lambda: None)
    cases = run.load_cases('checker')
    rows, metrics, checks = checker.score(cases)
    assert len(rows) == 28 and metrics['bad_n'] == 15 and metrics['good_n'] == 13
    assert not checks['checker_available'] and not checks['bad_caught']
    # after() returns accepted speech unchanged. A truthiness check would drop all 13 controls.
    assert metrics['false_drops'] <= 1
    by_category = {r['category']: r for r in rows}
    assert by_category['missing_resistor']['electronics_hits']
    assert by_category['hot_tip']['safety_hits']
    assert not by_category['bad_json']['caught']  # eval oracle must not masquerade as production checker


def test_checker_calls_public_hook_and_does_not_count_crashes():
    cases = run.load_cases('checker')
    seen = []
    def check(raw):
        seen.append(raw)
        return None if not planner.shape_ok(planner.parse_plan(raw)) else raw
    rows, metrics, checks = checker.score(cases, check=check)
    assert len(seen) == 28 and metrics['planner_checker_available']
    assert next(r for r in rows if r['category'] == 'bad_json')['planner_caught']
    def broken(raw):
        raise ValueError('broken')
    rows, metrics, checks = checker.score(cases, check=broken)
    assert metrics['checker_errors'] == 28 and not checks['no_errors']


def test_decision_both_files_and_actual_gate_not_argmax():
    cases = [
        {'id': 's1', 'dataset': 'scope', 'scope': 'now'},
        {'id': 's2', 'dataset': 'scope', 'scope': 'seconds'},
        {'id': 'r1', 'dataset': 'route', 'label': 'past'},
    ]
    output = {'scope_probs': {'now': .3, 'seconds': .4, 'minutes': .1, 'this_call': .1, 'past_calls': .1}, 'threshold': .81}
    records = [{'source': 'fixture', 'output': output}, {'source': 'fixture', 'output': output},
               {'source': 'fixture', 'output': {'label': 'past'}}]
    rows, metrics, checks = decision.score(cases, records)
    assert metrics['scope_accuracy'] == .5 and metrics['route_accuracy'] == 1
    assert metrics['now_held_by_mistake'] == 0 and metrics['past_coverage'] == 0
    assert not all(checks.values())
    with pytest.raises(ValueError, match='both'):
        decision.score(cases[-1:], records[-1:])


def test_decision_missing_cache_never_embeds(tmp_path, monkeypatch):
    from router import scope
    monkeypatch.setattr(scope, 'features', lambda *a: pytest.fail('must not embed on a cache miss'))
    backend = json.loads((run.ROOT / 'router/scope_model.json').read_text())['backend']
    with pytest.raises(ValueError, match='cache missing'):
        decision.cached_records(run.ROOT, backend, tmp_path)


def test_live_adapter_public_function_and_record_replay(tmp_path, monkeypatch):
    case = {'id': 'small', 'text': 'synthetic task', 'scene_caption': 'empty mat', 'parts_have': ['wire']}
    seen = []
    async def plan(text, caption, parts, *, model):
        seen.append((text, caption, parts, model))
        return {'outcome': 'no_trigger', 'plan': None, 'telemetry': {'calls': 0}}
    monkeypatch.setattr(run.importlib, 'import_module', lambda name: SimpleNamespace(plan=plan))
    records = run.collect_live('planner', [case], 'test-model')
    assert seen == [('synthetic task', 'empty mat', ['wire'], 'test-model')]
    assert records[0]['source'] == 'live'
    assert records[0]['telemetry']['calls'] == 0
    assert records[0]['telemetry']['latency_ms'] >= 0
    assert run.validate_records([case], records, 'test-model') == records


def test_false_drop_claim_with_plan_is_rejected():
    case = copy.deepcopy(run.load_cases('planner')[12])
    record = copy.deepcopy(run.read_jsonl(run.fixture_path('planner', 'fixture'))[0])
    record['output']['outcome'] = 'drop'
    assert not planner.score_case(case, record)['outcome_ok']


def test_fixture_failure_has_score_line(tmp_path):
    assert run.main(['decision', '--model', 'fixture', '--out', str(tmp_path)]) == 1
    report = json.loads((tmp_path / 'swap-decision-fixture.json').read_text())
    assert report['n'] == 200 and report['fixture'] and report['result'] == 'FAIL'
    assert len(report['worst_ids']) == 2
    assert len((tmp_path / 'swap.md').read_text().splitlines()) == 3


def test_cached_scope_runs_real_evaluator_without_cache_miss(tmp_path, monkeypatch):
    import numpy as np
    from router import features, scope
    from router.data import load
    from router.features import rows_key
    root = tmp_path / 'repo'
    data = root / 'router/data'
    data.mkdir(parents=True)
    cache = tmp_path / 'cache'
    cache.mkdir()
    scope_rows = [{'id': 's1', 'text': 'synthetic present question', 'scope': 'now'},
                  {'id': 's2', 'text': 'synthetic past question', 'scope': 'seconds'}]
    route_rows = [{'id': 'r1', 'text': 'synthetic present route', 'label': 'now'},
                  {'id': 'r2', 'text': 'synthetic past route', 'label': 'past'}]
    for name, rows in [('scope_heldout', scope_rows), ('heldout', route_rows)]:
        (data / (name + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in rows))
    for name, labels in [('scope_model', list(scope.SCOPES)), ('model', ['now', 'past', 'expert'])]:
        model = {'backend': 'synthetic', 'threshold': .8, 'labels': labels,
                 'layers': [{'w': [[-10], [10]] + [[0]] * (len(labels) - 2), 'b': [0] * len(labels)}]}
        (root / 'router' / (name + '.json')).write_text(json.dumps(model))
    for rows in (scope.load(data / 'scope_heldout.jsonl'), load(data / 'heldout.jsonl')):
        np.save(cache / f'synthetic-{rows_key(rows)}.npy', np.array([[-1.], [1.]]))
    monkeypatch.setattr(features, 'featurize', lambda *a: pytest.fail('cached evaluation must not embed'))
    original = scope.features
    records = decision.cached_records(root, 'synthetic', cache)
    assert scope.features is original
    rows, metrics, checks = decision.score(decision.cases(root), records)
    assert len(rows) == 4 and metrics['scope_accuracy'] == metrics['route_accuracy'] == 1
    assert metrics['past_coverage'] == 1 and not checks['latency']  # cached embeddings do not measure live latency

import copy
import json
import socket

import pytest

from eval.swap import planner, run


def test_offline_replay_is_deterministic_and_appends(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline scoring attempted a network call')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(run, 'collect_live', forbidden)
    args = ['planner', '--model', 'fixture', '--out', str(tmp_path)]
    assert run.main(args) == 0
    first = json.loads((tmp_path / 'swap-planner-fixture.json').read_text())
    assert run.main(args) == 0
    second = json.loads((tmp_path / 'swap-planner-fixture.json').read_text())
    assert first['metrics'] == second['metrics']
    assert first['rows'] == second['rows']
    assert first['fixture'] is True
    assert first['n'] == 20
    assert len((tmp_path / 'swap.md').read_text().splitlines()) == 4


def test_missing_duplicate_and_stale_records_fail_closed():
    cases = run.load_cases('planner')
    records = run.read_jsonl(run.fixture_path('planner', 'fixture'))
    for broken in (records[:-1], records + records[:1]):
        with pytest.raises(ValueError):
            run.validate_records(cases, broken, 'fixture')
    broken = copy.deepcopy(records)
    broken[0]['case_sha256'] = 'stale'
    with pytest.raises(ValueError, match='stale'):
        run.validate_records(cases, broken, 'fixture')


def test_metrics_detect_content_order_never_and_shape():
    case = run.load_cases('planner')[0]
    record = run.read_jsonl(run.fixture_path('planner', 'fixture'))[0]
    good = planner.score_case(case, record)
    assert good['plan_pass']
    bad = copy.deepcopy(record)
    bad['output']['plan']['steps'].reverse()
    assert not planner.score_case(case, bad)['order_ok']
    bad = copy.deepcopy(record)
    bad['output']['plan']['steps'][0]['say'] = 'touch the tip ' + 'word ' * 25
    scored = planner.score_case(case, bad)
    assert not scored['shape'] and scored['never_hits']
    bad['output']['plan'] = '{broken'
    scored = planner.score_case(case, bad)
    assert not scored['valid_json'] and not scored['plan_pass']


def test_missing_telemetry_is_unknown_not_zero():
    case = run.load_cases('planner')[0]
    record = run.read_jsonl(run.fixture_path('planner', 'fixture'))[0]
    record.pop('telemetry')
    row = planner.score_case(case, record)
    assert row['calls'] is None and row['cost_usd'] is None and row['latency_ms'] is None


def test_cli_rejects_unsafe_model_paths_and_record_without_live(tmp_path):
    for model in ('../escape', '/tmp/escape', 'a|b', '..'):
        with pytest.raises(ValueError):
            run.fixture_path('planner', model)
    with pytest.raises(SystemExit):
        run.main(['planner', '--model', 'fixture', '--record', '--out', str(tmp_path)])
    assert not list(tmp_path.iterdir())


def test_calls_and_cost_from_recorded_usage():
    case = run.load_cases('planner')[0]
    record = run.read_jsonl(run.fixture_path('planner', 'fixture'))[0]
    record['telemetry'] = {'calls': 1, 'latency_ms': 14000, 'usage': [
        {'input_tokens': 1000, 'output_tokens': 100, 'input_usd_per_million': 2,
         'output_usd_per_million': 10, 'price_source': 'test tariff'}]}
    row = planner.score_case(case, record)
    assert row['cost_usd'] == pytest.approx(.003)
    record['telemetry']['calls'] = 3
    row = planner.score_case(case, record)
    assert row['calls'] == 3 and row['cost_usd'] is None  # two calls have unrecorded usage


def test_live_record_is_exclusive_and_replays(tmp_path, monkeypatch):
    records = run.read_jsonl(run.fixture_path('planner', 'fixture'))
    for record in records:
        record.update(model='test-model', source='live')
    seen = []
    def collect(*args):
        seen.append(args)
        return records
    monkeypatch.setattr(run, 'collect_live', collect)
    path = tmp_path / 'record.jsonl'
    args = ['planner', '--model', 'test-model', '--fixture-file', str(path), '--out', str(tmp_path / 'out')]
    # Missing measured latency/cost/cache must fail real-run bars, but the recording is retained.
    assert run.main(args + ['--live', '--record']) == 1
    first = json.loads((tmp_path / 'out/swap-planner-test-model.json').read_text())
    assert run.main(args) == 1
    replay = json.loads((tmp_path / 'out/swap-planner-test-model.json').read_text())
    assert first['metrics'] == replay['metrics'] and first['rows'] == replay['rows']
    before = path.read_bytes()
    assert run.main(args + ['--live', '--record']) == 2
    assert path.read_bytes() == before and len(seen) == 1


def test_absent_part_permission_is_a_word_not_a_substring():
    case = copy.deepcopy(run.load_cases('planner')[0])
    case['parts_absent'] = ['flux pen']
    record = copy.deepcopy(run.read_jsonl(run.fixture_path('planner', 'fixture'))[0])
    record['output']['plan']['steps'][0]['say'] = 'Put the flux pen together with the wire.'
    assert planner.score_case(case, record)['absent_parts_hits'] == ['flux pen']
    record['output']['plan']['steps'][0]['say'] = 'Borrow a flux pen first.'
    assert planner.score_case(case, record)['absent_parts_hits'] == []

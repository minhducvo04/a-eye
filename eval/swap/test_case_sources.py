import copy
import json

import pytest

from eval.swap import planner, run


def test_independent_banks_preserve_source_and_schema():
    claude = run.load_cases('planner')
    grok = run.load_cases('planner', 'grok')
    talker = run.read_jsonl(run.ROOT / 'eval/cases/grok_talker.jsonl')
    assert len(claude) == 20 and all(c['source'] == 'claude' for c in claude)
    assert len(grok) == 22 and len({c['id'] for c in grok}) == 22
    assert sum(c['set'] == 'planner_rewrite' for c in grok) == 7
    assert sum(c['set'] == 'planner_new' for c in grok) == 15
    assert len(talker) == 30 and len({c['id'] for c in talker}) == 30
    assert all(c['source'] == 'grok' for c in grok + talker)
    assert all({'must', 'order', 'never', 'expect'} <= c.keys() for c in grok)
    assert all({'guide', 'must_do', 'must_never'} <= c.keys() for c in talker)
    # A rewritten rubric must not overwrite the original case with the same id.
    assert claude[0]['id'] == grok[0]['id'] and claude[0]['must'] != grok[0]['must']
    with pytest.raises(ValueError):
        run.load_cases('checker', 'grok')


def test_grok_requires_its_own_recordings(tmp_path):
    assert run.fixture_path('planner', 'fixture', 'grok') != run.fixture_path('planner', 'fixture')
    records = run.read_jsonl(run.fixture_path('planner', 'fixture'))
    with pytest.raises(ValueError):
        run.validate_records(run.load_cases('planner', 'grok'), records, 'fixture')
    assert run.main(['planner', '--model', 'fixture', '--case-source', 'grok', '--out', str(tmp_path)]) == 2
    assert not list(tmp_path.iterdir())


def test_source_report_and_artifacts_are_separate(tmp_path):
    case = run.load_cases('planner', 'grok')[0]
    # Synthetic plumbing probe only; never persisted as Grok/model evidence.
    record = copy.deepcopy(run.read_jsonl(run.fixture_path('planner', 'fixture'))[0])
    assert planner.score_case(case, record)['case_source'] == 'grok'
    report = dict(component='planner', model='probe', date='test', evidence='fixture',
                  n=1, metrics={}, worst_ids=[], result='FAIL', case_source='claude')
    original = run.write_report(report, tmp_path)
    report['case_source'] = 'grok'
    independent = run.write_report(report, tmp_path)
    assert original != independent
    assert json.loads(original.read_text())['case_source'] == 'claude'
    assert json.loads(independent.read_text())['case_source'] == 'grok'

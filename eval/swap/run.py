"""One command per component; offline scoring is the default and cannot open sockets."""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
import socket
import sys
from time import perf_counter
from unittest.mock import patch

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.swap import checker, decision, planner

ROOT = Path(__file__).resolve().parents[2]
VERSION = 1


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def model_name(model):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', model):
        raise ValueError('model must be a filename-safe id: letters, digits, dots, underscores or hyphens')
    return model


def fixture_path(component, model, case_source='claude'):
    directory = ROOT / 'eval/swap/fixtures' / component
    if case_source != 'claude':
        directory /= case_source
    return directory / (model_name(model) + '.jsonl')


def load_cases(component, case_source='claude'):
    if case_source not in ('claude', 'grok'):
        raise ValueError('unknown case source')
    if case_source == 'grok':
        if component != 'planner':
            raise ValueError('Grok supplies planner inputs and talker rubrics, not checker plans or decision cases')
        return (read_jsonl(ROOT / 'eval/cases/grok_planner_rewrite.jsonl')
                + read_jsonl(ROOT / 'eval/cases/grok_planner_new.jsonl'))
    if component == 'decision':
        return decision.cases(ROOT)
    if component == 'checker':
        return read_jsonl(ROOT / 'eval/cases/checker_bad_plans.jsonl') + read_jsonl(ROOT / 'eval/cases/checker_good_plans.jsonl')
    return read_jsonl(ROOT / 'eval/cases/planner_cases.jsonl')


def make_record(case, model, output, *, source='fixture', telemetry=None):
    record = {'v': VERSION, 'id': case['id'], 'model': model, 'source': source,
              'case_sha256': digest(case), 'output': output}
    if telemetry is not None:
        record['telemetry'] = telemetry
    return record


def validate_records(cases, records, model):
    ids = [case['id'] for case in cases]
    recorded = [r.get('id') for r in records]
    if not ids or len(set(ids)) != len(ids) or len(set(recorded)) != len(recorded) or set(ids) != set(recorded):
        raise ValueError('fixture must contain exactly one record for every case, with no extras or duplicates')
    by_id = {r['id']: r for r in records}
    ordered = []
    for case in cases:
        r = by_id[case['id']]
        if r.get('v') != VERSION or r.get('model') != model or r.get('source') not in ('fixture', 'live', 'cached_features'):
            raise ValueError('fixture version, model or source mismatch')
        if r.get('case_sha256') != digest(case):
            raise ValueError(f'stale fixture for {case["id"]}; case content changed')
        if not isinstance(r.get('output'), dict):
            raise ValueError(f'invalid output envelope for {case["id"]}')
        if not isinstance(r.get('telemetry', {}), dict):
            raise ValueError(f'invalid telemetry for {case["id"]}')
        json.dumps(r, allow_nan=False)
        ordered.append(r)
    return ordered


@contextmanager
def offline():
    def blocked(*args, **kwargs):
        raise RuntimeError('network is disabled during offline scoring')
    with patch.object(socket.socket, 'connect', blocked), patch.object(socket.socket, 'connect_ex', blocked), \
            patch.object(socket, 'create_connection', blocked), patch.object(socket, 'getaddrinfo', blocked):
        yield


def collect_live(component, cases, model):
    """Coordinator-only integration seam. Never loads credentials or a .env file.

    Planner public contract from the Board: plan(text, caption, parts). Model swapping additionally needs
    an explicit model keyword; fail before calling if the landed implementation does not expose it.
    The result envelope is documented in docs/results/evals.md; absent telemetry stays unknown.
    """
    if component == 'decision':
        return decision.collect_live(ROOT, cases, model)
    if component != 'planner':
        raise ValueError('checker uses production code and does not make model calls')
    try:
        module = importlib.import_module('server.planner')
    except ModuleNotFoundError as exc:
        if exc.name != 'server.planner':
            raise
        raise ValueError('server.planner has not landed; use --model fixture offline') from exc
    fn = module.plan
    if 'model' not in inspect.signature(fn).parameters:
        raise ValueError('planner.plan needs an explicit model keyword adapter before a model swap can be recorded')
    records = []

    async def call(case):
        value = fn(case['text'], case['scene_caption'], case['parts_have'], model=model)
        return await value if inspect.isawaitable(value) else value

    async def collect():
        for case in cases:
            start = perf_counter()
            value = await call(case)
            elapsed = (perf_counter() - start) * 1000
            if not isinstance(value, dict) or 'outcome' not in value:
                raise ValueError('planner result needs the documented outcome/plan/telemetry envelope; update adapter')
            telemetry = dict(value.get('telemetry', {}), latency_ms=elapsed)
            if value['outcome'] == 'plan':
                start = perf_counter()
                repeated = await call(case)
                telemetry['cache'] = {'latency_ms': (perf_counter() - start) * 1000,
                                      'calls': repeated.get('telemetry', {}).get('calls')}
            records.append(make_record(case, model, {k: v for k, v in value.items() if k != 'telemetry'},
                                       source='live', telemetry=telemetry))
    asyncio.run(collect())
    return records


def write_report(report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    source = report.get('case_source', 'claude')
    suffix = '' if source in ('claude', None) else f'-{source}'
    path = out / f'swap-{report["component"]}-{model_name(report["model"])}{suffix}.json'
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    table = out / 'swap.md'
    header = '| component | model | date (UTC) | evidence | n | metrics | worst ids | result |\n|---|---|---|---|---:|---|---|---|\n'
    with table.open('a') as stream:
        if table.stat().st_size == 0:
            stream.write(header)
        stream.write(f'| {report["component"]} | {report["model"]} | {report["date"]} | {report["evidence"]} | '
                     f'{report["n"]} | source={source}; {json.dumps(report["metrics"], sort_keys=True)} | '
                     f'{", ".join(report["worst_ids"])} | {report["result"]} |\n')
    return path


def source_hashes(component):
    paths = list((ROOT / 'eval/swap').glob('*.py'))
    if component == 'checker':
        paths += [ROOT / 'server/safety.py', ROOT / 'server/packs/electronics.py', ROOT / 'server/planner.py']
    elif component == 'decision':
        paths += [ROOT / 'router' / name for name in ('scope.py', 'route.py', 'eval.py', 'scope_model.json', 'model.json')]
    else:
        paths += [ROOT / 'server/planner.py']
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file() and not path.name.startswith('test_')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=('planner', 'checker', 'decision'))
    parser.add_argument('--model', required=True)
    parser.add_argument('--case-source', choices=('claude', 'grok'), default='claude',
                        help='case author; independent banks are scored separately (default: claude)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fixture', action='store_true', help='offline (default)')
    mode.add_argument('--live', action='store_true', help='coordinator only; may spend money')
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--fixture-file', type=Path)
    parser.add_argument('--cache', type=Path, help='decision only: existing .npy feature cache; no embedding or training')
    parser.add_argument('--out', type=Path, default=ROOT / 'eval/out')
    args = parser.parse_args(argv)
    if args.record and not args.live:
        parser.error('--record requires --live')
    if args.cache and (args.component != 'decision' or args.live or args.fixture_file):
        parser.error('--cache requires offline decision, without --fixture-file')
    if args.live and args.component == 'checker':
        parser.error('checker is code: use offline --model current')
    try:
        model_name(args.model)
        cases = load_cases(args.component, args.case_source)
        path = args.fixture_file or fixture_path(args.component, args.model, args.case_source)
        if args.live and args.record and path.exists():
            raise ValueError('recording already exists; use a new --fixture-file to preserve comparison evidence')
        if args.live:
            records = collect_live(args.component, cases, args.model)
        else:
            with offline():
                if args.component == 'checker':
                    if args.model != 'current':
                        raise ValueError('checker is production code: use --model current')
                    records = []
                elif args.cache:
                    records = decision.cached_records(ROOT, args.model, args.cache)
                else:
                    records = read_jsonl(path)
        if args.component != 'checker':
            records = validate_records(cases, records, args.model)
        with offline():
            rows, metrics, checks = {'planner': planner, 'checker': checker, 'decision': decision}[args.component].score(cases, records)
        if args.record:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as stream:
                for record in records:
                    stream.write(json.dumps(record, allow_nan=False) + '\n')
        synthetic = bool(records) and any(r['source'] == 'fixture' for r in records)
        evidence = 'fixture (hand-written; not model evidence)' if synthetic else ('production code on hand-written plans' if not records else records[0]['source'])
        worst = sorted(rows, key=lambda r: (r['ok'], r.get('must_recall') or 0, r['id']))[:2]
        report = {'v': VERSION, 'component': args.component, 'model': args.model,
                  'case_source': args.case_source if args.component != 'decision' else None,
                  'date': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'fixture': synthetic,
                  'evidence': evidence, 'n': len(rows), 'metrics': metrics, 'checks': checks,
                  'result': 'PASS' if all(checks.values()) else 'FAIL',
                  'worst_ids': [r['id'] for r in worst], 'rows': rows,
                  'case_sha256': digest(cases), 'records_sha256': digest(records),
                  'source_sha256': source_hashes(args.component)}
        output = write_report(report, args.out)
        print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2, allow_nan=False))
        print(f'Detail: {output}')
        return 0 if report['result'] == 'PASS' else 1
    except (ValueError, OSError, RuntimeError) as exc:
        # Input errors must never append a misleading scored PASS/FAIL row.
        print(f'Eval unavailable: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

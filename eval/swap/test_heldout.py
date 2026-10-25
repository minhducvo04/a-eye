"""No case text in server prompts/source or router training data (eight-word spans)."""
import ast
import json
from pathlib import Path
import re
import unicodedata

from eval.swap.run import ROOT, load_cases


def words(text):
    normalized = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    return re.findall(r"\w+(?:'\w+)*", normalized)


def spans(text):
    tokens = words(text)
    return {tuple(tokens[i:i + 8]) for i in range(len(tokens) - 7)}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def case_texts(case):
    # Score annotations are not model inputs. Checker plan bodies are their inputs.
    for field in ('text', 'scene_caption', 'context', 'plan'):
        yield from strings(case.get(field))


def leaks(cases, paths):
    index = {}
    for case in cases:
        for text in case_texts(case):
            for span in spans(text):
                index.setdefault(span, set()).add(case['id'])
    found = set()
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.name.startswith('.env'):
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        fragments = [text]
        if path.suffix == '.py':
            tree = ast.parse(text)
            fragments.extend(node.value for node in ast.walk(tree)
                             if isinstance(node, ast.Constant) and isinstance(node.value, str))
        elif path.suffix in ('.jsonl', '.json'):
            values = [json.loads(line) for line in text.splitlines() if line.strip() and not line.startswith('#')] if path.suffix == '.jsonl' else [json.loads(text)]
            fragments.extend(strings(values))
        hits = set().union(*(spans(fragment) for fragment in fragments)) & index.keys()
        for hit in hits:
            for case_id in index[hit]:
                found.add((case_id, str(path), ' '.join(hit)))
    return sorted(found)


def test_no_case_text_in_server_or_router_training():
    cases = load_cases('planner') + load_cases('checker') + load_cases('decision')
    server = [p for p in (ROOT / 'server').rglob('*') if '__pycache__' not in p.parts]
    training = list((ROOT / 'router/data').glob('*train*'))
    found = leaks(cases, server + training)
    assert not found, 'Held-out text leaked:\n' + '\n'.join(f'{c}: {Path(p).relative_to(ROOT)}: {s}' for c, p, s in found)


def test_guard_catches_partial_case_and_training_leaks(tmp_path):
    case = {'id': 'probe', 'text': 'prefix One two three four five six seven eight nine suffix'}
    prompt = tmp_path / 'prompt.py'
    prompt.write_text('PROMPT = "TWO three FOUR five\\nsix seven eight nine"\n')
    train = tmp_path / 'scope_train.jsonl'
    train.write_text(json.dumps({'text': 'one two three four five six seven eight'}) + '\n')
    assert {Path(hit[1]).name for hit in leaks([case], [prompt, train])} == {prompt.name, train.name}
    prompt.write_text('PROMPT = "one two three four five six seven"\n')
    assert not leaks([case], [prompt])


def test_contractions_are_one_word_and_eight_words_still_fail(tmp_path):
    case = {'id': 'probe', 'text': "Here's one two three four five six seven eight"}
    prompt = tmp_path / 'prompt.py'
    prompt.write_text('PROMPT = "Here’s one two three four five six"\n')
    assert len(words("Here's one two three four five six")) == 7
    assert not leaks([case], [prompt])
    prompt.write_text('PROMPT = "Here’s one two three four five six seven"\n')
    assert leaks([case], [prompt])

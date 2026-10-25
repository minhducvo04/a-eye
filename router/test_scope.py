"""Time-scope head (router/scope.py). The held-out check runs the real local EmbeddingGemma when its files exist."""
import statistics

import pytest

from router import scope
from router.embed_local import model_dir
from router.route import route, scope_of

REAL = (model_dir('gemma_local') / 'tokenizer.json').exists() and scope.OUT.exists()


def test_scope_of_gates_on_p_past():
    probs = {'now': .1, 'seconds': .2, 'minutes': .6, 'this_call': .05, 'past_calls': .05}
    assert scope_of(probs, .8)['scope'] == 'minutes'
    assert scope_of(dict(probs, now=.3, minutes=.4), .8)['scope'] == 'now'


def test_data_files_are_disjoint_and_cover_every_scope():
    train, held = scope.load(scope.TRAIN), scope.load(scope.HELDOUT)
    assert len(train) >= 250 and len(held) >= 100
    assert {r['scope'] for r in held} == set(scope.SCOPES)
    assert not {r['text'].lower() for r in train} & {r['text'].lower() for r in held}


@pytest.mark.skipif(not REAL, reason='local EmbeddingGemma files not fetched')
def test_heldout_accuracy_and_latency(tmp_path):
    report = scope.evaluate(type('A', (), dict(model=str(scope.OUT), cache=str(tmp_path), write=None))())
    assert report['acc'] >= .9
    assert report['now_held_by_mistake'] == 0 and report['gated_truly_past'] == 1.0
    route('warm up')
    times = [route(r['text'], ['user: hi', 'helper: hello'])['ms'] for r in scope.load(scope.HELDOUT)[:40]]
    assert statistics.median(times) < 60

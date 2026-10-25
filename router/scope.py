"""Time-scope head: from the user's question, which memory (if any) the answer needs.

    now         answer at once from the live camera and the conversation (includes chit-chat)
    seconds     the RAM log of the last few seconds ("what did I just do")
    minutes     the RAM log of the last few minutes ("two minutes ago")
    this_call   earlier in this call: Rewind (TwelveLabs) clips, else the RAM log
    past_calls  kept calls, sightings and task history from earlier calls ("last week")

It shares the router's embedding (router/route.py computes it once), so it adds one small dot product, not a
second embedding call. Data is handwritten: router/data/scope_train.jsonl (train and 5-fold CV tuning) and
router/data/scope_heldout.jsonl (written separately, never read by training).

Train: python -m router.scope train --cache DIR      Evaluate: python -m router.scope eval --cache DIR
Needs numpy (training only); inference is pure Python through route.classify.
"""
import argparse
import json
from pathlib import Path

SCOPES = ('now', 'seconds', 'minutes', 'this_call', 'past_calls')
HERE = Path(__file__).resolve().parent
TRAIN = HERE / 'data' / 'scope_train.jsonl'
HELDOUT = HERE / 'data' / 'scope_heldout.jsonl'
OUT = HERE / 'scope_model.json'
TARGET = 0.99  # out-of-fold precision of "past, not now" that sets the gate threshold on P(past) = 1 - P(now)


def load(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            row = json.loads(line)
            assert row['scope'] in SCOPES and row['text'].strip(), row
            rows.append(dict(row, context=[]))
    return rows


def fit(x, y, c, steps=400, lr=0.05):
    """Multinomial logistic regression with L2 (1 / c), full-batch Adam. Returns (w [k, d], b [k])."""
    import numpy as np
    n, d = x.shape
    k = len(SCOPES)
    w, b = np.zeros((k, d)), np.zeros(k)
    onehot = np.eye(k)[y]
    m = [np.zeros_like(w), np.zeros_like(b)]
    v = [np.zeros_like(w), np.zeros_like(b)]
    for t in range(1, steps + 1):
        z = x @ w.T + b
        z -= z.max(1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(1, keepdims=True)
        grads = [(p - onehot).T @ x / n + w / (c * n), (p - onehot).mean(0)]
        for i, (param, g) in enumerate(zip((w, b), grads)):
            m[i] = .9 * m[i] + .1 * g
            v[i] = .999 * v[i] + .001 * g * g
            param -= lr * (m[i] / (1 - .9 ** t)) / (np.sqrt(v[i] / (1 - .999 ** t)) + 1e-8)
    return w, b


def predict(w, b, x):
    import numpy as np
    z = x @ w.T + b
    z -= z.max(1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(1, keepdims=True)


def threshold(probs, y):
    """Lowest P(past) at which gated rows are truly past (any past scope) at least TARGET of the time.
    A false gate holds Live's own answer, so precision matters more than coverage; the regex covers the rest."""
    import numpy as np
    past = 1 - probs[:, 0]
    for t in np.arange(0.8, 0.99, 0.01):  # floor 0.8: hold only when clearly past
        keep = past >= t
        if keep.sum() and (y[keep] != 0).mean() >= TARGET:
            return round(float(t), 2)
    return 0.99


def features(rows, backend, cache):
    from router.features import cached
    return cached(rows, backend, cache)


def train(args):
    import numpy as np
    rows = load(TRAIN)
    x = features(rows, args.backend, args.cache).astype(np.float64)
    y = np.array([SCOPES.index(r['scope']) for r in rows])
    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(len(rows)), 5)
    best = None
    for c in (1, 3, 10, 30, 100):
        probs = np.zeros((len(rows), len(SCOPES)))
        for fold in folds:
            mask = np.ones(len(rows), bool)
            mask[fold] = False
            probs[fold] = predict(*fit(x[mask], y[mask], c), x[fold])
        acc = float((probs.argmax(1) == y).mean())
        print(f'c={c}: cv acc {acc:.3f}')
        if best is None or acc > best[0]:
            best = (acc, c, probs)
    acc, c, probs = best
    thresh = threshold(probs, y)
    w, b = fit(x, y, c)
    model = {'backend': args.backend, 'head': 'lr', 'labels': list(SCOPES), 'threshold': thresh,
             'layers': [{'w': w.round(6).tolist(), 'b': b.round(6).tolist()}],
             'cv': {'c': c, 'acc': round(acc, 4), 'target_kept_acc': TARGET, 'rows': len(rows)}}
    Path(args.out).write_text(json.dumps(model) + '\n')
    print('chosen', model['cv'], 'threshold', thresh, 'wrote', args.out)


def evaluate(args):
    """Held-out accuracy through the same pure-Python head the server runs."""
    from router.route import classify, load_model
    model = load_model(str(args.model))
    rows = load(HELDOUT)
    x = features(rows, model['backend'], args.cache)
    matrix = {a: {b: 0 for b in SCOPES} for a in SCOPES}
    gated = gated_right = scope_right = 0
    for row, vec in zip(rows, x.tolist()):
        probs = classify(vec, model)
        label = max(probs, key=probs.get)
        matrix[row['scope']][label] += 1
        if 1 - probs['now'] >= model['threshold']:
            gated += 1
            gated_right += row['scope'] != 'now'
            scope_right += max((s for s in SCOPES if s != 'now'), key=probs.get) == row['scope']
    n = len(rows)
    right = sum(matrix[s][s] for s in SCOPES)
    past = [r for r in rows if r['scope'] != 'now']
    report = {'n': n, 'acc': round(right / n, 4),
              'recall': {s: round(matrix[s][s] / max(1, sum(matrix[s].values())), 3) for s in SCOPES},
              'now_held_by_mistake': sum(v for k, v in matrix['now'].items() if k != 'now'),
              'gated': gated, 'gated_truly_past': round(gated_right / max(1, gated), 4),
              'gated_scope_acc': round(scope_right / max(1, gated), 4),
              'past_coverage': round(gated / max(1, len(past)), 4), 'threshold': model['threshold'],
              'matrix': matrix}
    print(json.dumps(report, indent=1))
    if args.write:
        Path(args.write).write_text(json.dumps(report, indent=1) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cmd', choices=('train', 'eval'))
    parser.add_argument('--backend', default='gemma_local')
    parser.add_argument('--cache', required=True)
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--model', default=str(OUT))
    parser.add_argument('--write')
    args = parser.parse_args()
    train(args) if args.cmd == 'train' else evaluate(args)

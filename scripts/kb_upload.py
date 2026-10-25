"""Upload the parts shelf cards (data/kb/cards.json) to the team SpacetimeDB `kb_card` table.

Cards are public knowledge. Each one passes the code allowlist (server.parts_shelf.check_card) and is sent as
the reducer `upsert_kb_card` with exactly the FIELDS, in that order; any other field stops the upload before
anything is sent. Uses the SpacetimeStore HTTP pattern (HTTPS only, bearer token from the environment, safe
errors). Never prints the token, URLs or response bodies.

    make kb-upload            # .env loaded by the Makefile
    python scripts/kb_upload.py --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.parts_shelf import DIR, FIELDS, check_card  # noqa: E402

REDUCER = 'upsert_kb_card'


def rows(path):
    cards = json.loads(Path(path).read_text())
    return [[check_card(card)[key] for key in FIELDS] for card in cards]


def upload(path, store=None):
    args = rows(path)  # validate every card before the first request
    if store is None:
        from server.memory_storage import SpacetimeStore
        store = SpacetimeStore('kb-upload')
    for row in args:
        store._request('/call/' + REDUCER, args=row)
    return len(args)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--cards', default=str(DIR / 'cards.json'))
    parser.add_argument('--dry-run', action='store_true', help='validate only; send nothing')
    opts = parser.parse_args()
    if opts.dry_run:
        print(f'{len(rows(opts.cards))} cards valid; fields: {", ".join(FIELDS)}')
        return
    print(f'{upload(opts.cards)} cards sent to {REDUCER}')


if __name__ == '__main__':
    main()

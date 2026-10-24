"""Validate tagged API examples without printing message payloads."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts import validate


def main():
    text = (ROOT / 'docs/api.md').read_text()
    pattern = r'^<!-- contract: ([A-Za-z0-9_]+) -->\n```json\n(.*?)\n```'
    examples = list(re.finditer(pattern, text, re.M | re.S))
    tags = re.findall(r'^<!-- contract:', text, re.M)
    if not examples or len(tags) != len(examples):
        raise SystemExit('FAIL: missing examples or malformed contract tags')
    for match in examples:
        name, body = match.groups()
        try:
            validate(name, json.loads(body))
        except Exception as exc:
            line = text[:match.start()].count('\n') + 1
            raise SystemExit(f'FAIL: {name} at line {line} ({type(exc).__name__})') from None
    print(f'PASS ({len(examples)} examples)')


if __name__ == '__main__':
    main()

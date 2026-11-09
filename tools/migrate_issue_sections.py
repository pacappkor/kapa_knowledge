# SPDX-License-Identifier: GPL-3.0-only
"""Remove unsupported generated designation from manual issue sections."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, safe_write_text, run_cli
from fetch_material import BEGIN, END


def migrate(root=ROOT):
    updates = {}
    for path in (root / 'issues').rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        if BEGIN not in text and END not in text:
            continue
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) >= text.index(END):
            raise ValueError('issue marker boundary error')
        updates[path] = text.replace(BEGIN + '\n', '').replace(END + '\n', '').replace('## 원문 메타데이터와 연결 [machine]', '## 근거 메타데이터와 연결 [analysis]')
    for path, text in updates.items():
        safe_write_text(path, text)
    return len(updates)


def main():
    print('manual issue sections:', migrate())
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))

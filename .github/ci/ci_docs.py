#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only snapshot check, also required when the tool suite is path-skipped."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from common import run_cli
from doc_snapshot import document_snapshot, load_snapshot, snapshot_difference


def main(root=ROOT):
    difference = snapshot_difference(document_snapshot(root), load_snapshot(root))
    if difference:
        print(difference)
        return 1
    print('Documentation snapshot matches.')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))

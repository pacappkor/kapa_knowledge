# SPDX-License-Identifier: GPL-3.0-only
"""Explicitly regenerate the reviewed whole-file documentation hashes."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, check_output_path, run_cli, safe_write_text
from doc_snapshot import SNAPSHOT, document_snapshot


def main():
    target = ROOT / SNAPSHOT
    check_output_path(target)
    records = document_snapshot(ROOT)
    safe_write_text(target, json.dumps(records, ensure_ascii=True, indent=2) + '\n')
    print('documentation snapshot updated:', len(records), 'files; review the snapshot diff in this PR')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))

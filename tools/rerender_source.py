# SPDX-License-Identifier: GPL-3.0-only
"""Offline formatting migration of source sections from verified saved payloads."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_material import rerender_saved
from common import run_cli


def main():
    if len(sys.argv) < 2:
        print('ERROR: 재생성할 저장소 상대 문서 경로 필요')
        return 1
    changed = 0
    for document in sys.argv[1:]:
        try:
            changed += int(rerender_saved(document))
        except Exception:
            # Source contents and credential-bearing errors are never printed.
            print('ERROR: 저장 원문 재생성 실패 (경로·메타데이터·해시·경계 확인 필요)')
            return 1
    print(f'documents: {len(sys.argv) - 1}  changed: {changed}')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))

# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_material import run_fetch
from common import run_cli


def main():
    # 기존 법제처 호출을 유지하며 중앙부처 웹 후보는 별도 종류로 지정한다.
    return run_fetch(sys.argv[2] if len(sys.argv) > 2 else 'expc', sys.argv[1])


if __name__ == '__main__':
    sys.exit(run_cli(main))

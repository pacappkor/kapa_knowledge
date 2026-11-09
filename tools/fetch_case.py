# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_material import run_fetch
from common import run_cli


def main():
    return run_fetch('prec', sys.argv[1])


if __name__ == '__main__':
    sys.exit(run_cli(main))

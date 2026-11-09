#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check test package layout without importing any repository modules."""
from pathlib import Path
import re
import sys

# Match unittest.loader.VALID_MODULE_NAME and its .match(filename) check.
VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)


def main():
    root = Path(__file__).resolve().parents[2]
    tools = root / 'tools'
    tests = sorted(path for path in tools.rglob('test_*.py') if path.is_file())
    if not tests:
        print('Test layout failed: no test files (tools/**/test_*.py)', file=sys.stderr)
        return 1
    missing = set()
    invalid = set()
    for test in tests:
        if not VALID_MODULE_NAME.match(test.name):
            invalid.add(test.relative_to(root).as_posix())
        directory = test.parent
        while directory != root:
            # Both 3.12 and 3.14 import package directory names as-is.
            initializer = directory / '__init__.py'
            if not initializer.is_file():
                missing.add(initializer.relative_to(root).as_posix())
            directory = directory.parent
    for path in sorted(missing):
        print(f'Test layout failed: missing package initializer: {path}', file=sys.stderr)
    for path in sorted(invalid):
        print(f'Test layout failed: invalid Python identifier: {path}', file=sys.stderr)
    return int(bool(missing or invalid))


if __name__ == '__main__':
    sys.exit(main())

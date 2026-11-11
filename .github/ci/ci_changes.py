#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""CI-only orchestration; repository maintenance tools never import this module."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GROUPS = ('validate', 'tests')


def classify(paths, all_checks=False):
    flags = dict.fromkeys(GROUPS, all_checks)
    for path in paths:
        if path.startswith(('.github/', 'tools/')) or path == 'deps.lock' or path.startswith('vendor/'):
            return dict.fromkeys(GROUPS, True)
        # Any changed path may be a Markdown link target. Data and docs do not
        # require rerunning all tool regression fixtures.
        flags['validate'] = True
        if not (path.endswith('.md') or path.startswith((
                'sources/', 'cases/', 'interpretations/', 'issues/', 'relations/',
                'reviews/', 'runs/', 'rules/', 'docs/', 'templates/', '00-knowledge-start/'))
                or path in {'LICENSE', 'NOTICE'}):
            return dict.fromkeys(GROUPS, True)
    return flags


def main():
    event = os.environ.get('CI_EVENT', '')
    resolved = dict(line.split('=', 1) for line in subprocess.check_output(
        ['bash', str(Path(__file__).with_name('ci_base.sh'))], cwd=ROOT,
        text=True, stderr=subprocess.PIPE).splitlines())
    start = resolved['base']
    all_checks = resolved['all'] == 'true'
    paths = []
    if not all_checks:
        separator = '...' if event == 'pull_request' else '..'
        try:
            result = subprocess.run(
                ['git', 'diff', '--no-renames', '--name-only', '-z', f'{start}{separator}HEAD'],
                cwd=ROOT, check=True, capture_output=True)
            paths = result.stdout.decode('utf-8').rstrip('\0').split('\0') if result.stdout else []
        except (OSError, subprocess.CalledProcessError, UnicodeError):
            all_checks = True
    flags = classify(paths, all_checks)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f"whitespace_base={resolved['whitespace_base']}\n")
        for group, enabled in flags.items():
            output.write(f'{group}={str(enabled).lower()}\n')
    summary = '## Changed-path recommendations (informational only)\n\n' + '\n'.join(
        f'- {group}: {"recommended" if enabled else "not required by paths"}' for group, enabled in flags.items())
    summary += ('\n- Offline validation, tests, environment-only scanner, tracked links, '
                'clean tree, whitespace: always run.\n'
                '- Actual-value credential scan: separate event-gated job; forks skip it.\n')
    if all_checks:
        summary += '- All checks: manual run, unusable base, rewritten history, or diff failure.\n'
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
        output.write(summary)
    print(summary)


if __name__ == '__main__':
    main()

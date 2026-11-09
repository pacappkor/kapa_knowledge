# SPDX-License-Identifier: GPL-3.0-only
"""The only production child: captured plumbing with no credential inheritance."""
import os
import subprocess

READ_ONLY_GIT = {
    'ls-files': {'-s', '-z', '--cached', '--others', '--exclude-standard'},
    'cat-file': {'-e', '-p', '-t', '-s', '--batch'},
    'rev-parse': {'--verify', '--show-toplevel', '--show-prefix', '--git-dir'},
    'ls-tree': {'-r', '-z', '--', '--name-only', '--full-tree'},
}


def child_environment():
    """Do not pass credentials, fallback paths or Git config/repository overrides.

    Fixed safety settings are re-added after scrubbing: partial-clone lazy
    fetches (which could run a configured upload-pack helper) and terminal
    credential prompts are disabled, so missing objects fail closed.
    """
    env = {name: value for name, value in os.environ.items()
           if name.upper() not in {'LAW_OC', 'LAW_OC_FILE'}
           and not name.upper().startswith('GIT_')}
    env['GIT_NO_LAZY_FETCH'] = '1'
    env['GIT_TERMINAL_PROMPT'] = '0'
    # An empty protocol allowlist overrides protocol.allow and every
    # protocol.<name>.allow rule and names no remote helper, so every transport
    # (including <helper>::<address> remote helpers) is refused.
    env['GIT_ALLOW_PROTOCOL'] = ''
    return env


def validate_arguments(args):
    if (not isinstance(args, (list, tuple)) or not args
            or any(not isinstance(item, str) for item in args)
            or args[0] not in READ_ONLY_GIT):
        raise ValueError('Git command is not allowlisted plumbing.')
    command = args[0]
    if command == 'cat-file':
        if args[1:] == ['--batch'] or args[1:] == ('--batch',):
            return
        if len(args) != 3 or args[1] not in {'-e', '-t', '-s', '-p'}:
            raise ValueError('Git cat-file mode is not allowlisted.')
    if any(item.startswith('-') and item not in READ_ONLY_GIT[command] for item in args[1:]):
        raise ValueError('Git option is not allowlisted.')


def run_git(root, args, *, text=False):
    """Fixed settings override repository fsmonitor/untracked-cache configuration.

    protocol.allow=never denies every transport, so a partial clone's missing
    object fails closed even on Git releases that ignore GIT_NO_LAZY_FETCH.
    """
    validate_arguments(args)
    return subprocess.run(['git', '-c', 'core.fsmonitor=false',
                           '-c', 'core.untrackedCache=false', '-c', 'protocol.allow=never',
                           '--no-replace-objects',
                           '-C', str(root), *args],
                          check=True, capture_output=True, text=text,
                          env=child_environment())

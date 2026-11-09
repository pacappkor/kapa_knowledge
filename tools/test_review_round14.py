# SPDX-License-Identifier: GPL-3.0-only
"""Offline tests for reviewed documentation, child policy and Git index modes."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from doc_snapshot import document_snapshot
from test_review_round10 import fenced_blocks, workflow_findings
from test_write_safety import GIT_PREFIX, direct_writes, production_write_findings, read_only_git_call


class RoundFourteenRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def inventory(self, text):
        data = text.encode('utf-8')
        return (hashlib.sha256(data).hexdigest(), len(data))

    def test_4509500778_non_python_commands_change_exact_snapshot(self):
        baseline = '```powershell\n$docs = Get-ChildItem cases\n```\n'
        snapshot = self.inventory(baseline)
        self.assertEqual(self.inventory(baseline), snapshot)
        for command in ('echo "$LAW_OC"', 'cp file ../../outside', 'unknown-command arbitrary-data'):
            with self.subTest(command=command):
                changed = baseline.replace('```\n', command + '\n```\n')
                self.assertNotEqual(self.inventory(changed), snapshot)
                self.assertEqual(self.inventory(changed)[1], len(changed.encode()))

    def test_4509500782_continuations_preserve_every_source_byte(self):
        baseline = '```sh\npython -I -B tools/validate.py\n```\n'
        for continuation in ('\\', '`'):
            changed = baseline.replace('validate.py\n', 'validate.py ' + continuation + '\n--help\n')
            with self.subTest(continuation=continuation):
                self.assertNotEqual(self.inventory(changed), self.inventory(baseline))
                self.assertEqual(self.inventory(changed)[1], len(changed.encode()))

    def test_4509500784_nested_and_variable_fences_are_inventoried(self):
        command = 'python -I -B tools/export_records.py\n'
        for prefix in ('', '    ', '> ', '- ', '1. ', '> - > 2. '):
            for marker in ('```', '~~~~', '```````'):
                with self.subTest(prefix=prefix, marker=marker):
                    block = prefix + marker + 'sh\n' + prefix + command + prefix + marker + '\n'
                    self.assertEqual(self.inventory(block)[1], len(block.encode()))
                    self.assertEqual(list(fenced_blocks(block)), [command])
                    self.assertTrue(workflow_findings(block, {'export_records.py'}))
                    self.assertNotEqual(self.inventory(block), [])
        unclosed = '> ```sh\n> echo "$LAW_OC"\n'
        self.assertEqual(self.inventory(unclosed)[1], len(unclosed.encode()))

    def test_snapshot_detects_indented_and_outside_launcher_lines(self):
        for text, kind in [('    arbitrary-command data\n', 'indented'),
                           ('\tarbitrary-command data\n', 'indented'),
                           ('>     arbitrary-command data\n', 'indented'),
                           ('python -I -B tools/validate.py\n', 'launcher'),
                           ('Run `git status` here.\n', 'launcher'),
                           ('echo "$LAW_OC"\n', 'launcher')]:
            with self.subTest(text=text):
                self.assertEqual(self.inventory(text)[1], len(text.encode()))

    def test_snapshot_tracks_file_order_exact_text_additions_and_removals(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)
        (self.root / 'README.md').write_text('```sh\nfirst\n```\n', encoding='utf-8')
        (self.root / 'AGENTS.md').write_text('```sh\nsecond\n```\n', encoding='utf-8')
        docs = self.root / 'docs'
        docs.mkdir()
        path = docs / 'nested.md'
        path.write_text('```sh\nthird\n```\n', encoding='utf-8')
        baseline = document_snapshot(self.root)
        self.assertEqual([row['file'] for row in baseline], ['AGENTS.md', 'README.md', 'docs/nested.md'])
        self.assertEqual(json.loads(json.dumps(baseline)), baseline)
        for changed in ('```sh\nthird \n```\n', '```sh\nfourth\n```\n', '',
                        '```sh\nthird\n```\n```sh\nnew\n```\n'):
            path.write_text(changed, encoding='utf-8')
            self.assertNotEqual(document_snapshot(self.root), baseline)
        path.write_text('```sh\nthird\n```\n', encoding='utf-8')
        self.assertEqual(document_snapshot(self.root), baseline)
        self.assertNotEqual(list(reversed(baseline)), baseline)
        path.rename(docs / 'renamed.md')
        self.assertNotEqual(document_snapshot(self.root), baseline)

    def test_4509500790_all_alternative_child_apis_fail_closed(self):
        # These are inert AST fixtures, never executed shell/process calls.
        calls = ['os.system', 'os.popen', 'os.execv', 'os.execve', 'os.execl', 'os.execlp',
                 'os.execvp', 'os.execvpe', 'os.spawnl', 'os.spawnve', 'os.posix_spawn',
                 'os.posix_spawnp', 'asyncio.create_subprocess_exec',
                 'asyncio.create_subprocess_shell', 'pty.spawn',
                 'subprocess.getoutput', 'subprocess.getstatusoutput']
        for call in calls:
            module, name = call.split('.')
            for source in (f'import {module}\n{call}("env")',
                           f'import {module} as child\nchild.{name}("env")',
                           f'from {module} import {name} as child\nchild("env")'):
                with self.subTest(call=call, source=source):
                    self.assertTrue(direct_writes(source, 'production.py'))
                    self.assertTrue(direct_writes(source, 'test_fixture.py', check_files=False))

    def test_4509500793_production_commands_require_literal_read_only_git(self):
        safe = ["['git', 'ls-files', '-z']", "['git', '-C', str(root), 'ls-files', '-s', '-z']",
                "['git', '--no-replace-objects', '-C', str(root), 'cat-file', '-p', revision + ':' + path]",
                "['git', 'cat-file', '-p', oid]", "['git', 'rev-parse', '--verify', revision]",
                "['git', 'ls-tree', '-r', '--name-only', revision, '--', 'reviews/2026/']",
                "['git', 'cat-file', '-e', oid]"]
        unsafe = ["['cp', 'payload', '../../outside']", "[executable, 'status']", "command",
                  "'git status'", "['git']", "['git', 'checkout', 'other']", "['git', *args]",
                  "['git', command]", "['git', '-c', 'alias.read=!env', 'show']",
                  "['git', '--exec-path=outside', 'show']", "['git', 'config', 'key', 'value']",
                  "['git', 'config', '--get', 'key', 'extra']", "['git', 'show', '--output=outside']",
                  "['git', 'diff', '--output', 'outside']", "['git', 'log', '--ext-diff']",
                  "['git', 'cat-file', '--filters', oid]", "['git', 'show', '--output=' + path]",
                  "['git', 'show', f'--output={path}']", "['git', 'status']",
                  "['git', '--no-optional-locks', 'status', '--short']"]
        for argv in safe + unsafe:
            with self.subTest(argv=argv):
                hardened = argv.replace("['git',", repr(GIT_PREFIX)[:-1] + ',', 1)
                source = 'import subprocess\nsubprocess.run(' + hardened + ', capture_output=True, env=child_environment())'
                call = ast.parse(source).body[-1].value
                self.assertEqual(read_only_git_call(call), argv in safe)
                self.assertTrue(direct_writes(source, 'production.py'))
                self.assertEqual(direct_writes(source, 'test_fixture.py', check_files=False), [])
        for options in (', shell=True', ', shell=dynamic', ', **options', ', executable="cp"',
                        ', preexec_fn=writer', ', env=dynamic'):
            source = 'import subprocess\nsubprocess.run(["git", "status"], capture_output=True' + options + ')'
            self.assertTrue(direct_writes(source, 'production.py'))
        self.assertTrue(direct_writes('import subprocess\nsubprocess.run(["git", "status"])', 'production.py'))

    def test_child_policy_applies_to_nested_production_modules(self):
        helper = self.root / 'nested'
        helper.mkdir()
        (self.root / '__init__.py').write_text('', encoding='utf-8')
        (helper / '__init__.py').write_text('', encoding='utf-8')
        for name, source in [('copy.py', 'import subprocess\nsubprocess.run(["cp", "a", "b"], capture_output=True)'),
                             ('execute.py', 'from os import system as child\nchild("env")'),
                             ('test_fixture.py', 'import subprocess\nsubprocess.run(["git", "init"], capture_output=True)')]:
            (helper / name).write_text(source, encoding='utf-8')
        self.assertEqual({row[0] for row in production_write_findings(self.root)}, {'nested/copy.py', 'nested/execute.py'})

    def test_4509500799_gitlink_rejected_by_preflight_and_normal_validate(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)
        # update-index accepts a synthetic commit OID without creating a submodule
        # or requiring symlink privileges, network, hooks or a real credential.
        subprocess.run(['git', '-C', str(self.root), 'update-index', '--add', '--cacheinfo',
                        '160000,' + '1' * 40 + ',sources'], check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, 'tracked gitlinks are not allowed'):
            common.check_tracked_links(self.root)
        script = common.CODE_ROOT / 'tools/validate.py'
        env = dict(os.environ, KK_ROOT=str(self.root), LAW_OC='', LAW_OC_FILE=str(self.root / 'never-read.txt'))
        for args in (['--check-links'], []):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-I', '-B', str(script), *args],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('tracked gitlinks are not allowed', result.stdout)
                self.assertNotIn('dependency', result.stdout)
                self.assertEqual(result.stderr, '')

    def test_tracked_mode_diagnostics_do_not_include_index_paths(self):
        for mode, message in [(b'120000', 'tracked symlinks'), (b'160000', 'tracked gitlinks')]:
            result = subprocess.CompletedProcess([], 0, stdout=mode + b' ' + b'1' * 40 + b' 0\tprivate-name\0')
            with patch.object(common.subprocess, 'run', return_value=result):
                with self.assertRaises(ValueError) as raised:
                    common.check_tracked_links(self.root)
            self.assertIn(message, str(raised.exception))
            self.assertNotIn('private-name', str(raised.exception))


if __name__ == '__main__':
    unittest.main()

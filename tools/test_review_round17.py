# SPDX-License-Identifier: GPL-3.0-only
"""Git hook suppression, credential-free child environments and helper-only calls."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import git_read
from test_write_safety import GIT_PREFIX, direct_writes, read_only_git_call

KEY = 'FsmonitorSynthetic' + 'Credential9/+?Value'


class RoundSeventeenRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_4510066563_child_environment_omits_credentials_and_git_overrides(self):
        parent = {('LAW_O' + 'C' + ''): KEY, ('LAW_O' + 'C' + '_FILE'): 'synthetic-fallback',
                  ('law_' + 'oc' + ''): KEY, 'Law_Oc_File': 'synthetic-fallback',
                  'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
                  'GIT_CONFIG_VALUE_0': 'poison', 'GIT_CONFIG_GLOBAL': 'poison',
                  'GIT_CONFIG_SYSTEM': 'poison', 'GIT_DIR': 'poison',
                  'GIT_WORK_TREE': 'poison', 'GIT_INDEX_FILE': 'poison',
                  'git_config_parameters': 'poison', 'PATH': 'synthetic-path',
                  'HOME': 'synthetic-home', 'KEEP_ME': 'ordinary'}
        result = subprocess.CompletedProcess([], 0, stdout=b'', stderr=b'')
        with patch.object(git_read.os, 'environ', parent), patch.object(git_read.subprocess, 'run', return_value=result) as child:
            git_read.run_git(self.root, ['ls-files', '-s', '-z'])
            argv = child.call_args.args[0]
            env = child.call_args.kwargs['env']
            self.assertEqual(argv[:5], GIT_PREFIX)
            self.assertIsNot(env, parent)
            self.assertEqual(set(env), {'PATH', 'HOME', 'KEEP_ME', 'GIT_NO_LAZY_FETCH',
                                        'GIT_TERMINAL_PROMPT', 'GIT_ALLOW_PROTOCOL'})
            self.assertEqual(env['GIT_ALLOW_PROTOCOL'], '')
            self.assertEqual(env['GIT_NO_LAZY_FETCH'], '1')
            self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
            self.assertTrue(child.call_args.kwargs['capture_output'])
            self.assertTrue(child.call_args.kwargs['check'])
            self.assertIn('LAW_OC', parent)  # Parent scanner still has its credential.

    def test_4510183676_lazy_fetch_stays_disabled_even_if_parent_enables_it(self):
        parent = {'GIT_NO_LAZY_FETCH': '0', 'git_no_lazy_fetch': '0',
                  'GIT_TERMINAL_PROMPT': '1', 'GIT_ALLOW_PROTOCOL': 'file:ext',
                  'PATH': 'synthetic-path'}
        with patch.object(git_read.os, 'environ', parent):
            env = git_read.child_environment()
        self.assertEqual(env, {'PATH': 'synthetic-path', 'GIT_NO_LAZY_FETCH': '1',
                               'GIT_TERMINAL_PROMPT': '0', 'GIT_ALLOW_PROTOCOL': ''})

    def test_runtime_helper_rejects_unknown_commands_and_options_before_spawn(self):
        for args in (['status'], ['show', 'HEAD'], ['cat-file', '--textconv', 'HEAD:a'],
                     ['cat-file', '--filters', 'HEAD:a'], ['-c', 'core.fsmonitor=hook', 'ls-files'],
                     ['ls-files', '--output=outside'], [], 'ls-files', ['ls-files', object()]):
            with self.subTest(kind=type(args).__name__), patch.object(git_read.subprocess, 'run') as child:
                with self.assertRaises(ValueError):
                    git_read.run_git(self.root, args)
                child.assert_not_called()

    def test_raw_child_checker_requires_fixed_prefix_and_sanitized_environment(self):
        argv = GIT_PREFIX + ['ls-files', '-s', '-z']
        def allowed(words, env='child_environment()'):
            call = ast.parse('subprocess.run(' + repr(words) + ', capture_output=True, env=' + env + ')').body[0].value
            return read_only_git_call(call)
        self.assertTrue(allowed(argv))
        self.assertFalse(allowed(['git', 'ls-files', '-s']))
        self.assertFalse(allowed(['git', '-c', 'core.fsmonitor=true'] + argv[3:]))
        self.assertFalse(allowed(argv, 'os.environ.copy()'))
        self.assertFalse(allowed(argv, '{}'))
        call = ast.parse('subprocess.run(' + repr(argv) + ', capture_output=True)').body[0].value
        self.assertFalse(read_only_git_call(call))

    def test_production_must_use_helper_even_for_hardened_literal_git(self):
        source = 'import subprocess\nsubprocess.run(' + repr(GIT_PREFIX + ['ls-files']) + ', capture_output=True, env=child_environment())'
        self.assertTrue(direct_writes(source, 'production.py'))
        safe = 'from git_read import run_git\nrun_git(root, ["ls-files", "-s", "-z"])'
        self.assertEqual(direct_writes(safe, 'production.py'), [])
        for suffix in (', env=custom', ', executable="outside"', ', **options'):
            source = 'from git_read import run_git\nrun_git(root, ["ls-files"]' + suffix + ')'
            self.assertTrue(direct_writes(source, 'production.py'))
        self.assertTrue(direct_writes('from git_read import run_git\nrun_git(root, command)', 'production.py'))

    def test_helper_sink_exemption_is_exact_and_not_inherited_by_other_modules(self):
        source = (common.CODE_ROOT / 'tools/git_read.py').read_text(encoding='utf-8')
        self.assertEqual(direct_writes(source, 'git_read.py'), [])
        self.assertTrue(direct_writes(source, 'nested/git_read.py'))
        for changed in (source.replace('env=child_environment()', 'env=os.environ.copy()'),
                        source.replace('core.fsmonitor=false', 'core.fsmonitor=true'),
                        source.replace('capture_output=True', 'capture_output=False')):
            self.assertTrue(direct_writes(changed, 'git_read.py'))

    def test_configured_fsmonitor_hook_is_not_run_by_production_reads(self):
        clean = git_read.child_environment()
        def fixture_git(*args, env=clean):
            return subprocess.run(['git', '-C', str(self.root), *args],
                                  env=env, check=True, capture_output=True)
        fixture_git('init', '-q')
        (self.root / 'README.md').write_bytes(b'fixture\n')
        fixture_git('add', 'README.md')
        marker = self.root / '.git/fsmonitor-ran'
        hook = self.root / '.git/fsmonitor-fixture.sh'
        # No credential value is ever emitted or saved, even by the poison hook.
        marker_arg = "'" + marker.as_posix().replace("'", "'\\''") + "'"
        hook.write_text('#!/bin/sh\nprintf "hook-ran\\n" >> ' + marker_arg
                        + '\nprintf "fixture-token\\000"\n', encoding='utf-8')
        try:
            hook.chmod(0o755)
            fixture_git('config', 'core.fsmonitor', hook.as_posix())
            fixture_git('config', 'core.fsmonitorHookVersion', '2')
            baseline_env = dict(clean, **{'LAW_O' + 'C': KEY}, LAW_OC_FILE='synthetic-fallback')
            fixture_git('update-index', '--fsmonitor', env=baseline_env)
            if marker.exists():
                marker.unlink()
            fixture_git('ls-files', '-s', '-z', env=baseline_env)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest('platform cannot execute the synthetic fsmonitor hook; environment unit tests remain active')
        if not marker.exists():
            self.skipTest('Git does not invoke the synthetic fsmonitor hook on this platform; environment unit tests remain active')
        marker.unlink()
        poisoned = {('LAW_O' + 'C' + ''): KEY, ('LAW_O' + 'C' + '_FILE'): 'synthetic-fallback',
                    'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
                    'GIT_CONFIG_VALUE_0': hook.as_posix(), 'GIT_DIR': 'missing-fixture-repository'}
        with patch.dict(os.environ, poisoned):
            common.check_tracked_links(self.root)
            output = git_read.run_git(self.root, ['ls-files', '-z', '--cached']).stdout
        self.assertIn(b'README.md', output)
        self.assertFalse(marker.exists(), 'production read invoked the configured fsmonitor hook')

    def test_4510295690_missing_partial_clone_object_fails_closed_without_lazy_fetch_env(self):
        # Simulate a Git release that ignores GIT_NO_LAZY_FETCH: only protocol.allow=never protects.
        def git(*args, cwd=None):
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
            return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                                  text=True, env=env)
        source, clone = self.root / 'source', self.root / 'clone'
        source.mkdir()
        try:
            git('init', '-q', cwd=source)
            git('config', 'uploadpack.allowFilter', 'true', cwd=source)
            git('config', 'uploadpack.allowAnySHA1InWant', 'true', cwd=source)
            (source / 'payload.txt').write_text('lazy fetch payload\n', encoding='utf-8')
            git('add', 'payload.txt', cwd=source)
            git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                'commit', '-q', '-m', 'fixture', cwd=source)
            blob = git('rev-parse', 'HEAD:payload.txt', cwd=source).stdout.strip()
            git('clone', '-q', '--no-checkout', '--filter=blob:none',
                source.resolve().as_uri(), str(clone))
        except (OSError, subprocess.CalledProcessError) as exc:
            self.skipTest(f'partial clone fixture unavailable: {type(exc).__name__}')
        missing = subprocess.run(['git', '-C', str(clone), 'cat-file', '-e', blob],
                                 capture_output=True, env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})
        if missing.returncode == 0:
            self.skipTest('partial clone fixture already contains the blob')
        # 4510368675: a repository-local per-protocol rule must not re-enable the transport.
        git('config', 'protocol.file.allow', 'always', cwd=clone)
        git('config', 'protocol.ext.allow', 'always', cwd=clone)
        without_flag = {k: v for k, v in git_read.child_environment().items() if k != 'GIT_NO_LAZY_FETCH'}
        with patch.object(git_read, 'child_environment', return_value=without_flag):
            with self.assertRaises(subprocess.CalledProcessError):
                git_read.run_git(clone, ['cat-file', '-p', blob])
        still_missing = subprocess.run(['git', '-C', str(clone), 'cat-file', '-e', blob],
                                       capture_output=True, env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})
        self.assertNotEqual(still_missing.returncode, 0, 'protected read lazily fetched the missing object')

    def test_4510448438_remote_helper_named_promisor_is_never_executed(self):
        # A promisor URL of the form <name>::<address> runs git-remote-<name> from PATH.
        def git(*args, cwd=None, env=None):
            base = env if env is not None else {k: v for k, v in os.environ.items()
                                                if not k.upper().startswith('GIT_')}
            return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                                  text=True, env=base)
        repo, bindir = self.root / 'repo', self.root / 'bin'
        marker = self.root / 'helper-ran'
        repo.mkdir()
        bindir.mkdir()
        helper = bindir / 'git-remote-kkhelper'
        helper.write_text('#!/bin/sh\n: > "' + marker.as_posix() + '"\nexit 1\n', encoding='utf-8', newline='\n')
        helper.chmod(0o755)
        missing_blob = '0123456789abcdef0123456789abcdef01234567'
        try:
            git('init', '-q', cwd=repo)
            git('config', 'remote.origin.url', 'kkhelper::payload', cwd=repo)
            git('config', 'remote.origin.promisor', 'true', cwd=repo)
            git('config', 'extensions.partialClone', 'origin', cwd=repo)
            git('config', 'protocol.allow', 'always', cwd=repo)
        except (OSError, subprocess.CalledProcessError) as exc:
            self.skipTest(f'remote-helper fixture unavailable: {type(exc).__name__}')
        control_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        control_env['PATH'] = str(bindir) + os.pathsep + control_env.get('PATH', '')
        subprocess.run(['git', '-C', str(repo), 'cat-file', '-p', missing_blob],
                       capture_output=True, env=control_env)
        if not marker.exists():
            self.skipTest('Git cannot execute the synthetic remote helper on this platform')
        marker.unlink()
        protected = dict(git_read.child_environment())
        protected.pop('GIT_NO_LAZY_FETCH', None)  # Simulate a Git release that ignores it.
        protected['PATH'] = control_env['PATH']
        with patch.object(git_read, 'child_environment', return_value=protected):
            with self.assertRaises(subprocess.CalledProcessError):
                git_read.run_git(repo, ['cat-file', '-p', missing_blob])
        self.assertFalse(marker.exists(), 'protected read executed the promisor remote helper')


if __name__ == '__main__':
    unittest.main()

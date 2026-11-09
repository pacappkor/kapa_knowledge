# SPDX-License-Identifier: GPL-3.0-only
"""Test layout validation and stock unittest completion reporting."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import importlib.util

CI = Path(__file__).resolve().parents[1] / '.github/ci'
spec = importlib.util.spec_from_file_location('ci_tests_supervise', CI / 'ci_tests_supervise.py')
ci_tests_supervise = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_tests_supervise)
completion_errors = ci_tests_supervise.completion_errors

TOOLS = CI
PASS = ('import unittest\nclass Example(unittest.TestCase):\n'
        '    def test_example(self): pass\n')


class DiscoveryTests(unittest.TestCase):
    def run_fixture(self, files, *, layout=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'tools/__init__.py').write_text('', encoding='utf-8')
            for name in ('ci_layout_check.py', 'ci_tests_supervise.py'):
                (root / '.github/ci').mkdir(parents=True, exist_ok=True)
                (root / '.github/ci' / name).write_bytes((TOOLS / name).read_bytes())
            for name, source in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if source is None:
                    path.unlink()
                else:
                    path.write_text(source, encoding='utf-8')
            script = 'ci_layout_check.py' if layout else 'ci_tests_supervise.py'
            def stop_child():
                if (root / 'child.pid').exists():
                    try:
                        os.kill(int((root / 'child.pid').read_text()), 15)
                    except ProcessLookupError:
                        pass
                    except OSError as error:
                        # These are our own same-token fixture children. Windows
                        # returns INVALID_PARAMETER for a vanished PID, or ACCESS_DENIED
                        # from TerminateProcess when it has already terminated.
                        if getattr(error, 'winerror', None) not in (5, 87):
                            raise
                    (root / 'child.pid').unlink()

            command = [sys.executable, '-I', '-B', str(root / '.github/ci' / script)]
            with subprocess.Popen(command, cwd=root.parent, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as process:
                try:
                    stdout, stderr = process.communicate(timeout=20)
                    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    # Close inherited writers before communicate retries on Windows.
                    stop_child()
                    process.kill()
                    process.communicate(timeout=5)
                    raise
                finally:
                    stop_child()
            self.assertFalse(list(root.rglob('__pycache__')))
            return result

    def test_missing_package_chain(self):
        for files, missing in [
            ({'tools/nested/test_example.py': PASS}, 'tools/nested/__init__.py'),
            ({'tools/test_example.py': PASS, 'tools/__init__.py': None}, 'tools/__init__.py'),
        ]:
            with self.subTest(missing=missing):
                result = self.run_fixture(files)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing package initializer: ' + missing, result.stderr)
                self.assertIn('not started', result.stderr)

    def test_invalid_discovery_identifiers(self):
        for path in ('tools/test_bad-name.py', 'tools/test_é.py'):
            with self.subTest(path=path):
                files = {path: PASS}
                if Path(path).parent != Path('tools'):
                    files[str(Path(path).parent / '__init__.py')] = ''
                result = self.run_fixture(files)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('invalid Python identifier', result.stderr)
                self.assertIn('not started', result.stderr)

    def test_package_names_follow_stock_loader(self):
        # __import__ accepts these names even though import statements do not.
        for name in ('class', 'my-pkg', '123abc'):
            with self.subTest(name=name):
                result = self.run_fixture({
                    f'tools/{name}/__init__.py': '',
                    f'tools/{name}/nested/__init__.py': '',
                    f'tools/{name}/nested/test_example.py': PASS,
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Ran 1 test', result.stderr)
                self.assertIn(f'tools.{name}.nested.test_example.Example', result.stderr)

    def test_nonidentifier_package_still_requires_initializer(self):
        result = self.run_fixture({'tools/my-pkg/test_example.py': PASS})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing package initializer: tools/my-pkg/__init__.py', result.stderr)

    def test_continuously_writing_descendant_does_not_hold_supervisor(self):
        child = ('import os, time\n'
                 'time.sleep(1)\n'
                 'while True:\n'
                 '    os.write(1, b"stdout noise\\n" * 1024)\n'
                 '    os.write(2, b"stderr noise\\n" * 1024)\n')
        source = ('import subprocess, sys, pathlib\n'
                  f'child = subprocess.Popen([sys.executable, "-I", "-B", "-c", {child!r}], '
                  'cwd=pathlib.Path.cwd().parent)\n'
                  'pathlib.Path("child.pid").write_text(str(child.pid))\n' + PASS)
        started = time.monotonic()
        result = self.run_fixture({'tools/test_background.py': source})
        self.assertLess(time.monotonic() - started, 18)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn('stdout noise', result.stdout)
        self.assertIn('stderr noise', result.stderr)
        self.assertIn('output readers cut off', result.stderr)
        self.assertIn('Test completion verified', result.stdout)

    def test_background_descendant_does_not_hold_supervisor(self):
        source = ('import subprocess, sys, pathlib\n'
                  'child = subprocess.Popen([sys.executable, "-I", "-B", "-c", '
                  '"import time; time.sleep(60)"], stdout=subprocess.DEVNULL, cwd=pathlib.Path.cwd().parent)\n'
                  'pathlib.Path("child.pid").write_text(str(child.pid))\n' + PASS)
        started = time.monotonic()
        result = self.run_fixture({'tools/test_background.py': source})
        self.assertLess(time.monotonic() - started, 18)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('output readers cut off', result.stderr)
        self.assertIn('Test completion verified', result.stdout)

    def test_post_exit_descendant_summary_is_ignored(self):
        child = ('import sys, time; time.sleep(1); '
                 'sys.stderr.write("Ran 0 tests in 0.001s\\n\\nNO TESTS RAN\\n"); '
                 'sys.stderr.flush()')
        source = ('import subprocess, sys, pathlib\n'
                  f'child = subprocess.Popen([sys.executable, "-I", "-B", "-c", {child!r}], '
                  'stdout=subprocess.DEVNULL, cwd=pathlib.Path.cwd().parent)\n' + PASS)
        result = self.run_fixture({'tools/test_background.py': source})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Ran 1 test', result.stderr)
        self.assertIn('NO TESTS RAN', result.stderr)
        self.assertIn('Test completion verified', result.stdout)

    def test_helpers_ignore_stdlib_shadows(self):
        result = self.run_fixture({
            'tools/test_example.py': PASS,
            'tools/pathlib.py': 'raise RuntimeError("shadow pathlib")\n',
            'tools/subprocess.py': 'raise RuntimeError("shadow subprocess")\n',
        })
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_files(self):
        result = self.run_fixture({})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no test files', result.stderr)

    def test_layout_does_not_import_packages(self):
        result = self.run_fixture({
            'tools/__init__.py': 'raise RuntimeError("must not import")\n',
            'tools/test_example.py': PASS}, layout=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_normal_suite(self):
        result = self.run_fixture({'tools/test_example.py': PASS})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Ran 1 test', result.stderr)
        self.assertIn('tools.test_example.Example', result.stderr)
        self.assertIn('Test completion verified', result.stdout)

    def test_atexit_stderr(self):
        source = ('import atexit, sys\n'
                  'atexit.register(lambda: sys.stderr.write("atexit diagnostic\\n"))\n' + PASS)
        result = self.run_fixture({'tools/test_atexit.py': source})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('atexit diagnostic', result.stderr)

    def test_encoding_without_getencoding(self):
        with mock.patch.object(ci_tests_supervise.locale, 'getencoding', create=True):
            del ci_tests_supervise.locale.getencoding
            for preferred in ('cp949', ''):
                with mock.patch.object(ci_tests_supervise.locale, 'getpreferredencoding',
                                       return_value=preferred) as fallback:
                    self.assertEqual(ci_tests_supervise.output_encoding(), preferred or 'utf-8')
                    fallback.assert_called_once_with(False)

    @unittest.skipUnless(os.name == 'nt', 'Windows pipe compatibility')
    def test_legacy_windows_nonblocking(self):
        with mock.patch.object(ci_tests_supervise.sys, 'version_info', (3, 10)):
            with subprocess.Popen([sys.executable, '-I', '-B', '-c',
                                   'input(); print("ok")'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                ci_tests_supervise.set_nonblocking(process.stdout)
                try:
                    with self.assertRaises(BlockingIOError):
                        ci_tests_supervise.read_pipe(process.stdout, 1024)
                finally:
                    process.stdin.write(b'\n')
                    process.stdin.flush()
                process.wait(timeout=10)
                self.assertIn(b'ok', ci_tests_supervise.read_pipe(process.stdout, 1024))
                self.assertEqual(ci_tests_supervise.read_pipe(process.stdout, 1024), b'')

    def test_early_exit(self):
        for source in ('import os; os._exit(0)\n',
                       PASS.replace('pass', '__import__("os")._exit(0)')):
            with self.subTest(source=source):
                result = self.run_fixture({'tools/test_exit.py': source})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('missing unittest summary', result.stderr)
                self.assertIn('missing final OK', result.stderr)

    def test_all_skipped(self):
        for source, count in [
            (PASS.replace('class Example', '@unittest.skip("skip")\nclass Example'), 1),
            (PASS + 'def setUpModule():\n    raise unittest.SkipTest("skip")\n', 0),
        ]:
            with self.subTest(count=count):
                result = self.run_fixture({'tools/test_skip.py': source})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'Ran {count} test', result.stderr)
                self.assertIn('OK (skipped=1)', result.stderr)

    def test_failure(self):
        result = self.run_fixture({'tools/test_bad.py': PASS.replace('pass', 'self.fail("fixture")')})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Test runner failed (exit 1)', result.stderr)
        self.assertIn('missing final OK', result.stderr)

    def test_empty_suite(self):
        result = self.run_fixture({'tools/test_empty.py': ''})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ran zero tests and reported no skips', result.stderr)

    def test_summary_parser_accepts_stock_output(self):
        for count, final in [(1, 'OK'), (3, 'OK (skipped=2)'), (0, 'OK (skipped=1)')]:
            with self.subTest(count=count, final=final):
                self.assertEqual(completion_errors(0, f'Ran {count} tests in 0.001s\n\n{final}\n'), [])
                self.assertEqual(completion_errors(0, f'Ran {count} tests in 0.001s\n\n{final}\nextra\n'), [])

    def test_summary_parser_rejects_incomplete_output(self):
        for code, output, reason in [
            (0, 'OK\n', 'missing unittest summary'),
            (0, 'Ran 1 test in 0.001s\n', 'missing final OK'),
            (0, 'Ran 0 tests in 0.001s\n\nOK\n', 'ran zero tests'),
            (0, 'Ran 0 tests in 0.001s\n\nOK (skipped=0)\n', 'ran zero tests'),
            (1, 'Ran 1 test in 0.001s\n\nOK\n', 'exit 1'),
            (0, 'Ran 1 test in 0.001s\n\nFAILED (failures=1)\nOK\n', 'missing final OK'),
            (0, 'Ran 1 test in 0.001s\n\nnoise\nOK\n', 'missing final OK'),
            (0, 'Ran 1 test in 0.001s\nOK\nRan 0 tests in 0.001s\nOK\n', 'ran zero tests'),
            (0, 'Ran 1 test in 0.001s\nOK\nRan 1 test in 0.001s\n', 'missing final OK'),
        ]:
            with self.subTest(code=code, output=output):
                self.assertTrue(any(reason in error for error in completion_errors(code, output)))


class StreamTests(unittest.TestCase):
    def make_stream(self, *, capture=False):
        destination = io.StringIO()
        stream = ci_tests_supervise.Stream(mock.Mock(), destination, threading.Event(),
                                          capture=capture)
        return stream, destination

    def test_busy_drain_is_bounded_by_initial_buffer(self):
        stream, destination = self.make_stream()
        with mock.patch.object(ci_tests_supervise, 'buffered_bytes', return_value=131073), \
                mock.patch.object(ci_tests_supervise, 'read_pipe',
                                  side_effect=[b'x' * 65536, b'x' * 65536, b'x',
                                               AssertionError('drain exceeded snapshot')]) as read:
            with stream.lock:
                stream.drain()
        self.assertEqual([call.args[1] for call in read.call_args_list], [65536, 65536, 1])
        self.assertEqual(len(destination.getvalue()), 131073)
        self.assertEqual(stream.captured, [])

    def test_snapshot_keeps_all_queued_stderr_but_not_later_output(self):
        stream, destination = self.make_stream(capture=True)
        summary = b'Ran 1 test in 0.001s\n\nOK\n'
        queued = b'x' * 131072 + b'\n' + summary
        chunks = iter((queued[:65536], queued[65536:131072], queued[131072:]))
        with mock.patch.object(ci_tests_supervise, 'buffered_bytes', return_value=len(queued)), \
                mock.patch.object(ci_tests_supervise, 'read_pipe',
                                  side_effect=lambda pipe, size: next(chunks)):
            stream.snapshot()
        captured = ''.join(stream.captured)
        self.assertEqual(captured, queued.decode())
        self.assertEqual(completion_errors(0, captured), [])
        late = b'Ran 0 tests in 0.001s\n\nNO TESTS RAN\n'
        with mock.patch.object(ci_tests_supervise, 'buffered_bytes', return_value=len(late)), \
                mock.patch.object(ci_tests_supervise, 'read_pipe', return_value=late):
            for _ in range(100):
                with stream.lock:
                    stream.drain()
        self.assertEqual(''.join(stream.captured), captured)
        self.assertEqual(destination.getvalue(), captured + late.decode() * 100)

    def test_real_pipe_buffer_count_and_snapshot(self):
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, 'rb', buffering=0) as pipe, \
                os.fdopen(write_fd, 'wb', buffering=0) as writer:
            ci_tests_supervise.set_nonblocking(pipe)
            summary = b'Ran 1 test in 0.001s\n\nOK\n'
            writer.write(summary)
            self.assertEqual(ci_tests_supervise.buffered_bytes(pipe), len(summary))
            destination = io.StringIO()
            stream = ci_tests_supervise.Stream(pipe, destination, threading.Event(), capture=True)
            stream.snapshot()
            self.assertEqual(''.join(stream.captured), summary.decode())
            self.assertEqual(ci_tests_supervise.buffered_bytes(pipe), 0)
            writer.write(b'later\n')
            with stream.lock:
                stream.drain()
            self.assertEqual(''.join(stream.captured), summary.decode())
            self.assertEqual(destination.getvalue(), summary.decode() + 'later\n')


if __name__ == '__main__':
    unittest.main()

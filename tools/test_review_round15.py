# SPDX-License-Identifier: GPL-3.0-only
"""No-follow snapshot reads, bounded diagnostics and deny-by-default regressions."""
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from doc_snapshot import SnapshotError, document_snapshot, load_snapshot, snapshot_difference
from test_review_round10 import PS_EXIT, UNITTEST_COMMAND, workflow_findings
from test_write_safety import direct_writes, production_write_findings

KEY = 'SnapshotSynthetic' + 'Credential9/+?Value'


class RoundFifteenRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        for name in ('README.md', 'AGENTS.md'):
            (self.root / name).write_bytes(b'Guide.\n')
        for name in ('docs', 'rules'):
            (self.root / name).mkdir()
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)

    def test_4509651096_refuses_nonregular_and_reparse_docs_before_any_read(self):
        path = self.root / 'rules/linked.md'
        path.write_bytes(b'ordinary')
        original = Path.lstat
        for mode, attributes in [(stat.S_IFLNK, 0), (stat.S_IFREG, 0x400),
                                 (stat.S_IFIFO, 0), (stat.S_IFDIR, 0)]:
            def metadata(candidate, *args, **kwargs):
                if candidate == path:
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original(candidate, *args, **kwargs)
            with self.subTest(mode=mode, attributes=attributes), patch.object(Path, 'lstat', metadata), patch.object(Path, 'read_bytes') as read:
                with self.assertRaises(SnapshotError):
                    document_snapshot(self.root)
                read.assert_not_called()

    def test_snapshot_refuses_resolved_escape_before_read(self):
        path = self.root / 'docs/escape.md'
        path.write_bytes(b'ordinary')
        original = Path.resolve
        def resolve(candidate, *args, **kwargs):
            return self.base / 'outside.md' if candidate == path else original(candidate, *args, **kwargs)
        with patch.object(Path, 'resolve', resolve), patch.object(Path, 'read_bytes') as read:
            with self.assertRaises(SnapshotError):
                document_snapshot(self.root)
            read.assert_not_called()

    def test_snapshot_does_not_traverse_junction_parent(self):
        path = self.root / 'rules'
        original = Path.lstat
        def metadata(candidate, *args, **kwargs):
            if candidate == path:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(candidate, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), patch.object(Path, 'iterdir') as walk, patch.object(Path, 'read_bytes') as read:
            with self.assertRaises(SnapshotError):
                document_snapshot(self.root)
            walk.assert_not_called()
            read.assert_not_called()

    def test_real_document_symlink_never_reads_external_fixture(self):
        external = self.base / 'external.md'
        external.write_text('<pre>' + KEY + '</pre>', encoding='utf-8')
        try:
            (self.root / 'rules/linked.md').symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest('symlink privilege unavailable; mocked no-follow tests remain active')
        with patch.object(Path, 'read_bytes') as read:
            with self.assertRaises(SnapshotError):
                document_snapshot(self.root)
            read.assert_not_called()

    def test_snapshot_refuses_both_tracked_link_modes_before_any_read(self):
        blob = subprocess.run(['git', '-C', str(self.root), 'hash-object', '-w', '--stdin'],
                              input=b'../external.md', check=True, capture_output=True).stdout.decode().strip()
        for mode, oid in [('120000', blob), ('160000', '1' * 40)]:
            subprocess.run(['git', '-C', str(self.root), 'update-index', '--add', '--cacheinfo',
                            mode + ',' + oid + ',rules/link.md'], check=True, capture_output=True)
            with self.subTest(mode=mode), patch.object(Path, 'read_bytes') as read:
                with self.assertRaises(SnapshotError):
                    document_snapshot(self.root)
                read.assert_not_called()

    def test_snapshot_json_is_guarded_and_parse_failures_do_not_echo_data(self):
        tools = self.root / 'tools'
        tools.mkdir()
        path = tools / 'doc_command_snapshot.json'
        path.write_bytes(b'[]')
        original = Path.lstat
        def metadata(candidate, *args, **kwargs):
            if candidate == path:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return original(candidate, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), patch.object(Path, 'read_bytes') as read:
            with self.assertRaises(SnapshotError):
                load_snapshot(self.root)
            read.assert_not_called()
        path.write_text(KEY, encoding='utf-8')
        with self.assertRaises(SnapshotError) as raised:
            load_snapshot(self.root)
        self.assertNotIn(KEY, str(raised.exception))

    def test_snapshot_unittest_failure_prints_only_redacted_metadata(self):
        def record(path, body):
            return {'file': path, 'sha256': hashlib.sha256(body.encode()).hexdigest(), 'size': len(body.encode())}
        actual = [record('rules/' + KEY + '.md', 'OpaqueBodyShouldNeverAppear ' + KEY + ' ' + KEY.encode().hex())]
        expected = [record('rules/example.md', 'EarlierOpaqueBody')]
        stream = io.StringIO()
        class SyntheticMismatch(unittest.TestCase):
            def runTest(inner):
                difference = snapshot_difference(actual, expected)
                if difference:
                    inner.fail(difference)
        with patch.dict(os.environ, {'LAW_OC': KEY}):
            result = unittest.TextTestRunner(stream=stream).run(SyntheticMismatch())
        output = stream.getvalue()
        self.assertEqual(len(result.failures), 1)
        for value in (KEY, KEY.encode().hex(), 'OpaqueBodyShouldNeverAppear', 'EarlierOpaqueBody'):
            self.assertNotIn(value, output)
        self.assertIn('sha256=', output)
        self.assertIn('size=', output)
        self.assertNotIn('block 1', output)
        self.assertIn('[redacted]', output)
        with patch.dict(os.environ, {'LAW_OC': KEY}):
            # Even a credential-like field in the final message is redacted.
            diagnostic = snapshot_difference([record(KEY, 'body')], [])
            self.assertNotIn(KEY, diagnostic)
        self.assertEqual(snapshot_difference(actual, actual), '')

    def test_document_validation_and_unittest_commands_are_fail_stop(self):
        validate = 'python -I -B tools/validate.py'
        for command in (validate, UNITTEST_COMMAND):
            for valid in (command + ' || exit 1', command + '\n' + PS_EXIT):
                self.assertEqual(workflow_findings('```sh\n' + valid + '\n```\n'), [])
            for invalid in (command, command + '\ntrue', command + ' || true'):
                self.assertTrue(workflow_findings('```sh\n' + invalid + '\n```\n'))

    def test_4509655620_git_status_is_never_production_allowlisted(self):
        for argv in (['git', 'status'], ['git', '-C', 'outside', 'status', '--short'],
                     ['git', '--no-optional-locks', 'status', '--short']):
            source = 'import subprocess\nsubprocess.run(' + repr(argv) + ', capture_output=True)'
            self.assertTrue(direct_writes(source, 'production.py'))

    def test_4509655623_any_event_loop_subprocess_attribute_is_guarded(self):
        for target in ('loop', 'obj.loop', 'get_loop()', 'unknown_object'):
            for method in ('subprocess_exec', 'subprocess_shell'):
                source = 'async def launch():\n    await ' + target + '.' + method + '(factory, "cp", "a", "b")'
                self.assertTrue(direct_writes(source, 'production.py'))
                self.assertTrue(direct_writes(source, 'test_fixture.py', check_files=False))

    def test_4509655628_raw_html_is_pinned_without_region_parsing(self):
        path = self.root / 'docs/raw.html'
        for tag in ('pre', 'code', 'script', 'textarea', 'PRE', 'CoDe'):
            for text in ('<' + tag + '>payload</' + tag + '>\n',
                         '<' + tag + '\n class="example">\npayload\n',
                         '<pre title="</pre>"><code>payload</code></pre>\n'):
                path.write_text(text, encoding='utf-8')
                baseline = document_snapshot(self.root)
                path.write_text(text.replace('payload', 'replacement'), encoding='utf-8')
                self.assertNotEqual(document_snapshot(self.root), baseline)

    def make_tools(self):
        tools = self.root / 'tools'
        tools.mkdir()
        (tools / '__init__.py').write_bytes(b'')
        return tools

    def test_4509655635_production_imports_test_named_helpers_fail(self):
        tools = self.make_tools()
        (tools / 'test_writer.py').write_text('def perform():\n    path.write_text("outside")\n', encoding='utf-8')
        producer = tools / 'producer.py'
        for source in ('import test_writer as helper\nhelper.perform()',
                       'from test_writer import perform\nperform()',
                       'from . import test_writer\ntest_writer.perform()',
                       'from tools.test_writer import perform\nperform()'):
            with self.subTest(source=source):
                producer.write_text(source, encoding='utf-8')
                findings = production_write_findings(tools)
                self.assertTrue(any(row[0] == 'producer.py' and 'imports test-named' in row[2] for row in findings))
                self.assertTrue(any(row[0] == 'test_writer.py' and row[2] == 'write_text' for row in findings))

    def test_unresolved_test_named_imports_are_still_rejected(self):
        tools = self.make_tools()
        path = tools / 'producer.py'
        for source in ('import test_external_helper\n', 'from test_external_helper import perform\n',
                       'from helpers import test_external_helper\n'):
            path.write_text(source, encoding='utf-8')
            self.assertTrue(any('imports test-named' in row[2] for row in production_write_findings(tools)))

    def test_only_actual_discovery_targets_receive_fixture_write_exemptions(self):
        tools = self.make_tools()
        package = tools / 'nested'
        package.mkdir()
        fixture = package / 'test_fixture.py'
        fixture.write_text('def fixture():\n    path.write_text("fixture")\n', encoding='utf-8')
        self.assertTrue(production_write_findings(tools))  # No package, not discovered.
        (package / '__init__.py').write_bytes(b'')
        self.assertEqual(production_write_findings(tools), [])
        invalid = tools / 'test_not-valid.py'
        invalid.write_bytes(fixture.read_bytes())
        self.assertTrue(any(row[0] == invalid.name for row in production_write_findings(tools)))

    def test_production_import_closure_removes_transitive_test_exemptions(self):
        tools = self.make_tools()
        (tools / 'producer.py').write_text('import test_helper\n', encoding='utf-8')
        (tools / 'test_helper.py').write_text('from test_writer import perform\n', encoding='utf-8')
        (tools / 'test_writer.py').write_text('def perform():\n    path.write_text("outside")\n', encoding='utf-8')
        findings = production_write_findings(tools)
        self.assertTrue(any(row[0] == 'test_helper.py' and 'imports test-named' in row[2] for row in findings))
        self.assertTrue(any(row[0] == 'test_writer.py' and row[2] == 'write_text' for row in findings))


if __name__ == '__main__':
    unittest.main()

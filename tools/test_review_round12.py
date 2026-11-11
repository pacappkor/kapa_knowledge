# SPDX-License-Identifier: GPL-3.0-only
"""Table-driven regressions for encoded payloads and tool safety policy aids."""
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import credentials
import secret_scan
from tools.test_review_round10 import (PREFLIGHT_PAIRS, UNITTEST_COMMAND, fenced_blocks,
                                       python_invocations, test_launcher_findings, workflow_findings, writer_tools)
from tools.test_write_safety import production_write_findings

KEY = 'PersistSynthetic' + '9/+? value'


class RoundTwelveRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def encoded_forms(self):
        forms = [(name, needle.decode('utf-8')) for name, needle in secret_scan.value_needles(KEY)]
        for name, form in list(forms):
            if name.startswith('url-'):
                forms.append((name + '-lower-percent', re.sub(r'%[0-9A-F]{2}', lambda item: item[0].lower(), form)))
            if name.startswith('hex-'):
                forms.append((name + '-mixed', ''.join(char.upper() if index % 2 else char.lower()
                                                      for index, char in enumerate(form))))
            if name.startswith('base64'):
                forms.append((name + '-wrapped', ' \r\n\t'.join(form[index:index + 3] for index in range(0, len(form), 3))))
        for encode in (base64.b64encode, base64.urlsafe_b64encode):
            for offset in range(3):
                forms.append(('embedded-' + str(offset), encode(b'x' * offset + KEY.encode() + b'after').decode()))
        return forms

    def test_4509302146_all_documented_forms_mask_values_and_mapping_keys(self):
        needles = secret_scan.value_needles(KEY)
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): KEY}), patch.object(common, 'ROOT', self.root):
            for name, form in self.encoded_forms():
                with self.subTest(form=name):
                    payload = {'key-' + form: {'nested': ['before-' + form + '-after']}}
                    masked = common.mask(payload)
                    self.assertNotEqual(masked, payload)
                    for key, value in masked.items():
                        for text in (key, value['nested'][0]):
                            self.assertFalse(list(secret_scan.matching_encodings(text.encode(), needles)))
                    with self.assertRaisesRegex(ValueError, 'unmasked secret'):
                        common.canonical(payload, reject_masked=True)
                    output = self.root / 'payload.json'
                    common.save_json(output, payload)
                    self.assertEqual(json.loads(output.read_text(encoding='utf-8')), masked)
                    self.assertFalse(list(secret_scan.matching_encodings(output.read_bytes(), needles)))
            normal = {'ordinary': ['unchanged', 123]}
            self.assertEqual(json.loads(common.canonical(normal, reject_masked=True)), normal)

    def test_4509302146_encoded_selected_fallback_and_mapping_collisions(self):
        filename = str(self.root / 'never-read.txt')
        form = KEY.encode().hex().upper()
        with patch.dict(os.environ, {('LAW_O' + 'C' + ''): '', ('LAW_O' + 'C' + '_FILE'): filename}), patch.object(credentials, '_file_selection', (filename, KEY)), patch.object(Path, 'read_text', side_effect=AssertionError('unexpected credential read')):
            self.assertEqual(common.mask({form: form}), {'***': '***'})
            with self.assertRaisesRegex(ValueError, 'unmasked secret'):
                common.canonical({'value': form}, reject_masked=True)
            with self.assertRaisesRegex(ValueError, 'masked mapping keys collide'):
                common.mask({form: 1, '***': 2})

    def test_4509302123_both_fence_characters_and_variable_lengths(self):
        writer = 'python -I -B tools/export_records.py\n'
        preflights = ('python -I -B tools/validate.py --check-links || exit 1\n'
                      'python -I -B tools/secret_scan.py --require --worktree || exit 1\n')
        for char in ('`', '~'):
            for opening, closing in ((3, 3), (4, 4), (3, 5), (7, 8)):
                with self.subTest(char=char, opening=opening, closing=closing):
                    def fence(body):
                        return char * opening + 'sh\n' + body + char * closing + '\n'
                    self.assertEqual(list(fenced_blocks(fence(writer))), [writer])
                    self.assertTrue(workflow_findings(fence(writer), {'export_records.py'}))
                    self.assertEqual(workflow_findings(fence(preflights + writer), {'export_records.py'}), [])
        self.assertEqual(list(fenced_blocks('~~~~sh\n```\n~~~\n~~~~\n')), ['```\n~~~\n'])
        self.assertTrue(workflow_findings('~~~sh\n' + writer, {'export_records.py'}))

    def test_4509302129_writer_status_follows_shared_sink_calls_not_names(self):
        tools = self.root / 'tools'
        tools.mkdir()
        modules = {
            'common.py': 'def safe_write_text(path, text): pass\ndef readjson(text): return text\n',
            'store.py': 'from common import safe_write_text as put\ndef persist(): put("path", "text")\n',
            'export_records.py': 'from store import persist as emit\ndef main(): emit()\n',
            'neutral.py': 'import store as storage\ndef main(): storage.persist()\n',
            'reader.py': 'from common import readjson\ndef main(): return readjson("text")\n',
            'cycle_a.py': 'from cycle_b import go\ndef run(): go()\n',
            'cycle_b.py': 'from cycle_a import run\nfrom store import persist\ndef go(): run(); persist()\n',
            'staging.py': 'from common import staged_files\ndef main(): staged_files([])\n',
            'snapshot.py': 'from common import save_json\ndef main(): save_json("path", {})\n',
            'bytes_out.py': 'import common as c\ndef main(): c.safe_write_bytes("path", b"text")\n',
            'helpers/nested.py': 'from common import safe_write_text\ndef put(): safe_write_text("path", "text")\n',
            'dotted.py': 'import helpers.nested\ndef main(): helpers.nested.put()\n',
        }
        for name, source in modules.items():
            (tools / name).parent.mkdir(parents=True, exist_ok=True)
            (tools / name).write_text(source, encoding='utf-8')
        writers = writer_tools(tools)
        self.assertEqual(writers, {'store.py', 'export_records.py', 'neutral.py', 'cycle_a.py',
                                   'cycle_b.py', 'staging.py', 'snapshot.py', 'bytes_out.py', 'nested.py', 'dotted.py'})
        for name in writers:
            self.assertTrue(workflow_findings('```sh\npython -I -B tools/' + name + '\n```', writers))
        self.assertEqual(workflow_findings('```sh\npython -I -B tools/reader.py\n```', writers), [])

    def test_4509302136_subprocess_launchers_share_the_documentation_flag_check(self):
        for launcher in ('sys.executable', repr('python'), repr('python3'), repr('python3.12'), repr('py'), repr('python.exe')):
            version = ["'-3.12'"] if launcher == repr('py') else []
            for flags, safe in (([], False), (["'-I'"], False), (["'-B'"], False),
                                (["'-I'", "'-B'"], True), (["'-B'", "'-I'"], True)):
                with self.subTest(launcher=launcher, flags=flags):
                    elements = [launcher] + version + flags + ["'tools/example.py'"]
                    command = '[' + ', '.join(elements) + ']'
                    for source in ('subprocess.run(' + command + ', capture_output=True)',
                                   'command = ' + command + '\nsubprocess.run(command, capture_output=True)'):
                        self.assertEqual(bool(test_launcher_findings(source)), not safe)
            late_flags = '[' + ', '.join([launcher] + version + ["'tools/example.py'", "'-I'", "'-B'"]) + ']'
            self.assertTrue(test_launcher_findings('subprocess.run(' + late_flags + ', capture_output=True)'))
        self.assertEqual(test_launcher_findings("subprocess.run(['git', 'status'], capture_output=True)"), [])

    def test_4509310479_quoted_launchers_use_flags_and_preflight_checks(self):
        launchers = (
            '\"python\"', "'python3'", '\"python3.12.exe\"', "'py' -3.12",
            '\"pythonw\"', "'pythonw.exe'", "'/opt/Python Home/python3.12'",
            r'& "C:\Python312\python.exe"',
            r'& "C:\Program Files\Python312\pythonw.exe"',
            r"&'C:\Python312\py.exe' -3.12",
            r'C:\Python312\python.exe',
        )
        preflights = ('python -I -B tools/validate.py --check-links || exit 1\n'
                      'python -I -B tools/secret_scan.py --require --worktree || exit 1\n')
        for launcher in launchers:
            for flags, safe in (('', False), ('-I', False), ('-B', False),
                                ('-I -B', True), ('-B -I', True)):
                with self.subTest(launcher=launcher, flags=flags):
                    command = launcher + ' ' + flags + ' tools/export_records.py\n'
                    parsed = python_invocations(command)
                    self.assertEqual(len(parsed), 1)
                    self.assertEqual(parsed[0]['target'], 'export_records.py')
                    self.assertEqual({'-I', '-B'} <= parsed[0]['flags'], safe)
                    self.assertTrue(workflow_findings('~~~sh\n' + command + '~~~', {'export_records.py'}))
                    # Docs now reject every noncanonical form, even with valid
                    # flags/preflights; subprocess argument parsing stays tolerant.
                    self.assertTrue(workflow_findings('~~~sh\n' + preflights + command + '~~~',
                                                      {'export_records.py'}))
        # The same launcher classification is used for subprocess argument lists.
        for launcher in ('pythonw', 'pythonw.exe', r'C:\Program Files\Python312\python.exe'):
            for flags, safe in (([], False), (['-I', '-B'], True)):
                source = 'subprocess.run(' + repr([launcher] + flags + ['tools/example.py']) + ', capture_output=True)'
                self.assertEqual(bool(test_launcher_findings(source)), not safe)
        self.assertEqual(len(python_invocations('\"python\" -I -B tools/example.py \"')), 1)

    def test_4509424163_4509424167_4509424172_docs_only_allow_canonical_forms(self):
        writer = 'python -I -B tools/export_records.py records.json'
        shell = '\n'.join(PREFLIGHT_PAIRS[0])
        powershell = '\n'.join(PREFLIGHT_PAIRS[1])
        def check(commands):
            return workflow_findings('~~~sh\n' + commands + '\n~~~', {'export_records.py'})
        for commands in ('python -I -B tools/validate.py || exit 1', UNITTEST_COMMAND + ' || exit 1',
                         shell + '\n' + writer, powershell + '\n' + writer):
            with self.subTest(canonical=commands):
                self.assertEqual(check(commands), [])
        noncanonical = (
            'PYTHONDONTWRITEBYTECODE=1 python tools/export_records.py',
            ('LAW_O' + 'C' + '=fixture python -I -B tools/export_records.py'),
            'env python -I -B tools/export_records.py',
            'command python -I -B tools/export_records.py',
            'python -I -B tools/export_records.py; true',
            'python -I -B tools/export_records.py && true',
            'python -I -B tools/export_records.py | cat',
            'python -I -B tools/export_records.py --help',
            'python -I -B tools/export_records.py -h',
            'python -I -B tools/export_records.py "--help"',
            '"python" -I -B tools/export_records.py',
            "'py' -3.12 -I -B tools/export_records.py",
            'python3 -I -B tools/export_records.py',
            'pythonw.exe -I -B tools/export_records.py',
            'python -B -I tools/export_records.py',
            'python -I tools/export_records.py',
            'python -I -B tools/export_records.py $variable',
            'python -I -B tools/export_records.py $(command)',
            'python -I -B tools/export_records.py > output',
            'python -I -B tools/export_records.py `command`',
        )
        for command in noncanonical:
            with self.subTest(noncanonical=command):
                self.assertTrue(check(shell + '\n' + command))
        bad_pairs = (
            shell.replace(' || exit 1', '; true || exit 1'),
            shell.replace('--check-links', '--help --check-links'),
            shell.replace('--require', '--help --require'),
            shell.replace('--check-links', '-h --check-links'),
            shell.replace('--require', '-h --require'),
            powershell.replace('{ exit 1 }', "{ throw 'failed' }"),
            '\n'.join(reversed(PREFLIGHT_PAIRS[0])),
            PREFLIGHT_PAIRS[0][0],
        )
        for preflights in bad_pairs:
            with self.subTest(preflights=preflights):
                self.assertTrue(check(preflights + '\n' + writer))
        self.assertTrue(check(writer + '\n' + shell))

    def test_4509302141_test_files_keep_fixture_writes_but_must_capture_children(self):
        tools = self.root / 'tools'
        nested = tools / 'helpers'
        nested.mkdir(parents=True)
        (tools / '__init__.py').write_text('', encoding='utf-8')
        (nested / '__init__.py').write_text('', encoding='utf-8')
        path = nested / 'test_example.py'
        fixture = 'path.write_text("fixture")\n'
        for command, safe in (
            ('subprocess.run(["git"])', False),
            ('subprocess.run(["git"], capture_output=True)', True),
            ('subprocess.Popen(["git"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)', True),
            ('subprocess.check_output(["git"], stderr=subprocess.PIPE)', True),
            ('subprocess.call(["git"], stdout=subprocess.PIPE)', False),
        ):
            with self.subTest(command=command):
                path.write_text('import subprocess\n' + fixture + command, encoding='utf-8')
                findings = production_write_findings(tools)
                self.assertEqual(bool(findings), not safe)
                if findings:
                    self.assertEqual(findings[0][0], 'helpers/test_example.py')
                    self.assertIn('inherits stdio', findings[0][2])

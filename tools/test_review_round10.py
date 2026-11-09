# SPDX-License-Identifier: GPL-3.0-only
"""Offline regressions for CLI redaction, preflight ordering and bytecode safety."""
import argparse
import ast
from functools import lru_cache
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import credentials
import secret_scan
from doc_snapshot import (checked_documents, document_snapshot, load_snapshot,
                          read_snapshot_input, snapshot_difference)

KEY = 'CliDiagnostic' + 'Synthetic9/+?Value'


def unquote(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in '\"\'':
        return token[1:-1]
    return token


def python_launcher(token):
    basename = unquote(token).replace('\\', '/').rsplit('/', 1)[-1]
    return bool(re.fullmatch(r'(?:python(?:\d+(?:\.\d+)*|w)?|py)(?:\.exe)?', basename, re.I))


def command_tokens(command):
    """POSIX tokenization, with a small fallback preserving Windows paths."""
    command = command.lstrip()
    if command.startswith('&'):
        command = command[1:].lstrip()
    try:
        words = shlex.split(command, posix=True)
        if '\\' in command:
            words = shlex.split(command, posix=False)
    except ValueError:
        # Tolerate surrounding Markdown/Python text without throwing away
        # matching quotes around an executable or a path containing spaces.
        words = re.findall(r'''"[^"]*"|'[^']*'|\S+''', command)
    words = [unquote(word) for word in words]
    while words and words[0] in {'&', '$', 'run:'}:
        words.pop(0)
    return words


def python_invocations(text):
    """Tokenize commands before classifying their unquoted launcher basename."""
    commands = []
    text = text.replace('\\\n', ' ').replace('`\n', ' ')
    for line in text.splitlines():
        for segment in re.split(r'`+|\|\||&&|[;|]', line):
            words = command_tokens(segment)
            if not words or not python_launcher(words[0]):
                continue
            args = words[1:]
            if not args:
                continue
            # Ignore ordinary prose about Python, not actual launcher syntax.
            if not (args[0].startswith('-') or args[0].endswith('.py') or '/' in args[0]
                    or '\\' in args[0] or words[0].islower()):
                continue
            flags, target, tool_args, index = set(), '', [], 0
            while index < len(args):
                arg = args[index]
                if arg in {'-m', '-c'}:
                    target = args[index + 1] if index + 1 < len(args) else ''
                    if arg == '-m':
                        target = target.replace('.', '/') + '.py'
                    tool_args = args[index + 2:]
                    break
                if not arg.startswith('-') or arg == '--':
                    offset = index + int(arg == '--')
                    target = args[offset] if offset < len(args) else ''
                    tool_args = args[offset + 1:]
                    break
                if arg in {'-X', '-W', '--check-hash-based-pycs'}:
                    index += 2
                    continue
                if arg.startswith('-') and set(arg[1:]) <= set('IB'):
                    flags.update('-' + option for option in arg[1:])
                index += 1
            commands.append(dict(flags=flags, target=target.replace('\\', '/').rsplit('/', 1)[-1],
                                 args=tool_args, line=line))
    return commands


@lru_cache(maxsize=16)
def writer_tools(tools=common.CODE_ROOT / 'tools'):
    """Small direct-call graph, including import aliases and tool-to-tool calls.

    This regression aid follows named functions, not arbitrary Python dataflow.
    A module is a writer if any of its calls transitively reaches a shared sink.
    """
    graph, modules = {}, set()
    for path in tools.rglob('*.py'):
        if path.name.startswith('test_'):
            continue
        module = '.'.join(path.relative_to(tools).with_suffix('').parts)
        modules.add(module)
        tree = ast.parse(path.read_text(encoding='utf-8'))
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    bound = item.asname or item.name.split('.')[0]
                    aliases[bound] = item.name if item.asname else bound
            elif isinstance(node, ast.ImportFrom):
                source = (node.module or '').removeprefix('tools.')
                if node.level:
                    source = '.'.join(module.split('.')[:-node.level] + ([source] if source else []))
                for item in node.names:
                    aliases[item.asname or item.name] = source + '.' + item.name
        def qualified(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, module + '.' + node.id)
            if isinstance(node, ast.Attribute):
                return qualified(node.value) + '.' + node.attr
            return ''
        owners = [(module + '.$module', tree)]
        owners += [(module + '.' + node.name, node) for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for name, owner in owners:
            graph[name] = {qualified(node.func).removeprefix('tools.')
                           for node in ast.walk(owner) if isinstance(node, ast.Call)}
    writing = {'common.staged_files', 'common.save_json'}
    writing |= {name for calls in graph.values() for name in calls if name.startswith('common.safe_write_')}
    while True:
        reached = {name for name, calls in graph.items() if calls & writing}
        if reached <= writing:
            break
        writing |= reached
    return {module.rsplit('.', 1)[-1] + '.py' for module in modules if module + '.$module' in writing}


def test_launcher_findings(source):
    """Check literal/assigned argument lists using the documentation parser too."""
    tree = ast.parse(source)
    assigned = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
    commands = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or ast.unparse(call.func).rsplit('.', 1)[-1] not in {
                'run', 'call', 'check_call', 'check_output', 'Popen'}:
            continue
        argument = call.args[0] if call.args else next((kw.value for kw in call.keywords if kw.arg == 'args'), None)
        if isinstance(argument, ast.Name):
            commands.extend(node for node in assigned.get(argument.id, []) if node.elts)
        elif isinstance(argument, (ast.List, ast.Tuple)) and argument.elts:
            commands.append(argument)
    findings = []
    for node in commands:
        first = node.elts[0]
        executable = ast.unparse(first) == 'sys.executable'
        if not executable and not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                                   and python_launcher(first.value)):
            continue
        words = ['python' if executable else first.value]
        words += [item.value if isinstance(item, ast.Constant) and isinstance(item.value, str)
                  else '__target__' for item in node.elts[1:]]
        commands = python_invocations(subprocess.list2cmdline(words))
        if not commands or not {'-I', '-B'} <= commands[0]['flags']:
            findings.append(node.lineno)
    return findings


LINK_PREFLIGHT = 'python -I -B tools/validate.py --check-links'
KEY_PREFLIGHT = 'python -I -B tools/secret_scan.py --require --worktree'
PS_EXIT = 'if ($LASTEXITCODE -ne 0) { exit 1 }'
PREFLIGHT_PAIRS = (
    [LINK_PREFLIGHT + ' || exit 1', KEY_PREFLIGHT + ' || exit 1'],
    [LINK_PREFLIGHT, PS_EXIT, KEY_PREFLIGHT, PS_EXIT],
)
UNITTEST_COMMAND = 'python -I -B -m unittest discover -s tools -t . -p "test_*.py"'
VALIDATE_COMMAND = 'python -I -B tools/validate.py'
PYTHON_TOKEN = re.compile(r'(?<![\w.-])(?:python(?:\d+(?:\.\d+)*|w)?|py)(?:\.exe)?(?![\w.-])', re.I)
CANONICAL_TOOL = re.compile(r'^python -I -B tools/(?P<tool>[a-z_]+\.py)(?: [^;&|`$<>\r\n]*)?$')


def fenced_blocks(markdown):
    """Only a sanity parser for canonical preflight pairs, not snapshot coverage."""
    fence, body = '', []
    for line in markdown.splitlines(keepends=True):
        content = line.lstrip(' 	>')
        while True:
            container = re.match(r'(?:[-+*]|\d+[.)])\s+', content)
            if not container:
                break
            content = content[container.end():].lstrip(' 	>')
        marker = re.match(r'(`{3,}|~{3,})', content)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not content[marker.end():].strip():
                yield ''.join(body)
                fence, body = '', []
            else:
                body.append(content)
        elif marker:
            fence, body = marker[1], []
    if fence:
        yield ''.join(body)


def workflow_findings(markdown, writers=None):
    """Deny noncanonical Python lines; never infer shell control-flow semantics."""
    writers = writer_tools() if writers is None else writers
    findings = []
    for number, block in enumerate(fenced_blocks(markdown), 1):
        lines, first_write = block.splitlines(), None
        for index, line in enumerate(lines):
            if not PYTHON_TOKEN.search(line):
                continue
            if line in PREFLIGHT_PAIRS[0] or line in {UNITTEST_COMMAND + ' || exit 1', VALIDATE_COMMAND + ' || exit 1'}:
                continue
            if line in {LINK_PREFLIGHT, KEY_PREFLIGHT, VALIDATE_COMMAND, UNITTEST_COMMAND}:
                if index + 1 >= len(lines) or lines[index + 1] != PS_EXIT:
                    findings.append((number, 'noncanonical PowerShell preflight'))
                continue
            match = CANONICAL_TOOL.fullmatch(line)
            help_flag = any(token.strip('\"\'').split('=', 1)[0] in {'-h', '--help'} for token in line.split())
            if not match or help_flag:
                findings.append((number, 'noncanonical Python command'))
                continue
            write_option = any(token == '--write' or token.startswith('--write-') for token in line.split())
            if first_write is None and (match['tool'] in writers or write_option):
                first_write = index
        if first_write is not None:
            prefix = lines[:first_write]
            if not any(prefix[index:index + len(pair)] == pair
                       for pair in PREFLIGHT_PAIRS for index in range(len(prefix))):
                findings.append((number, 'write without canonical preflight pair'))
    return findings


class RoundTenRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def capture(self, main):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = common.run_cli(main)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_4509085821_cli_redacts_split_output_and_encoded_exceptions(self):
        for number, (_, needle) in enumerate(secret_scan.value_needles(KEY)):
            with self.subTest(form=number), patch.dict(os.environ, {'LAW_OC': KEY}):
                form = needle.decode('utf-8')
                def fail():
                    print(KEY[:10], end='')
                    print(KEY[10:])
                    print(form, file=sys.stderr)
                    raise ValueError('malformed JSON key: ' + form)
                status, stdout, stderr = self.capture(fail)
                self.assertEqual(status, 1)
                self.assertEqual(stdout, '[redacted]')
                self.assertEqual(stderr, '[redacted]')
                self.assertNotIn('Traceback', stdout + stderr)

    def test_cli_preserves_status_and_redacts_argparse_and_systemexit(self):
        with patch.dict(os.environ, {'LAW_OC': KEY}):
            def ordinary():
                print('ordinary result')
                return 7
            self.assertEqual(self.capture(ordinary), (7, 'ordinary result\n', ''))
            def parse():
                argparse.ArgumentParser(prog='synthetic').parse_args(['--unknown', KEY])
            status, stdout, stderr = self.capture(parse)
            self.assertEqual((status, stdout, stderr), (2, '', '[redacted]'))
            def exit_value():
                raise SystemExit(KEY)
            self.assertEqual(self.capture(exit_value), (1, '', '[redacted]'))
            self.assertEqual(self.capture(lambda: KEY), (1, '', '[redacted]'))

    def test_cli_reuses_selected_fallback_without_opening_any_file(self):
        filename = str(self.root / 'never-opened.txt')
        with patch.dict(os.environ, {'LAW_OC': '', 'LAW_OC_FILE': filename}), patch.object(credentials, '_file_selection', (filename, KEY)), patch.object(Path, 'read_text', side_effect=AssertionError('unexpected file read')):
            def fail():
                raise ValueError(KEY.encode().hex())
            self.assertEqual(self.capture(fail), (1, '', '[redacted]'))

    def test_4509085821_real_json_migration_clis_suppress_duplicate_key_tracebacks(self):
        case = self.root / 'cases/synthetic/2020/1.md'
        case.parent.mkdir(parents=True)
        case.write_text('---\nprecSeq: "1"\nprovenance: {"court": "source"}\n---\n', encoding='utf-8')
        source = self.root / 'sources/prec/1.json'
        source.parent.mkdir(parents=True)
        env = dict(os.environ, LAW_OC=KEY, KK_ROOT=str(self.root), LAW_OC_FILE=str(self.root / 'never-opened.txt'))
        forms = [KEY, KEY.encode().hex(), next(needle.decode() for name, needle in secret_scan.value_needles(KEY) if name == 'base64-full')]
        for script in ('restore_source_court.py', 'migrate_source_fields.py'):
            for number, form in enumerate(forms):
                with self.subTest(script=script, form=number):
                    field = json.dumps(form)
                    source.write_text('{' + field + ':1,' + field + ':2}', encoding='utf-8')
                    result = subprocess.run([sys.executable, '-I', '-B', str(common.CODE_ROOT / 'tools' / script)],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(result.stderr, '[redacted]')
                    self.assertNotIn('Traceback', result.stderr)

    def test_repository_reading_cli_entrypoints_use_shared_wrapper(self):
        found = set()
        for path in (common.CODE_ROOT / 'tools').rglob('*.py'):
            if path.name.startswith('test_') or path.name == 'secret_scan.py':
                continue  # Scanner reads bytes, not repository JSON, and has safe errors.
            tree = ast.parse(path.read_text(encoding='utf-8'))
            guards = [node for node in tree.body if isinstance(node, ast.If) and '__main__' in ast.unparse(node.test)]
            for guard in guards:
                found.add(path.name)
                self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                    and node.func.id == 'run_cli' for node in ast.walk(guard)), path.name)
        self.assertEqual(found, {'update_doc_snapshot.py', 'build_review_manifest.py', 'collect_article.py', 'fetch_case.py',
                                 'fetch_interp.py', 'migrate_issue_sections.py', 'migrate_source_fields.py',
                                 'migrate_review_digest.py', 'restore_source_court.py', 'rerender_source.py', 'validate.py',
                                 'vendor_skills.py'})

    def test_4509085821_each_write_workflow_checks_credentials_after_links(self):
        root = common.CODE_ROOT
        actual = document_snapshot(root)
        snapshot = load_snapshot(root)
        # Never give unittest raw records: its automatic diff exposes bodies.
        difference = snapshot_difference(actual, snapshot)
        if difference:
            self.fail(difference)
        # Canonical forms are sanity checks, not a shell interpreter.
        findings = [(path.relative_to(root).as_posix(), finding)
                    for path in checked_documents(root)
                    if path.relative_to(root).parts[0] == 'rules' and path.name == 'SKILL.md'
                    for finding in workflow_findings(read_snapshot_input(path, root).decode('utf-8'))]
        if findings:
            self.fail(secret_scan.redact_diagnostic('\n'.join(
                f'{path} block {number}: {reason}' for path, (number, reason) in findings)))

    def test_4509194492_writers_select_workflows_even_without_any_preflight(self):
        link = 'python -I -B tools/validate.py --check-links || exit 1\n'
        scan = 'python -I -B tools/secret_scan.py --require --worktree || exit 1\n'
        writers = ['migrate_issue_sections.py', 'migrate_source_fields.py',
                   'migrate_review_digest.py', 'collect_article.py', 'fetch_case.py',
                   'fetch_interp.py', 'restore_source_court.py', 'rerender_source.py',
                   'build_review_manifest.py', 'validate.py --write-review']
        def block(commands):
            return '```sh\n' + commands + '```\n'
        for writer in writers:
            write = 'python -I -B tools/' + writer + '\n'
            for unsafe in (write, link + write, scan + link + write,
                           write + link + scan, link + scan.replace(' --worktree', '') + write,
                           link + scan.replace(' || exit 1', '') + write,
                           link.replace(' || exit 1', '') + scan + write):
                with self.subTest(writer=writer, unsafe=unsafe):
                    self.assertTrue(workflow_findings(block(unsafe)))
            self.assertEqual(workflow_findings(block(link + scan + write)), [])
        valid = block(link + scan + 'python -I -B tools/fetch_case.py 1\n')
        self.assertEqual(workflow_findings(valid * 4), [])
        self.assertEqual(workflow_findings(block('python -I -B tools/validate.py || exit 1\n')), [])
        powershell = (link.replace(' || exit 1', '') + PS_EXIT + '\n'
                      + scan.replace(' || exit 1', '') + PS_EXIT + '\n'
                      + 'python -I -B tools/build_review_manifest.py\n')
        self.assertEqual(workflow_findings(block(powershell)), [])

    def test_4509194500_launcher_detection_is_independent_of_required_flags(self):
        for launcher in ('python', 'python3', 'python3.12', 'python.exe', 'py -3', 'py -3.12'):
            for options in ('', '-I', '-B', '-I tools/other.py -B'):
                with self.subTest(launcher=launcher, options=options):
                    commands = python_invocations(launcher + ' ' + options + ' tools/foo.py')
                    self.assertEqual(len(commands), 1)
                    self.assertFalse({'-I', '-B'} <= commands[0]['flags'])
            for options in ('-I -B', '-B -I', '-IB', '-B -X dev -I', '-I -W ignore -B'):
                with self.subTest(launcher=launcher, options=options):
                    commands = python_invocations('run: ' + launcher + ' ' + options + ' tools/foo.py')
                    self.assertEqual(len(commands), 1)
                    self.assertEqual(commands[0]['target'], 'foo.py')
                    self.assertTrue({'-I', '-B'} <= commands[0]['flags'])
        self.assertEqual(len(python_invocations('`python tools/foo.py` and `py -3.12 tools/bar.py`')), 2)
        command = python_invocations('python -B -I -m tools.validate --write-review')[0]
        self.assertEqual((command['target'], command['args']), ('validate.py', ['--write-review']))
        self.assertEqual(python_invocations('Python 환경변수를 무시한다.'), [])
        command = python_invocations(r'py -3.12 -B -I "tools\fetch_case.py" 1')[0]
        self.assertEqual(command['target'], 'fetch_case.py')

    def test_4509194508_captured_child_output_reaches_shared_redactor(self):
        child = 'import os, sys; print(os.environ["LAW_OC"]); print(os.environ["LAW_OC"].encode().hex(), file=sys.stderr)'
        wrapped = (
            'import subprocess, sys\n'
            f'sys.path.insert(0, {str(common.CODE_ROOT / "tools")!r})\n'
            'from common import run_cli\n'
            'def main():\n'
            f'    child = subprocess.run([sys.executable, "-I", "-B", "-c", {child!r}], capture_output=True, text=True)\n'
            '    print(child.stdout, end="")\n'
            '    print(child.stderr, end="", file=sys.stderr)\n'
            '    return child.returncode\n'
            'sys.exit(run_cli(main))\n'
        )
        result = subprocess.run([sys.executable, '-I', '-B', '-c', wrapped],
                                env=dict(os.environ, LAW_OC=KEY), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((result.stdout, result.stderr), ('[redacted]', '[redacted]'))

    def test_4509101484_test_subprocess_invocations_disable_bytecode(self):
        findings = []
        for path in (common.CODE_ROOT / 'tools').rglob('test_*.py'):
            findings.extend((path.name, line) for line in test_launcher_findings(path.read_text(encoding='utf-8')))
        self.assertEqual(findings, [])

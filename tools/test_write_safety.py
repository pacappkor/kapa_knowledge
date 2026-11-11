# SPDX-License-Identifier: GPL-3.0-only
"""All production tool writes must pass the shared repository path guard."""
import ast
from contextlib import redirect_stdout
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
import build_review_manifest
import common
import fetch_material
import migrate_issue_sections


# Only these read-only Git command forms may bypass repository write sinks.
# New options need explicit review; in particular --output, --exec-path, -c,
# --ext-diff, --textconv and config writes are not accepted.
READ_ONLY_GIT = {
    'ls-files': {'-s', '-z', '--cached', '--others', '--exclude-standard'},
    'cat-file': {'-e', '-p', '-t', '-s', '--batch'},
    'rev-parse': {'--verify', '--show-toplevel', '--show-prefix', '--git-dir'},
    'ls-tree': {'-r', '-z', '--', '--name-only', '--full-tree'},
}


GIT_PREFIX = ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false']


def read_only_git_call(call):
    keywords = {item.arg: item.value for item in call.keywords}
    allowed_keywords = {'args', 'shell', 'check', 'capture_output', 'stdout', 'stderr',
                        'text', 'encoding', 'errors', 'input', 'timeout', 'cwd', 'env'}
    if len(call.args) > 1 or not set(keywords) <= allowed_keywords or ('shell' in keywords and not (
            isinstance(keywords['shell'], ast.Constant) and keywords['shell'].value is False)):
        return False
    argv = call.args[0] if call.args else keywords.get('args')
    if not isinstance(argv, (ast.List, ast.Tuple)) or any(isinstance(item, ast.Starred) for item in argv.elts):
        return False
    items = argv.elts
    def literal(index):
        return items[index].value if index < len(items) and isinstance(items[index], ast.Constant) else None
    if [literal(index) for index in range(len(GIT_PREFIX))] != GIT_PREFIX:
        return False
    if 'env' not in keywords or ast.unparse(keywords['env']) != 'child_environment()':
        return False
    index = len(GIT_PREFIX)
    while index < len(items):
        option = literal(index)
        if option == '-C' and index + 1 < len(items):
            index += 2
        elif option == '--no-replace-objects':
            index += 1
        else:
            break
    command = literal(index)
    if command not in READ_ONLY_GIT:
        return False
    index += 1
    if command == 'cat-file':
        mode = literal(index)
        if mode == '--batch':
            return len(items) == index + 1
        if mode not in {'-e', '-t', '-s', '-p'} or len(items) != index + 2:
            return False
    # Dynamic positional values (repository paths/object IDs) remain trusted
    # code, not arbitrary shell fragments. Dynamic argv expansion is forbidden.
    def static_prefix(item):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            return item.value
        if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Add):
            return static_prefix(item.left)
        if isinstance(item, ast.JoinedStr) and item.values:
            return static_prefix(item.values[0])
        return ''
    return all(not (static_prefix(item).startswith('-') and not (
                    isinstance(item, ast.Constant) and item.value in READ_ONLY_GIT[command]))
               for item in items[index:])


def helper_git_call(call):
    """Callers cannot replace the fixed prefix, child environment or capture policy."""
    if len(call.args) != 2 or any(kw.arg != 'text' or not isinstance(kw.value, ast.Constant)
                                or type(kw.value.value) is not bool for kw in call.keywords):
        return False
    argv = call.args[1]
    if not isinstance(argv, (ast.List, ast.Tuple)):
        return False
    synthetic = ast.parse("subprocess.run([], env=child_environment())").body[0].value
    synthetic.args[0] = ast.List(elts=[ast.Constant(item) for item in GIT_PREFIX] + list(argv.elts))
    return read_only_git_call(synthetic)


def hardened_helper_child(call):
    # Only this exact dynamic child form is trusted, only inside git_read.run_git.
    expected = ast.parse("subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', "
                         "'core.untrackedCache=false', '-c', 'protocol.allow=never', "
                         "'--no-replace-objects', '-C', str(root), *args], "
                         "check=True, capture_output=True, text=text, env=child_environment())").body[0].value
    return ast.dump(call, include_attributes=False) == ast.dump(expected, include_attributes=False)


def direct_writes(source, filename, *, check_files=True):
    """Regression aid for direct filesystem/child calls, including import aliases.

    Routine edits must keep using safe_write_* and captured child output. This
    is not alias dataflow or a sandbox: deliberate rebinding/evasion is trusted
    repository code covered by PR review under README's threat model.
    """
    tree = ast.parse(source)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or '') + '.' + item.name

    def qualified(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return qualified(node.value) + '.' + node.attr
        return ''

    methods = {'write', 'writelines', 'truncate', 'touch', 'mkdir', 'chmod', 'lchmod',
               'unlink', 'rmdir', 'rename', 'symlink_to', 'hardlink_to', 'link_to'}
    mutations = {
        'os.' + name for name in (
            'open', 'fdopen', 'write', 'writev', 'pwrite', 'pwritev', 'truncate', 'ftruncate',
            'remove', 'unlink', 'rmdir', 'removedirs', 'rename', 'renames', 'replace',
            'symlink', 'link', 'mkdir', 'makedirs', 'mknod', 'mkfifo', 'chmod', 'fchmod',
            'lchmod', 'chown', 'fchown', 'lchown', 'utime')
    } | {'shutil.rmtree', 'shutil.move', 'shutil.chown', 'tempfile.mkstemp',
         'tempfile.mkdtemp', 'tempfile.TemporaryDirectory', 'tempfile.NamedTemporaryFile',
         'tempfile.TemporaryFile', 'tempfile.SpooledTemporaryFile'}
    allowed = {'safe_write_bytes': {'write_bytes', 'mkdir'},
               'staged_files': {'mkdir', 'unlink', 'os.replace', 'tempfile.mkstemp'}}
    findings = []

    class Visitor(ast.NodeVisitor):
        scope = ''
        def visit_FunctionDef(self, node):
            old = self.scope
            self.scope = node.name
            self.generic_visit(node)
            self.scope = old
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            name = qualified(node.func)
            leaf = node.func.attr if isinstance(node.func, ast.Attribute) else name.rsplit('.', 1)[-1]
            sink = (name if name in mutations or name.startswith('shutil.copy')
                    else leaf if leaf in methods or leaf.startswith('write_') else None)
            # A bound Path.replace takes one target, whereas str.replace takes
            # old/new arguments. Also cover explicit unbound Path.replace calls.
            if leaf == 'replace' and (len(node.args) < 2
                    or any(isinstance(arg, ast.Starred) for arg in node.args)
                    or name in {'pathlib.Path.replace', 'pathlib.PosixPath.replace', 'pathlib.WindowsPath.replace'}):
                sink = sink or 'replace'
            if leaf == 'open':
                method = isinstance(node.func, ast.Attribute) and name not in {'io.open', 'builtins.open', 'codecs.open'}
                position = 0 if method else 1
                mode = next((kw.value for kw in node.keywords if kw.arg == 'mode'),
                            node.args[position] if len(node.args) > position else ast.Constant('r'))
                if not isinstance(mode, ast.Constant) or mode.value not in {'r', 'rb', 'rt'}:
                    sink = 'open'
            if check_files and sink and not (filename == 'common.py' and sink in allowed.get(self.scope, set())):
                findings.append((node.lineno, sink))
            alternative_child = (name in {'os.system', 'os.popen', 'pty.spawn',
                'asyncio.create_subprocess_exec', 'asyncio.create_subprocess_shell',
                'subprocess.getoutput', 'subprocess.getstatusoutput'}
                or name.startswith(('os.exec', 'os.spawn', 'os.posix_spawn'))
                or isinstance(node.func, ast.Attribute) and leaf in {'subprocess_exec', 'subprocess_shell'})
            if alternative_child:
                # No alternative child API is allowlisted, including in tests.
                findings.append((node.lineno, name + ' child API is not allowlisted'))
            if check_files and name == 'git_read.run_git' and not helper_git_call(node):
                findings.append((node.lineno, 'Git helper command is not allowlisted'))
            if name in {'subprocess.run', 'subprocess.call', 'subprocess.check_call',
                        'subprocess.check_output', 'subprocess.Popen'}:
                if check_files and not (filename == 'git_read.py' and self.scope == 'run_git'
                                        and hardened_helper_child(node)):
                    findings.append((node.lineno, name + ' must use hardened Git helper'))
                keywords = {item.arg: item.value for item in node.keywords}
                capture = keywords.get('capture_output')
                captured = (name == 'subprocess.run' and isinstance(capture, ast.Constant)
                            and capture.value is True)
                stdout = qualified(keywords.get('stdout'))
                stderr = qualified(keywords.get('stderr'))
                # check_output always captures stdout and rejects a stdout kwarg.
                output_safe = name == 'subprocess.check_output' or stdout in {'subprocess.PIPE', 'subprocess.DEVNULL'}
                if not captured and not (output_safe and stderr in {
                        'subprocess.PIPE', 'subprocess.DEVNULL', 'subprocess.STDOUT'}):
                    findings.append((node.lineno, name + ' inherits stdio'))
            self.generic_visit(node)

    Visitor().visit(tree)
    return findings


def production_write_findings(tools):
    """Only discoverable tests outside production's import closure get exemptions."""
    tools = Path(tools)
    sources = {path: path.read_text(encoding='utf-8') for path in sorted(tools.rglob('*.py'))}
    modules = {'.'.join(path.relative_to(tools).with_suffix('').parts).removesuffix('.__init__'): path
               for path in sources}
    discovered = set()
    # unittest discover recurses only into packages; it matches test_*.py.
    for path in sources:
        if not path.name.startswith('test_') or not path.stem.isidentifier():
            continue
        parts = path.relative_to(tools).parts[:-1]
        parents = [tools.joinpath(*parts[:index]) for index in range(len(parts) + 1)]
        if all((parent / '__init__.py').is_file() for parent in parents):
            discovered.add(path)
    imports, test_imports = {}, {}
    for path, source in sources.items():
        edges, test_lines = [], set()
        package = list(path.relative_to(tools).parts[:-1])
        for node in ast.walk(ast.parse(source)):
            names = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = '.'.join(prefix + ([node.module] if node.module else []))
                names = [base] + ['.'.join(filter(None, [base, item.name])) for item in node.names]
            for name in names:
                # Reject test-named imports even if runtime sys.path resolution
                # is outside this small local module graph.
                if any(part.startswith('test_') for part in name.split('.')):
                    test_lines.add(node.lineno)
                name = name.removeprefix(tools.name + '.')
                for module, target in modules.items():
                    if name == module or name.startswith(module + '.'):
                        edges.append((target, node.lineno))
        imports[path], test_imports[path] = edges, test_lines
    production = set(sources) - discovered
    while True:
        reached = {target for path in production for target, _ in imports[path]}
        if reached <= production:
            break
        production |= reached
    findings = []
    for path, source in sources.items():
        relative = path.relative_to(tools).as_posix()
        if path in production:
            findings.extend((relative, line, 'production imports test-named module')
                            for line in sorted(test_imports[path]))
        findings.extend((relative, line, sink) for line, sink in direct_writes(
            source, relative, check_files=path in production))
    return findings


class WriteSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('KK_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.sentinel = self.base / 'outside.json'
        self.sentinel.write_text('sentinel', encoding='utf-8')
        root_patch = patch.object(common, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def manifest_arguments(self, output):
        return ['--repository', str(self.root), '--commit', 'synthetic', '--output', str(output)]

    def test_4508981672_manifest_mocked_symlink_refused_before_open(self):
        output = self.root / 'pilot-review-manifest.json'
        original = Path.lstat
        def metadata(path, *args, **kwargs):
            if path == output:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', metadata), patch.object(build_review_manifest, 'build') as build, patch.object(Path, 'write_bytes') as write:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                build_review_manifest.main(self.manifest_arguments(output))
            build.assert_not_called()
            write.assert_not_called()
        self.assertEqual(self.sentinel.read_text(encoding='utf-8'), 'sentinel')

    def test_manifest_real_symlink_does_not_change_outside_file(self):
        output = self.root / 'pilot-review-manifest.json'
        try:
            output.symlink_to(self.sentinel)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable; mocked manifest test remains active')
        with patch.object(build_review_manifest, 'build', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                build_review_manifest.main(self.manifest_arguments(output))
        self.assertEqual(self.sentinel.read_text(encoding='utf-8'), 'sentinel')

    def test_manifest_normal_output_and_outside_rejection(self):
        output = self.root / 'pilot-review-manifest.json'
        with patch.object(build_review_manifest, 'build', return_value=[]), redirect_stdout(io.StringIO()):
            self.assertEqual(build_review_manifest.main(self.manifest_arguments(output)), 0)
        self.assertEqual(output.read_bytes(), b'[]\n')
        with patch.object(build_review_manifest, 'build') as build:
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                build_review_manifest.main(self.manifest_arguments(self.sentinel))
            build.assert_not_called()
        self.assertEqual(self.sentinel.read_text(encoding='utf-8'), 'sentinel')

    def test_all_common_sinks_refuse_reparse_and_outside_paths(self):
        output = self.root / 'target.json'
        output.write_text('', encoding='utf-8')
        original = Path.lstat
        def metadata(path, *args, **kwargs):
            if path == output:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        sinks = [lambda path: common.safe_write_bytes(path, b'new'),
                 lambda path: common.safe_write_text(path, 'new'),
                 lambda path: common.save_json(path, {'new': True}),
                 lambda path: common.add_relations([], path=path)]
        for number, sink in enumerate(sinks):
            with self.subTest(sink=number), patch.object(Path, 'lstat', metadata), patch.object(Path, 'write_bytes') as write:
                with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                    sink(output)
                write.assert_not_called()
            # add_relations reads its prior rows first, so use a missing outside
            # output rather than a deliberately non-JSON sentinel for this case.
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                sink(self.base / 'new.json')
        self.assertEqual(output.read_text(encoding='utf-8'), '')

    def test_migration_and_rerender_refuse_link_targets(self):
        path = self.root / 'issues/legacy.md'
        path.parent.mkdir()
        path.write_text(fetch_material.BEGIN + '\nmanual\n' + fetch_material.END + '\n', encoding='utf-8')
        original = Path.lstat
        def metadata(candidate, *args, **kwargs):
            if candidate == path:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
            return original(candidate, *args, **kwargs)
        before = path.read_bytes()
        with patch.object(Path, 'lstat', metadata), patch.object(fetch_material, 'ROOT', self.root):
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                migrate_issue_sections.migrate(self.root)
            with self.assertRaisesRegex(ValueError, 'Unsafe output path'):
                fetch_material.rerender_saved(path)
        self.assertEqual(path.read_bytes(), before)

    def test_production_tools_have_no_unchecked_direct_file_writes(self):
        self.assertEqual(production_write_findings(common.CODE_ROOT / 'tools'), [])

    def test_direct_write_guard_catches_future_bypass_styles(self):
        examples = ['path.write_text("unsafe")', 'path.write_bytes(b"unsafe")',
                    'open("path", "w")', 'Path("path").open(mode="a")',
                    'from builtins import open as out\nout("path", "x")',
                    'import os as ops\nops.open("path", 0)',
                    'from shutil import copyfile as cp\ncp("a", "b")']
        for number, source in enumerate(examples):
            with self.subTest(style=number):
                self.assertTrue(direct_writes(source, 'new_tool.py'))
        self.assertEqual(direct_writes('open("path", "rb")\nsafe_write_text(path, "safe")', 'new_tool.py'), [])

    def test_4509085838_destructive_and_link_sinks_are_guarded(self):
        examples = [f'os.{name}("outside", 0)' for name in (
            'truncate', 'ftruncate', 'remove', 'unlink', 'rename', 'replace', 'symlink',
            'link', 'mkdir', 'makedirs', 'removedirs', 'renames')]
        examples += [f'shutil.{name}("outside")' for name in (
            'rmtree', 'move', 'copy', 'copy2', 'copyfile', 'copyfileobj', 'copytree', 'copymode', 'copystat')]
        examples += [f'path.{name}("outside")' for name in (
            'unlink', 'rename', 'replace', 'symlink_to', 'hardlink_to', 'touch', 'mkdir',
            'write_text', 'write_bytes')]
        examples += ['from os import symlink as link_out\nlink_out("a", "b")',
                     'import shutil as files\nfiles.rmtree("outside")',
                     'from pathlib import Path as P\nP.replace(source, target)',
                     'Path("source").replace("outside")']
        for number, source in enumerate(examples):
            with self.subTest(style=number):
                self.assertTrue(direct_writes(source, 'new_tool.py'))
        self.assertEqual(direct_writes('text.replace("old", "new")', 'new_tool.py'), [])
        self.assertTrue(direct_writes('def staged_files():\n    os.truncate("outside", 0)', 'common.py'))

    def test_4509085850_recursive_guard_catches_nested_modules(self):
        tools = self.root / 'tools'
        helpers = tools / 'helpers'
        helpers.mkdir(parents=True)
        (helpers / 'export.py').write_text('path.write_text("unsafe")\n', encoding='utf-8')
        (helpers / 'test_fixture.py').write_text('path.write_text("fixture")\n', encoding='utf-8')
        # A nested module with the trusted basename does not inherit its allowlist.
        (helpers / 'common.py').write_text('def safe_write_bytes():\n    path.write_bytes(b"unsafe")\n', encoding='utf-8')
        self.assertEqual({row[0] for row in production_write_findings(tools)},
                         {'helpers/common.py', 'helpers/export.py', 'helpers/test_fixture.py'})

    def test_4509194508_children_cannot_inherit_output_descriptors(self):
        for api in ('run', 'call', 'check_call', 'check_output', 'Popen'):
            for options in ('', ', stdout=subprocess.PIPE', ', stderr=subprocess.PIPE'):
                with self.subTest(api=api, options=options):
                    source = f'import subprocess\nsubprocess.{api}(["git"]{options})'
                    # check_output captures stdout intrinsically; explicit stderr
                    # capture is sufficient for this API, unlike the other four.
                    expected = not (api == 'check_output' and options == ', stderr=subprocess.PIPE')
                    self.assertEqual(bool(direct_writes(source, 'test_child.py', check_files=False)), expected)
        safe = [
            'import subprocess as sp\nsp.run(["git"], capture_output=True)',
            'from subprocess import run as child\nchild(["git"], capture_output=True)',
            'from subprocess import PIPE, DEVNULL, Popen\nPopen(["git"], stdout=PIPE, stderr=DEVNULL)',
            'import subprocess\nsubprocess.run(["git"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)',
        ]
        for source in safe:
            self.assertEqual(direct_writes(source, 'test_child.py', check_files=False), [])
        self.assertTrue(direct_writes('from subprocess import run as child\nchild(["git"])', 'child.py'))
        self.assertTrue(direct_writes('import subprocess\nsubprocess.run(["git"], capture_output=False)', 'child.py'))

    def test_cheap_tracked_link_cli_requires_no_dependency_or_credential(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)
        script = common.CODE_ROOT / 'tools/validate.py'
        env = dict(os.environ, KK_ROOT=str(self.root), **{'LAW_O' + 'C': ''}, LAW_OC_FILE=str(self.base / 'never-read.txt'))
        def run():
            return subprocess.run([sys.executable, '-I', '-B', str(script), '--check-links'],
                                  cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(run().returncode, 0)
        oid = subprocess.run(['git', '-C', str(self.root), 'hash-object', '-w', '--stdin'],
                             input=b'../outside.json', check=True, capture_output=True).stdout.decode().strip()
        subprocess.run(['git', '-C', str(self.root), 'update-index', '--add', '--cacheinfo',
                        f'120000,{oid},pilot-review-manifest.json'], check=True, capture_output=True)
        result = run()
        self.assertEqual(result.returncode, 1)
        self.assertIn('tracked symlinks are not allowed', result.stdout)
        self.assertEqual(result.stderr, '')

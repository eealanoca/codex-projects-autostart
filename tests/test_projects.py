import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
projects = load('projects')
configure = load('configure')


def fixture(root):
    project = {'id': 'local-one', 'name': 'Example project', 'rootPaths': [str(root / 'folder with spaces')]}
    return {'local-projects': {}, 'project-order': [], 'unrelated': {'preserve': True},
            'electron-account-renderer-state-v1': {'owner': 'current', 'inactive': {'other': {'globals': {
                'local-projects': {'local-one': project, 'g-p-cloud': {'name': 'Cloud project', 'rootPaths': [str(root / 'cloud')]}},
                'thread-project-assignments': {'thread-one': {'projectKind': 'local', 'projectId': 'local-one'}},
                'thread-project-membership-host-ids': {'thread-one': 'local'},
                'app-server-project-id-by-legacy-project-id-by-host': {'local:example': {'local-one': 'server-one'}}}}}}}


class ProjectTests(unittest.TestCase):
    def test_merge_preserves_state_and_excludes_cloud(self):
        original = fixture(Path('/example'))
        saved = copy.deepcopy(original)
        merged, added = projects.merge_state(original)
        self.assertEqual(original, saved)
        self.assertEqual(added, ['Example project'])
        self.assertEqual(merged['unrelated'], original['unrelated'])
        self.assertNotIn('g-p-cloud', merged['local-projects'])
        self.assertEqual(merged['thread-project-assignments']['thread-one']['projectId'], 'local-one')
        self.assertEqual(projects.merge_state(merged)[0], merged)

    def test_existing_membership_and_completed_migration_preserved(self):
        state = fixture(Path('/example'))
        state['thread-project-assignments'] = {'thread-one': {'projectKind': 'local', 'projectId': 'different-project'}}
        state['app-server-projects-migration-by-host'] = {'local:example': {'threadAssignmentsMigrated': True}}
        merged, _ = projects.merge_state(state)
        self.assertEqual(merged['thread-project-assignments'], state['thread-project-assignments'])
        self.assertTrue(merged['app-server-projects-migration-by-host']['local:example']['threadAssignmentsMigrated'])

    def test_conflicting_roots_and_unknown_schema_rejected(self):
        state = fixture(Path('/example'))
        state['local-projects']['local-one'] = {'rootPaths': ['/different']}
        with self.assertRaises(ValueError):
            projects.merge_state(state)
        with self.assertRaises(ValueError):
            projects.merge_state({'unexpected': {}})

    def test_closed_app_restore_creates_exact_backup_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'codex'; home.mkdir()
            state = fixture(root)
            path = home / '.codex-global-state.json'
            raw = json.dumps(state).encode()
            path.write_bytes(raw)
            with patch.object(projects, 'app_running', return_value=False):
                result = projects.restore(home, apply=True, storage=root / 'private')
                self.assertTrue(result['changed'])
                self.assertEqual(Path(result['backup']).read_bytes(), raw)
                self.assertFalse(projects.restore(home, apply=True, storage=root / 'private')['changed'])
            self.assertEqual(projects.catalog(home, root / 'catalog'), 2)
            self.assertIn('PROJECTS.md', [p.name for p in (root / 'catalog').iterdir()])

    def test_running_app_and_concurrent_change_block_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / '.codex-global-state.json'
            raw = json.dumps(fixture(root)).encode(); path.write_bytes(raw)
            with patch.object(projects, 'app_running', return_value=True):
                with self.assertRaises(RuntimeError):
                    projects.restore(root, apply=True, storage=root / 'private')
            self.assertEqual(path.read_bytes(), raw)
            with patch.object(projects, 'app_running', side_effect=[False, True]):
                with self.assertRaises(RuntimeError):
                    projects.restore(root, apply=True, storage=root / 'private')
            self.assertEqual(path.read_bytes(), raw)

    def test_detector_distinguishes_desktop_from_cli(self):
        for executable in ['/usr/lib/chatgpt/ChatGPT', '/Applications/Codex.app/Contents/MacOS/Codex']:
            self.assertTrue(projects.is_app_executable(executable))
        self.assertFalse(projects.is_app_executable('/usr/lib/chatgpt/resources/codex'))
        self.assertFalse(projects.is_app_executable('/usr/local/bin/codex'))

    def test_install_remove_and_login_precedence(self):
        with tempfile.TemporaryDirectory(prefix='codex test ') as directory:
            root = Path(directory)
            (root / '.bash_profile').write_text('# Existing login configuration\n')
            (root / '.bashrc').write_text('# Existing interactive configuration\n')
            env = {'HOME': str(root), 'XDG_CONFIG_HOME': str(root / '.config'), 'XDG_DATA_HOME': str(root / '.local/share'), 'XDG_STATE_HOME': str(root / '.local/state')}
            with patch.dict(os.environ, env), patch.object(configure.subprocess, 'run') as run:
                run.return_value.returncode = 0
                with patch('sys.argv', ['configure.py', '--no-start']):
                    configure.main(); configure.main()
                self.assertEqual((root / '.bash_profile').read_text().count(configure.START), 1)
                self.assertFalse((root / '.profile').exists())
                self.assertTrue((root / '.config/systemd/user/codex-projects-autostart.service').exists())
                with patch('sys.argv', ['configure.py', '--remove']):
                    configure.main()
                self.assertEqual((root / '.bash_profile').read_text(), '# Existing login configuration\n')
                self.assertEqual((root / '.bashrc').read_text(), '# Existing interactive configuration\n')
                self.assertFalse((root / '.config/systemd/user/codex-projects-autostart.service').exists())


if __name__ == '__main__':
    unittest.main()

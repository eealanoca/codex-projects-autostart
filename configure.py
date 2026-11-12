#!/usr/bin/env python3
"""Install or disable per-user startup integration without administrator access."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import subprocess
import sys

START = '# >>> codex-projects-autostart >>>'
END = '# <<< codex-projects-autostart <<<'


def strip_hook(text):
    if START not in text and END not in text:
        return text
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('Ambiguous shell startup block; file left unchanged')
    begin = text.index(START)
    finish = text.index(END, begin) + len(END)
    if text[finish:finish + 1] == '\n':
        finish += 1
    return text[:begin] + text[finish:]


def systemd_quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove', action='store_true', help='Disable startup integration; keep data and backups')
    parser.add_argument('--codex-home', type=Path, help='Override the Codex data directory')
    parser.add_argument('--no-start', action='store_true', help='Install startup entries without launching the worker now')
    args = parser.parse_args()
    if sys.version_info < (3, 9) or sys.platform not in ('linux', 'darwin'):
        parser.error('Linux or macOS with Python 3.9+ is required')
    home = Path.home()
    source = Path(__file__).resolve().parent
    install = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) / 'codex-projects-autostart'
    storage = Path(os.environ.get('XDG_STATE_HOME', str(home / '.local/state'))) / 'codex-projects-autostart'
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    backups = storage / 'setup-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    def write(path, content):
        if path.is_symlink():
            raise ValueError('Refusing to overwrite a symbolic link: ' + str(path))
        old = path.read_text() if path.exists() else None
        if old == content:
            return
        backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        if old is not None:
            shutil.copy2(path, backups / (str(path.relative_to(home)).replace('/', '__') if path.is_relative_to(home) else path.name))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    def remove(path):
        if path.exists():
            if path.is_symlink():
                raise ValueError('Refusing to remove a symbolic link: ' + str(path))
            backups.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, backups / path.name)
            path.unlink()
    launcher = shlex.quote(str(install / 'start.sh'))
    bash = shutil.which('bash')
    if not bash:
        parser.error('Bash is required')
    unit_name = 'codex-projects-autostart.service'
    unit_path = config_home / 'systemd/user' / unit_name
    desktop_path = config_home / 'autostart/codex-projects-autostart.desktop'
    plist_path = home / 'Library/LaunchAgents/io.github.codex-projects-autostart.plist'
    # Preserve the existing Bash login-file precedence.
    login = next((home / p for p in ('.bash_profile', '.bash_login') if (home / p).exists()), home / '.profile')
    shell_paths = {login, home / '.bashrc', home / '.zprofile'}
    if args.remove:
        shell_paths.update(home / p for p in ('.profile', '.bash_profile', '.bash_login'))
    for path in shell_paths:
        old = path.read_text() if path.exists() else ''
        clean = strip_hook(old)
        block = START + '\n' + shlex.quote(bash) + ' ' + launcher + ' >/dev/null 2>&1 &\n' + END + '\n'
        content = clean if args.remove else clean + ('' if not clean or clean.endswith('\n') else '\n') + block
        if content != old:
            write(path, content)
    if args.remove:
        if shutil.which('systemctl'):
            subprocess.run(['systemctl', '--user', 'disable', '--now', unit_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sys.platform == 'darwin':
            subprocess.run(['launchctl', 'bootout', 'gui/' + str(os.getuid()), str(plist_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lock = storage / 'worker.lock'
        if lock.exists():
            try:
                pid = int(lock.read_text().strip())
                command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'args='], text=True)
                if str(install / 'projects.py') in command and 'watch' in command:
                    os.kill(pid, signal.SIGTERM)
            except (ValueError, ProcessLookupError, subprocess.CalledProcessError):
                pass
        for path in (unit_path, desktop_path, plist_path):
            remove(path)
        if shutil.which('systemctl'):
            subprocess.run(['systemctl', '--user', 'daemon-reload'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('Startup disabled. Local catalogs and backups were kept in ' + str(storage))
        return
    install.mkdir(parents=True, exist_ok=True)
    for name in ('projects.py', 'configure.py', 'install.sh', 'start.sh', 'README.md'):
        if (source / name).resolve() != (install / name).resolve():
            shutil.copy2(source / name, install / name)
    for name in ('install.sh', 'start.sh'):
        (install / name).chmod(0o755)
    codex_home = (args.codex_home or Path(os.environ.get('CODEX_HOME') or home / '.codex')).expanduser().resolve()
    write(storage / 'config.json', json.dumps({'codex_home': str(codex_home)}, indent=2) + '\n')
    started = False
    if sys.platform == 'linux':
        unit = '[Unit]\nDescription=Restore local Codex projects across saved profiles\n\n[Service]\nType=simple\nExecStart=' + systemd_quote(bash) + ' ' + systemd_quote(str(install / 'start.sh')) + '\nRestart=on-failure\nRestartSec=15\n'
        for key, value in (('XDG_STATE_HOME', str(storage.parent)), ('CODEX_PROJECTS_PYTHON', sys.executable)):
            unit += 'Environment=' + systemd_quote(key + '=' + value) + '\n'
        unit += '\n[Install]\nWantedBy=default.target\n'
        write(unit_path, unit)
        # A desktop entry also covers sessions without a user systemd manager.
        desktop_exec = '"' + bash.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '" "' + str(install / 'start.sh').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        write(desktop_path, '[Desktop Entry]\nType=Application\nName=Codex Projects Autostart\nExec=' + desktop_exec + '\nTerminal=false\nStartupNotify=false\n')
        if shutil.which('systemctl'):
            reload_result = subprocess.run(['systemctl', '--user', 'daemon-reload'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if reload_result.returncode == 0:
                command = ['systemctl', '--user', 'enable'] + ([] if args.no_start else ['--now']) + [unit_name]
                started = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    else:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'Label': 'io.github.codex-projects-autostart', 'ProgramArguments': [bash, str(install / 'start.sh')], 'RunAtLoad': True, 'EnvironmentVariables': {'XDG_STATE_HOME': str(storage.parent), 'CODEX_PROJECTS_PYTHON': sys.executable}}
        write(plist_path, plistlib.dumps(payload).decode())
        if not args.no_start:
            subprocess.run(['launchctl', 'bootout', 'gui/' + str(os.getuid()), str(plist_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            started = subprocess.run(['launchctl', 'bootstrap', 'gui/' + str(os.getuid()), str(plist_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not args.no_start and not started:
        env = os.environ.copy()
        env['CODEX_PROJECTS_PYTHON'] = sys.executable
        subprocess.Popen([bash, str(install / 'start.sh')], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)
    print('Installed in ' + str(install))
    print('Startup enabled for this user. Restoration waits while the desktop app is open.')
    print('Log: ' + str(storage / 'worker.log'))
    print('Catalog: ' + str(storage / 'PROJECTS.md'))


if __name__ == '__main__':
    main()

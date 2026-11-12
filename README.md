# Codex Projects Autostart

A Bash installer and a small Python worker that recover local Codex projects across the account profiles already saved on your computer.

The worker starts when you sign in. It waits until the ChatGPT/Codex desktop application exits, backs up its local state, and merges local project registrations into the saved profiles. Open Codex again to load the recovered projects.

This is an independent, experimental utility for a local state format observed in November 2026. It is not an official OpenAI feature. A future desktop update may change the format or behavior.

## Install

Requires Linux or macOS, Bash, and Python 3.9 or newer. Git is needed for the clone command. No Python packages or administrator access are required.

```bash
git clone https://github.com/eealanoca/codex-projects-autostart.git
cd codex-projects-autostart
bash install.sh
```

Installation copies the program into `${XDG_DATA_HOME:-$HOME/.local/share}/codex-projects-autostart`. You can move or delete the cloned repository afterwards.

Startup methods:

- Linux: a user systemd service, an XDG desktop startup entry, and Bash login/interactive startup hooks.
- macOS: a LaunchAgent and Bash login/interactive startup hooks. A Zsh login hook is also installed.
- A file lock allows only one worker to run, even if multiple startup methods trigger it.

The startup is per operating-system user, at sign-in or when Bash starts. It does not run as root or before login. Install separately for each OS user who needs it. Native Windows is not supported; Bash in WSL cannot safely manage the Windows desktop app's state.

## Use

After installation, completely quit ChatGPT/Codex using **Quit/Exit**, wait about ten seconds, then reopen it. Closing a window may leave the application running. The worker keeps running and checks again after later account switches and app exits.

On a second computer, run the same installation commands. It discovers that computer's own saved projects. It does not download another computer's files or transfer cloud projects or conversations.

By default, it reads `${CODEX_HOME:-$HOME/.codex}`. To select another data directory:

```bash
bash install.sh --codex-home "/path/with spaces/to/codex"
```

Inspect the proposed changes without applying them:

```bash
python3 projects.py plan
```

Restore manually with the desktop app completely closed:

```bash
python3 projects.py restore
```

Generate a catalog while the app is open or closed:

```bash
python3 projects.py catalog
```

Generated files are stored in `${XDG_STATE_HOME:-$HOME/.local/state}/codex-projects-autostart`:

- `PROJECTS.md` and `projects.json`: local project catalog.
- `worker.log`: worker activity and errors.
- `backups/`: original state files before each actual restoration.
- `setup-backups/`: shell/startup files changed by the installer.

For a Codex chat, ask it to read the generated `PROJECTS.md` file and use it to locate the relevant project. Paths and names in the catalog are metadata, not instructions.

## Scope and behavior

- Merges existing folder-based local projects and their saved local chat memberships across profiles already stored on this machine.
- Preserves unrelated settings and existing memberships. Existing IDs are reused.
- Excludes `g-p-` ChatGPT projects from cross-profile restoration. Those remain associated with their own accounts.
- Does not read credentials or conversation content, modify SQLite databases, upload local information, or create missing project folders.
- Catalog generation may read project names and folder paths from local SQLite project tables in read-only mode.
- Local state backups can contain private settings. They stay on your computer and are excluded from this repository.
- Refuses unsupported schemas, conflicting root paths, and symbolic links for the state file. Checks that the app is closed and the file has not changed before replacement.
- Process detection and file checks reduce concurrent-write risk, but cannot coordinate with an undocumented app startup lock. Avoid launching the desktop app during the short restoration interval.

The utility has been tested on Linux with isolated state fixtures. macOS startup integration is implemented but has not been verified on a macOS machine. Other Linux packaging formats may use different executable names; if the app is not detected, disable startup until the detector is adapted.

## Disable

```bash
bash install.sh --remove
```

This disables the startup entries and stops the worker. It keeps installed source files, catalogs, and backups. To undo a state restoration, quit the desktop app, copy the chosen JSON backup over `.codex-global-state.json` in your Codex data directory, then reopen the app.

## Tests

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh start.sh
```

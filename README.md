# TmuxPilot

Lightweight Windows GUI for managing remote tmux sessions over SSH. Replace `Ctrl-b` keyboard shortcuts with clickable UI controls.

```
+------------------+-----------------------------------------------+
| CONNECTIONS      |  Window Tabs: [ 0:bash ] [ 1:vim ] [ 2:htop ] |
|                  +-----------------------------------------------+
| > server1 (3)   |  +-------------------+  +-------------------+  |
|   main (2 win)  |  |  %1 bash          |  |  %2 python        |  |
|   dev  (4 win)  |  |  $ ls -la         |  |  >>> import torch  |  |
|                  |  |  drwxr-x 2 user   |  |  >>> model = ...   |  |
| > server2 (1)   |  |  $ _              |  |  >>>               |  |
|   work (3 win)  |  +-------------------+  +-------------------+  |
|                  |  +-------------------------------------------+ |
|                  |  |  %3 tail -f /var/log/syslog               | |
|                  |  |  Apr 10 12:34:56 server1 kernel: [...]    | |
|                  |  +-------------------------------------------+ |
+------------------+-----------------------------------------------+
```

## Features

- **Session navigation** -- tree view of servers, sessions, and windows; click to switch
- **Window tabs** -- tab bar mirroring tmux windows in the active session
- **Pane layout** -- visual grid matching the actual tmux pane arrangement, with live text previews
- **ANSI color rendering** -- pane previews display colors (8/256/24-bit), bold, underline
- **Pane management** -- create, split (horizontal/vertical), close, resize, and zoom panes via toolbar or right-click
- **Scrollback history** -- view full pane history with search
- **SSH multiplexing** -- single TCP connection per host with auto-reconnect
- **Lightweight** -- PySide6 (Qt 6) native app, ~30-50 MB packaged

## Requirements

- Python >= 3.11
- Remote server(s) with tmux installed

## Installation

```bash
# Clone
git clone git@github.com:windymount/tmux_gui.git
cd tmux_gui

# Create venv and install
uv venv --python 3.11
uv pip install -e ".[dev]"
```

## Usage

```bash
# Run the app
python -m src.app
```

1. Click **Connect** in the toolbar
2. Enter SSH connection details (host, port, username, key file or password)
3. The connection tree populates with tmux sessions and windows
4. Click windows/tabs to switch, use toolbar buttons to split, close, or zoom panes
5. Right-click panes for context actions; click **History** to view scrollback

## Project Structure

```
src/
  app.py                  # Entry point (qasync event loop)
  main_window.py          # Main window: menus, toolbar, status bar
  core/
    ssh_pool.py           # asyncssh connection pool with auto-reconnect
    tmux_manager.py       # tmux command execution and state polling
    tmux_state.py         # Data models + tmux layout string parser
    ansi_parser.py        # ANSI SGR color parser
    config.py             # App config (JSON persistence)
  widgets/
    connect_dialog.py     # SSH connection dialog
    connection_tree.py    # Server/session/window tree
    window_tabs.py        # Window tab bar
    pane_layout.py        # Pane grid (nested QSplitters)
    pane_widget.py        # Single pane preview with ANSI colors
    history_dialog.py     # Scrollback viewer with search
tests/
  test_ansi_parser.py     # ANSI parser tests
  test_config.py          # Config round-trip tests
  test_tmux_state.py      # Layout parser tests
```

## Development

```bash
# Run tests
pytest -v

# Lint
ruff check src/ tests/

# Build standalone exe (Windows)
pyinstaller --onefile --name tmuxpilot src/app.py
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| GUI | PySide6 (Qt 6) |
| SSH | asyncssh |
| Async/Qt bridge | qasync |
| tmux interface | CLI commands with `-F` format strings |
| Packaging | PyInstaller |

## License

MIT

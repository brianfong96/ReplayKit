# ReplayKit

A lightweight Windows tool to record and replay mouse & keyboard actions.

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

## Features

- **Record** mouse movements, clicks, scrolls, and keyboard input
- **Play back** recordings once or on repeat
- **Adjustable speed** — 0.25× to 4× via slider
- **Global hotkeys** — work even when the window isn't focused
- **Always-on-top** window stays visible while you work

## Hotkeys

| Key | Action |
|-----|--------|
| F1  | Toggle recording |
| F2  | Play once |
| F3  | Repeat (loop) |
| F4  | Stop |

## Quick Start

### Run from source

```bash
pip install -r requirements.txt
python replay_kit.py
```

### Build standalone exe

```powershell
.\build.ps1
```

The executable is written to `dist\ReplayKit.exe` — a single file, no Python installation needed.

To do a clean build:

```powershell
.\build.ps1 -Clean
```

## Requirements

- Python 3.12+
- Windows (uses `pynput` for global input capture)
- Dependencies listed in `requirements.txt`

## License

MIT

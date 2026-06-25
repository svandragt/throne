# Throne (Window Manager Ruler)

Automatically applies window manager properties when applications open.

## Requirements

```
uv add python-xlib tomli        # tomli only needed on Python < 3.11
sudo apt install wmctrl xdotool x11-utils  # x11-utils provides xprop
```

## Usage

```bash
# Install config
mkdir -p ~/.config/throne
cp rules.example.toml ~/.config/throne/rules.toml

# Run
python throne.py
```

To run on login, add to your session autostart (e.g. `~/.xprofile` or a systemd user service).

## Identifying a window's class

Run this, then click the target window:

```bash
xprop WM_CLASS
```

Output looks like: `WM_CLASS(STRING) = "instance", "ClassName"` — use either value in `match.class`.

To inspect a running window interactively:

```bash
xwininfo        # click a window, shows window ID
xprop -id 0x… WM_CLASS _NET_WM_NAME _NET_WM_PID
```

## Rules

Config lives at `~/.config/throne/rules.toml`. Rules are evaluated in order; **all matching rules apply**.

```toml
[[rules]]
match.class = "zoom"           # match on WM_CLASS (instance or class name, case-insensitive, globs ok)
match.title = "*meeting*"      # match on window title (glob, case-insensitive)
match.executable = "obs"       # match on process executable name
actions = ["always_on_top"]
```

All `match` fields are optional and ANDed together. Globs (`*`, `?`) are supported in all fields.

## Actions

### Stacking

| Action | Effect |
|---|---|
| `always_on_top` | Keep window above all others |
| `always_on_bottom` | Keep window below all others |

### Visibility

| Action | Effect |
|---|---|
| `sticky` | Show on all workspaces |
| `skip_taskbar` | Hide from taskbar/dock |
| `skip_pager` | Hide from workspace pager |
| `fullscreen` | Make fullscreen |

### Size & position

| Action | Effect |
|---|---|
| `maximize` | Maximize horizontally and vertically |
| `maximize_vertical` | Maximize vertically only |
| `maximize_horizontal` | Maximize horizontally only |
| `shade` | Roll up to title bar |
| `minimize` | Minimize/iconify on open |
| `geometry=WxH+X+Y` | Set size and position, e.g. `geometry=800x600+100+50` |
| `workspace=N` | Move to workspace N (1-indexed) |

### Focus

| Action | Effect |
|---|---|
| `focus` | Focus window on open |

### Appearance

| Action | Effect |
|---|---|
| `opacity=0.0–1.0` | Set window opacity, e.g. `opacity=0.85` |

## Config reload

throne watches the config file and reloads it automatically when it changes — no restart needed.

## Debugging

throne logs matched rules and errors to stdout/stderr. To watch what classes windows have as they open:

```bash
xdotool search --onlyvisible --name "" getwindowclassname %@
```

Or watch live with:

```bash
while true; do xdotool getactivewindow getwindowclassname 2>/dev/null; sleep 1; done
```

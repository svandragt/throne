#!/usr/bin/env python3
"""throne — X11 window rule daemon"""
import fnmatch
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Install tomli: uv add tomli  (or use Python 3.11+)", file=sys.stderr)
        sys.exit(1)

from Xlib import X, display as xdisplay

CONFIG_PATH = Path.home() / ".config" / "throne" / "rules.toml"
APPLY_DELAY = 0.15  # seconds — wait for WM to finish decorating the window

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")

_STATE_ACTIONS = {
    "always_on_top":      "above",
    "always_on_bottom":   "below",
    "sticky":             "sticky",
    "skip_taskbar":       "skip_taskbar",
    "skip_pager":         "skip_pager",
    "fullscreen":         "fullscreen",
    "maximize":           "maximized_vert,maximized_horz",
    "maximize_vertical":  "maximized_vert",
    "maximize_horizontal":"maximized_horz",
    "shade":              "shaded",
}


def compile_rules(raw_rules):
    """Pre-process rules at load time: lowercase patterns, parse parametrized actions,
    batch wmctrl state changes into a single call."""
    compiled = []
    for rule in raw_rules:
        raw_match = rule.get("match", {})
        match = {k: v.lower() for k, v in raw_match.items()}  # lowercase once

        states = []   # collected into one wmctrl call
        actions = []  # everything else

        for action in rule.get("actions", []):
            if action in _STATE_ACTIONS:
                states.append(_STATE_ACTIONS[action])
            elif action in ("minimize", "focus"):
                actions.append((action, None))
            elif action.startswith("opacity="):
                try:
                    value = int(float(action.split("=", 1)[1]) * 0xFFFFFFFF)
                    actions.append(("opacity", value))
                except ValueError:
                    print(f"[throne] bad opacity value: {action}", file=sys.stderr)
            elif action.startswith("workspace="):
                try:
                    ws = int(action.split("=", 1)[1]) - 1
                    actions.append(("workspace", ws))
                except ValueError:
                    print(f"[throne] bad workspace value: {action}", file=sys.stderr)
            elif action.startswith("geometry="):
                m = _GEOMETRY_RE.match(action.split("=", 1)[1])
                if m:
                    w, h, x, y = m.groups()
                    actions.append(("geometry", f"0,{x},{y},{w},{h}"))
                else:
                    print(f"[throne] bad geometry format: {action}", file=sys.stderr)
            else:
                print(f"[throne] unknown action: {action}", file=sys.stderr)

        if states:
            actions.insert(0, ("wmctrl_state", "add," + ",".join(states)))

        compiled.append({
            "match": match,
            "actions": actions,
            "needs_pid": "executable" in match,
        })
    return compiled


def load_config(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return compile_rules(data.get("rules", []))


def get_wm_class(window):
    try:
        cls = window.get_wm_class()
        if cls:
            return cls[0], cls[1]
    except Exception:
        pass
    return None, None


def get_window_title(window):
    try:
        name = window.get_wm_name()
        if name:
            return name
    except Exception:
        pass
    return ""


def get_window_pid(window, pid_atom):
    try:
        prop = window.get_full_property(pid_atom, X.AnyPropertyType)
        if prop:
            return prop.value[0]
    except Exception:
        pass
    return None


def get_executable(pid):
    if pid is None:
        return None
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except Exception:
        pass
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except Exception:
        pass
    return None


def matches(rule_match, wm_instance, wm_class, title, executable):
    if "class" in rule_match:
        pattern = rule_match["class"]
        if not (wm_instance and fnmatch.fnmatch(wm_instance.lower(), pattern)) and \
           not (wm_class and fnmatch.fnmatch(wm_class.lower(), pattern)):
            return False

    if "title" in rule_match:
        if not title or not fnmatch.fnmatch(title.lower(), rule_match["title"]):
            return False

    if "executable" in rule_match:
        if not executable:
            return False
        if not fnmatch.fnmatch(Path(executable).name.lower(), rule_match["executable"]):
            return False

    return True


def apply_actions(wid, actions):
    wid_hex = hex(wid)
    for action, param in actions:
        if action == "wmctrl_state":
            _run(["wmctrl", "-i", "-r", wid_hex, "-b", param])
        elif action == "workspace":
            _run(["wmctrl", "-i", "-r", wid_hex, "-t", str(param)])
        elif action == "geometry":
            _run(["wmctrl", "-i", "-r", wid_hex, "-e", param])
        elif action == "opacity":
            _run(["xprop", "-id", str(wid), "-f", "_NET_WM_WINDOW_OPACITY",
                  "32c", "-set", "_NET_WM_WINDOW_OPACITY", str(param)])
        elif action == "minimize":
            _run(["xdotool", "windowminimize", str(wid)])
        elif action == "focus":
            _run(["xdotool", "windowfocus", str(wid)])


def _run(cmd):
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"[throne] command failed: {' '.join(cmd)}: {e.stderr.decode().strip()}", file=sys.stderr)
    except FileNotFoundError:
        print(f"[throne] command not found: {cmd[0]}", file=sys.stderr)


def handle_window(dpy, window, rules, pid_atom):
    time.sleep(APPLY_DELAY)
    try:
        wm_instance, wm_class = get_wm_class(window)
        title = None
        pid = None
        executable = None

        for rule in rules:
            rule_match = rule["match"]

            # Fetch title lazily — only if a rule needs it
            if "title" in rule_match and title is None:
                title = get_window_title(window)

            # Fetch pid/exe lazily — only if a rule needs it
            if rule["needs_pid"] and pid is None:
                pid = get_window_pid(window, pid_atom)
                executable = get_executable(pid)

            if matches(rule_match, wm_instance, wm_class, title or "", executable):
                label = wm_class or wm_instance or str(window.id)
                print(f"[throne] matched {label!r} → {[a for a, _ in rule['actions']]}")
                apply_actions(window.id, rule["actions"])
    except Exception as e:
        print(f"[throne] error handling window: {e}", file=sys.stderr)


def watch_config(config_path, rules):
    last_mtime = config_path.stat().st_mtime
    while True:
        time.sleep(2)
        try:
            mtime = config_path.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                new_rules = load_config(config_path)
                rules.clear()
                rules.extend(new_rules)
                print(f"[throne] reloaded {len(rules)} rule(s)")
        except Exception as e:
            print(f"[throne] config reload error: {e}", file=sys.stderr)


def main():
    if not CONFIG_PATH.exists():
        print(f"[throne] config not found: {CONFIG_PATH}", file=sys.stderr)
        print(f"[throne] create it with [[rules]] entries — see README.md", file=sys.stderr)
        sys.exit(1)

    rules = load_config(CONFIG_PATH)
    print(f"[throne] loaded {len(rules)} rule(s) from {CONFIG_PATH}")

    threading.Thread(target=watch_config, args=(CONFIG_PATH, rules), daemon=True).start()

    dpy = xdisplay.Display()
    root = dpy.screen().root
    client_list_atom = dpy.intern_atom("_NET_CLIENT_LIST")
    pid_atom = dpy.intern_atom("_NET_WM_PID")  # cached once

    # Single worker serializes all X11 calls — python-xlib isn't thread-safe
    work_queue = queue.Queue()

    def worker():
        while True:
            window = work_queue.get()
            handle_window(dpy, window, rules, pid_atom)
            work_queue.task_done()

    threading.Thread(target=worker, daemon=True).start()

    seen = set()
    print("[throne] watching for windows (polling _NET_CLIENT_LIST)...")

    while True:
        try:
            prop = root.get_full_property(client_list_atom, X.AnyPropertyType)
            current = set(prop.value) if prop else set()
            for wid in current - seen:
                work_queue.put(dpy.create_resource_object("window", wid))
            seen = current
        except Exception as e:
            print(f"[throne] poll error: {e}", file=sys.stderr)
        time.sleep(0.5)


if __name__ == "__main__":
    main()

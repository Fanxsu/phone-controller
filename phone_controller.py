#!/usr/bin/env python3
"""phone-controller: drive an Android device over ADB.

Works on Windows (primary), and on macOS/Linux for everything except OCR.
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "1.0.0"

BLOCKLIST = (
    "支付",
    "购买",
    "立即支付",
    "确认支付",
    "付款",
    "充值",
    "删除",
    "清空",
    "注销",
    "退出登录",
    "退出账号",
    "解除绑定",
    "取消订阅",
    "提交",
    "提交审核",
    "发布",
    "上架",
    "卸载",
    "重置",
    "恢复出厂",
    "pay",
    "purchase",
    "delete",
    "logout",
    "sign out",
    "uninstall",
    "reset",
)

KEYCODES = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "menu": 82,
    "app_switch": 187,
    "delete": 67,
    "del": 67,
    "tab": 61,
    "escape": 111,
    "esc": 111,
    "power": 26,
    "volume_up": 24,
    "volume_down": 25,
    "wakeup": 224,
    "sleep": 223,
}


class ToolError(Exception):
    pass


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def find_adb(explicit=None):
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_adb = os.environ.get("ADB")
    if env_adb:
        candidates.append(env_adb)
    which = shutil.which("adb")
    if which:
        candidates.append(which)
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(key)
        if root:
            exe = "adb.exe" if os.name == "nt" else "adb"
            candidates.append(os.path.join(root, "platform-tools", exe))
    if os.name == "nt":
        candidates.extend(
            [
                os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
                r"C:\dev\android-sdk\platform-tools\adb.exe",
            ]
        )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise ToolError(
        "adb not found. Install Android platform-tools, put adb on PATH, "
        "or set ANDROID_HOME / ANDROID_SDK_ROOT / ADB."
    )


def run(cmd, binary=False, timeout=30, check=True):
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise ToolError("command not found: %s" % cmd[0])
    except subprocess.TimeoutExpired:
        raise ToolError("command timed out: %s" % " ".join(cmd))
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        out = proc.stdout.decode("utf-8", "replace").strip()
        detail = err or out or "(no output)"
        raise ToolError("command failed (%s): %s\n%s" % (proc.returncode, " ".join(cmd), detail))
    if binary:
        return proc.stdout
    return proc.stdout.decode("utf-8", "replace")


def adb_base(serial):
    cmd = [ADB]
    if serial:
        cmd.extend(["-s", serial])
    return cmd


def list_devices():
    out = run([ADB, "devices", "-l"])
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        model = ""
        match = re.search(r"\bmodel:(\S+)", line)
        if match:
            model = match.group(1)
        devices.append({"serial": parts[0], "state": parts[1], "model": model})
    return devices


def pick_serial(args):
    if getattr(args, "device", None):
        return args.device
    env_serial = os.environ.get("ANDROID_SERIAL")
    if env_serial:
        return env_serial
    devices = list_devices()
    ready = [d for d in devices if d["state"] == "device"]
    if len(ready) == 1:
        return ready[0]["serial"]
    if not ready:
        detail = ""
        if devices:
            detail = " Found: " + ", ".join("%s(%s)" % (d["serial"], d["state"]) for d in devices)
        raise ToolError(
            "no authorized device. Connect USB, enable USB debugging, accept the RSA prompt."
            + detail
        )
    raise ToolError(
        "multiple devices connected. Use --device <serial> or ANDROID_SERIAL. Found: "
        + ", ".join(d["serial"] for d in ready)
    )


def parse_bounds(value):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


def dump_nodes(serial, timeout=30):
    remote_paths = [
        "/data/local/tmp/phone_controller_ui.xml",
        "/sdcard/window_dump.xml",
    ]
    xml = ""
    last_error = None
    for remote in remote_paths:
        try:
            run(adb_base(serial) + ["shell", "uiautomator", "dump", remote], timeout=timeout)
            xml = run(adb_base(serial) + ["exec-out", "cat", remote], timeout=timeout)
            if xml.lstrip().startswith("<"):
                break
            last_error = "uiautomator dump produced empty output"
        except ToolError as exc:
            last_error = str(exc)
            xml = ""
    if not xml.lstrip().startswith("<"):
        raise ToolError(
            "uiautomator dump failed. Is the screen unlocked? Details: %s" % last_error
        )
    return parse_nodes(xml)


def parse_nodes(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ToolError("uiautomator dump returned invalid XML: %s" % exc)

    nodes = []
    for node in root.iter("node"):
        bounds = parse_bounds(node.get("bounds", ""))
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        nodes.append(
            {
                "index": len(nodes),
                "text": node.get("text", ""),
                "desc": node.get("content-desc", ""),
                "class": node.get("class", ""),
                "bounds": [x1, y1, x2, y2],
                "center": [(x1 + x2) // 2, (y1 + y2) // 2],
                "clickable": node.get("clickable", "false") == "true",
                "enabled": node.get("enabled", "false") == "true",
            }
        )
    return nodes


def meaningful(node):
    return bool(node["text"].strip() or node["desc"].strip())


def label(node):
    text = node["text"].strip()
    desc = node["desc"].strip()
    if text and desc and text != desc:
        return "%s | %s" % (text, desc)
    return text or desc


def area(node):
    x1, y1, x2, y2 = node["bounds"]
    return max(0, x2 - x1) * max(0, y2 - y1)


def find_matches(nodes, needle, exact=False, desc_only=False):
    needle_folded = needle.casefold()
    matches = []
    for node in nodes:
        fields = [node["desc"]] if desc_only else [node["text"], node["desc"]]
        for field in fields:
            value = field.strip()
            if not value:
                continue
            if exact:
                hit = value == needle
            else:
                hit = needle_folded in value.casefold()
            if hit:
                matches.append(node)
                break
    return matches


def best_match(matches):
    if not matches:
        return None
    clickable = [node for node in matches if node["clickable"]]
    pool = clickable or matches
    return min(pool, key=area)


def blocked_keyword(node):
    text = ("%s %s" % (node["text"], node["desc"])).casefold()
    for word in BLOCKLIST:
        if word.casefold() in text:
            return word
    return None


def ensure_not_blocked(node, force):
    if force:
        return
    word = blocked_keyword(node)
    if word:
        raise ToolError(
            "refusing to tap %r: matched dangerous keyword %r. "
            "Use --force only after explicit user approval." % (label(node), word)
        )


def print_json(value):
    # ASCII-escaped JSON is safe across Windows consoles and agent pipes.
    print(json.dumps(value, ensure_ascii=True, indent=2))


def tap_point(serial, x, y):
    run(adb_base(serial) + ["shell", "input", "tap", str(int(x)), str(int(y))])


def long_press_point(serial, x, y, duration=800):
    run(
        adb_base(serial)
        + [
            "shell",
            "input",
            "swipe",
            str(int(x)),
            str(int(y)),
            str(int(x)),
            str(int(y)),
            str(int(duration)),
        ]
    )


def wait_for_text(serial, text, timeout=10, exact=False, desc_only=False):
    deadline = time.time() + timeout
    while time.time() < deadline:
        nodes = dump_nodes(serial)
        matches = find_matches(nodes, text, exact=exact, desc_only=desc_only)
        chosen = best_match(matches)
        if chosen:
            return chosen
        time.sleep(0.5)
    raise ToolError("timed out after %ss waiting for %r" % (timeout, text))


def png_size(data):
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height
    return None


def find_ocr_helper():
    helper = Path(__file__).with_name("phone_controller_ocr.ps1")
    if not helper.is_file():
        raise ToolError("OCR helper not found: %s" % helper)
    return helper


def find_windows_powershell():
    if os.name != "nt":
        raise ToolError("OCR is only available on Windows in this version")
    candidates = [
        shutil.which("powershell.exe"),
        os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        ),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise ToolError("Windows PowerShell 5.1 not found; it is required for OCR")


def ocr_image(path):
    helper = find_ocr_helper()
    powershell = find_windows_powershell()
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise ToolError("image not found: %s" % path)
    handle, out_path = tempfile.mkstemp(prefix="phone-controller-ocr-", suffix=".txt")
    os.close(handle)
    try:
        run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                "-Path",
                path,
                "-Out",
                out_path,
            ],
            timeout=60,
        )
        with open(out_path, "r", encoding="utf-8", errors="replace") as stream:
            return stream.read().lstrip("\ufeff")
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def detect_package():
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        for name in ("build.gradle.kts", "build.gradle"):
            gradle = parent / "android" / "app" / name
            if gradle.is_file():
                text = gradle.read_text(encoding="utf-8", errors="replace")
                match = re.search(r"applicationId\s*=?\s*[\"']([^\"']+)", text)
                if match:
                    return match.group(1)
                match = re.search(r"namespace\s*=?\s*[\"']([^\"']+)", text)
                if match:
                    return match.group(1)
        manifest = parent / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
        if manifest.is_file():
            text = manifest.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'package="([^"]+)"', text)
            if match:
                return match.group(1)
    return None


def command_devices(args):
    devices = list_devices()
    if args.json:
        print_json({"devices": devices})
        return 0
    if not devices:
        print("No Android devices found. Connect USB and enable USB debugging.")
        return 1
    print("SERIAL\tSTATE\tMODEL")
    for device in devices:
        print("%s\t%s\t%s" % (device["serial"], device["state"], device["model"] or "-"))
    return 0


def command_status(args):
    serial = pick_serial(args)
    size_out = run(adb_base(serial) + ["shell", "wm", "size"])
    density_out = run(adb_base(serial) + ["shell", "wm", "density"])
    focus_out = run(adb_base(serial) + ["shell", "dumpsys", "window"])
    model = run(adb_base(serial) + ["shell", "getprop", "ro.product.model"], check=False).strip()
    release = run(adb_base(serial) + ["shell", "getprop", "ro.build.version.release"], check=False).strip()

    size_match = re.search(r"(\d+)x(\d+)", size_out)
    density_match = re.search(r"(\d+)", density_out)
    focus_match = re.search(r"mCurrentFocus=.*?\s([^\s/]+)/([^\s}]+)", focus_out)
    package = focus_match.group(1) if focus_match else None
    activity = focus_match.group(2) if focus_match else None

    payload = {
        "serial": serial,
        "model": model or None,
        "android": release or None,
        "size": size_match.group(0) if size_match else None,
        "density": density_match.group(1) if density_match else None,
        "package": package,
        "activity": activity,
    }
    if args.json:
        print_json(payload)
        return 0
    print("serial   : %s" % serial)
    print("model    : %s" % (model or "-"))
    print("android  : %s" % (release or "-"))
    print("size     : %s" % (payload["size"] or "-"))
    print("density  : %s" % (payload["density"] or "-"))
    print("package  : %s" % (package or "-"))
    print("activity : %s" % (activity or "-"))
    return 0


def command_dump(args):
    serial = pick_serial(args)
    nodes = dump_nodes(serial)
    visible = nodes if args.all else [node for node in nodes if meaningful(node)]
    if args.json:
        print_json({"nodes": visible})
        return 0
    print("IDX\tTEXT / DESC\tBOUNDS\tCLICKABLE\tCLASS")
    for node in visible:
        text = label(node).replace("\n", "\\n")
        if len(text) > 70:
            text = text[:67] + "..."
        bounds = "[%d,%d][%d,%d]" % tuple(node["bounds"])
        print(
            "%d\t%s\t%s\t%s\t%s"
            % (node["index"], text, bounds, "yes" if node["clickable"] else "no", node["class"])
        )
    return 0


def command_find(args):
    serial = pick_serial(args)
    nodes = dump_nodes(serial)
    matches = find_matches(nodes, args.text, exact=args.exact, desc_only=args.desc)
    if args.json:
        print_json({"found": bool(matches), "matches": matches})
        return 0 if matches else 1
    if not matches:
        print("Not found: %r" % args.text)
        return 1
    for index, node in enumerate(matches):
        print("[%d] %s" % (index, label(node).replace("\n", "\\n")))
        print(
            "    bounds=[%d,%d][%d,%d] center=(%d, %d) clickable=%s class=%s"
            % (
                node["bounds"][0],
                node["bounds"][1],
                node["bounds"][2],
                node["bounds"][3],
                node["center"][0],
                node["center"][1],
                "yes" if node["clickable"] else "no",
                node["class"],
            )
        )
    return 0


def command_tap(args):
    serial = pick_serial(args)
    nodes = dump_nodes(serial)
    matches = find_matches(nodes, args.text, exact=args.exact, desc_only=args.desc)
    if not matches:
        raise ToolError("not found: %r" % args.text)
    if args.index is not None:
        if args.index < 0 or args.index >= len(matches):
            raise ToolError("--index %s out of range (0..%s)" % (args.index, len(matches) - 1))
        chosen = matches[args.index]
    else:
        chosen = best_match(matches)
    ensure_not_blocked(chosen, args.force)
    x, y = chosen["center"]
    tap_point(serial, x, y)
    found = None
    if args.wait:
        found = wait_for_text(serial, args.wait, timeout=args.wait_timeout)
    if args.json:
        payload = {"ok": True, "tapped": chosen, "point": [x, y]}
        if args.wait:
            payload["waited_for"] = args.wait
            payload["found"] = found
        print_json(payload)
    else:
        print("tapped %r at (%d, %d)" % (label(chosen), x, y))
        if args.wait:
            print("found %r after tap" % args.wait)
    return 0


def command_tap_xy(args):
    serial = pick_serial(args)
    nodes = dump_nodes(serial)
    x, y = args.x, args.y
    containing = []
    for node in nodes:
        if not meaningful(node):
            continue
        x1, y1, x2, y2 = node["bounds"]
        if x1 <= x <= x2 and y1 <= y <= y2:
            containing.append(node)
    chosen = min(containing, key=area) if containing else None
    if chosen:
        ensure_not_blocked(chosen, args.force)
    tap_point(serial, x, y)
    if args.json:
        print_json({"ok": True, "point": [x, y], "node": chosen})
    else:
        if chosen:
            print("tapped (%d, %d) over %r" % (x, y, label(chosen)))
        else:
            print("tapped (%d, %d)" % (x, y))
    return 0


def command_long_press(args):
    serial = pick_serial(args)
    nodes = dump_nodes(serial)
    matches = find_matches(nodes, args.text, exact=args.exact, desc_only=args.desc)
    if not matches:
        raise ToolError("not found: %r" % args.text)
    chosen = matches[args.index] if args.index is not None else best_match(matches)
    ensure_not_blocked(chosen, args.force)
    x, y = chosen["center"]
    long_press_point(serial, x, y, args.duration)
    if args.json:
        print_json({"ok": True, "long_pressed": chosen, "point": [x, y]})
    else:
        print("long-pressed %r at (%d, %d)" % (label(chosen), x, y))
    return 0


def command_type(args):
    serial = pick_serial(args)
    text = args.text
    if any(ord(char) > 127 for char in text):
        eprint(
            "warning: adb input text is unreliable for non-ASCII. "
            "Use a clipboard/IME bridge for Chinese input."
        )
    escaped = shlex.quote(text.replace(" ", "%s"))
    run(adb_base(serial) + ["shell", "input text %s" % escaped])
    if args.json:
        print_json({"ok": True, "typed": text})
    else:
        print("typed %r" % text)
    return 0


def command_key(args):
    serial = pick_serial(args)
    name = args.key.strip()
    if name.upper().startswith("KEYCODE_"):
        code = name.upper()
    else:
        code = KEYCODES.get(name.casefold())
        if code is None:
            raise ToolError(
                "unknown key %r. Use %s or KEYCODE_*."
                % (name, ", ".join(sorted(KEYCODES)))
            )
    run(adb_base(serial) + ["shell", "input", "keyevent", str(code)])
    if args.json:
        print_json({"ok": True, "key": name, "code": code})
    else:
        print("pressed %s" % name)
    return 0


def command_swipe(args):
    serial = pick_serial(args)
    run(
        adb_base(serial)
        + [
            "shell",
            "input",
            "swipe",
            str(args.x1),
            str(args.y1),
            str(args.x2),
            str(args.y2),
            str(args.duration),
        ]
    )
    if args.json:
        print_json(
            {
                "ok": True,
                "from": [args.x1, args.y1],
                "to": [args.x2, args.y2],
                "duration": args.duration,
            }
        )
    else:
        print(
            "swiped (%d, %d) -> (%d, %d) in %sms"
            % (args.x1, args.y1, args.x2, args.y2, args.duration)
        )
    return 0


def command_shot(args):
    serial = pick_serial(args)
    path = Path(args.path).expanduser()
    if path.parent and str(path.parent):
        path.parent.mkdir(parents=True, exist_ok=True)
    data = run(adb_base(serial) + ["exec-out", "screencap", "-p"], binary=True)
    path.write_bytes(data)
    size = png_size(data)
    if args.json:
        print_json(
            {
                "ok": True,
                "path": str(path),
                "bytes": len(data),
                "width": size[0] if size else None,
                "height": size[1] if size else None,
            }
        )
    else:
        if size:
            print("saved %s (%dx%d, %d bytes)" % (path, size[0], size[1], len(data)))
        else:
            print("saved %s (%d bytes)" % (path, len(data)))
    return 0


def command_ocr(args):
    text = ocr_image(args.path)
    if args.json:
        print_json({"ok": True, "path": args.path, "text": text})
    else:
        print(text)
    return 0


def command_wait(args):
    serial = pick_serial(args)
    node = wait_for_text(
        serial, args.text, timeout=args.timeout, exact=args.exact, desc_only=args.desc
    )
    if args.json:
        print_json({"found": True, "node": node})
    else:
        print(
            "found %r at (%d, %d)"
            % (label(node), node["center"][0], node["center"][1])
        )
    return 0


def command_launch(args):
    serial = pick_serial(args)
    package = args.package or detect_package()
    if not package:
        raise ToolError(
            "package not given and could not infer it from the current Flutter project. "
            "Use: phone-controller launch <package>"
        )
    run(adb_base(serial) + ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    if args.json:
        print_json({"ok": True, "package": package})
    else:
        print("launched %s" % package)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="phone-controller",
        description="Drive an Android device over ADB (UI tree, taps, screenshots, OCR).",
    )
    parser.add_argument("--version", action="version", version="phone-controller " + VERSION)
    parser.add_argument("--adb", help="path to adb (default: auto-detect)")

    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-d", "--device", help="device serial (default: auto-select)")
    common.add_argument("--json", action="store_true", help="machine-readable output")

    sub.add_parser("devices", parents=[common], help="list connected devices")

    sub.add_parser("status", parents=[common], help="show current app, size, density")

    dump_parser = sub.add_parser("dump", parents=[common], help="dump the UI tree")
    dump_parser.add_argument("--all", action="store_true", help="include nodes without text/desc")

    find_parser = sub.add_parser("find", parents=[common], help="find a node by text/content-desc")
    find_parser.add_argument("text")
    find_parser.add_argument("--exact", action="store_true")
    find_parser.add_argument("--desc", action="store_true", help="search content-desc only")

    tap_parser = sub.add_parser("tap", parents=[common], help="tap a node by text/content-desc")
    tap_parser.add_argument("text")
    tap_parser.add_argument("--exact", action="store_true")
    tap_parser.add_argument("--desc", action="store_true", help="search content-desc only")
    tap_parser.add_argument("--index", type=int, help="pick the Nth match")
    tap_parser.add_argument("--force", action="store_true", help="allow dangerous keywords")
    tap_parser.add_argument("--wait", help="after tapping, wait for this text")
    tap_parser.add_argument("--wait-timeout", type=float, default=10)

    tap_xy_parser = sub.add_parser("tap-xy", parents=[common], help="tap absolute coordinates")
    tap_xy_parser.add_argument("x", type=int)
    tap_xy_parser.add_argument("y", type=int)
    tap_xy_parser.add_argument("--force", action="store_true", help="allow dangerous keywords")

    long_parser = sub.add_parser(
        "long-press", parents=[common], help="long press a node by text/content-desc"
    )
    long_parser.add_argument("text")
    long_parser.add_argument("--exact", action="store_true")
    long_parser.add_argument("--desc", action="store_true")
    long_parser.add_argument("--index", type=int)
    long_parser.add_argument("--duration", type=int, default=800)
    long_parser.add_argument("--force", action="store_true")

    type_parser = sub.add_parser("type", parents=[common], help="type ASCII text")
    type_parser.add_argument("text")

    key_parser = sub.add_parser("key", parents=[common], help="press a key")
    key_parser.add_argument("key")

    swipe_parser = sub.add_parser("swipe", parents=[common], help="swipe between two points")
    swipe_parser.add_argument("x1", type=int)
    swipe_parser.add_argument("y1", type=int)
    swipe_parser.add_argument("x2", type=int)
    swipe_parser.add_argument("y2", type=int)
    swipe_parser.add_argument("--duration", type=int, default=300)

    shot_parser = sub.add_parser("shot", parents=[common], help="save a screenshot")
    shot_parser.add_argument("path")

    ocr_parser = sub.add_parser("ocr", parents=[common], help="OCR a screenshot on Windows")
    ocr_parser.add_argument("path")

    wait_parser = sub.add_parser("wait", parents=[common], help="wait until text appears")
    wait_parser.add_argument("text")
    wait_parser.add_argument("--timeout", type=float, default=10)
    wait_parser.add_argument("--exact", action="store_true")
    wait_parser.add_argument("--desc", action="store_true")

    launch_parser = sub.add_parser("launch", parents=[common], help="launch an app")
    launch_parser.add_argument("package", nargs="?")

    for name in ("back", "home", "enter"):
        sub.add_parser(name, parents=[common], help="press the %s key" % name)

    return parser


def main(argv=None):
    global ADB
    parser = build_parser()
    args = parser.parse_args(argv)
    ADB = find_adb(args.adb)
    try:
        command = args.command
        if command == "devices":
            return command_devices(args)
        if command == "status":
            return command_status(args)
        if command == "dump":
            return command_dump(args)
        if command == "find":
            return command_find(args)
        if command == "tap":
            return command_tap(args)
        if command == "tap-xy":
            return command_tap_xy(args)
        if command == "long-press":
            return command_long_press(args)
        if command == "type":
            return command_type(args)
        if command == "key":
            return command_key(args)
        if command == "swipe":
            return command_swipe(args)
        if command == "shot":
            return command_shot(args)
        if command == "ocr":
            return command_ocr(args)
        if command == "wait":
            return command_wait(args)
        if command == "launch":
            return command_launch(args)
        if command in ("back", "home", "enter"):
            args.key = command
            return command_key(args)
        raise ToolError("unknown command: %s" % command)
    except ToolError as exc:
        eprint("phone-controller: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

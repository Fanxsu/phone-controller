# phone-controller — Design Spec

## Goal

A reusable Android device automation CLI + agent skill for Flutter projects on Windows. It wraps ADB, `uiautomator dump`, screenshots, and Windows OCR so humans and agents can inspect and drive a real device without guessing coordinates.

## Scope (v1)

- Android real devices and emulators.
- Windows host.
- UI inspection: current app, UI tree, find by `text` / `content-desc`.
- Actions: tap, tap-xy, long-press, swipe, key, ASCII type, launch.
- Evidence: screenshot, OCR.
- Works from any Flutter project; no project-specific assumptions.
- Portable install: copy folder or `git clone`, then `install.ps1`.

## Non-goals

- iOS, Flutter Web, Windows desktop drivers.
- Payment / login / OTP automation.
- Pixel-perfect visual verification.
- Full Chinese text input via ADB.

## Architecture

```text
phone-controller/
  phone_controller.py       # single-file Python stdlib CLI
  phone_controller_ocr.ps1  # Windows.Media.Ocr helper (PowerShell 5.1)
  phone-controller.cmd      # %~dp0 shim; tries python then py -3
  SKILL.md                  # agent workflow + safety rules
  install.ps1               # copy to ~/.local/bin + skill dirs
  uninstall.ps1
  README.md
  VERSION
```

Data flow:

```text
adb devices / status
  -> adb shell uiautomator dump
  -> parse XML (text / content-desc / bounds)
  -> find / best match
  -> adb shell input tap/swipe/key
  -> optional shot + OCR
```

## Command surface

`devices`, `status`, `dump`, `find`, `tap`, `tap-xy`, `long-press`, `type`, `key`, `swipe`, `shot`, `ocr`, `wait`, `launch`, `back`, `home`, `enter`.

Machine-readable output: `--json` (ASCII-escaped for safe piping).

## Safety

- Default blocklist: payment, purchase, delete, logout, submit, publish, uninstall, reset, etc.
- `tap` / `tap-xy` / `long-press` refuse blocklisted labels unless `--force`.
- `tap-xy` reverse-looks-up the node under the point before deciding.
- The skill forbids automating login, OTP, and payment confirmation.

## Portability

- No machine-specific absolute paths in runtime code.
- `adb` lookup: `ADB` env var -> PATH -> `ANDROID_HOME` / `ANDROID_SDK_ROOT` -> common paths.
- `.cmd` uses `%~dp0`; OCR helper is resolved relative to the Python file.
- `install.ps1` checks Python, ADB, PATH, and Windows OCR language packs.
- Method A: copy folder + install. Method B: `git clone` + install.

## Verification

1. `python -m py_compile phone_controller.py`.
2. `phone-controller --version`, `devices`, `status`.
3. On a real device: `dump` -> `find` -> `tap` -> `wait` -> `shot` -> `ocr`.
4. Safety: `tap "立即支付"` must refuse without `--force`.
5. Portability: install into a temp bin dir and run from there.

## Future

- iOS driver (requires macOS).
- Flutter Web / desktop driver.
- Clipboard/IME bridge for Chinese input.
- Visual diff / golden comparison integration.

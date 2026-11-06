---
name: phone-controller
description: Drive an Android phone or emulator from Windows via ADB for Flutter app testing. Use when you need to inspect the current screen, find or tap UI by text/content-desc, swipe, type ASCII, take screenshots, or OCR Chinese UI text. Triggers include "drive the phone", "tap through the Android app", "take a device screenshot", "verify UI text on the device", "真机点按", "手机截图", "验证安卓界面".
---

# phone-controller

用 `phone-controller` 驱动 Android 真机/模拟器。它封装了 ADB、`uiautomator dump`、截图和 Windows OCR；优先按 UI 树里的 `text` / `content-desc` 定位，而不是猜坐标。

## 先决条件

1. 手机通过 USB 连接，已开启 USB 调试并授权 RSA。
2. 屏幕已解锁；Flutter App 已安装并运行。
3. 先跑：
   ```powershell
   phone-controller devices
   phone-controller status
   ```
   只应有一台状态为 `device` 的设备；多台时用 `--device <serial>` 或 `ANDROID_SERIAL`。

## 标准流程

```powershell
phone-controller status
phone-controller dump
phone-controller find "设置"
phone-controller tap "设置"
phone-controller wait "会员订阅"
phone-controller shot out.png
phone-controller ocr out.png
```

规则：

- **每次页面切换后重新 `dump` 或 `find`**，不要复用旧坐标。
- 优先按可见文字或 `content-desc` 定位；`tap-xy` 只作兜底。
- 需要机器可读结果时加 `--json`。
- 点击后可用 `--wait "下一页文字"` 等待页面变化。
- 找不到元素时先 `dump` 看真实文案；Flutter 的语义文本可能把多行合并成一个 `content-desc`。

## 安全边界（硬性）

- **绝不自动点击**：支付、购买、充值、删除、清空、注销、退出登录、提交、提交审核、发布、上架、卸载、重置。
- 工具默认会拦截这些关键词；只有用户明确批准后才能加 `--force`。
- 登录、短信验证码、支付确认必须由用户本人完成。
- 不确定当前页面时先 `status` + `dump`，不要盲点坐标。

## 常用命令

```powershell
phone-controller devices
phone-controller status
phone-controller dump [--json] [--all]
phone-controller find "文字" [--exact] [--desc] [--json]
phone-controller tap "文字" [--index N] [--wait "下一页文字"]
phone-controller tap-xy 540 1200
phone-controller long-press "文字" [--duration 800]
phone-controller type "hello world"
phone-controller key back|home|enter|delete
phone-controller swipe 540 1800 540 600 --duration 300
phone-controller shot out.png
phone-controller ocr out.png
phone-controller launch [package]
```

## 限制

- OCR 仅 Windows 可用；需要系统安装带 OCR 的中文语言包。
- `type` 对中文不可靠（ADB 原生限制）；中文输入用系统输入法或剪贴板桥。
- 不能替代视觉验收：颜色、间距、动画、遮挡仍需人看或视觉模型。
- 坐标与分辨率绑定；换设备后重新 `dump` 取 bounds。

## 排错

- `no authorized device`：检查 USB、USB 调试、RSA 授权弹窗。
- `uiautomator dump failed`：解锁屏幕，确认当前不是系统弹窗/权限弹窗。
- `adb not found`：安装 Android platform-tools，或设置 `ANDROID_HOME` / `ANDROID_SDK_ROOT`。
- OCR 为空：安装 Windows 中文 OCR 语言包，并确认调用的是 Windows PowerShell 5.1（不是 PowerShell 7）。

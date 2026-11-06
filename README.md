# phone-controller

用命令行驱动 Android 真机/模拟器，适合 Flutter 项目的真机 UI 测试：

- 查看当前 App / Activity / 分辨率
- 导出 UI 树，按文字或 `content-desc` 查找、点击
- 点击坐标、滑动、长按、按键
- 截图
- Windows 下 OCR 识别截图中的中文

它只依赖 Python 标准库和 ADB。第一版面向 Windows；macOS/Linux 可以使用除 OCR 外的命令。

## 一、准备环境

每台电脑需要：

1. **Windows**（OCR 和 `.cmd` 入口按 Windows 设计）
2. **Python 3.9+**
3. **Android SDK platform-tools**（能运行 `adb`）
4. 手机开启 USB 调试并授权

`adb` 的查找顺序：

1. `ADB` 环境变量
2. PATH 中的 `adb`
3. `ANDROID_HOME` / `ANDROID_SDK_ROOT` 下的 `platform-tools/adb.exe`
4. 常见安装路径（如 `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`）

## 二、安装

### 方式 A：拷贝整个目录

把本目录（`phone-controller/`）整体拷到新电脑，例如：

```text
C:\tools\phone-controller\
```

然后在目录里运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

如果 `%USERPROFILE%\.local\bin` 不在 PATH：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -AddToPath
```

### 方式 B：git clone

#### B1. 已有远程仓库

在源电脑把仓库推到远程（只需做一次）：

```powershell
cd <source-path>
git remote add origin <你的仓库 URL>
git push -u origin main
```

在新电脑：

```powershell
git clone <你的仓库 URL> phone-controller
cd phone-controller
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

#### B2. 没有远程仓库，但在同一局域网/共享盘

如果源目录本身是 git 仓库，可以直接从本地路径 clone：

```powershell
git clone <source-path> <target-path>
cd C:\tools\phone-controller
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

#### B3. 以后更新

```powershell
cd C:\tools\phone-controller
git pull
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 安装脚本做了什么

`install.ps1` 会：

1. 复制 `phone_controller.py`、`phone_controller_ocr.ps1`、`phone-controller.cmd` 到 `%USERPROFILE%\.local\bin`。
2. 复制 `SKILL.md`（和本 README）到：
   - `%USERPROFILE%\.claude\skills\phone-controller\`
   - `%USERPROFILE%\.agents\skills\phone-controller\`
3. 检查 Python、ADB、PATH、Windows OCR 语言包，缺什么就明确提示。
4. 默认**不擅自修改系统 PATH**；需要时用 `-AddToPath`，或按提示手动添加。

安装完成后，**新开一个终端**，运行：

```powershell
phone-controller --version
phone-controller devices
phone-controller status
```

看到设备序列号、`device` 状态和当前 Activity 才算装好。

## 三、使用

```powershell
phone-controller devices
phone-controller status
phone-controller dump
phone-controller find "设置"
phone-controller tap "设置"
phone-controller wait "会员订阅"
phone-controller shot out.png
phone-controller ocr out.png
```

点击后等待下一页：

```powershell
phone-controller tap "会员订阅" --wait "选择会员时长"
```

多台设备：

```powershell
phone-controller --device <serial> status
# 或
$env:ANDROID_SERIAL = "<serial>"
```

机器可读输出：

```powershell
phone-controller dump --json
phone-controller find "设置" --json
phone-controller status --json
```

### 命令速查

| 命令 | 作用 |
|---|---|
| `devices` | 列出设备 |
| `status` | 当前包/Activity、分辨率、密度 |
| `dump [--json]` | 导出 UI 树 |
| `find <文字>` | 按 text/content-desc 查找 |
| `tap <文字>` | 查找并点击 |
| `tap-xy <x> <y>` | 按坐标点击（会反查危险词） |
| `long-press <文字>` | 长按 |
| `type <ASCII>` | 输入 ASCII |
| `key back\|home\|enter\|delete` | 按键 |
| `swipe x1 y1 x2 y2` | 滑动 |
| `shot <路径>` | 截图 |
| `ocr <路径>` | Windows OCR |
| `wait <文字>` | 等文字出现 |
| `launch [包名]` | 启动 App；不给包名时从当前 Flutter 工程推断 |

## 四、安全边界

工具默认拦截以下关键词的点击：

```text
支付、购买、立即支付、确认支付、付款、充值、删除、清空、注销、
退出登录、退出账号、解除绑定、取消订阅、提交、提交审核、发布、
上架、卸载、重置、恢复出厂、pay、purchase、delete、logout、uninstall、reset
```

命中时会拒绝执行。只有用户明确批准后，才可加 `--force`。

登录、短信验证码、支付确认必须由用户本人完成。

## 五、限制

- OCR 仅 Windows 可用，依赖系统中文 OCR 语言包。
- `type` 对中文不可靠；ADB 原生 `input text` 不适合中文。
- 不能替代视觉验收：颜色、间距、动画、遮挡仍需人看或视觉模型。
- 坐标与分辨率绑定；换设备后重新 `dump`。
- 第一版不做 iOS、Flutter Web、Windows 桌面驱动。

## 六、卸载

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

如果安装时用 `-AddToPath` 添加过 PATH：

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveFromPath
```

## 七、排错

| 现象 | 处理 |
|---|---|
| `no authorized device` | 检查 USB、USB 调试、RSA 授权弹窗 |
| `adb not found` | 安装 platform-tools，或设置 `ANDROID_HOME` / `ANDROID_SDK_ROOT` |
| `uiautomator dump failed` | 解锁屏幕；关闭系统权限弹窗后重试 |
| OCR 为空 | 安装 Windows 中文 OCR 语言包；确认调用 Windows PowerShell 5.1 |
| `phone-controller` 不是命令 | 新开终端；或把 `%USERPROFILE%\.local\bin` 加入 PATH |

## 八、目录说明

```text
phone_controller.py         主程序
phone_controller_ocr.ps1    Windows OCR 辅助
phone-controller.cmd        命令入口（用 %~dp0 定位同目录脚本）
SKILL.md                    agent 使用说明
install.ps1 / uninstall.ps1 安装与卸载
VERSION                     版本号
LICENSE                     MIT 许可证
```

## 九、License

MIT License. Copyright (c) 2026 北京夙棠科技有限公司 (Suttech Technology Co., Ltd.). 详见 [LICENSE](LICENSE)。

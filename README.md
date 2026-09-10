# Codex Auto Resume

Codex Plus 额度用完时，当前对话会停住。额度恢复后（5 小时到点、中途被刷新、或你自己 reset credit），这个小工具会**在原来那条对话里继续**，不会新建聊天。

Windows 和 macOS 用的是**同一套 Python 代码**。差别只在开机/登录自启：Windows 写启动项，macOS 写 LaunchAgent。

---

## 先搞清楚 3 个命令

| 命令 | 作用 | 要不要一直开着 |
|---|---|---|
| `python run.py doctor` | 检查 Python、Codex、额度接口是否正常 | 不用。检查一次就行 |
| `python run.py status` | 看当前额度和有没有在等续跑的对话 | 不用。想看再跑 |
| `python run.py watch` | **真正干活的守护进程** | 要。关掉就不再自动续 |

开机自启**只自动跑** `watch`，不会跑 `doctor` / `status`。

额度回来后，直接打开 Codex App 里**原来被打断的那条对话**即可。成功时同一条聊天里会出现一句续跑提示，然后 Codex 接着干。不必再跑 `status`。

---

## 需要准备什么

1. Python 3.10 或更高  
   - Windows：终端里能运行 `python --version`  
   - macOS：终端里能运行 `python3 --version`
2. 本机已经登录 Codex（Desktop 或 CLI 都行，会话目录是共用的）
3. 如果 Codex 家目录不在默认位置，需要能读到 `CODEX_HOME`  
   例如 Windows 上是 `D:\codex`，macOS 默认一般是 `~/.codex`

---

## Windows 怎么用

### 1. 打开工具目录

PowerShell：

```powershell
cd D:\vibcoding\codex-auto-resume
```

如果你是 git clone 下来的，改成你的实际路径，例如：

```powershell
cd $HOME\codex-auto-resume
```

### 2. 先检查一次

```powershell
python run.py doctor
```

看到 `app_server OK`、`sessions_exist True` 就说明能读额度和会话。  
`waiting_threads` 是当前已经发现、在等额度恢复的对话数量。

### 3. 启动自动续跑

两种用法，选一种即可。

**用法 A：当前窗口挂着（适合马上要用）**

```powershell
python run.py watch
```

看到 `codex-auto-resume 已启动，按 Ctrl+C 结束` 就对了。  
这个窗口不要关；关掉就停。

**用法 B：开机后自动在后台跑（推荐长期用）**

```powershell
python run.py install-autostart
```

它会：

1. 优先写 Windows 任务计划
2. 没有权限时，改写当前用户「启动」文件夹里的 `codex-auto-resume.vbs`
3. 马上在后台拉起一次 `watch`

以后每次登录 Windows，它自己起来，不用再敲命令。

卸掉开机自启：

```powershell
python run.py uninstall-autostart
```

### 4. 额度用完之后你要做什么

什么都不用做。继续开着 `watch`（或已经装了开机自启）。

额度恢复后，打开 Codex App，点进**原来那条停住的对话**。不要去找新开的聊天。

---

## macOS 怎么用

Mac 版已经做了：代码和 Windows 相同，登录自启用 LaunchAgent。

### 1. 打开工具目录

```bash
cd /你的路径/codex-auto-resume
```

例如 clone 之后：

```bash
cd ~/codex-auto-resume
```

### 2. 先检查一次

```bash
python3 run.py doctor
```

同样看 `app_server OK`、`sessions_exist True`。

如果提示找不到 `codex`，先确认终端里能运行 `codex --version`。  
只装了 ChatGPT / Codex 桌面端、没有 CLI 时，工具会尝试使用：

- `/Applications/ChatGPT.app/Contents/Resources/codex`
- `/Applications/Codex.app/Contents/Resources/codex`

### 3. 启动自动续跑

**用法 A：当前窗口挂着**

```bash
python3 run.py watch
```

看到已启动后，保持这个终端开着。

**用法 B：登录 Mac 后自动在后台跑**

```bash
python3 run.py install-autostart
```

这会写入：

`~/Library/LaunchAgents/com.vibcoding.codex-auto-resume.plist`

登录后自动执行 `python3 run.py watch --quiet`。

卸掉：

```bash
python3 run.py uninstall-autostart
```

日志在：

- `~/Library/Logs/codex-auto-resume.log`
- `~/Library/Logs/codex-auto-resume.err.log`

### 4. 额度用完之后

同样：不用操作。额度回来后去 Codex App 打开**原来那条对话**。

---

## 它实际会做什么

1. 扫描最近 36 小时内、因为 usage limit 停住的会话
2. 读取当前额度（优先走 Codex 本机 app-server）
3. 等到 5 小时窗口恢复，或发现额度突然降下来（提前刷新）
4. 对**原来的 thread id** 执行续跑，不用 `--last`，避免续错对话
5. 如果桌面端正占着这条会话，会改成往同一条会话里排队发续跑消息

续跑时发给 Codex 的提示大意是：先检查工作区，不要重复已经做完的步骤，然后从未完成处继续。

默认最多自动跨 **1 个**额度窗口，避免无人值守把新额度烧光。

---

## 常用命令

在工具目录里执行。Windows 用 `python`，macOS 用 `python3`。

```text
run.py doctor              检查环境
run.py status              看额度和跟踪中的对话
run.py once --dry-run      只扫描，不真的续跑
run.py once                扫描一次，额度已恢复就续跑
run.py watch               前台常驻
run.py watch --quiet       后台静默常驻（开机自启用这个）
run.py install-autostart   安装开机/登录自启
run.py uninstall-autostart 取消开机/登录自启
```

`doctor` / `status` 只是给人看的，不是自动续跑本身。

---

## 配置在哪

第一次运行后自动生成，一般不用改。

- Windows：`%LOCALAPPDATA%\vibcoding\codex-auto-resume\config.json`
- macOS：`~/Library/Application Support/vibcoding/codex-auto-resume/config.json`

常见可改项：

| 字段 | 含义 | 默认 |
|---|---|---|
| `codex_home` | Codex 数据目录 | 环境变量 `CODEX_HOME`，否则 `~/.codex` |
| `lookback_hours` | 只处理最近多少小时内被打断的对话 | `36` |
| `max_auto_windows` | 同一条对话最多自动续几次额度窗口 | `1` |
| `poll_seconds` | 轮询间隔 | `30` |
| `resume_prompt` | 恢复后发给原对话的提示 | 见配置文件 |

运行日志：

- Windows：`%LOCALAPPDATA%\vibcoding\codex-auto-resume\daemon.log`
- macOS：同上 Application Support 目录下的 `daemon.log`，以及 `~/Library/Logs/codex-auto-resume*.log`

---

## 常见问题

**关了 `watch` 窗口还会自动续吗？**  
不会。要么把那个窗口一直开着，要么执行过 `install-autostart`。

**会不会新建一条对话？**  
不会。只在原来的 thread 里继续。

**会不会续错最近一条会话？**  
不会。它按原来的 thread id 续，不用 `--last`。

**我自己已经在原对话里又发过消息了？**  
它会认为你已经接手，不再自动发。

**很久以前停住的对话会不会被拉起来？**  
默认只看最近 36 小时。更早的不会动。

**Desktop 和 CLI 都能用吗？**  
能。它们共用同一套会话文件。续跑发生在原 thread，Codex App 打开那条聊天就能看到。

---

## 开发者

```bash
python -m unittest discover -s tests -v
```

Windows / macOS / Linux 都能跑这套测试。不需要真的登录 Codex。

# session-index-viewer

[English](README.md) · **简体中文**

本机浏览 AI 编程 CLI 会话的小工具。合并 **Claude Code**、**Codex**、**Devin**、
**Grok**、**Pi**、**Copilot CLI**、**opencode** 的 session，可搜索，可看 token /
工具用量（有元数据时），一键在
Terminal 新窗口里 resume。

<p align="center">
  <img src="docs/screenshot.jpg" alt="Session Index Viewer — 浏览并恢复 Claude Code / Codex / Devin / Grok / Pi / Copilot / opencode 会话" width="900" />
</p>

各 CLI 的 resume 列表多半只有 session ID 和时间戳，看不出当时在聊什么。本工具
展示每条 session 的开头提问和最后一次回复，方便挑中目标并接上。

hero 右上角有**深色模式**切换按钮，选择会保存在本地，首次访问时跟随系统
`prefers-color-scheme`。

> **仅支持 macOS。** 用 launchd 自启，通过 AppleScript / `open -na` 调用
> Ghostty、iTerm 或 Terminal.app。按该顺序自动检测已安装的终端。

## 运行

```bash
./install.sh            # 装成 launchd agent（开机自启 + 保活）
open http://localhost:7333
```

前台运行：`python3 server.py`。

改 UI 后重建前端（可选）：

```bash
cd frontend && npm install && npm run build
```

有 `frontend/dist/` 时由 `server.py` 提供该构建；否则回退到
`sessions-index.html`。

## 支持的来源

| 来源 | 默认路径 | Resume | 用量说明 |
|------|----------|--------|----------|
| Claude Code | `~/.claude/projects/*/*.jsonl` | `claude --resume <id>` | 累加 assistant 的 `message.usage`；Context 约为单轮 input+cache 峰值 |
| Codex | `~/.codex/sessions/**/rollout-*.jsonl` | `codex resume <id>` | 取最后一次累计 `token_count`；Context 约为各轮 total 最大 |
| Devin | `~/.local/share/devin/cli/sessions.db` | `devin -r <id>` | 从 `message_nodes` 聚合 |
| Grok | `$GROK_HOME/sessions`（默认 `~/.grok/sessions`） | `grok --resume <id>` | 磁盘上多为 **上下文占用**（`signals.json`） |
| Pi | `~/.pi/agent/sessions/*/*.jsonl` | `pi --session <id>` | 累加每轮 assistant 的 `message.usage`；Context 约为各轮 total 最大 |
| Copilot CLI | `~/.copilot/session-store.db` | `copilot --resume <id>` | 累加每轮 `assistant_usage_events`；Context 约为单轮 input 峰值 |
| opencode | `~/.local/share/opencode/opencode.db` | `opencode --session <id>` | 取 `session` 累计 token 汇总；Context 约为单条 assistant 消息 total 最大 |

详情栏里的 usage 是短 chip（`ctx · out · tools · turns`）。点击，或按
**`u`**，打开 modal：Overview KPI、token 分项、Activity、**上下文压力条**
（峰值 context 占该模型窗口上限的百分比，绿 / 黄 / 红三色），以及该 source
的计量口径说明。

**Context** 表示峰值 / 窗口占用，不是整场会话的计费 total。Grok 往往只有
size 信号（chip 上标 **size only**）。

## 布局

左栏列出 session，置顶的在前，其余按时间倒序。右栏显示当前 session 的
resume 和复制命令、usage 以及对话内容。对话里显示你的提问和 agent 的
回复，tool 调用只计数。打开时停在最新的消息，**Load earlier** 往前翻。
窗口较窄时，列表占满窗口，对话从右侧滑出覆盖在列表上。

## 搜索

输入时按标题、第一条和最后一条提问、cwd 和 session id 过滤，整串查询作为
一个字符串匹配。停止输入片刻后，同一个查询还会在所有对话的正文里搜索。
这一层每个词单独匹配，所有词都要出现在同一条消息里；`"双引号"` 可以把
短语当成一个整体。只在对话里命中的 session 也会加进列表，并显示命中条数。
结果仍按时间排序。中文、日文和代码片段都能搜到。

对话里的命中会高亮，`n` / `N` 在命中之间跳转。还没加载的消息里的命中会
显示条数，点击即可加载。

搜索索引存放在 `~/.cache/session-index-viewer/`，首次启动时在后台建立。
建好之前，列表会提示结果可能不全。删掉索引也没关系，会自动重建。

## 键盘

| 键 | 作用 |
|----|------|
| `j` / `k` 或方向键 | 移动当前 session（详情栏跟着切换） |
| `Enter` | 在 Terminal 中 resume |
| `c` | 复制 resume 命令（不含 ⌘C，系统复制仍可用） |
| `p` | 置顶 / 取消置顶 |
| `u` | 打开 usage modal（有用量数据时） |
| `x` | 删除 session（二次确认后移入 Trash） |
| `m` / ⌘ 点击 | 标记待批量删除；之后按 `x` 删除全部标记项 |
| `n` / `N` | 详情栏中跳到下一个 / 上一个搜索命中 |
| `Esc` | 清除标记；窄屏时关闭详情栏 |
| `⌘K` / `Ctrl+K` | 命令面板 |

## Headless session

没人能在里面接话的 session 算 **headless**，包括 `-p` 和 exec 运行、
ACP 或 MCP 驱动的会话以及 subagent，不论是脚本还是别的 agent 启动的。
它们带 `headless` 标记，默认隐藏，可以用工具栏的 origin 筛选显示出来。
`Headless Only` 配合批量删除可以一次清理。

| 来源 | 判定信号 |
|------|----------|
| Claude Code | 所有记录的 `entrypoint` 都是 `sdk-*`（`sdk-cli` 即 `claude -p`）；之后在 TUI 里接着聊就算交互 |
| Codex | `session_meta.originator` 为 `codex_exec`、`acpx` 或 `codex_cli_rs`，或 `source` 是 subagent（guardian 审批、派生的子线程） |
| Devin | 用户消息都不带 `chisel/client-message-id`。旧版 Devin 从不写这个字段，所以旧版产生的 session 不会被标记 |
| Copilot CLI | `session-state/<id>/events.jsonl` 的 system prompt 含 "running in non-interactive mode" |
| opencode | `opencode run`（`permission` 里 deny 了 `question`）或 subagent（有 `parent_id`） |
| Grok | `prompt_context.json` 中 `is_non_interactive: true` |
| Pi | 无法识别，`pi -p` 写出的 JSONL 与 TUI 相同 |

## 删除 session

详情栏顶部的垃圾桶按钮（或按 `x`）确认后经 `~/.Trash` 移除——
文件类 source（Claude / Codex / Pi / Grok）整体移入废纸篓；数据库类
source（Devin / Copilot / opencode）先把该 session 的所有行导出为
JSON 放入废纸篓，再删库里的行。`~/.Trash` 不存在时删除功能整体禁用。
工具栏的 **Turns** 筛选（`≤ 1/2/3`）可以把低轮次会话筛出来——比如
"reply with just: ok" 之类的单次会话——方便快速清理。

## 各部分

- `server.py` — 薄入口（`python3 server.py` / launchd）。
- `siv/` — 仅标准库的后端，监听 `127.0.0.1:7333`：
  - `GET /` 返回页面。
  - `GET /api/sessions` 实时扫描 session，按 mtime/size 缓存。
  - `GET /api/session` 返回某个 session 对话的一页。
  - `GET /api/search` 返回每个 session 的全文命中。
  - `POST /api/resume` 校验后打开终端执行
    `cd <cwd> && <工具> resume <id>`。若 cwd 是另一台机器的 home 前缀，
    会先映射到本机。
  - Host 标签取自 cwd 中的用户名（`/Users/<name>/...` 或 `/home/<name>/...`）。
  - 解析逻辑在 `siv/sources/`（`claude` / `codex` / `devin` / `grok` / `pi` /
    `copilot` / `opencode`）。
- `frontend/` — React 两栏 UI（session 列表和对话详情栏，含搜索、筛选、
  置顶、usage modal 和深浅色主题）。
- `sessions-index.html` — 旧版单文件 UI（无 dist 时回退）。
- `install.sh` — 写入 launchd plist，并可构建前端。日志：
  `~/Library/Logs/session-index-viewer.log`。
- `index-sessions.sh` — 早期 shell 索引，已被 `server.py` 取代。

## 多机配置

用 Syncthing 等同步 session 目录时：

| 路径 | 是否适合同步 |
|------|----------------|
| `~/.claude/projects` | 适合（按文件 jsonl） |
| `~/.codex/sessions` | 适合（按文件 jsonl） |
| `~/.grok/sessions` | 适合，建议只同步会话目录，并忽略 `session_search.sqlite`、`*.lock` |
| `~/.pi/agent/sessions` | 适合（按文件 jsonl） |
| Devin `sessions.db` | **不适合** — 单库 SQLite 无法多机合并 |
| Copilot `session-store.db` | **不适合** — 单库 SQLite 无法多机合并 |
| opencode `opencode.db` | **不适合** — 单库 SQLite 无法多机合并 |

Viewer 无需额外配置：按 session 记录的 cwd 用户名打 host 标签，toolbar
过滤器会列出这些 host。多台机器若 username 相同，会归到同一 host。

避免两台机器同时写同一个 session id（会产生 conflict 副本）。

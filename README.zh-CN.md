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
| Grok | `$GROK_HOME/sessions`（默认 `~/.grok/sessions`） | `grok --resume <id>` | 磁盘上多为 **上下文占用**（`signals.json`）；无头单次（`is_non_interactive`）会跳过 |
| Pi | `~/.pi/agent/sessions/*/*.jsonl` | `pi --session <id>` | 累加每轮 assistant 的 `message.usage`；Context 约为各轮 total 最大 |
| Copilot CLI | `~/.copilot/session-store.db` | `copilot --resume <id>` | 累加每轮 `assistant_usage_events`；Context 约为单轮 input 峰值 |
| opencode | `~/.local/share/opencode/opencode.db` | `opencode --session <id>` | 取 `session` 累计 token 汇总；Context 约为单条 assistant 消息 total 最大 |

卡片上的 usage 是短 chip（`ctx · out · tools · turns`）。点击，或在选中卡片后
按 **`u`**，打开 modal：Overview KPI、token 分项、Activity、**上下文压力条**
（峰值 context 占该模型窗口上限的百分比，绿 / 黄 / 红三色），以及该 source
的计量口径说明。

**Context** 表示峰值 / 窗口占用，不是整场会话的计费 total。Grok 往往只有
size 信号（chip 上标 **size only**）。

## 键盘

| 键 | 作用 |
|----|------|
| `j` / `k` 或方向键 | 移动当前卡片 |
| `Enter` | 在 Terminal 中 resume |
| `c` | 复制 resume 命令（不含 ⌘C，系统复制仍可用） |
| `p` | 置顶 / 取消置顶 |
| `u` | 打开 usage modal（有用量数据时） |
| `x` | 删除 session（二次确认后移入 Trash） |
| `⌘K` / `Ctrl+K` | 命令面板 |

## 删除 session

每张卡片有删除按钮（或选中后按 `x`），确认后经 `~/.Trash` 移除——
文件类 source（Claude / Codex / Pi / Grok）整体移入废纸篓；数据库类
source（Devin / Copilot / opencode）先把该 session 的所有行导出为
JSON 放入废纸篓，再删库里的行。`~/.Trash` 不存在时删除功能整体禁用。
工具栏的 **Turns** 筛选（`≤ 1/2/3`）可以把低轮次会话筛出来——比如
"reply with just: ok" 之类的单次会话——方便快速清理。

## 各部分

- `server.py` — 薄入口（`python3 server.py` / launchd）。
- `siv/` — 仅标准库的后端，监听 `127.0.0.1:7333`：
  - `GET /` 返回页面。
  - `GET /api/sessions?limit=1000` 实时扫描 session，按 mtime/size 缓存。
  - `POST /api/resume` 校验后打开终端执行
    `cd <cwd> && <工具> resume <id>`。若 cwd 是另一台机器的 home 前缀，
    会先映射到本机。
  - Host 标签取自 cwd 中的用户名（`/Users/<name>/...` 或 `/home/<name>/...`）。
  - 解析逻辑在 `siv/sources/`（`claude` / `codex` / `devin` / `grok` / `pi` /
    `copilot` / `opencode`）。
- `frontend/` — React 卡片 UI（搜索、source/host 过滤、置顶、usage modal、
  深色 / 浅色主题切换）。
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

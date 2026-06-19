# session-index-viewer

[English](README.md) · **简体中文**

本机浏览 Claude Code（`~/.claude/projects`）和 Codex（`~/.codex/sessions`）
session 的小工具：合并两边的会话历史、按时间排序、可搜索，一键在 Terminal
新窗口里 resume。

<p align="center">
  <img src="docs/screenshot.jpg" alt="Session Index Viewer — 浏览并恢复 Claude Code / Codex 会话" width="900" />
</p>

`claude --resume` 和 `codex resume` 只列出 session ID 和时间戳——根本看不出
哪一条是你想要的。这个工具会显示每条 session 的开头提问和最后一次回复，
让你一眼挑出"就是它"，回到上次断的地方继续。

> **仅支持 macOS。** 用 launchd 自启，通过 AppleScript / `open -na` 调用
> Ghostty、iTerm 或 Terminal.app。按这个顺序自动检测已安装的终端。

## 运行

```bash
./install.sh            # 装成 launchd agent（开机自启 + 保活）
open http://localhost:7333
```

或者前台跑：`python3 server.py`。

## 各部分

- `server.py` — 仅依赖标准库的 HTTP server，绑 `127.0.0.1:7333`。
  - `GET /` 返回页面。
  - `GET /api/sessions?limit=100` 实时扫描 session 文件，按 mtime/size
    缓存，只重新解析变化过的文件。
  - `POST /api/resume` 打开终端窗口执行
    `cd <cwd> && claude --resume <id>`（或 `codex resume <id>`）。如果
    session 记录的是另一台机器上的 home 路径，会先映射到当前机器再打开。
  - Host 标签从 cwd 的用户名推断：`/Users/<name>/...` 或
    `/home/<name>/...` 都标成 `<name>`，本机也一样。
- `sessions-index.html` — 卡片视图，含搜索、source / host 过滤器，每张
  卡片有 Copy / Open Terminal 两个 resume 入口。
- `install.sh` — 渲染 launchd plist 并 bootstrap。日志写到
  `~/Library/Logs/session-index-viewer.log`。
- `index-sessions.sh` — 早期的 shell 索引脚本，写 `sessions-index.json`，
  已被 `server.py` 取代。

## 多机配置

如果你用 syncthing 之类的工具把 `~/.claude/projects` 和 `~/.codex/sessions`
同步到多台机器，无需任何配置——每条 session 会按 cwd 里的 username 自动
打标签，toolbar 上的 host 过滤器会自动出现这些选项。如果另一台机器恰好
用相同 username，那两边会被归到同一个 host。

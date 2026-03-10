# CodeGuard Global Launcher

This folder contains the global `codeguard` launcher.
It is not a second implementation. Its job is to forward project commands to the local official script at `scripts/codeguard.py`.

这个目录包含全局 `codeguard` 启动器。
它不是第二套实现，它的作用只是把项目命令转发给项目内的官方脚本 `scripts/codeguard.py`。

## Install

Requires Python 3.10 or newer.

需要 Python 3.10 或更高版本。

```bash
# Install the skill bundle into detected IDE skill folders
python install.py

# Install the bundle and the global launcher
python install.py --install-cli
```

```bash
# 安装技能包到检测到的 IDE 技能目录
python install.py

# 同时安装技能包和全局启动器
python install.py --install-cli
```

On Windows the launcher is installed into `%USERPROFILE%\.codeguard\bin`.
On macOS and Linux it is installed into `~/.local/bin`.

在 Windows 上，启动器会安装到 `%USERPROFILE%\.codeguard\bin`。
在 macOS 和 Linux 上，会安装到 `~/.local/bin`。

## Supported Commands

Global command:

- `codeguard status`

Forwarded project-local commands:

- `codeguard init`
- `codeguard add`
- `codeguard index`
- `codeguard show-index`
- `codeguard validate-index`
- `codeguard backup`
- `codeguard confirm`
- `codeguard snapshot`
- `codeguard rollback`
- `codeguard list`

支持的命令：

全局命令：

- `codeguard status`

会转发到项目内官方脚本的命令：

- `codeguard init`
- `codeguard add`
- `codeguard index`
- `codeguard show-index`
- `codeguard validate-index`
- `codeguard backup`
- `codeguard confirm`
- `codeguard snapshot`
- `codeguard rollback`
- `codeguard list`

## Notes

- Run the launcher inside a project that already contains the CodeGuard bundle.
- For files over 200 lines, create or update the feature index only after the user authorizes it.
- Success still depends on explicit user confirmation, not on tests alone.

补充说明：

- 请在已经包含 CodeGuard 技能包的项目内使用这个启动器。
- 对超过 200 行的文件，只有在用户授权后才能创建或更新功能索引。
- 成功仍然只以用户明确确认作为准绳，不能仅靠测试结果判断。

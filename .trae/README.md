# Trae Installation

Use the shared installer to place the canonical CodeGuard bundle in a Trae or Trae CN skills directory.

使用共享安装脚本可以把标准 CodeGuard 技能包安装到 Trae 或 Trae CN 的技能目录中。

## Install

Requires Python 3.10 or newer.

需要 Python 3.10 或更高版本。

```bash
# Install into the first detected Trae skills directory and copy the Trae registry file
# 安装到第一个检测到的 Trae 技能目录，并复制 Trae 注册文件
python .trae/install.py

# Dry-run the copy plan
# 只预览复制计划，不实际写入
python .trae/install.py --dry-run

# Install into an explicit Trae skills directory
# 安装到指定的 Trae 技能目录
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry
```

The installer copies:

安装脚本会复制以下文件：

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/codeguard.py`
- `scripts/codeguard-cli.py`
- `README.md`
- `LICENSE`
- `.trae/skills/codeguard-skill.json` next to the installed bundle
- `.trae/skills/codeguard-skill.json`，放在技能包旁边

## Verify

After installation, the skills directory should contain:

安装完成后，技能目录应类似如下结构：

```text
<skills-dir>/
|- codeguard-skill/
|  |- SKILL.md
|  |- agents/openai.yaml
|  `- scripts/
`- codeguard-skill.json
```

Restart Trae after copying the files so the skill registry is reloaded.

复制完成后请重启 Trae，让技能注册表重新加载。

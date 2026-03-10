# Trae Installation

Use the shared installer to place the canonical CodeGuard bundle in a Trae or Trae CN skills directory.

使用共享安装脚本把标准 CodeGuard 技能包安装到 Trae 或 Trae CN 的技能目录中。

## Install

Requires Python 3.10 or newer.

需要 Python 3.10 或更高版本。

```bash
# Install into the first detected Trae skills directory and copy the Trae registry file
python .trae/install.py

# Dry-run the copy plan
python .trae/install.py --dry-run

# Install into an explicit Trae skills directory
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry
```

```bash
# 安装到第一个检测到的 Trae 技能目录，并复制 Trae 注册文件
python .trae/install.py

# 仅预览复制计划
python .trae/install.py --dry-run

# 安装到指定的 Trae 技能目录
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry
```

The installer copies:

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/codeguard.py`
- `scripts/codeguard-cli.py`
- `README.md`
- `LICENSE`
- `.trae/skills/codeguard-skill.json` next to the installed bundle

安装器会复制：

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/codeguard.py`
- `scripts/codeguard-cli.py`
- `README.md`
- `LICENSE`
- 以及安装目录旁边的 `.trae/skills/codeguard-skill.json`

## Verify

After installation, the skills directory should look like this:

安装完成后，技能目录应类似这样：

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

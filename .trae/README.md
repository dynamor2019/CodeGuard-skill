# Trae Installation

Use the shared installer to place the canonical CodeGuard bundle in a Trae or Trae CN skills directory.

## Install

Requires Python 3.10 or newer.

```bash
# Install into the first detected Trae skills directory and copy the Trae registry file
python .trae/install.py

# Dry-run the copy plan
python .trae/install.py --dry-run

# Install into an explicit Trae skills directory
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry
```

The installer copies:

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/codeguard_v2.py`
- `scripts/codeguard-v2.py`
- `scripts/codeguard-cli.py`
- `README.md`
- `LICENSE`
- `.trae/skills/codeguard-skill.json` next to the installed bundle

## Verify

After installation, the skills directory should contain:

```text
<skills-dir>/
|- codeguard-skill/
|  |- SKILL.md
|  |- agents/openai.yaml
|  `- scripts/
`- codeguard-skill.json
```

Restart Trae after copying the files so the skill registry is reloaded.

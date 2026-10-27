"""Instala arquivos que ferramentas remotas não podem gravar diretamente.

- Subagentes do Claude Code: infrastructure/claude-agents → .claude/agents
- Workflows do GitHub Actions: infrastructure/github-workflows → .github/workflows
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ROOT / "infrastructure" / "claude-agents": (ROOT / ".claude" / "agents", "*.md"),
    ROOT / "infrastructure" / "github-workflows": (ROOT / ".github" / "workflows", "*.yml"),
}


def main() -> None:
    for source_dir, (target_dir, pattern) in TARGETS.items():
        target_dir.mkdir(parents=True, exist_ok=True)
        for definition in sorted(source_dir.glob(pattern)):
            shutil.copyfile(definition, target_dir / definition.name)
            print(f"instalado: {target_dir / definition.name}")


if __name__ == "__main__":
    main()

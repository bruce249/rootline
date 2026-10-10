from __future__ import annotations

import shutil
from pathlib import Path

from rootline.clients.git import git, repo_root

# Agent hook settings that are not tracked on older branches. A worktree without
# them would run the fixer with no Entire hooks, so its session would have no checkpoint.
_HOOK_FILES = [".claude/settings.json", ".codex/hooks.json", ".cursor/hooks.json"]


def worktree_path(run_id: str) -> Path:
    return repo_root() / ".rootline" / "worktrees" / run_id


def ensure_worktree(state: dict) -> Path:
    """Check out the investigated branch in a private worktree, once per run.

    Rootline runs from the main checkout. FIX and VERIFY work in this worktree, so
    switching branches never swaps Rootline's own code out from under it.
    """
    root = repo_root()
    path = worktree_path(state["run_id"])
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "prune", cwd=root)
        git("worktree", "add", "--detach", str(path), state["branch"], cwd=root)
    for name in _HOOK_FILES:
        source = root / name
        target = path / name
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    state["worktree"] = str(path)
    return path


def remove_worktree(state: dict) -> None:
    path = state.get("worktree")
    if path and Path(path).exists():
        git("worktree", "remove", "--force", path, cwd=repo_root())

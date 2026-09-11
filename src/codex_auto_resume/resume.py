from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .paths import resolve_codex_command
from .procutil import hidden_popen, process_running

BUSY_HINTS = (
    "already owns",
    "already loaded",
    "cannot resume",
    "thread is loaded",
    "held open",
    "-32600",
)


def spawn_resume(
    *,
    thread_id: str,
    prompt: str,
    cwd: str | None,
    log_file: Path,
    extra_args: list[str],
    skip_git_repo_check: bool,
    prefer_queue_if_busy: bool,
    codex_bin: str | None,
    extra_env: dict[str, str] | None,
) -> tuple[int, str]:
    command = resolve_codex_command(codex_bin)
    args = [*command, "exec", "resume", "--all"]
    if skip_git_repo_check:
        args.append("--skip-git-repo-check")
    args.extend(extra_args)
    args.extend([thread_id, prompt])
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handle = log_file.open("a", encoding="utf-8", errors="replace")
    handle.write(f"$ {' '.join(args)}\n")
    handle.flush()
    proc = hidden_popen(
        args,
        cwd=cwd if cwd and Path(cwd).exists() else None,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if prefer_queue_if_busy:
        try:
            code = proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            return proc.pid, "exec-resume"
        output = log_file.read_text(encoding="utf-8", errors="replace")[-2000:].lower()
        if code != 0 and any(hint in output for hint in BUSY_HINTS):
            handle.write("\n# exec resume failed, fallback to queue\n")
            handle.flush()
            return _spawn_queue(
                command=command,
                thread_id=thread_id,
                prompt=prompt,
                cwd=cwd,
                handle=handle,
                env=env,
                extra_args=extra_args,
            ), "queue"
        if code != 0:
            raise RuntimeError(f"codex exec resume 失败，exit={code}，详见 {log_file}")
        return proc.pid, "exec-resume-finished"
    return proc.pid, "exec-resume"


def _spawn_queue(
    *,
    command: list[str],
    thread_id: str,
    prompt: str,
    cwd: str | None,
    handle,
    env: dict[str, str],
    extra_args: list[str],
) -> int:
    args = [*command, "queue", "--thread", thread_id, "--message", prompt, *extra_args]
    handle.write(f"$ {' '.join(args)}\n")
    handle.flush()
    proc = hidden_popen(
        args,
        cwd=cwd if cwd and Path(cwd).exists() else None,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc.pid

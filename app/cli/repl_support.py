"""Shared support for the admin CLI interactive shell."""

from __future__ import annotations

import shlex
from pathlib import Path

try:
    import readline
except ImportError:  # pragma: no cover
    readline = None

MAX_HISTORY_BYTES = 1024 * 1024
MAX_HISTORY_LINES = 2000


def normalize_repl_tokens(raw: str) -> list[str]:
    """Parse one raw REPL command line into CLI tokens."""

    normalized = raw.lstrip()
    if normalized.startswith("/"):
        normalized = normalized[1:].lstrip()
    return shlex.split(normalized)


def repl_command_catalog() -> list[str]:
    """Return the static command list used for REPL completion."""

    return sorted(
        [
            "artifact fetch",
            "customer billing create",
            "customer billing delete",
            "customer billing duplicates",
            "customer billing list",
            "customer billing merge",
            "customer billing update",
            "customer billing usage",
            "customer create",
            "customer delete",
            "customer duplicates",
            "customer list",
            "customer merge",
            "customer update",
            "customer usage",
            "device approve",
            "device issue-token",
            "device list",
            "device pending",
            "device revoke",
            "device validate",
            "exit",
            "export changes",
            "export geojson-fetch",
            "export image-fetch",
            "export images-fetch-all",
            "final inspect",
            "final set-correction",
            "final set-final",
            "help",
            "job assign",
            "job create",
            "job inspect",
            "job list-assignments",
            "job set-status",
            "job unassign",
            "job unlock",
            "job update",
            "net ipv4",
            "net ipv6",
            "quit",
            "review inspect",
            "round inspect",
            "round reopen",
            "set api-key",
            "set host",
            "show",
            "stage sync",
            "tree identify",
            "use cloud",
            "use local",
            "use remote",
        ]
    )


def setup_repl_readline(*, history_path: Path, commands: list[str] | None = None) -> None:
    """Configure readline history and completion for the REPL."""

    if readline is None:
        return
    try:
        if history_path.exists() and history_path.stat().st_size <= MAX_HISTORY_BYTES:
            readline.read_history_file(str(history_path))
    except FileNotFoundError:
        pass
    except OSError:
        pass

    if hasattr(readline, "set_history_length"):
        readline.set_history_length(MAX_HISTORY_LINES)

    known_commands = commands or repl_command_catalog()

    def completer(text: str, state: int) -> str | None:
        buffer = readline.get_line_buffer().lstrip("/")
        prefix = buffer if buffer else text
        matches = [cmd for cmd in known_commands if cmd.startswith(prefix)]
        if state >= len(matches):
            return None
        return matches[state]

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def save_repl_history(*, history_path: Path) -> None:
    """Persist readline history when available."""

    if readline is None:
        return
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(str(history_path))
    except OSError:
        pass

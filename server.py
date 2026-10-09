import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import sqlite3
from contextlib import closing

mcp = FastMCP("personal-mcp")

# The ONLY folder the tools are allowed to touch
WORKSPACE = Path(
    os.environ.get("MCP_WORKSPACE", Path(__file__).parent / "workspace")
).resolve()
WORKSPACE.mkdir(exist_ok=True)

MAX_READ_BYTES = 200_000
MAX_RESULTS = 50
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".py",
    ".json",
    ".csv",
    ".log",
    ".toml",
    ".yaml",
    ".yml",
}
MAX_NOTE_CHARS = 5000

DB_PATH = Path(__file__).parent / "memory.db"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with db() as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes(
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)


def safe_path(relative: str) -> Path:
    """Turn a user-given path into a real path, refusing anything outside WORKSPACE."""
    candidate = (WORKSPACE / relative).resolve()
    if not candidate.is_relative_to(WORKSPACE):
        raise ValueError("Path is outside the authorized workspace")
    return candidate


@mcp.tool()
def ping() -> str:
    """Health check: confirms the server is alive."""
    return "pong"


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@mcp.tool()
def list_files(subdir: str = ".") -> list[str]:
    """List files and folders in the workspace (or a subfolder of it)."""
    base = safe_path(subdir)
    if not base.is_dir():
        raise ValueError(f"Not a folder: {subdir}")
    return sorted(
        str(p.relative_to(WORKSPACE)) + ("/" if p.is_dir() else "")
        for p in base.iterdir()
    )


@mcp.tool()
def read_file(path: str) -> str:
    """Read a text file from the workspace."""
    file = safe_path(path)
    if not file.is_file():
        raise ValueError(f"Not a file: {path}")
    if file.stat().st_size > MAX_READ_BYTES:
        raise ValueError("File is too large to read")
    return file.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def search_text(query: str, subdir: str = ".") -> list[str]:
    """Search text files in the workspace for a word or phrase (case-insensitive)."""
    base = safe_path(subdir)
    q = query.lower()
    results: list[str] = []
    for file in base.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if not file.resolve().is_relative_to(WORKSPACE):
                continue
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if q in line.lower():
                results.append(
                    f"{file.relative_to(WORKSPACE)}:{number}: {line.strip()[:200]}"
                )
                if len(results) >= MAX_RESULTS:
                    return results
    return results


@mcp.tool()
def add_notes(content: str) -> str:
    """Save a note to personal memory."""
    content = content.strip()
    if not content:
        raise ValueError("Note is empty")
    if len(content) > MAX_NOTE_CHARS:
        raise ValueError(f"Note too long(max {MAX_NOTE_CHARS} characters)")
    with closing(db()) as conn, conn:
        cur = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        return f"Saved note #{cur.lastrowid}"


if __name__ == "__main__":
    mcp.run()

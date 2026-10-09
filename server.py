import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

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


def safe_path(relative: str) -> Path:
    """Turn a user-given path into a real path, refusing anything outside WORKSPACE."""
    candidate = (WORKSPACE / relative).resolve()  # resolves ../ and symlinks
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


if __name__ == "__main__":
    mcp.run()

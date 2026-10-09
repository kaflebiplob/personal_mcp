import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import sqlite3
from contextlib import closing
import httpx
import re
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

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
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

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
def add_note(content: str) -> str:
    """Save a note to personal memory."""
    content = content.strip()
    if not content:
        raise ValueError("Note is empty")
    if len(content) > MAX_NOTE_CHARS:
        raise ValueError(f"Note too long(max {MAX_NOTE_CHARS} characters)")
    with closing(db()) as conn, conn:
        cur = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        return f"Saved note #{cur.lastrowid}"


@mcp.tool()
def list_notes(limit: int = 20) -> list[str]:
    """List the most recent notes (newest note first)"""
    limit = max(1, min(limit, 100))
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [f"#{r['id']} [{r['created_at']}] {r['content']}" for r in rows]


@mcp.tool()
def search_notes(query: str) -> list[str]:
    """Search saved notes for a word or phrase."""
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id,content,created_at FROM notes "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
    return [f"#{r['id']} [{r['created_at']}] {r['content']}" for r in rows]


@mcp.tool()
def delete_note(note_id: int) -> str:
    """Delete a note  by its id number."""
    with closing(db()) as conn, conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cur.rowcount == 0:
            raise ValueError(f"No note with id {note_id}")
    return f"Deleted note #{note_id}"


def github_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Github token is not set, please check .env file")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-Github-Api-Version": "2022-11-28",
    }


@mcp.tool()
async def list_repos(limit: int = 20) -> list[str]:
    """List Github repositories the token can access."""
    limit = max(1, min(limit, 50))
    github_api = os.environ.get("GITHUB_API")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{github_api}/user/repos",
            headers=github_headers(),
            params={"sort": "updated", "per_page": limit},
        )
        resp.raise_for_status()
    return [
        f"{r['full_name']} ({'private' if r['private'] else 'public'})"
        f"- {r.get('description') or 'no description'}"
        for r in resp.json()
    ]


@mcp.tool()
async def list_issues(repo: str, limit: int = 10) -> list[str]:
    """List open issues in a Github repo. Use the owner name"""
    if not REPO_PATTERN.match(repo):
        raise ValueError("Repo must look like owner/name")

    limit = max(1, min(limit, 30))
    github_api = os.environ.get("GITHUB_API")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{github_api}/repos/{repo}/issues",
            headers=github_headers(),
            params={"state": "open", "per_page": limit},
        )
        resp.raise_for_status()
    return [
        f"#{i['number']} {i['title']} (by {i['user']['login']})"
        for i in resp.json()
        if "pull_request" not in i
    ]


@mcp.tool()
async def get_weather(city: str) -> str:
    """Get the current weather for a city (uses the free open-meteo service)."""
    city = city.strip()
    if not city:
        raise ValueError("City is empty")

    async with httpx.AsyncClient(timeout=10) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
        )
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            raise ValueError(f"City not found: {city}")
        place = results[0]
        weather = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,wind_speed_10m",
            },
        )
        weather.raise_for_status()
        current = weather.json()["current"]
    return (
        f"{place['name']}, {place.get('country', '')}: "
        f"{current['temperature_2m']}°C, wind {current['wind_speed_10m']} km/h"
    )


if __name__ == "__main__":
    mcp.run()

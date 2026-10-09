import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import httpx
import re
import psycopg
from psycopg.rows import dict_row
import functools
import inspect
import logging
import time


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

LOG_PATH = Path(__file__).parent / "logs" / "tools.log"
LOG_PATH.parent.mkdir(exist_ok=True)

audit = logging.getLogger("audit")
audit.setLevel(logging.INFO)
audit.propagate = False
_handler = logging.FileHandler(LOG_PATH)
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
audit.addHandler(_handler)


def db() -> psycopg.Connection:
    url = os.environ.get("MCP_DATABASE_URL")
    if not url:
        raise ValueError("DATABASE URL is not set please check .env file")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=5)


def init_db() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                content    TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


def format_note(r) -> str:
    return f"#{r['id']} [{r['created_at']:%Y-%m-%d %H:%M}] {r['content']}"


init_db()


def logged(fn):
    def describe(args, kwargs):
        parts = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
        return ", ".join(parts)[:200]

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                audit.info(
                    "ERROR %s(%s) -> %s",
                    fn.__name__,
                    describe(args, kwargs),
                    type(exc).__name__,
                )
                raise
            audit.info(
                "ok %s(%s) %0fms",
                fn.__name__,
                describe(args, kwargs),
                (time.perf_counter() - start) * 1000,
            )
            return result

    else:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                audit.info(
                    "ERROR %s(%s) -> %s",
                    fn.__name__,
                    describe(args, kwargs),
                    type(exc).__name__,
                )
                raise
            audit.info(
                "ok %s(%s) %0fms",
                fn.__name__,
                describe(args, kwargs),
                (time.perf_counter() - start) * 1000,
            )
            return result

    return wrapper


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
@logged
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
@logged
def read_file(path: str) -> str:
    """Read a text file from the workspace."""
    file = safe_path(path)
    if not file.is_file():
        raise ValueError(f"Not a file: {path}")
    if file.stat().st_size > MAX_READ_BYTES:
        raise ValueError("File is too large to read")
    return file.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
@logged
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
@logged
def add_note(content: str) -> str:
    """Save a note to personal memory."""
    content = content.strip()
    if not content:
        raise ValueError("Note is empty")
    if len(content) > MAX_NOTE_CHARS:
        raise ValueError(f"Note too long(max {MAX_NOTE_CHARS} characters)")
    with db() as conn:
        row = conn.execute(
            "INSERT INTO notes (content) VALUES (%s) RETURNING id", (content,)
        ).fetchone()
    return f"Saved note #{row['id']}"


@mcp.tool()
@logged
def list_notes(limit: int = 20) -> list[str]:
    """List the most recent notes (newest note first)"""
    limit = max(1, min(limit, 100))
    with db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [format_note(r) for r in rows]


@mcp.tool()
@logged
def search_notes(query: str) -> list[str]:
    """Search saved notes for a word or phrase."""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes "
            "WHERE content ILIKE %s ORDER BY id DESC LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
    return [format_note(r) for r in rows]


@mcp.tool()
@logged
def delete_note(note_id: int) -> str:
    """Delete a note  by its id number."""
    with db() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))
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
@logged
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
@logged
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
@logged
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

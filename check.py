import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="uv", args=["run", "server.py"])


async def call(session, name, args):
    result = await session.call_tool(name, args)
    text = " | ".join(c.text for c in result.content)
    status = "ERROR" if result.isError else "ok"
    print(f"[{status}] {name}({args})\n    -> {text}\n")


async def main():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools], "\n")

            await call(session, "list_files", {})
            await call(session, "read_file", {"path": "hello.txt"})
            await call(session, "search_text", {"query": "mcp"})

            await call(session, "read_file", {"path": "../pyproject.toml"})
            await call(session, "read_file", {"path": "/etc/passwd"})

            await call(session, "add_note", {"content": "My first note"})
            await call(session, "list_notes", {})
            await call(session, "search_notes", {"query": "first"})
            await call(session, "delete_note", {"note_id": 1})
            await call(session, "list_notes", {})


asyncio.run(main())

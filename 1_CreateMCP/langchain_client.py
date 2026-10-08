from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio
import os

project_dir = os.path.dirname(os.path.abspath(__file__))
venv_dir = os.path.join(os.path.dirname(project_dir), "venv")
mcp_server = os.path.join(project_dir, "first_mcp_server_stdio.py")


async def main():

    client = MultiServerMCPClient(
        # MCP Server Config
        {
            "data_fetch_mcp_stdio": {
                "transport": "stdio",
                "command": os.path.join(venv_dir, "bin", "python3.14"),
                "args": [str(mcp_server)],
            }
        }
    )

    tools = await client.get_tools()
    print("Available tools", tools)


if __name__ == "__main__":
    asyncio.run(main())

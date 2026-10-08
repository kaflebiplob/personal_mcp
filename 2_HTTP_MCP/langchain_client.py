from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio


async def main():

    client = MultiServerMCPClient(
        # MCP Server Config
        {
            "data_fetch_mcp_http": {
                "transport": "streamable-http",
                "url": "http://localhost:8050/mcp",
            },
        }
    )

    tools = await client.get_tools()
    print("Available tools", tools)


if __name__ == "__main__":
    asyncio.run(main())

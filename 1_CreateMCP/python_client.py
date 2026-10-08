import os
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters, Client
import asyncio

# Path to our mcp server

mcp_server_script = os.path.join(os.path.dirname(__file__), "first_mcp_server_stdio.py")

print(mcp_server_script)

# create server parameters
server_params = StdioServerParameters(
    command="python",
    args=[str(mcp_server_script)],
    env={},
)

# create a client session

async def main():
    async with stdio_client(server_params) as (read, write):

        async with ClientSession(read,write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Available tools:",tools)

            result = await session.call_tool("process",arguments={"path":"/path/to/data"})
            print("result:",result)



if __name__ == "__main__":
    asyncio.run(main())
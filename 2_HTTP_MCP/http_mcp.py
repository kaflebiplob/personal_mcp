from fastmcp import FastMCP

# create mcp instance
mcp = FastMCP()


@mcp.tool()
def fetch():
    """This is string and converts into the description."""
    return {"data": "Hello, this is MCP"}


@mcp.tool()
def process(path: str):

    return {"data": "Hello, MCP Process here!!" + path}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8050)

from fastmcp import FastMCP

# create mcp instance
mcp = FastMCP()


@mcp.tool()
def fetch():
    '''This is string and converts into the description.'''
    return {"data": "Hello, this is MCP"}


@mcp.tool()
def process():

    return {"data": "Hello, MCP Process here!!"}


if __name__ == "__main__":
    mcp.run(transport="stdio")

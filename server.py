from mcp.server.fastmcp import FastMCP

mcp = FastMCP("personal-mcp")


@mcp.tool()
def ping() -> str:
    """Health check: confirms the server is still alive."""
    return "pong"


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run()

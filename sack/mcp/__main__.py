"""Run with `python -m sack.mcp`; HTTP requires bearer authentication."""

import argparse
import logging
import os

from .server import BearerAuth, create_server, load_tokens


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")
    parser.add_argument("--host", default=os.environ.get("SACK_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SACK_MCP_PORT", "8765")))
    parser.add_argument("--allowed-host", action="append", help="Allowed Host header, e.g. sack.example.com (repeatable).")
    parser.add_argument("--allowed-origin", action="append", help="Allowed browser Origin, e.g. https://sack.example.com (repeatable).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = create_server(allowed_hosts=args.allowed_host, allowed_origins=args.allowed_origin)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        import uvicorn
        app = BearerAuth(server.streamable_http_app(), load_tokens())
        # Access logs include query strings; audit only client labels and tool results above.
        uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()

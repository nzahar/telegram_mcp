"""FastMCP stdio entrypoint.

Run as ``python -m tg_mcp.server``. The server speaks JSON-RPC over stdio,
so nothing may be written to stdout outside the protocol — all diagnostic
output goes through the file logger configured by :mod:`tg_mcp.logging_setup`.
``show_banner=False`` is set explicitly to suppress FastMCP's startup banner.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware

from . import client as tg_client
from . import tools
from .logging_setup import setup_logging


log = logging.getLogger("tg_mcp.server")


def _route_fastmcp_logs_to_file() -> None:
    """Strip FastMCP's RichHandler and re-enable propagation so its logs flow
    through our root file handler instead of leaking onto stderr.

    Called at import time so any entry point (``python -m tg_mcp.server``,
    direct import + ``mcp.run()``, or in-process test harness) inherits the
    clean configuration without having to remember to go through :func:`main`.
    """
    fastmcp_logger = logging.getLogger("fastmcp")
    for h in list(fastmcp_logger.handlers):
        fastmcp_logger.removeHandler(h)
        h.close()
    fastmcp_logger.propagate = True


_route_fastmcp_logs_to_file()


@asynccontextmanager
async def _lifespan(_mcp: FastMCP) -> Any:
    log.info("server starting")
    try:
        yield
    finally:
        log.info("server stopping; disconnecting Telethon client")
        await tg_client.shutdown()


class _CallLoggingMiddleware(Middleware):
    """Logs each tool call: name, arg keys, elapsed ms.

    Arg values are not logged — only keys — so ``send_to_self.text`` content
    never appears in the log file.
    """

    async def on_call_tool(self, context, call_next):
        params = context.message
        name = params.name
        arg_keys = sorted((params.arguments or {}).keys())
        start = time.monotonic()
        log.info("tool_call name=%s arg_keys=%s", name, arg_keys)
        try:
            result = await call_next(context)
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            log.exception("tool_error name=%s elapsed_ms=%.1f", name, elapsed_ms)
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        log.info("tool_done name=%s elapsed_ms=%.1f", name, elapsed_ms)
        return result


mcp = FastMCP(
    "tg-mcp",
    lifespan=_lifespan,
    middleware=[_CallLoggingMiddleware()],
)
mcp.tool(tools.search_channels)
mcp.tool(tools.get_recent)
mcp.tool(tools.send_to_self)


def main() -> None:
    load_dotenv()
    setup_logging()
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()

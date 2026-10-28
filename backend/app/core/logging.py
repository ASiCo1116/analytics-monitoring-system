import logging
import re
import sys
import time

from fastapi import Request

logger = logging.getLogger("app.request")


TOKEN_IN_URL = re.compile(r"(token=)[^&\s\"]+")


class RedactTokens(logging.Filter):
    """Hide `token=...` query values in log messages.

    Uvicorn logs every WebSocket handshake with its full URL, and
    /ws/metrics carries the JWT in the query string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                TOKEN_IN_URL.sub(r"\1***", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        if isinstance(record.msg, str):
            record.msg = TOKEN_IN_URL.sub(r"\1***", record.msg)
        return True


def setup_logging(level: str) -> None:
    """Send all application logs to stdout as `time level logger message`."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # A logger's filters only see records logged on that logger itself, so
    # the filter goes on the one uvicorn uses for the handshake lines
    logging.getLogger("uvicorn.error").addFilter(RedactTokens())


async def log_requests(request: Request, call_next):
    """HTTP middleware: one log line per request.

    Logs method, path, status and duration. Only the path is logged, never
    the query string, so tokens in URLs stay out of the logs.
    """
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

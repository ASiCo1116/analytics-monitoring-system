import logging
import sys
import time

from fastapi import Request

logger = logging.getLogger("app.request")


def setup_logging(level: str) -> None:
    """Send all application logs to stdout as `time level logger message`."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


async def log_requests(request: Request, call_next):
    """HTTP middleware: one log line per request with method, path, status and duration.

    Only the path is logged, never the query string, so tokens in URLs stay out of the logs.
    """
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s %s %.1fms", request.method, request.url.path, response.status_code, duration_ms
    )
    return response

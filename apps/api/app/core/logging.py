# WHAT: Configures the root logger so every module's `logging.getLogger(__name__)`
#       emits structured lines to stdout.
# WHY:  Render captures stdout as log output. Calling this once at startup,
#       before any other module initialises its logger, means every log line
#       (from routers, services, etc.) is formatted consistently and uvicorn's
#       noisy per-request access log is silenced down to WARNING.

import logging
import sys


def configure_logging() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

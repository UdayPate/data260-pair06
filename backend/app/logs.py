"""Log set-up: make the project's own log lines (logger names starting with "handshake") visible in `docker logs`.
uvicorn only configures its own loggers, so without this the API's "event=published ... trace_id=..." lines would be dropped."""
import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    log = logging.getLogger("handshake")
    if not log.handlers:                       # only once, however many apps are created
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMAT))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False

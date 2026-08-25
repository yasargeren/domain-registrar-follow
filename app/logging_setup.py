import logging
import sys
from logging.handlers import RotatingFileHandler
from .config import LOG_PATH, LOG_LEVEL

_configured = False


def setup(component="app"):
    global _configured
    if _configured:
        return logging.getLogger(component)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    try:
        fileh = RotatingFileHandler(LOG_PATH, maxBytes=20 * 1024 * 1024, backupCount=5)
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
    except OSError as exc:  # read-only volume etc. -- keep stdout logging alive
        root.warning("file logging disabled: %s", exc)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _configured = True
    return logging.getLogger(component)

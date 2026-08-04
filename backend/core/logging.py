"""Application logging configuration (CPM-001, unmodified)."""
from __future__ import annotations

import logging
import logging.handlers

from backend.core.config import Settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_FILE_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5


def configure_logging(settings: Settings) -> None:
    settings.log_file_path.parent.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=settings.log_file_path, maxBytes=MAX_LOG_FILE_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger(__name__).info(
        "Logging initialized (level=%s, console=on, file=%s)",
        settings.LOG_LEVEL.upper(), settings.log_file_path,
    )

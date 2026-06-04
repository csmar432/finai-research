"""Logging configuration for the research workflow."""

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    log_dir: str = ".cache/logs",
    level: int = logging.INFO,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    console: bool = True,
) -> logging.Logger:
    """
    Configure project-wide logging with file rotation and console output.

    Args:
        log_dir: Directory to store log files.
        level: Minimum log level for the logger.
        max_bytes: Maximum size of each log file before rotation.
        backup_count: Number of backup log files to keep.
        console: Whether to add console handler (WARNING+ only).

    Returns:
        Configured root logger for the project.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("finai")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    fh = logging.handlers.RotatingFileHandler(
        log_path / "workflow.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    if console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.

    Args:
        name: Module name (e.g., "data_pipeline", "llm").

    Returns:
        Child logger instance under the "finai" namespace.
    """
    return logging.getLogger(f"finai.{name}")

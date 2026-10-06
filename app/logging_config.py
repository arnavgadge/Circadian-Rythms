"""Centralized logging configuration for the application.

Application code should use ``logging.getLogger(__name__)`` and never
``print`` for operational output; this module wires the root logger up
once at startup.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root logger for the whole application.

    Safe to call multiple times (e.g. across tests); each call resets
    the root logger's handlers so output is not duplicated.
    """

    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

import logging
import sys

from loguru import logger

from app.core.config import settings


def configure_logging() -> None:
    logging.getLogger("uvicorn.access").disabled = True
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        colorize=sys.stdout.isatty(),
        backtrace=False,
        diagnose=False,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    )

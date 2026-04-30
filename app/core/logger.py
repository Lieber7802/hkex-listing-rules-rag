import logging
import sys
from app.core.config import settings


def setup_logger(name: str = "agentic_rag") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


logger = setup_logger()

"""
日志系统 - 结构化日志输出
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_DIR = "logs"


def setup_logger(
    name: str = "memory_assistant", log_level: str = "INFO"
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "memory_assistant") -> logging.Logger:
    return logging.getLogger(name)


default_logger = setup_logger()


def debug(msg: str, *args, **kwargs):
    default_logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    default_logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    default_logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    default_logger.error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs):
    default_logger.critical(msg, *args, **kwargs)


def get_module_logger(module_name: str) -> logging.Logger:
    return logging.getLogger(f"memory_assistant.{module_name}")

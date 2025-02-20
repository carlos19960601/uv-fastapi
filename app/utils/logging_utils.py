import logging
import sys
from typing import Optional

from app.core.config import settings


def configure_logging(
    name: Optional[str] = None,
    log_level: int = settings.log.level,
) -> logging.Logger:
    """
    一个日志记录器，支持日志轮转和控制台输出，使用 ConcurrentRotatingFileHandler 处理器。

    A logger that supports log rotation and console output, using the ConcurrentRotatingFileHandler handler.

    :param name: 日志记录器的名称，默认为 None，使用根记录器。 | The name of the logger, default is None, using the root logger.
    :param log_level: 日志级别，默认为 logging.DEBUG。 | The log level, default is logging.DEBUG.
    :param log_dir: 日志文件目录，默认为 './log_files'。 | The log file directory, default is './log_files'.
    :param log_file_prefix: 日志文件前缀，默认为 'app'。 | The log file prefix, default is 'app'.
    :param backup_count: 保留的备份文件数量，默认为 7。 | The number of backup files to keep, default is 7.
    :param encoding: 日志文件编码，默认为 'utf-8'。 | The log file encoding, default is 'utf-8'.
    :return: 配置好的日志记录器。 | The configured logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # 防止重复添加处理器 | Prevent duplicate handlers
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 配置控制台处理器 | Configure console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

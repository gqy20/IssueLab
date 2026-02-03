"""日志配置模块"""

import logging
import sys
from pathlib import Path


def setup_logging(
    level: str = "INFO", log_file: Path | None = None, format_string: str | None = None
) -> logging.Logger:
    """配置日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（可选）
        format_string: 日志格式字符串（可选）

    Returns:
        配置好的 logger
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

    # 配置根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # 清除现有 handlers
    root_logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(format_string)

    # 控制台处理器 - 输出到stderr以避免与JSON输出混淆
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG)  # 改为 DEBUG 级别以显示完整日志
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（如果指定）
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 返回 issuelab 命名空间的 logger
    return logging.getLogger("issuelab")


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger

    Args:
        name: logger 名称

    Returns:
        Logger 实例
    """
    return logging.getLogger(f"issuelab.{name}")

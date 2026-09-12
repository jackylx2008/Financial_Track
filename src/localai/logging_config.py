"""旧导入路径的日志兼容层；新代码应从项目根模块导入。"""

from logging_config import configure_utf8_stdio, get_logger, setup_logger

__all__ = ["configure_utf8_stdio", "get_logger", "setup_logger"]

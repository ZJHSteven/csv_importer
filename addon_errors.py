# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件提供统一的异常与日志接口，保证错误处理集中在一处，主流程只调用这里的能力。
"""  # 说明：文件级说明，强调职责边界

from __future__ import annotations  # 说明：允许使用前向引用类型标注

import logging  # 说明：使用标准库日志模块统一输出


class CsvImporterError(Exception):  # 说明：插件基础异常类型，统一继承入口
    """插件统一异常基类。"""  # 说明：用中文说明该异常用途

    pass  # 说明：基类无需额外实现


class ConfigError(CsvImporterError):  # 说明：配置相关异常
    """配置读取或写入时的异常。"""  # 说明：中文解释异常范围

    pass  # 说明：无额外逻辑


class ParseError(CsvImporterError):  # 说明：解析相关异常
    """解析混合格式文本时的异常。"""  # 说明：中文解释异常范围

    pass  # 说明：无额外逻辑


class ImportProcessError(CsvImporterError):  # 说明：导入相关异常
    """导入到 Anki 集合时的异常。"""  # 说明：中文解释异常范围

    pass  # 说明：无额外逻辑


class TtsError(CsvImporterError):  # 说明：TTS 相关异常
    """语音生成或写入媒体时的异常。"""  # 说明：中文解释异常范围

    pass  # 说明：无额外逻辑


class SessionError(CsvImporterError):  # 说明：会话记录相关异常
    """导入会话记录与回滚时的异常。"""  # 说明：中文解释异常范围

    pass  # 说明：无额外逻辑


class AppLogger:  # 说明：统一日志封装，便于后续替换为 Anki 的 UI 日志
    """统一日志封装。"""  # 说明：简要说明用途

    def __init__(self, name: str = "csv_importer") -> None:  # 说明：初始化日志对象
        self._logger = logging.getLogger(name)  # 说明：获取标准库 logger 实例
        self._logger.setLevel(logging.INFO)  # 说明：默认设置为 INFO 级别
        if not self._logger.handlers:  # 说明：避免重复添加 handler
            handler = logging.StreamHandler()  # 说明：输出到标准输出的 handler
            formatter = logging.Formatter("[%(levelname)s] %(message)s")  # 说明：简单易读格式
            handler.setFormatter(formatter)  # 说明：把格式器绑定到 handler
            self._logger.addHandler(handler)  # 说明：将 handler 注册到 logger

    def info(self, message: str) -> None:  # 说明：输出普通信息
        self._logger.info(message)  # 说明：调用标准库 info

    def warning(self, message: str) -> None:  # 说明：输出警告信息
        self._logger.warning(message)  # 说明：调用标准库 warning

    def error(self, message: str) -> None:  # 说明：输出错误信息
        self._logger.error(message)  # 说明：调用标准库 error


logger = AppLogger()  # 说明：提供一个模块级默认 logger，供全局使用

# -*- coding: utf-8 -*-
"""
本文件测试插件日志封装。

重点不是验证 Python logging 本身，而是防止回归到“把 INFO 写入标准输出/错误流”的实现。
在 Anki 插件环境里，标准输出/错误流可能被 Anki 当作插件异常信息展示给用户。
"""

from __future__ import annotations

import importlib
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]  # 说明：插件根目录，用于按临时包加载源码
PACKAGE_NAME = "csv_importer_logger_test_pkg"  # 说明：避免执行真实 __init__.py 里的 aqt 入口


def _load_module(module_name: str):
    """按临时包名加载插件模块。

    输入：模块短名。
    输出：导入后的模块对象。
    核心逻辑：给源码创建一个临时包上下文，让相对导入能够正常解析。
    """
    if PACKAGE_NAME not in sys.modules:  # 说明：首次导入时创建临时包
        package = types.ModuleType(PACKAGE_NAME)  # 说明：构造轻量包对象
        package.__path__ = [str(ROOT)]  # 说明：指定源码查找路径
        sys.modules[PACKAGE_NAME] = package  # 说明：注册到导入系统
    return importlib.import_module(f"{PACKAGE_NAME}.{module_name}")  # 说明：导入子模块


addon_errors = _load_module("addon_errors")  # 说明：加载被测日志模块


class AppLoggerTests(unittest.TestCase):
    """覆盖日志 handler 的安全配置。"""

    def test_logger_clears_stream_handler_and_keeps_file_handler_only(self):
        logger_name = "csv_importer_test_stream_cleanup"  # 说明：使用独立 logger，避免污染真实插件 logger
        raw_logger = logging.getLogger(logger_name)  # 说明：拿到底层标准库 logger
        raw_logger.handlers = []  # 说明：清空历史状态，保证测试可重复
        raw_logger.addHandler(logging.StreamHandler())  # 说明：模拟旧版本遗留的标准输出 handler

        with patch.object(addon_errors, "get_log_path", return_value=ROOT / "user_files" / "logs" / "test_logger.log"):
            addon_errors.AppLogger(logger_name)  # 说明：初始化插件 logger，应清理旧 handler 并添加文件 handler

        self.assertFalse(raw_logger.propagate)  # 说明：不向 root logger 传播，避免被 Anki 捕获
        self.assertEqual(len(raw_logger.handlers), 1)  # 说明：只保留一个文件 handler
        self.assertIs(type(raw_logger.handlers[0]), logging.FileHandler)  # 说明：FileHandler 虽继承 StreamHandler，但不会写标准输出/错误流


if __name__ == "__main__":
    unittest.main()

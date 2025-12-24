# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
插件入口文件：注册菜单入口并打开主界面。
"""  # 说明：文件级说明

from __future__ import annotations  # 说明：允许前向引用类型标注

from aqt import mw  # 说明：Anki 主窗口
from aqt.qt import QAction  # 说明：菜单动作

from addon_ui import MainDialog  # 说明：主对话框


def _open_main_dialog() -> None:  # 说明：打开主界面
    dialog = MainDialog(addon_name=__name__, parent=mw)  # 说明：创建对话框
    dialog.exec()  # 说明：以模态方式展示


def _register_menu() -> None:  # 说明：注册菜单入口
    action = QAction("CSV 批量导入与 TTS", mw)  # 说明：创建菜单动作
    action.triggered.connect(_open_main_dialog)  # 说明：绑定点击事件
    mw.form.menuTools.addAction(action)  # 说明：添加到工具菜单


_register_menu()  # 说明：加载插件时注册菜单

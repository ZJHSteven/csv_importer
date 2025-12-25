# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
插件入口文件：注册菜单入口并打开主界面。
"""  # 说明：文件级说明

from __future__ import annotations  # 说明：允许前向引用类型标注

from aqt import mw  # 说明：Anki 主窗口
from aqt.qt import QAction, Qt  # 说明：菜单动作与 Qt 枚举

from .addon_ui import MainDialog  # 说明：主对话框


_main_dialog = None  # 说明：缓存主对话框实例


def _clear_main_dialog() -> None:  # 说明：清理对话框引用
    global _main_dialog  # 说明：声明全局变量
    _main_dialog = None  # 说明：置空引用


def _open_main_dialog() -> None:  # 说明：打开主界面
    global _main_dialog  # 说明：声明全局变量
    if _main_dialog is not None:  # 说明：已存在窗口
        _main_dialog.raise_()  # 说明：提到最前
        _main_dialog.activateWindow()  # 说明：激活窗口
        return  # 说明：直接返回
    dialog = MainDialog(addon_name=__name__, parent=mw)  # 说明：创建对话框
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # 说明：关闭时释放资源
    dialog.destroyed.connect(_clear_main_dialog)  # 说明：绑定清理回调
    dialog.show()  # 说明：以非模态方式展示
    _main_dialog = dialog  # 说明：保存实例


def _register_menu() -> None:  # 说明：注册菜单入口
    action = QAction("CSV 批量导入与 TTS", mw)  # 说明：创建菜单动作
    action.triggered.connect(_open_main_dialog)  # 说明：绑定点击事件
    mw.form.menuTools.addAction(action)  # 说明：添加到工具菜单


_register_menu()  # 说明：加载插件时注册菜单

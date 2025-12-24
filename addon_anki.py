# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件封装与 Anki 集合交互的常用操作，避免主流程直接调用底层 API。
"""  # 说明：文件级说明，强调桥接层职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import re  # 说明：用于清理牌堆名前缀
from typing import Any, List, Optional, cast  # 说明：类型标注所需

from .addon_errors import ImportProcessError, logger  # 说明：统一异常与日志


def get_or_create_deck_id(mw, deck_name: str) -> int:  # 说明：获取或创建牌堆
    if not deck_name:  # 说明：牌堆名为空时直接报错
        raise ImportProcessError("牌堆名称不能为空")  # 说明：抛出导入异常
    decks = mw.col.decks  # 说明：获取牌堆管理器
    if hasattr(decks, "id"):  # 说明：新版本接口包含 id()
        deck_id = decks.id(deck_name)  # 说明：获取或创建牌堆并返回 ID
        return int(deck_id)  # 说明：确保返回 int 类型
    existing = decks.by_name(deck_name)  # 说明：旧版本通过名称查找
    if existing:  # 说明：已存在牌堆
        return int(existing["id"])  # 说明：返回已有 ID
    created = decks.add_normal_deck_with_name(deck_name)  # 说明：创建新牌堆
    return int(created.id)  # 说明：返回创建的 ID


def get_notetype_by_name(mw, note_type: str):  # 说明：根据名称获取笔记类型
    if not note_type:  # 说明：名称为空直接报错
        raise ImportProcessError("笔记类型名称不能为空")  # 说明：抛出导入异常
    model = mw.col.models.by_name(note_type)  # 说明：按名称查找笔记类型
    if not model:  # 说明：未找到
        raise ImportProcessError(f"未找到笔记类型: {note_type}")  # 说明：抛出导入异常
    return model  # 说明：返回笔记类型对象


def get_notetype_field_names(notetype) -> List[str]:  # 说明：读取笔记类型字段名列表
    fields = notetype.get("flds", [])  # 说明：读取字段定义列表
    return [field.get("name", "") for field in fields]  # 说明：提取字段名


def create_note(mw, notetype, field_values: List[str]):  # 说明：创建 Note 对象
    from anki.notes import Note  # 说明：延迟导入，避免启动时依赖问题
    note = Note(mw.col, notetype)  # 说明：创建新笔记
    for index, value in enumerate(field_values):  # 说明：按序写入字段
        if index < len(note.fields):  # 说明：避免越界
            note.fields[index] = value  # 说明：写入字段值
    return note  # 说明：返回 Note 对象


def add_note_to_deck(mw, note, deck_id: int) -> None:  # 说明：把 Note 加入指定牌堆
    try:  # 说明：捕获添加异常
        mw.col.add_note(note, deck_id)  # 说明：添加笔记并生成卡片
    except Exception as exc:  # 说明：捕获异常
        raise ImportProcessError(f"添加笔记失败: {exc}")  # 说明：转为统一异常


def update_note(mw, note) -> None:  # 说明：更新笔记
    mw.col.update_note(note)  # 说明：写回修改


def update_note_fields_and_tags(mw, note_id: int, field_values: List[str], tags: List[str]) -> None:  # 说明：按字段与标签更新笔记
    note = mw.col.get_note(note_id)  # 说明：获取笔记对象
    if note is None:  # 说明：笔记不存在
        raise ImportProcessError(f"未找到笔记: {note_id}")  # 说明：抛出导入异常
    for index, value in enumerate(field_values):  # 说明：逐字段更新
        if index < len(note.fields):  # 说明：避免越界
            note.fields[index] = value  # 说明：写入字段
    for tag in tags:  # 说明：合并标签
        if tag not in note.tags:  # 说明：避免重复
            note.tags.append(tag)  # 说明：追加标签
    mw.col.update_note(note)  # 说明：保存更新


def find_notes(mw, query: str) -> List[int]:  # 说明：根据搜索语句查询笔记
    try:  # 说明：捕获查询异常
        ids = mw.col.find_notes(query)  # 说明：执行查询
        return [int(note_id) for note_id in ids]  # 说明：确保返回 int 列表
    except Exception as exc:  # 说明：捕获异常
        logger.error(f"查找笔记失败: {exc}")  # 说明：记录日志
    return []  # 说明：失败时返回空列表


def get_all_deck_names(mw) -> List[str]:  # 说明：获取所有牌堆名称
    if mw is None or mw.col is None:  # 说明：集合未就绪
        return []  # 说明：返回空列表
    decks = mw.col.decks  # 说明：获取牌堆管理器
    if hasattr(decks, "all_names"):  # 说明：新版本接口
        return list(decks.all_names())  # 说明：返回全部名称
    if hasattr(decks, "allNames"):  # 说明：旧版本接口
        return list(decks.allNames())  # 说明：返回全部名称
    return []  # 说明：兜底返回空列表


def open_browser_with_note_ids(mw, note_ids: List[int]) -> None:  # 说明：打开浏览器并定位到指定笔记
    if not note_ids:  # 说明：空列表无需操作
        return  # 说明：直接返回
    query = build_note_id_query(note_ids)  # 说明：构造搜索语句
    open_browser_with_query(mw, query)  # 说明：打开浏览器并执行搜索


def build_note_id_query(note_ids: List[int]) -> str:  # 说明：根据笔记 ID 构造搜索语句
    unique_ids = [str(note_id) for note_id in dict.fromkeys(note_ids)]  # 说明：去重并保持顺序
    if not unique_ids:  # 说明：空列表保护
        return ""  # 说明：返回空查询
    return f"nid:{','.join(unique_ids)}"  # 说明：使用官方常见的逗号语法


def _set_browser_search_text(browser, query: str) -> None:  # 说明：兼容不同搜索框组件
    if browser is None:  # 说明：浏览器为空
        return  # 说明：直接返回
    if not hasattr(browser, "form"):  # 说明：无表单对象
        return  # 说明：直接返回
    search_widget = cast(Any, getattr(browser.form, "searchEdit", None))  # 说明：获取搜索控件并放宽类型
    if search_widget is None:  # 说明：控件不存在
        return  # 说明：直接返回
    if hasattr(search_widget, "setText"):  # 说明：QLineEdit 等支持 setText
        search_widget.setText(query)  # 说明：写入搜索文本
        return  # 说明：结束处理
    if hasattr(search_widget, "setCurrentText"):  # 说明：QComboBox 使用 setCurrentText
        search_widget.setCurrentText(query)  # 说明：写入搜索文本
        return  # 说明：结束处理
    if hasattr(search_widget, "lineEdit") and callable(search_widget.lineEdit):  # 说明：可访问 lineEdit
        line_edit = cast(Any, search_widget.lineEdit())  # 说明：获取内置输入框并放宽类型
        if line_edit is not None and hasattr(line_edit, "setText"):  # 说明：支持 setText
            line_edit.setText(query)  # 说明：写入搜索文本
            return  # 说明：结束处理


def open_browser_with_query(mw, query: str) -> None:  # 说明：打开 Anki 浏览器并执行搜索
    if mw is None:  # 说明：主窗口为空
        return  # 说明：无法打开浏览器
    try:  # 说明：捕获浏览器打开异常
        from aqt import dialogs  # 说明：延迟导入，减少启动依赖
        browser = dialogs.open("Browser", mw)  # 说明：打开或复用浏览器
        _run_browser_search(browser, query)  # 说明：执行搜索
    except Exception as exc:  # 说明：捕获异常
        logger.error(f"打开浏览器失败: {exc}")  # 说明：记录错误


def _run_browser_search(browser, query: str) -> None:  # 说明：兼容不同版本的搜索方式
    if browser is None:  # 说明：浏览器对象为空
        return  # 说明：无法执行搜索
    _set_browser_search_text(browser, query)  # 说明：先写入查询，保持 UI 与实际一致
    if hasattr(browser, "onSearchActivated"):  # 说明：优先使用与回车一致的搜索入口
        browser.onSearchActivated()  # 说明：触发搜索
        return  # 说明：结束处理
    if hasattr(browser, "search_for"):  # 说明：旧版本 search_for 接口
        browser.search_for(query)  # 说明：执行搜索
        return  # 说明：结束处理
    if hasattr(browser, "search"):  # 说明：新版本 search 接口
        try:  # 说明：捕获不同签名导致的异常
            browser.search(query)  # 说明：优先按带参数调用
            return  # 说明：结束处理
        except TypeError:  # 说明：search 无参数版本
            browser.search()  # 说明：触发无参搜索
            return  # 说明：结束处理


def normalize_deck_tag(deck_name: str, strip_regex: str) -> str:  # 说明：从牌堆名生成标签
    if not deck_name:  # 说明：空值保护
        return ""  # 说明：返回空字符串
    if "::" in deck_name:  # 说明：分级牌堆时取最后一级作为章节标签
        deck_name = deck_name.split("::")[-1]  # 说明：截取最后一级名称
    try:  # 说明：捕获正则异常
        cleaned = re.sub(strip_regex, "", deck_name).strip()  # 说明：去掉序号前缀
    except re.error:  # 说明：正则非法
        cleaned = deck_name.strip()  # 说明：回退为原始名称
    return cleaned  # 说明：返回清理后的标签

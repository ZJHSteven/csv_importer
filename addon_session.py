# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责导入会话的持久化与回滚，提供“可追溯 + 可回退”的会话记录能力。
"""  # 说明：文件级说明，强调会话记录职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import json  # 说明：用于读写会话 JSON
from dataclasses import asdict  # 说明：将 dataclass 转为 dict
from datetime import datetime  # 说明：生成时间戳
from pathlib import Path  # 说明：路径处理
from typing import Dict, List, Optional  # 说明：类型标注所需

from .addon_errors import SessionError, logger  # 说明：统一异常与日志
from .addon_anki import (  # 说明：导入 Anki 交互封装
    add_note_to_deck,  # 说明：添加笔记
    create_note,  # 说明：创建 Note
    get_notetype_by_name,  # 说明：获取笔记类型
    get_or_create_deck_id,  # 说明：获取或创建牌堆
    update_note_fields_and_tags,  # 说明：更新字段与标签
)
from .addon_models import ImportSession, ImportSessionItem, RollbackResult, StrategyApplyResult  # 说明：会话与回滚数据结构


def generate_session_id() -> str:  # 说明：生成会话 ID
    return datetime.now().strftime("%Y%m%d_%H%M%S")  # 说明：用时间戳生成可读 ID


def _session_root() -> Path:  # 说明：获取会话存储目录
    base = Path(__file__).resolve().parent  # 说明：定位插件根目录
    session_dir = base / "user_files" / "import_sessions"  # 说明：会话子目录
    session_dir.mkdir(parents=True, exist_ok=True)  # 说明：确保目录存在
    return session_dir  # 说明：返回目录路径


def _session_path(session_id: str) -> Path:  # 说明：计算会话文件路径
    return _session_root() / f"import_session_{session_id}.json"  # 说明：按命名规则构造文件名


def _latest_path() -> Path:  # 说明：最新会话索引文件路径
    return _session_root() / "latest.json"  # 说明：固定文件名保存最新会话 ID


def save_import_session(session: ImportSession, keep_limit: int = 20) -> Path:  # 说明：保存会话记录
    if not session.session_id:  # 说明：缺少会话 ID
        raise SessionError("会话 ID 不能为空")  # 说明：抛出会话异常
    session_file = _session_path(session.session_id)  # 说明：获取会话文件路径
    payload = asdict(session)  # 说明：转为可序列化 dict
    session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 说明：写入 JSON 文件
    _write_latest_session_id(session.session_id)  # 说明：更新最新会话索引
    _cleanup_old_sessions(keep_limit)  # 说明：清理过旧会话
    return session_file  # 说明：返回保存路径


def load_import_session(session_id: str) -> ImportSession:  # 说明：读取指定会话
    if not session_id:  # 说明：会话 ID 为空
        raise SessionError("会话 ID 不能为空")  # 说明：抛出异常
    session_file = _session_path(session_id)  # 说明：定位会话文件
    if not session_file.exists():  # 说明：文件不存在
        raise SessionError(f"会话文件不存在: {session_file}")  # 说明：抛出异常
    data = json.loads(session_file.read_text(encoding="utf-8"))  # 说明：读取并解析 JSON
    return _dict_to_session(data)  # 说明：转为 ImportSession 对象


def load_latest_session() -> Optional[ImportSession]:  # 说明：读取最新会话
    session_id = _read_latest_session_id()  # 说明：读取最新会话 ID
    if not session_id:  # 说明：未找到最新 ID
        return None  # 说明：返回空
    return load_import_session(session_id)  # 说明：读取对应会话


def list_import_sessions() -> List[ImportSession]:  # 说明：列出所有会话记录
    session_dir = _session_root()  # 说明：获取会话目录
    sessions: List[ImportSession] = []  # 说明：初始化会话列表
    for session_file in session_dir.glob("import_session_*.json"):  # 说明：遍历会话文件
        try:  # 说明：捕获单文件解析异常
            data = json.loads(session_file.read_text(encoding="utf-8"))  # 说明：读取 JSON 内容
            sessions.append(_dict_to_session(data))  # 说明：转为会话对象
        except Exception as exc:  # 说明：捕获异常
            logger.warning(f"读取会话失败: {session_file} {exc}")  # 说明：记录警告
    sessions.sort(key=lambda item: item.created_at, reverse=True)  # 说明：按时间倒序
    return sessions  # 说明：返回列表


def delete_import_session(session_id: str) -> None:  # 说明：删除指定会话记录
    if not session_id:  # 说明：空 ID 直接返回
        return  # 说明：结束处理
    session_file = _session_path(session_id)  # 说明：定位会话文件
    if session_file.exists():  # 说明：文件存在才删除
        session_file.unlink()  # 说明：删除会话文件
    latest_id = _read_latest_session_id()  # 说明：读取最新会话 ID
    if latest_id != session_id:  # 说明：非最新会话无需更新
        return  # 说明：结束处理
    sessions = list_import_sessions()  # 说明：重新读取会话列表
    if not sessions:  # 说明：已无会话记录
        latest_file = _latest_path()  # 说明：索引文件路径
        if latest_file.exists():  # 说明：索引文件存在
            latest_file.unlink()  # 说明：删除索引文件
        return  # 说明：结束处理
    _write_latest_session_id(sessions[0].session_id)  # 说明：写入新的最新会话


def apply_duplicate_strategy(  # 说明：对指定行应用重复策略
    mw,  # 说明：Anki 主窗口
    session_id: str,  # 说明：会话 ID
    line_numbers: List[int],  # 说明：需要处理的行号
    target_mode: str,  # 说明：目标策略（英文内部值）
) -> StrategyApplyResult:  # 说明：返回处理结果
    result = StrategyApplyResult()  # 说明：初始化结果
    if mw is None or mw.col is None:  # 说明：集合不可用
        result.errors.append("集合未加载，无法调整策略")  # 说明：记录错误
        return result  # 说明：直接返回
    session = load_import_session(session_id)  # 说明：读取会话记录
    base_items = _collect_base_items(session)  # 说明：收集基础条目
    normalized_mode = _normalize_strategy_mode(target_mode)  # 说明：规范化目标策略
    for line_no in line_numbers:  # 说明：逐行处理
        item = base_items.get(int(line_no))  # 说明：获取基础条目
        if item is None:  # 说明：未找到条目
            result.errors.append(f"未找到行号 {line_no} 的记录")  # 说明：记录错误
            continue  # 说明：继续处理
        if not item.duplicate_note_ids:  # 说明：没有重复项
            result.errors.append(f"行号 {line_no} 没有重复笔记，无法改策略")  # 说明：记录错误
            continue  # 说明：继续处理
        current_mode = _resolve_current_mode(session, item)  # 说明：读取当前策略
        if current_mode == normalized_mode:  # 说明：无需调整
            result.skipped += 1  # 说明：统计跳过
            continue  # 说明：跳过该行
        try:  # 说明：捕获单行异常
            _apply_strategy_for_item(mw, session, item, normalized_mode)  # 说明：应用策略
            session.strategy_overrides[str(item.line_no)] = normalized_mode  # 说明：写入覆盖策略
            result.applied += 1  # 说明：统计成功
        except Exception as exc:  # 说明：捕获异常
            result.errors.append(f"行号 {line_no} 调整失败: {exc}")  # 说明：记录错误
    save_import_session(session, keep_limit=0)  # 说明：保存会话并避免清理
    return result  # 说明：返回处理结果


def _normalize_strategy_mode(value: str) -> str:  # 说明：规范化策略值
    mapping = {  # 说明：支持中英文
        "duplicate": "duplicate",  # 说明：保留重复
        "保留重复": "duplicate",  # 说明：中文映射
        "update": "update",  # 说明：覆盖更新
        "覆盖更新": "update",  # 说明：中文映射
        "skip": "skip",  # 说明：跳过重复
        "跳过重复": "skip",  # 说明：中文映射
    }  # 说明：映射表结束
    return mapping.get(str(value), "duplicate")  # 说明：未知值回退默认


def _action_to_mode(action: str) -> str:  # 说明：把动作映射为策略
    mapping = {  # 说明：动作到策略映射
        "added": "duplicate",  # 说明：新增视为保留重复
        "updated": "update",  # 说明：更新视为覆盖
        "skipped": "skip",  # 说明：跳过视为跳过
        "manual_update": "update",  # 说明：手动更新视为覆盖
        "manual_duplicate": "duplicate",  # 说明：手动复制视为保留重复
    }  # 说明：映射表结束
    return mapping.get(str(action), "duplicate")  # 说明：默认回退


def _collect_base_items(session: ImportSession) -> Dict[int, ImportSessionItem]:  # 说明：收集基础条目
    base_items: Dict[int, ImportSessionItem] = {}  # 说明：初始化映射
    for item in session.items:  # 说明：遍历会话条目
        if item.action not in ("added", "updated", "skipped"):  # 说明：仅保留基础动作
            continue  # 说明：跳过手动记录
        if item.line_no not in base_items:  # 说明：避免覆盖
            base_items[item.line_no] = item  # 说明：记录条目
    return base_items  # 说明：返回映射


def _resolve_current_mode(session: ImportSession, item: ImportSessionItem) -> str:  # 说明：解析当前策略
    override = session.strategy_overrides.get(str(item.line_no), "")  # 说明：读取覆盖策略
    if override:  # 说明：有覆盖时优先使用
        return _normalize_strategy_mode(override)  # 说明：返回覆盖策略
    return _action_to_mode(item.action)  # 说明：回退到原始动作


def _apply_strategy_for_item(  # 说明：对单条记录应用策略
    mw,  # 说明：Anki 主窗口
    session: ImportSession,  # 说明：会话对象
    item: ImportSessionItem,  # 说明：基础条目
    target_mode: str,  # 说明：目标策略
) -> None:  # 说明：无返回值
    existing_note_id = _get_primary_duplicate_id(item)  # 说明：获取主重复笔记
    if target_mode == "update":  # 说明：覆盖更新
        _delete_latest_duplicate_if_needed(mw, session, item, existing_note_id)  # 说明：删除重复副本
        _apply_update_to_existing(mw, session, item, existing_note_id)  # 说明：更新原笔记
        return  # 说明：结束处理
    if target_mode == "duplicate":  # 说明：保留重复
        _restore_original_if_needed(mw, session, item, existing_note_id)  # 说明：恢复原笔记
        _create_duplicate_note(mw, session, item)  # 说明：创建新笔记副本
        return  # 说明：结束处理
    if target_mode == "skip":  # 说明：跳过重复
        _delete_latest_duplicate_if_needed(mw, session, item, existing_note_id)  # 说明：删除重复副本
        _restore_original_if_needed(mw, session, item, existing_note_id)  # 说明：恢复原笔记
        return  # 说明：结束处理
    raise SessionError(f"未知策略: {target_mode}")  # 说明：兜底异常


def _get_primary_duplicate_id(item: ImportSessionItem) -> int:  # 说明：获取主重复笔记 ID
    if not item.duplicate_note_ids:  # 说明：重复列表为空
        raise SessionError("缺少重复笔记 ID，无法调整策略")  # 说明：抛出异常
    return int(item.duplicate_note_ids[0])  # 说明：使用第一条作为主笔记


def _find_latest_duplicate_note_id(session: ImportSession, line_no: int) -> Optional[int]:  # 说明：查找最近的副本笔记
    for item in reversed(session.items):  # 说明：逆序查找最新记录
        if item.line_no != line_no:  # 说明：不同的行号
            continue  # 说明：跳过
        if item.action in ("added", "manual_duplicate"):  # 说明：新增或手动复制
            return int(item.note_id)  # 说明：返回副本 ID
    return None  # 说明：未找到返回空


def _delete_latest_duplicate_if_needed(  # 说明：删除最新副本笔记
    mw,  # 说明：Anki 主窗口
    session: ImportSession,  # 说明：会话对象
    item: ImportSessionItem,  # 说明：基础条目
    existing_note_id: int,  # 说明：主笔记 ID
) -> None:  # 说明：无返回值
    duplicate_note_id = _find_latest_duplicate_note_id(session, item.line_no)  # 说明：查找副本
    if duplicate_note_id is None:  # 说明：没有副本
        return  # 说明：无需处理
    if duplicate_note_id == existing_note_id:  # 说明：避免误删主笔记
        return  # 说明：直接返回
    _delete_note_if_exists(mw, duplicate_note_id)  # 说明：删除副本笔记


def _apply_update_to_existing(  # 说明：把主笔记更新为导入内容
    mw,  # 说明：Anki 主窗口
    session: ImportSession,  # 说明：会话对象
    item: ImportSessionItem,  # 说明：基础条目
    existing_note_id: int,  # 说明：主笔记 ID
) -> None:  # 说明：无返回值
    old_fields = _snapshot_note_fields(mw, existing_note_id)  # 说明：记录更新前字段
    old_tags = _snapshot_note_tags(mw, existing_note_id)  # 说明：记录更新前标签
    update_note_fields_and_tags(mw, existing_note_id, item.fields, item.tags)  # 说明：执行更新
    _append_manual_update(session, item, existing_note_id, item.fields, item.tags, old_fields, old_tags)  # 说明：记录手动更新


def _restore_original_if_needed(  # 说明：恢复主笔记为原始内容
    mw,  # 说明：Anki 主窗口
    session: ImportSession,  # 说明：会话对象
    item: ImportSessionItem,  # 说明：基础条目
    existing_note_id: int,  # 说明：主笔记 ID
) -> None:  # 说明：无返回值
    if not item.old_fields and not item.old_tags:  # 说明：缺少原始快照
        raise SessionError("缺少原始字段快照，无法恢复")  # 说明：抛出异常
    current_fields = _snapshot_note_fields(mw, existing_note_id)  # 说明：读取当前字段
    current_tags = _snapshot_note_tags(mw, existing_note_id)  # 说明：读取当前标签
    if current_fields == item.old_fields and current_tags == item.old_tags:  # 说明：已是原始状态
        return  # 说明：无需处理
    _set_note_fields_and_tags(mw, existing_note_id, item.old_fields, item.old_tags)  # 说明：恢复原始内容
    _append_manual_update(  # 说明：记录恢复操作
        session,  # 说明：会话对象
        item,  # 说明：基础条目
        existing_note_id,  # 说明：主笔记 ID
        item.old_fields,  # 说明：恢复后的字段
        item.old_tags,  # 说明：恢复后的标签
        current_fields,  # 说明：恢复前字段
        current_tags,  # 说明：恢复前标签
    )


def _create_duplicate_note(mw, session: ImportSession, item: ImportSessionItem) -> None:  # 说明：创建副本笔记
    notetype = get_notetype_by_name(mw, item.note_type)  # 说明：获取笔记类型
    note = create_note(mw, notetype, item.fields)  # 说明：创建新笔记
    note.tags = list(item.tags)  # 说明：写入标签
    deck_id = get_or_create_deck_id(mw, item.deck_name)  # 说明：获取牌堆 ID
    add_note_to_deck(mw, note, deck_id)  # 说明：添加到牌堆
    if not note.id:  # 说明：未生成 ID
        raise SessionError("创建副本笔记失败，未获得笔记 ID")  # 说明：抛出异常
    session.items.append(  # 说明：记录手动复制动作
        ImportSessionItem(
            line_no=item.line_no,  # 说明：源行号
            action="manual_duplicate",  # 说明：动作类型
            note_id=int(note.id),  # 说明：新笔记 ID
            deck_name=item.deck_name,  # 说明：牌堆名称
            note_type=item.note_type,  # 说明：题型名称
            fields=list(item.fields),  # 说明：写入字段
            tags=list(item.tags),  # 说明：写入标签
            duplicate_note_ids=list(item.duplicate_note_ids),  # 说明：重复列表
        )
    )


def _append_manual_update(  # 说明：记录手动更新动作
    session: ImportSession,  # 说明：会话对象
    item: ImportSessionItem,  # 说明：基础条目
    note_id: int,  # 说明：笔记 ID
    new_fields: List[str],  # 说明：更新后的字段
    new_tags: List[str],  # 说明：更新后的标签
    old_fields: List[str],  # 说明：更新前字段
    old_tags: List[str],  # 说明：更新前标签
) -> None:  # 说明：无返回值
    session.items.append(  # 说明：追加会话记录
        ImportSessionItem(
            line_no=item.line_no,  # 说明：源行号
            action="manual_update",  # 说明：动作类型
            note_id=int(note_id),  # 说明：笔记 ID
            deck_name=item.deck_name,  # 说明：牌堆名称
            note_type=item.note_type,  # 说明：题型名称
            fields=list(new_fields),  # 说明：更新后字段
            tags=list(new_tags),  # 说明：更新后标签
            old_fields=list(old_fields),  # 说明：更新前字段
            old_tags=list(old_tags),  # 说明：更新前标签
            duplicate_note_ids=list(item.duplicate_note_ids),  # 说明：重复列表
        )
    )


def _set_note_fields_and_tags(  # 说明：直接覆盖字段与标签
    mw,  # 说明：Anki 主窗口
    note_id: int,  # 说明：笔记 ID
    fields: List[str],  # 说明：字段内容
    tags: List[str],  # 说明：标签列表
) -> None:  # 说明：无返回值
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    if note is None:  # 说明：笔记不存在
        raise SessionError(f"笔记不存在: {note_id}")  # 说明：抛出异常
    for index, value in enumerate(fields):  # 说明：逐字段写入
        if index < len(note.fields):  # 说明：避免越界
            note.fields[index] = value  # 说明：写入字段
    note.tags = list(tags)  # 说明：覆盖标签
    mw.col.update_note(note)  # 说明：保存更新


def _snapshot_note_fields(mw, note_id: int) -> List[str]:  # 说明：快照字段内容
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    return list(note.fields) if note else []  # 说明：返回字段列表


def _snapshot_note_tags(mw, note_id: int) -> List[str]:  # 说明：快照标签内容
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    return list(note.tags) if note else []  # 说明：返回标签列表


def _delete_note_if_exists(mw, note_id: int) -> None:  # 说明：删除笔记（若存在）
    if mw is None or mw.col is None:  # 说明：集合不可用
        return  # 说明：直接返回
    note = mw.col.get_note(note_id)  # 说明：读取笔记
    if note is None:  # 说明：笔记不存在
        return  # 说明：无需删除
    _delete_note(mw, note_id)  # 说明：调用删除逻辑


def append_session_items(session_id: str, items: List[ImportSessionItem]) -> None:  # 说明：追加会话条目
    if not items:  # 说明：无新增条目
        return  # 说明：无需处理
    session = load_import_session(session_id)  # 说明：读取现有会话
    session.items.extend(items)  # 说明：追加条目
    save_import_session(session)  # 说明：保存更新后的会话


def rollback_session(mw, session: ImportSession) -> RollbackResult:  # 说明：回滚指定会话
    result = RollbackResult()  # 说明：初始化统计结果
    for item in reversed(session.items):  # 说明：按逆序回滚确保依赖顺序
        try:  # 说明：捕获单条回滚异常
            if item.action in ("added", "manual_duplicate"):  # 说明：新增或手动复制的笔记需要删除
                _delete_note(mw, item.note_id)  # 说明：删除笔记
                result.deleted += 1  # 说明：统计删除数量
                continue  # 说明：进入下一条
            if item.action in ("updated", "manual_update"):  # 说明：更新类动作恢复旧值
                _restore_note(mw, item.note_id, item.old_fields, item.old_tags)  # 说明：恢复字段与标签
                result.restored += 1  # 说明：统计恢复数量
                continue  # 说明：进入下一条
        except Exception as exc:  # 说明：捕获异常
            message = f"回滚失败 note_id={item.note_id}: {exc}"  # 说明：构造错误信息
            logger.error(message)  # 说明：记录日志
            result.errors.append(message)  # 说明：记录错误
    return result  # 说明：返回回滚结果


def _restore_note(mw, note_id: int, fields: List[str], tags: List[str]) -> None:  # 说明：恢复笔记字段与标签
    if mw is None or mw.col is None:  # 说明：集合不可用
        raise SessionError("集合未加载，无法回滚")  # 说明：抛出异常
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    if note is None:  # 说明：笔记不存在
        raise SessionError(f"笔记不存在: {note_id}")  # 说明：抛出异常
    for index, value in enumerate(fields):  # 说明：逐字段恢复
        if index < len(note.fields):  # 说明：避免越界
            note.fields[index] = value  # 说明：写入字段值
    note.tags = list(tags)  # 说明：恢复标签
    mw.col.update_note(note)  # 说明：写回修改


def _delete_note(mw, note_id: int) -> None:  # 说明：删除指定笔记
    if mw is None or mw.col is None:  # 说明：集合不可用
        raise SessionError("集合未加载，无法删除笔记")  # 说明：抛出异常
    if mw.col.get_note(note_id) is None:  # 说明：笔记不存在
        return  # 说明：直接返回
    if hasattr(mw.col, "remove_notes"):  # 说明：新接口
        mw.col.remove_notes([note_id])  # 说明：删除笔记
        return  # 说明：结束处理
    if hasattr(mw.col, "remNotes"):  # 说明：旧接口
        mw.col.remNotes([note_id])  # 说明：删除笔记
        return  # 说明：结束处理
    raise SessionError("当前 Anki 版本不支持删除笔记接口")  # 说明：兜底异常


def _dict_to_session(data: dict) -> ImportSession:  # 说明：把 dict 转为 ImportSession
    items = []  # 说明：初始化条目列表
    for raw_item in data.get("items", []):  # 说明：遍历条目
        items.append(  # 说明：追加条目对象
            ImportSessionItem(
                line_no=int(raw_item.get("line_no", 0)),  # 说明：行号
                action=str(raw_item.get("action", "")),  # 说明：动作类型
                note_id=int(raw_item.get("note_id", 0)),  # 说明：笔记 ID
                deck_name=str(raw_item.get("deck_name", "")),  # 说明：牌堆名称
                note_type=str(raw_item.get("note_type", "")),  # 说明：笔记类型
                fields=list(raw_item.get("fields", [])),  # 说明：字段列表
                tags=list(raw_item.get("tags", [])),  # 说明：标签列表
                old_fields=list(raw_item.get("old_fields", [])),  # 说明：旧字段
                old_tags=list(raw_item.get("old_tags", [])),  # 说明：旧标签
                duplicate_note_ids=list(raw_item.get("duplicate_note_ids", [])),  # 说明：重复笔记列表
            )
        )
    strategy_overrides = data.get("strategy_overrides", {})  # 说明：读取策略覆盖
    if not isinstance(strategy_overrides, dict):  # 说明：类型兜底
        strategy_overrides = {}  # 说明：回退为空字典
    return ImportSession(  # 说明：构造会话对象
        session_id=str(data.get("session_id", "")),  # 说明：会话 ID
        created_at=str(data.get("created_at", "")),  # 说明：创建时间
        source_path=str(data.get("source_path", "")),  # 说明：源文件路径
        duplicate_mode=str(data.get("duplicate_mode", "")),  # 说明：重复策略
        items=items,  # 说明：会话条目
        strategy_overrides={str(k): str(v) for k, v in strategy_overrides.items()},  # 说明：确保为字符串映射
    )


def _write_latest_session_id(session_id: str) -> None:  # 说明：写入最新会话 ID
    if not session_id:  # 说明：空 ID 不写入
        return  # 说明：直接返回
    payload = {"session_id": session_id}  # 说明：构造索引内容
    _latest_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 说明：保存索引文件


def _read_latest_session_id() -> str:  # 说明：读取最新会话 ID
    latest_file = _latest_path()  # 说明：索引文件路径
    if not latest_file.exists():  # 说明：索引文件不存在
        return ""  # 说明：返回空字符串
    data = json.loads(latest_file.read_text(encoding="utf-8"))  # 说明：读取索引内容
    return str(data.get("session_id", ""))  # 说明：返回会话 ID


def _cleanup_old_sessions(keep_limit: int) -> None:  # 说明：清理超出数量的旧会话
    if keep_limit <= 0:  # 说明：不需要保留
        return  # 说明：直接返回
    session_dir = _session_root()  # 说明：获取会话目录
    session_files = sorted(session_dir.glob("import_session_*.json"), key=lambda path: path.stat().st_mtime)  # 说明：按修改时间排序
    if len(session_files) <= keep_limit:  # 说明：未超过上限
        return  # 说明：无需清理
    for old_file in session_files[:-keep_limit]:  # 说明：遍历需要删除的旧文件
        try:  # 说明：捕获删除异常
            old_file.unlink()  # 说明：删除旧会话文件
        except Exception as exc:  # 说明：捕获异常
            logger.warning(f"删除旧会话失败: {old_file} {exc}")  # 说明：记录警告

# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责导入会话的持久化与回滚，提供“可追溯 + 可回退”的会话记录能力。
"""  # 说明：文件级说明，强调会话记录职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import json  # 说明：用于读写会话 JSON
from dataclasses import asdict  # 说明：将 dataclass 转为 dict
from datetime import datetime  # 说明：生成时间戳
from pathlib import Path  # 说明：路径处理
from typing import List, Optional  # 说明：类型标注所需

from .addon_errors import SessionError, logger  # 说明：统一异常与日志
from .addon_models import ImportSession, ImportSessionItem, RollbackResult  # 说明：会话与回滚数据结构


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
            if item.action == "added":  # 说明：新增的笔记需要删除
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
    return ImportSession(  # 说明：构造会话对象
        session_id=str(data.get("session_id", "")),  # 说明：会话 ID
        created_at=str(data.get("created_at", "")),  # 说明：创建时间
        source_path=str(data.get("source_path", "")),  # 说明：源文件路径
        duplicate_mode=str(data.get("duplicate_mode", "")),  # 说明：重复策略
        items=items,  # 说明：会话条目
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

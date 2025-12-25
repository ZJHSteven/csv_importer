# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件定义数据结构（模型），用于在解析、导入、TTS 各阶段传递清晰的结构化数据。
"""  # 说明：文件级说明，强调仅存放数据结构

from __future__ import annotations  # 说明：允许前向引用类型标注

from dataclasses import dataclass, field  # 说明：使用 dataclass 简化样板代码
from typing import Dict, List, Optional  # 说明：类型标注所需


@dataclass
class ParsedRow:  # 说明：单行 CSV 解析结果
    fields: List[str]  # 说明：该行解析出的字段列表
    line_no: int  # 说明：该行在原始文件中的行号（从 1 开始）


@dataclass
class ParsedSection:  # 说明：一个题型分段（同一牌堆 + 同一题型）
    deck_name: str  # 说明：段落所属牌堆名称
    note_type: str  # 说明：段落对应的笔记类型名称
    rows: List[ParsedRow] = field(default_factory=list)  # 说明：段落内所有行
    start_line_no: int = 0  # 说明：段落起始行号，用于定位错误


@dataclass
class ParseWarning:  # 说明：解析阶段的警告信息
    message: str  # 说明：警告文本
    line_no: int  # 说明：警告发生行号


@dataclass
class ParseResult:  # 说明：整体解析结果
    sections: List[ParsedSection] = field(default_factory=list)  # 说明：所有分段
    warnings: List[ParseWarning] = field(default_factory=list)  # 说明：解析警告列表


@dataclass
class ImportResult:  # 说明：导入阶段统计结果
    added: int = 0  # 说明：新增笔记数量
    updated: int = 0  # 说明：更新笔记数量
    skipped: int = 0  # 说明：跳过笔记数量
    errors: List[str] = field(default_factory=list)  # 说明：错误信息列表
    imported_note_ids: List[int] = field(default_factory=list)  # 说明：导入成功的笔记 ID
    added_note_ids: List[int] = field(default_factory=list)  # 说明：新增笔记 ID 列表
    updated_note_ids: List[int] = field(default_factory=list)  # 说明：更新笔记 ID 列表
    skipped_note_ids: List[int] = field(default_factory=list)  # 说明：跳过的重复笔记 ID 列表
    duplicate_note_ids: List[int] = field(default_factory=list)  # 说明：遇到的重复笔记 ID 汇总
    session_id: str = ""  # 说明：导入会话 ID，便于关联回滚


@dataclass
class TtsTask:  # 说明：单条 TTS 任务
    note_id: int  # 说明：需要生成语音的笔记 ID
    text: str  # 说明：需要合成的文本
    voice_name: str  # 说明：使用的音色名称
    target_field: str  # 说明：写入音频标记的字段名


@dataclass
class TtsResult:  # 说明：TTS 执行结果
    generated: int = 0  # 说明：成功生成音频数量
    reused: int = 0  # 说明：复用已有媒体的数量
    skipped: int = 0  # 说明：跳过数量（已有音频）
    errors: List[str] = field(default_factory=list)  # 说明：错误列表


@dataclass
class ImportSessionItem:  # 说明：导入会话中的单条记录
    line_no: int  # 说明：源文件行号
    action: str  # 说明：动作类型（added/updated/skipped/manual_update）
    note_id: int  # 说明：关联的笔记 ID
    deck_name: str  # 说明：对应的牌堆名称
    note_type: str  # 说明：对应的笔记类型
    fields: List[str]  # 说明：导入时使用的字段值
    tags: List[str]  # 说明：导入时使用的标签
    old_fields: List[str] = field(default_factory=list)  # 说明：更新前字段快照
    old_tags: List[str] = field(default_factory=list)  # 说明：更新前标签快照
    duplicate_note_ids: List[int] = field(default_factory=list)  # 说明：查到的重复笔记 ID


@dataclass
class ImportSession:  # 说明：导入会话记录
    session_id: str  # 说明：会话唯一 ID
    created_at: str  # 说明：会话创建时间
    source_path: str  # 说明：源文件路径
    duplicate_mode: str  # 说明：导入时的重复处理策略
    items: List[ImportSessionItem] = field(default_factory=list)  # 说明：会话明细列表
    strategy_overrides: Dict[str, str] = field(default_factory=dict)  # 说明：手动策略覆盖映射（key 为行号）


@dataclass
class RollbackResult:  # 说明：回滚结果统计
    restored: int = 0  # 说明：恢复更新的数量
    deleted: int = 0  # 说明：删除新增的数量
    errors: List[str] = field(default_factory=list)  # 说明：回滚错误信息


@dataclass
class StrategyApplyResult:  # 说明：策略调整结果
    applied: int = 0  # 说明：成功调整数量
    skipped: int = 0  # 说明：无需调整数量
    errors: List[str] = field(default_factory=list)  # 说明：错误详情

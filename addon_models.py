# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件定义数据结构（模型），用于在解析、导入、TTS 各阶段传递清晰的结构化数据。
"""  # 说明：文件级说明，强调仅存放数据结构

from __future__ import annotations  # 说明：允许前向引用类型标注

from dataclasses import dataclass, field  # 说明：使用 dataclass 简化样板代码
from typing import List, Optional  # 说明：类型标注所需


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


@dataclass
class TtsTask:  # 说明：单条 TTS 任务
    note_id: int  # 说明：需要生成语音的笔记 ID
    text: str  # 说明：需要合成的文本
    voice_name: str  # 说明：使用的音色名称
    target_field: str  # 说明：写入音频标记的字段名


@dataclass
class TtsResult:  # 说明：TTS 执行结果
    generated: int = 0  # 说明：成功生成音频数量
    skipped: int = 0  # 说明：跳过数量（已有音频）
    errors: List[str] = field(default_factory=list)  # 说明：错误列表

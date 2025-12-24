# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责解析自定义混合格式文本，输出结构化的分段数据。
"""  # 说明：文件级说明，强调解析职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import csv  # 说明：使用标准库 CSV 解析器
import re  # 说明：使用正则表达式解析题型行
from pathlib import Path  # 说明：路径处理
from typing import Iterable, List  # 说明：类型标注所需

from .addon_errors import ParseError  # 说明：统一异常类型
from .addon_models import ParsedRow, ParsedSection, ParseResult, ParseWarning  # 说明：数据结构


def parse_file(path: str, config: dict) -> ParseResult:  # 说明：从文件路径解析
    if not path:  # 说明：路径为空直接报错
        raise ParseError("文件路径不能为空")  # 说明：抛出解析异常
    file_path = Path(path)  # 说明：构造路径对象
    if not file_path.exists():  # 说明：检查文件是否存在
        raise ParseError(f"文件不存在: {path}")  # 说明：提示不存在
    text = file_path.read_text(encoding="utf-8")  # 说明：读取文本内容
    return parse_text(text, config)  # 说明：委托给文本解析函数


def parse_text(text: str, config: dict) -> ParseResult:  # 说明：解析完整文本
    lines = text.splitlines()  # 说明：按行切分
    return parse_lines(lines, config)  # 说明：委托给行解析函数


def parse_lines(lines: Iterable[str], config: dict) -> ParseResult:  # 说明：逐行解析
    result = ParseResult()  # 说明：初始化解析结果
    deck_prefix = str(config.get("deck_line_prefix", "//"))  # 说明：读取牌堆标记前缀
    allow_english_colon = bool(config.get("type_line_allow_english_colon", True))  # 说明：是否允许英文冒号
    type_pattern = _build_type_pattern(allow_english_colon)  # 说明：构建题型识别正则
    current_deck = ""  # 说明：当前牌堆名称
    current_type = ""  # 说明：当前题型名称
    current_section: ParsedSection | None = None  # 说明：当前分段对象
    for index, raw_line in enumerate(lines, start=1):  # 说明：逐行扫描
        line = raw_line.strip()  # 说明：去掉首尾空白
        if not line:  # 说明：空行直接跳过
            continue  # 说明：不处理空行
        if line.startswith(deck_prefix):  # 说明：识别到牌堆标记行
            deck_name = line[len(deck_prefix):].strip()  # 说明：解析牌堆名称
            if not deck_name:  # 说明：牌堆名为空
                result.warnings.append(ParseWarning("牌堆行缺少名称", index))  # 说明：记录警告
                current_deck = ""  # 说明：清空当前牌堆
                current_type = ""  # 说明：清空当前题型
                current_section = None  # 说明：清空当前分段
                continue  # 说明：进入下一行
            current_deck = deck_name  # 说明：更新当前牌堆
            current_type = ""  # 说明：新牌堆下等待题型声明
            current_section = None  # 说明：新牌堆重置分段
            continue  # 说明：进入下一行
        type_match = type_pattern.match(line)  # 说明：尝试匹配题型行
        if type_match:  # 说明：匹配成功
            type_name = type_match.group("name").strip()  # 说明：提取题型名称
            rest_text = type_match.group("rest").strip()  # 说明：提取冒号后的内容
            if not type_name:  # 说明：题型名为空
                result.warnings.append(ParseWarning("题型行缺少名称", index))  # 说明：记录警告
                current_type = ""  # 说明：清空当前题型
                current_section = None  # 说明：清空当前分段
                continue  # 说明：进入下一行
            if not current_deck:  # 说明：题型出现前没有牌堆
                result.warnings.append(ParseWarning("题型行前未声明牌堆", index))  # 说明：记录警告
            current_type = type_name  # 说明：更新当前题型
            current_section = ParsedSection(  # 说明：创建新的分段
                deck_name=current_deck,  # 说明：设置牌堆名称
                note_type=current_type,  # 说明：设置题型名称
                rows=[],  # 说明：初始化空行列表
                start_line_no=index,  # 说明：记录起始行号
            )
            result.sections.append(current_section)  # 说明：加入解析结果
            if rest_text:  # 说明：题型行后面直接跟了内容
                fields = _parse_csv_line(rest_text, index, result)  # 说明：解析紧随内容
                if fields is not None:  # 说明：解析成功
                    current_section.rows.append(ParsedRow(fields=fields, line_no=index))  # 说明：追加同一行内容
            continue  # 说明：进入下一行
        if not current_deck or not current_type or current_section is None:  # 说明：CSV 行缺少上下文
            result.warnings.append(ParseWarning("CSV 行缺少牌堆或题型上下文", index))  # 说明：记录警告
            continue  # 说明：跳过该行
        fields = _parse_csv_line(raw_line, index, result)  # 说明：解析 CSV 字段
        if fields is None:  # 说明：解析失败
            continue  # 说明：已记录警告，跳过
        current_section.rows.append(ParsedRow(fields=fields, line_no=index))  # 说明：追加行记录
    return result  # 说明：返回解析结果


def _build_type_pattern(allow_english_colon: bool) -> re.Pattern:  # 说明：构建题型匹配正则
    if allow_english_colon:  # 说明：允许英文冒号
        pattern = r"^(?P<name>.+?)[：:](?P<rest>.*)$"  # 说明：允许冒号后带内容
    else:  # 说明：仅允许中文冒号
        pattern = r"^(?P<name>.+?)[：](?P<rest>.*)$"  # 说明：允许冒号后带内容
    return re.compile(pattern)  # 说明：编译正则并返回


def _parse_csv_line(raw_line: str, line_no: int, result: ParseResult) -> List[str] | None:  # 说明：解析单行 CSV
    try:  # 说明：尝试解析
        reader = csv.reader([raw_line], delimiter=",", quotechar='"')  # 说明：创建 CSV reader
        fields = next(reader)  # 说明：读取字段列表
        return [field.strip() for field in fields]  # 说明：去掉字段首尾空白
    except Exception as exc:  # 说明：捕获解析异常
        result.warnings.append(ParseWarning(f"CSV 行解析失败: {exc}", line_no))  # 说明：记录警告
        return None  # 说明：解析失败返回 None

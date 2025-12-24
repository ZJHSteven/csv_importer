# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责解析自定义混合格式文本，输出结构化的分段数据。
"""  # 说明：文件级说明，强调解析职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import csv  # 说明：使用标准库 CSV 解析器
from typing import Tuple  # 说明：类型标注所需
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
    # 说明：题型行识别改为“忽略引号内冒号”的扫描，避免把 CSV 内容误当题型
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
        type_split = _try_split_type_line(line, allow_english_colon)  # 说明：尝试拆分题型行
        if type_split is not None:  # 说明：匹配成功
            type_name, rest_text = type_split  # 说明：解包题型与尾随内容
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


def _try_split_type_line(line: str, allow_english_colon: bool) -> Tuple[str, str] | None:  # 说明：识别题型行并拆分
    if not line:  # 说明：空行直接返回
        return None  # 说明：空行不是题型
    delimiters = ("：", ":") if allow_english_colon else ("：",)  # 说明：可接受的冒号集合
    in_quotes = False  # 说明：是否处于双引号内
    comma_outside = False  # 说明：是否出现过“引号外的逗号”
    colon_index: int | None = None  # 说明：记录引号外冒号位置
    index = 0  # 说明：扫描索引
    while index < len(line):  # 说明：逐字符扫描
        char = line[index]  # 说明：当前字符
        if char == '"':  # 说明：遇到双引号
            if in_quotes and index + 1 < len(line) and line[index + 1] == '"':  # 说明：处理 CSV 内部转义引号
                index += 2  # 说明：跳过成对引号
                continue  # 说明：继续扫描
            in_quotes = not in_quotes  # 说明：切换引号状态
            index += 1  # 说明：移动索引
            continue  # 说明：继续扫描
        if not in_quotes:  # 说明：只在引号外判断分隔符
            if char == ",":  # 说明：识别引号外的逗号
                comma_outside = True  # 说明：记录出现过逗号
            if colon_index is None and char in delimiters:  # 说明：记录第一个引号外冒号
                colon_index = index  # 说明：保存冒号位置
        index += 1  # 说明：递增索引
    if colon_index is None:  # 说明：未找到引号外冒号
        return None  # 说明：不是题型行
    name = line[:colon_index].strip()  # 说明：冒号前为题型名
    rest = line[colon_index + 1 :].strip()  # 说明：冒号后为可能的 CSV 内容
    if not name:  # 说明：题型名为空
        return None  # 说明：判定为无效题型
    if comma_outside:  # 说明：行内出现了引号外逗号
        # 说明：如果是“题型：CSV”，CSV 一般以引号开头；否则更像普通 CSV 行
        if not rest.lstrip().startswith('"'):  # 说明：尾随内容不以引号开头
            return None  # 说明：当作 CSV 行而非题型行
    return name, rest  # 说明：返回题型名与尾随内容


def _parse_csv_line(raw_line: str, line_no: int, result: ParseResult) -> List[str] | None:  # 说明：解析单行 CSV
    try:  # 说明：尝试解析
        reader = csv.reader([raw_line], delimiter=",", quotechar='"')  # 说明：创建 CSV reader
        fields = next(reader)  # 说明：读取字段列表
        return [field.strip() for field in fields]  # 说明：去掉字段首尾空白
    except Exception as exc:  # 说明：捕获解析异常
        result.warnings.append(ParseWarning(f"CSV 行解析失败: {exc}", line_no))  # 说明：记录警告
        return None  # 说明：解析失败返回 None

# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责把解析结果导入 Anki，包含重复处理、标签补齐、字段校验等逻辑。
"""  # 说明：文件级说明，强调导入职责

from __future__ import annotations  # 说明：允许前向引用类型标注

from typing import List, Tuple  # 说明：类型标注所需

from .addon_anki import (  # 说明：导入 Anki 交互封装
    add_note_to_deck,  # 说明：添加笔记
    create_note,  # 说明：创建 Note
    find_notes,  # 说明：查找笔记
    get_notetype_by_name,  # 说明：获取笔记类型
    get_notetype_field_names,  # 说明：获取字段名
    get_or_create_deck_id,  # 说明：获取或创建牌堆
    normalize_deck_tag,  # 说明：清理牌堆标签
    update_note_fields_and_tags,  # 说明：更新字段与标签
)
from .addon_errors import ImportProcessError, logger  # 说明：统一异常与日志
from .addon_models import ImportResult, ImportSession, ImportSessionItem, ParseResult  # 说明：数据结构
from .addon_session import generate_session_id, save_import_session  # 说明：会话记录能力


def import_parse_result(mw, parse_result: ParseResult, config: dict, source_path: str = "") -> ImportResult:  # 说明：导入入口
    result = ImportResult()  # 说明：初始化导入结果
    session_id = generate_session_id()  # 说明：生成会话 ID
    session = ImportSession(  # 说明：初始化会话对象
        session_id=session_id,  # 说明：会话 ID
        created_at=session_id,  # 说明：创建时间（与 ID 同步）
        source_path=source_path,  # 说明：源文件路径
        duplicate_mode=str(config.get("duplicate_mode", "")),  # 说明：保存重复策略
        items=[],  # 说明：初始化条目列表
    )
    for section in parse_result.sections:  # 说明：逐分段导入
        _import_section(mw, section, config, result, session)  # 说明：导入单个分段
    result.session_id = session_id  # 说明：写入会话 ID
    keep_limit = int(config.get("import_session_keep_limit", 20))  # 说明：读取会话保留上限
    save_import_session(session, keep_limit=keep_limit)  # 说明：保存会话记录
    return result  # 说明：返回统计结果


def _normalize_duplicate_mode(value: str) -> str:  # 说明：统一重复处理模式为英文内部值
    mapping = {  # 说明：兼容中文与旧英文值
        "duplicate": "duplicate",  # 说明：已是英文内部值
        "update": "update",  # 说明：已是英文内部值
        "skip": "skip",  # 说明：已是英文内部值
        "保留重复": "duplicate",  # 说明：中文值映射为内部值
        "覆盖更新": "update",  # 说明：中文值映射为内部值
        "跳过重复": "skip",  # 说明：中文值映射为内部值
    }  # 说明：映射表结束
    return mapping.get(str(value), "duplicate")  # 说明：未知值回退默认


def _snapshot_note_fields(mw, note_id: int) -> List[str]:  # 说明：获取笔记字段快照
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    return list(note.fields) if note else []  # 说明：返回字段列表


def _snapshot_note_tags(mw, note_id: int) -> List[str]:  # 说明：获取笔记标签快照
    note = mw.col.get_note(note_id)  # 说明：读取笔记对象
    return list(note.tags) if note else []  # 说明：返回标签列表


def _import_section(mw, section, config: dict, result: ImportResult, session: ImportSession) -> None:  # 说明：导入单个分段
    note_type_map = config.get("note_type_map", {})  # 说明：读取题型映射
    mapped_type = note_type_map.get(section.note_type, section.note_type)  # 说明：映射题型到笔记类型
    deck_id = get_or_create_deck_id(mw, section.deck_name)  # 说明：获取牌堆 ID
    notetype = get_notetype_by_name(mw, mapped_type)  # 说明：获取笔记类型
    field_names = get_notetype_field_names(notetype)  # 说明：获取字段名列表
    field_count = len(field_names)  # 说明：字段数量
    tags_add_chapter = bool(config.get("tags_add_chapter", True))  # 说明：是否补充章节标签
    tags_add_note_type = bool(config.get("tags_add_note_type", True))  # 说明：是否补充题型标签
    tags_splitter = str(config.get("tags_splitter", " "))  # 说明：标签分隔符
    strip_regex = str(config.get("deck_prefix_strip_regex", r"^\d+[\-_.]+"))  # 说明：牌堆前缀清理正则
    duplicate_mode = _normalize_duplicate_mode(str(config.get("duplicate_mode", "保留重复")))  # 说明：重复处理方式
    tags_from_extra = bool(config.get("tags_from_extra_column", True))  # 说明：是否从额外列读取标签
    joiner = str(config.get("field_extra_joiner", "\n"))  # 说明：字段拼接符
    scope_deck_only = bool(config.get("import_scope_deck_only", True))  # 说明：重复检测范围
    deck_tags = normalize_deck_tag(section.deck_name, strip_regex)  # 说明：生成章节标签列表
    for row in section.rows:  # 说明：逐行导入
        try:  # 说明：单行错误不影响整体
            field_values, row_tags = _prepare_fields_and_tags(  # 说明：整理字段与标签
                row.fields,  # 说明：原始字段列表
                field_count,  # 说明：目标字段数量
                tags_from_extra,  # 说明：是否将最后一列当作标签
                tags_splitter,  # 说明：标签分隔符
                joiner,  # 说明：字段拼接符
            )
            all_tags = _merge_tags(  # 说明：合并标签
                row_tags,  # 说明：行内标签
                deck_tags if tags_add_chapter else [],  # 说明：章节标签列表
                section.note_type if tags_add_note_type else "",  # 说明：题型标签
                tags_splitter,  # 说明：分隔符
            )
            duplicated_ids = _find_duplicates(  # 说明：查找重复笔记
                mw,  # 说明：主窗口
                field_names,  # 说明：字段名
                field_values,  # 说明：字段值
                mapped_type,  # 说明：笔记类型
                section.deck_name if scope_deck_only else "",  # 说明：限制牌堆
            )
            if duplicated_ids and duplicate_mode == "skip":  # 说明：遇到重复且选择跳过
                result.skipped += 1  # 说明：统计跳过
                target_id = int(duplicated_ids[0])  # 说明：默认记录第一条重复
                result.skipped_note_ids.append(target_id)  # 说明：记录跳过笔记 ID
                result.duplicate_note_ids.extend([int(note_id) for note_id in duplicated_ids])  # 说明：记录所有重复 ID
                session.items.append(  # 说明：写入会话记录
                    ImportSessionItem(
                        line_no=row.line_no,  # 说明：源行号
                        action="skipped",  # 说明：动作类型
                        note_id=target_id,  # 说明：关联的笔记 ID
                        deck_name=section.deck_name,  # 说明：牌堆名称
                        note_type=section.note_type,  # 说明：题型名称
                        fields=field_values,  # 说明：导入字段
                        tags=all_tags,  # 说明：导入标签
                        old_fields=_snapshot_note_fields(mw, target_id),  # 说明：保存原字段快照
                        old_tags=_snapshot_note_tags(mw, target_id),  # 说明：保存原标签快照
                        duplicate_note_ids=[int(note_id) for note_id in duplicated_ids],  # 说明：重复笔记列表
                    )
                )
                continue  # 说明：跳过该行
            if duplicated_ids and duplicate_mode == "update":  # 说明：遇到重复且选择更新
                target_id = int(duplicated_ids[0])  # 说明：默认更新第一条重复
                old_fields = _snapshot_note_fields(mw, target_id)  # 说明：更新前字段快照
                old_tags = _snapshot_note_tags(mw, target_id)  # 说明：更新前标签快照
                update_note_fields_and_tags(mw, target_id, field_values, all_tags)  # 说明：更新第一条
                result.updated += 1  # 说明：统计更新
                result.updated_note_ids.append(target_id)  # 说明：记录更新 ID
                result.imported_note_ids.append(target_id)  # 说明：记录导入 ID
                result.duplicate_note_ids.extend([int(note_id) for note_id in duplicated_ids])  # 说明：记录重复 ID
                session.items.append(  # 说明：写入会话记录
                    ImportSessionItem(
                        line_no=row.line_no,  # 说明：源行号
                        action="updated",  # 说明：动作类型
                        note_id=target_id,  # 说明：更新的笔记 ID
                        deck_name=section.deck_name,  # 说明：牌堆名称
                        note_type=section.note_type,  # 说明：题型名称
                        fields=field_values,  # 说明：导入字段
                        tags=all_tags,  # 说明：导入标签
                        old_fields=old_fields,  # 说明：旧字段快照
                        old_tags=old_tags,  # 说明：旧标签快照
                        duplicate_note_ids=[int(note_id) for note_id in duplicated_ids],  # 说明：重复笔记列表
                    )
                )
                continue  # 说明：更新完成后跳过新增
            note = create_note(mw, notetype, field_values)  # 说明：创建新笔记
            note.tags = all_tags  # 说明：写入标签
            add_note_to_deck(mw, note, deck_id)  # 说明：添加到指定牌堆
            result.added += 1  # 说明：统计新增
            if note.id:  # 说明：确保有 ID
                note_id = int(note.id)  # 说明：转换为 int
                result.imported_note_ids.append(note_id)  # 说明：记录新增的笔记 ID
                result.added_note_ids.append(note_id)  # 说明：记录新增 ID
                if duplicated_ids:  # 说明：存在重复记录
                    result.duplicate_note_ids.extend([int(note_id) for note_id in duplicated_ids])  # 说明：记录重复 ID
                old_fields = []  # 说明：初始化旧字段快照
                old_tags = []  # 说明：初始化旧标签快照
                if duplicated_ids:  # 说明：保留重复时也要保存旧笔记快照
                    primary_id = int(duplicated_ids[0])  # 说明：取第一条重复作为主笔记
                    old_fields = _snapshot_note_fields(mw, primary_id)  # 说明：保存原字段快照
                    old_tags = _snapshot_note_tags(mw, primary_id)  # 说明：保存原标签快照
                session.items.append(  # 说明：写入会话记录
                    ImportSessionItem(
                        line_no=row.line_no,  # 说明：源行号
                        action="added",  # 说明：动作类型
                        note_id=note_id,  # 说明：新增的笔记 ID
                        deck_name=section.deck_name,  # 说明：牌堆名称
                        note_type=section.note_type,  # 说明：题型名称
                        fields=field_values,  # 说明：导入字段
                        tags=all_tags,  # 说明：导入标签
                        old_fields=old_fields,  # 说明：保存旧字段快照
                        old_tags=old_tags,  # 说明：保存旧标签快照
                        duplicate_note_ids=[int(note_id) for note_id in duplicated_ids],  # 说明：重复笔记列表
                    )
                )
            if note.id:  # 说明：确保有 ID
                result.imported_note_ids.append(int(note.id))  # 说明：记录新增的笔记 ID
        except Exception as exc:  # 说明：捕获单行异常
            _record_error(result, f"第 {row.line_no} 行导入失败: {exc}")  # 说明：记录错误


def _prepare_fields_and_tags(  # 说明：整理字段与标签
    raw_fields: List[str],  # 说明：原始字段列表
    field_count: int,  # 说明：目标字段数
    tags_from_extra: bool,  # 说明：是否从额外列读取标签
    tags_splitter: str,  # 说明：标签分隔符
    joiner: str,  # 说明：字段拼接符
) -> Tuple[List[str], List[str]]:  # 说明：返回字段列表与标签列表
    fields = list(raw_fields)  # 说明：复制原始字段
    tags: List[str] = []  # 说明：初始化标签列表
    if tags_from_extra and len(fields) > field_count:  # 说明：额外列作为标签
        tag_text = fields[-1]  # 说明：取最后一列作为标签字符串
        fields = fields[:-1]  # 说明：移除标签列
        tags = _split_tags(tag_text, tags_splitter)  # 说明：解析标签
    if len(fields) < field_count:  # 说明：字段不足时补空
        fields = fields + [""] * (field_count - len(fields))  # 说明：补齐空字段
    if len(fields) > field_count:  # 说明：字段过多时拼接
        head = fields[:field_count - 1]  # 说明：保留前 n-1 个字段
        tail = joiner.join(fields[field_count - 1:])  # 说明：合并多余字段
        fields = head + [tail]  # 说明：拼接成合规字段列表
    return fields, tags  # 说明：返回整理结果


def _split_tags(text: str, splitter: str) -> List[str]:  # 说明：拆分标签字符串
    if not text:  # 说明：空字符串直接返回空列表
        return []  # 说明：无标签
    normalized = text.replace("\t", splitter).strip()  # 说明：先归一化分隔符
    return [item for item in normalized.split(splitter) if item]  # 说明：按配置分隔并去空


def _build_type_tag(note_type: str, prefix: str) -> str:  # 说明：生成题型标签
    cleaned = note_type.strip()  # 说明：去掉首尾空白
    if not cleaned:  # 说明：空题型名直接返回
        return ""  # 说明：返回空字符串
    if cleaned.startswith(prefix):  # 说明：已包含题型前缀
        return cleaned  # 说明：直接返回原值
    return f"{prefix}{cleaned}"  # 说明：补齐题型前缀并返回


def _is_type_tag(tag: str, prefix: str) -> bool:  # 说明：判断是否题型标签
    return tag.startswith(prefix)  # 说明：题型标签以固定前缀开头


def _contains_type_tag(tags: List[str], prefix: str) -> bool:  # 说明：判断是否已有题型标签
    for tag in tags:  # 说明：逐个检查标签
        if _is_type_tag(tag, prefix):  # 说明：发现题型标签
            return True  # 说明：已存在则返回 True
    return False  # 说明：未找到题型标签


def _split_tag_parts(tag: str) -> List[str]:  # 说明：将树状标签拆为层级
    if not tag:  # 说明：空字符串直接返回
        return []  # 说明：无层级
    return [item.strip() for item in tag.split("::") if item.strip()]  # 说明：去空并保留顺序


def _find_deck_overlap(deck_parts: List[str], tag_parts: List[str]) -> int:  # 说明：查找可重叠层级长度
    max_size = min(len(deck_parts), len(tag_parts))  # 说明：最大可能重叠长度
    for size in range(max_size, 0, -1):  # 说明：从最大重叠开始尝试
        if deck_parts[-size:] == tag_parts[:size]:  # 说明：尾部与头部匹配
            return size  # 说明：返回匹配长度
    return 0  # 说明：无重叠


def _prefix_tag_with_deck(tag: str, deck_parts: List[str]) -> str:  # 说明：为标签补齐牌堆前缀
    tag_parts = _split_tag_parts(tag)  # 说明：拆分标签层级
    if not tag_parts:  # 说明：空标签直接返回原值
        return tag  # 说明：原样返回
    if deck_parts[:len(tag_parts)] == tag_parts:  # 说明：标签已是牌堆前缀
        merged_parts = list(deck_parts)  # 说明：直接使用牌堆层级
    else:  # 说明：需要根据重叠情况拼接
        overlap = _find_deck_overlap(deck_parts, tag_parts)  # 说明：计算重叠层级长度
        if overlap > 0:  # 说明：存在重叠层级
            merged_parts = list(deck_parts[:-overlap]) + list(tag_parts)  # 说明：补齐缺失前缀
        else:  # 说明：无重叠时直接拼接
            merged_parts = list(deck_parts) + list(tag_parts)  # 说明：完整前缀 + 原标签
    return "::".join(merged_parts)  # 说明：合并为树状标签字符串


def _apply_deck_prefix_to_tags(row_tags: List[str], deck_tag: str, type_prefix: str) -> List[str]:  # 说明：为普通标签补齐牌堆前缀
    normalized: List[str] = []  # 说明：准备返回的新标签列表
    deck_parts = _split_tag_parts(deck_tag)  # 说明：拆分牌堆层级
    for raw_tag in row_tags:  # 说明：逐个处理行内标签
        cleaned = raw_tag.strip()  # 说明：清理空白
        if not cleaned:  # 说明：空标签跳过
            continue  # 说明：继续下一个标签
        if _is_type_tag(cleaned, type_prefix):  # 说明：题型标签不套牌堆前缀
            normalized.append(cleaned)  # 说明：保留原题型标签
            continue  # 说明：进入下一个标签
        if not deck_parts:  # 说明：没有牌堆前缀
            normalized.append(cleaned)  # 说明：保留原标签
            continue  # 说明：进入下一个标签
        if cleaned == deck_tag or cleaned.startswith(f"{deck_tag}::"):  # 说明：已带牌堆前缀
            normalized.append(cleaned)  # 说明：直接保留
            continue  # 说明：进入下一个标签
        prefixed = _prefix_tag_with_deck(cleaned, deck_parts)  # 说明：补齐牌堆前缀
        normalized.append(prefixed)  # 说明：保存补齐后的标签
    return normalized  # 说明：返回处理后的标签列表


def _merge_tags(row_tags: List[str], deck_tags: List[str], type_tag: str, splitter: str) -> List[str]:  # 说明：合并标签
    _ = splitter  # 说明：保留参数位，便于后续扩展
    type_prefix = "题型::"  # 说明：题型标签统一前缀
    deck_root = deck_tags[0] if deck_tags else ""  # 说明：用于补齐前缀的牌堆标签
    normalized_rows = _apply_deck_prefix_to_tags(row_tags, deck_root, type_prefix)  # 说明：补齐行内标签的牌堆前缀
    merged = list(normalized_rows)  # 说明：复制行内标签
    for deck_tag in deck_tags:  # 说明：逐个处理章节标签
        if deck_tag and deck_tag not in merged:  # 说明：仅追加缺失的标签
            merged.append(deck_tag)  # 说明：加入章节标签
    built_type = _build_type_tag(type_tag, type_prefix)  # 说明：生成题型标签
    if built_type and not _contains_type_tag(merged, type_prefix):  # 说明：无题型标签时才补齐
        merged.append(built_type)  # 说明：加入题型标签
    merged = [item.strip() for item in merged if item.strip()]  # 说明：去除空标签
    return merged  # 说明：返回合并结果


def _find_duplicates(  # 说明：查找重复笔记
    mw,  # 说明：主窗口
    field_names: List[str],  # 说明：字段名列表
    field_values: List[str],  # 说明：字段值列表
    note_type: str,  # 说明：笔记类型
    deck_name: str,  # 说明：限制牌堆名称（可为空）
) -> List[int]:  # 说明：返回重复笔记 ID 列表
    if not field_names or not field_values:  # 说明：字段不足无法查重
        return []  # 说明：返回空列表
    key_field = field_names[0]  # 说明：用第一个字段做查重 ключ
    key_value = field_values[0]  # 说明：用第一个字段的值做查重
    if not key_value:  # 说明：空值不做查重
        return []  # 说明：返回空列表
    query_parts = []  # 说明：构造查询条件
    query_parts.append(f"note:\"{note_type}\"")  # 说明：限定笔记类型
    if deck_name:  # 说明：需要限定牌堆
        query_parts.append(f"deck:\"{deck_name}\"")  # 说明：限定牌堆
    escaped_value = _escape_search_value(key_value)  # 说明：转义查询文本
    query_parts.append(f"{key_field}:\"{escaped_value}\"")  # 说明：字段查询条件
    query = " ".join(query_parts)  # 说明：拼接查询语句
    return find_notes(mw, query)  # 说明：返回查找结果


def _escape_search_value(value: str) -> str:  # 说明：转义搜索字符串
    return value.replace('"', '\\"')  # 说明：将双引号替换为转义形式


def _record_error(result: ImportResult, message: str) -> None:  # 说明：统一错误记录
    logger.error(message)  # 说明：记录日志
    result.errors.append(message)  # 说明：追加错误信息

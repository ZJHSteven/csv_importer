# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件提供 TTS 相关能力，包括拉取音色、合成音频、写入媒体与更新笔记。
"""  # 说明：文件级说明，强调 TTS 职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import hashlib  # 说明：用于生成稳定文件名
import json  # 说明：用于自定义请求体处理
import urllib.request  # 说明：使用标准库发起 HTTP 请求
from typing import Any, Dict, List, Optional  # 说明：类型标注所需
from urllib.parse import urlparse  # 说明：解析 URL 以做基础校验

from .addon_errors import TtsError, logger  # 说明：统一异常与日志
from .addon_models import TtsResult, TtsTask  # 说明：TTS 数据结构


def azure_list_voices(azure_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:  # 说明：拉取 Azure 音色列表
    _ensure_azure_required_fields(azure_cfg)  # 说明：检查必填参数
    url = _build_url(azure_cfg.get("base_url", ""), azure_cfg.get("endpoints", {}).get("voices_list", ""))  # 说明：构建接口 URL
    headers = _render_headers(azure_cfg.get("headers", {}).get("voices_list", {}), azure_cfg)  # 说明：渲染请求头
    data = _http_request(url, "GET", headers=headers, data=None, timeout=azure_cfg.get("timeout_seconds", 20))  # 说明：发送请求
    try:  # 说明：解析 JSON
        return json.loads(data.decode("utf-8"))  # 说明：返回音色列表
    except Exception as exc:  # 说明：捕获解析异常
        raise TtsError(f"音色列表解析失败: {exc}")  # 说明：抛出统一异常


def azure_synthesize(  # 说明：Azure 合成入口
    azure_cfg: Dict[str, Any],  # 说明：Azure 配置
    text: str,  # 说明：待合成文本
    voice_name: str,  # 说明：音色名称
    variables: Optional[Dict[str, Any]] = None,  # 说明：额外模板变量
) -> bytes:  # 说明：返回音频二进制
    _ensure_azure_required_fields(azure_cfg)  # 说明：检查必填参数
    url = _build_url(azure_cfg.get("base_url", ""), azure_cfg.get("endpoints", {}).get("synthesize", ""))  # 说明：构建接口 URL
    headers = _render_headers(azure_cfg.get("headers", {}).get("synthesize", {}), azure_cfg)  # 说明：渲染请求头
    template = str(azure_cfg.get("ssml_template", ""))  # 说明：读取 SSML 模板
    if not template:  # 说明：模板为空
        raise TtsError("SSML 模板不能为空")  # 说明：抛出统一异常
    defaults = dict(azure_cfg.get("defaults", {}))  # 说明：读取默认变量
    payload_vars: Dict[str, Any] = {}  # 说明：准备模板变量
    payload_vars.update(defaults)  # 说明：先写入默认变量
    payload_vars.update({"text": text, "voice_name": voice_name})  # 说明：写入核心变量
    if variables:  # 说明：合并额外变量
        payload_vars.update(variables)  # 说明：覆盖或补充
    ssml = _safe_format(template, payload_vars)  # 说明：渲染 SSML
    data = _http_request(url, "POST", headers=headers, data=ssml.encode("utf-8"), timeout=azure_cfg.get("timeout_seconds", 20))  # 说明：发起合成请求
    return data  # 说明：返回音频数据


def build_audio_filename(text: str, voice_name: str, suffix: str = "mp3") -> str:  # 说明：生成稳定音频文件名
    raw = f"{voice_name}|{text}".encode("utf-8")  # 说明：构造哈希输入
    digest = hashlib.md5(raw).hexdigest()  # 说明：生成 MD5 哈希
    return f"tts_{digest}.{suffix}"  # 说明：返回文件名


def ensure_audio_for_tasks(mw, tasks: List[TtsTask], config: Dict[str, Any]) -> TtsResult:  # 说明：执行 TTS 任务
    result = TtsResult()  # 说明：初始化结果
    provider = str(config.get("provider", "azure"))  # 说明：读取服务商配置
    if provider != "azure":  # 说明：当前仅实现 Azure
        raise TtsError("当前仅支持 Azure，其他服务商请先在配置中留空")  # 说明：抛出异常
    azure_cfg = config.get("azure", {})  # 说明：读取 Azure 配置
    for task in tasks:  # 说明：逐任务执行
        try:  # 说明：单条失败不影响整体
            note = mw.col.get_note(task.note_id)  # 说明：读取笔记对象
            if _field_has_audio_marker(note, task.target_field):  # 说明：已有音频标记则跳过
                result.skipped += 1  # 说明：统计跳过
                continue  # 说明：跳过该任务
            filename = build_audio_filename(task.text, task.voice_name)  # 说明：生成稳定文件名
            if mw.col.media.have(filename):  # 说明：媒体已存在
                result.skipped += 1  # 说明：统计跳过
                continue  # 说明：跳过该任务
            audio_data = azure_synthesize(azure_cfg, task.text, task.voice_name)  # 说明：调用 Azure 合成
            mw.col.media.write_data(filename, audio_data)  # 说明：写入媒体文件
            _append_audio_marker(mw, task.note_id, task.target_field, filename, config)  # 说明：写入音频标记
            result.generated += 1  # 说明：统计生成
        except Exception as exc:  # 说明：捕获异常
            error_text = _format_tts_error(task, exc)  # 说明：格式化错误信息
            logger.error(f"TTS 失败: {error_text}")  # 说明：记录日志
            result.errors.append(error_text)  # 说明：记录错误
    return result  # 说明：返回结果


def _append_audio_marker(mw, note_id: int, field_name: str, filename: str, config: Dict[str, Any]) -> None:  # 说明：向字段追加音频标记
    note = mw.col.get_note(note_id)  # 说明：获取笔记
    marker_format = config.get("audio_marker_format", " [sound:{filename}]")  # 说明：读取标记模板
    marker = marker_format.format(filename=filename)  # 说明：生成标记文本
    if field_name not in note:  # 说明：字段不存在
        raise TtsError(f"字段不存在: {field_name}")  # 说明：抛出异常
    if marker in note[field_name]:  # 说明：已包含标记
        return  # 说明：无需重复添加
    note[field_name] = f"{note[field_name]}{marker}"  # 说明：追加音频标记
    mw.col.update_note(note)  # 说明：保存更新


def build_tts_tasks(mw, note_ids: List[int], config: Dict[str, Any]) -> List[TtsTask]:  # 说明：生成 TTS 任务列表
    tasks: List[TtsTask] = []  # 说明：初始化任务列表
    tts_cfg = config  # 说明：直接使用传入配置
    text_field_index = int(tts_cfg.get("text_field_index", 0))  # 说明：读取文本字段索引
    audio_field_index = int(tts_cfg.get("audio_field_index", 0))  # 说明：读取音频写入字段索引
    default_voice = str(tts_cfg.get("azure", {}).get("default_voice", ""))  # 说明：读取默认音色
    if not default_voice:  # 说明：未设置默认音色则不生成任务
        return tasks  # 说明：直接返回空任务列表
    for note_id in note_ids:  # 说明：逐笔记构建任务
        note = mw.col.get_note(note_id)  # 说明：读取笔记
        if text_field_index >= len(note.fields):  # 说明：索引越界
            continue  # 说明：跳过该笔记
        text = note.fields[text_field_index]  # 说明：读取文本内容
        if not text:  # 说明：空文本无需合成
            continue  # 说明：跳过该笔记
        field_names = _get_note_field_names(note)  # 说明：获取字段名列表
        if not field_names:  # 说明：字段名为空无法写入
            continue  # 说明：跳过该笔记
        target_field = field_names[audio_field_index] if audio_field_index < len(field_names) else field_names[0]  # 说明：获取写入字段名
        tasks.append(TtsTask(note_id=note_id, text=text, voice_name=default_voice, target_field=target_field))  # 说明：创建任务对象
    return tasks  # 说明：返回任务列表


def _get_note_field_names(note) -> List[str]:  # 说明：安全获取字段名列表
    if hasattr(note, "keys"):  # 说明：优先使用 dict 风格接口
        return list(note.keys())  # 说明：返回字段名列表
    if hasattr(note, "model"):  # 说明：尝试从模型读取
        model = note.model()  # 说明：读取模型
        if isinstance(model, dict):  # 说明：确保为字典
            return [field.get("name", "") for field in model.get("flds", [])]  # 说明：提取字段名
    return []  # 说明：兜底返回空列表


def _build_url(base_url: str, path_or_url: str) -> str:  # 说明：拼接 URL
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):  # 说明：已是完整 URL
        return path_or_url  # 说明：直接返回
    if not base_url:  # 说明：缺少基础 URL
        raise TtsError("base_url 不能为空")  # 说明：抛出异常
    _ensure_http_url(base_url, "base_url")  # 说明：校验基础 URL 格式
    return base_url.rstrip("/") + "/" + path_or_url.lstrip("/")  # 说明：拼接并返回


def _render_headers(template: Dict[str, str], azure_cfg: Dict[str, Any]) -> Dict[str, str]:  # 说明：渲染请求头模板
    rendered: Dict[str, str] = {}  # 说明：初始化字典
    for key, value in template.items():  # 说明：逐键替换
        rendered[key] = value.format(subscription_key=azure_cfg.get("subscription_key", ""))  # 说明：替换订阅密钥
    return rendered  # 说明：返回请求头


def _safe_format(template: str, variables: Dict[str, Any]) -> str:  # 说明：安全模板渲染
    try:  # 说明：捕获缺失变量
        return template.format(**variables)  # 说明：执行格式化
    except KeyError as exc:  # 说明：缺失变量
        raise TtsError(f"SSML 模板变量缺失: {exc}")  # 说明：抛出统一异常


def _http_request(url: str, method: str, headers: Dict[str, str], data: Optional[bytes], timeout: int) -> bytes:  # 说明：发送 HTTP 请求
    req = urllib.request.Request(url, data=data, method=method)  # 说明：构造请求对象
    for key, value in headers.items():  # 说明：写入请求头
        req.add_header(key, value)  # 说明：追加头字段
    try:  # 说明：捕获网络异常
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # 说明：发送请求
            return resp.read()  # 说明：读取响应内容
    except Exception as exc:  # 说明：捕获异常
        raise TtsError(f"HTTP 请求失败: {exc}")  # 说明：抛出统一异常


def _ensure_http_url(value: str, field_name: str) -> None:  # 说明：检查 URL 是否包含协议
    parsed = urlparse(value)  # 说明：解析 URL
    if parsed.scheme not in ("http", "https"):  # 说明：未包含协议
        raise TtsError(f"{field_name} 必须以 http:// 或 https:// 开头")  # 说明：抛出友好错误


def _ensure_azure_required_fields(azure_cfg: Dict[str, Any]) -> None:  # 说明：校验 Azure 必填配置
    base_url = str(azure_cfg.get("base_url", "")).strip()  # 说明：读取 base_url
    if not base_url:  # 说明：base_url 为空
        raise TtsError("base_url 不能为空")  # 说明：提示用户填写
    _ensure_http_url(base_url, "base_url")  # 说明：校验 URL 格式
    subscription_key = str(azure_cfg.get("subscription_key", "")).strip()  # 说明：读取订阅密钥
    if not subscription_key:  # 说明：密钥为空
        raise TtsError("subscription_key 不能为空")  # 说明：提示用户填写


def _field_has_audio_marker(note, field_name: str) -> bool:  # 说明：检测字段是否已有音频标记
    if field_name not in note:  # 说明：字段不存在
        raise TtsError(f"字段不存在: {field_name}")  # 说明：抛出异常
    return "[sound:" in note[field_name]  # 说明：简单判断是否已有音频


def _format_tts_error(task: TtsTask, exc: Exception) -> str:  # 说明：格式化 TTS 错误详情
    text = task.text.replace("\n", " ").strip()  # 说明：清理文本中的换行
    preview = text[:60] + ("..." if len(text) > 60 else "")  # 说明：生成文本预览
    return f"note_id={task.note_id} 字段={task.target_field} 文本={preview} 错误={exc}"  # 说明：返回详情

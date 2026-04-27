# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件提供 TTS 相关能力，包括拉取音色、合成音频、写入媒体与更新笔记。
"""  # 说明：文件级说明，强调 TTS 职责

from __future__ import annotations  # 说明：允许前向引用类型标注

import hashlib  # 说明：用于生成稳定文件名
import re  # 说明：用于清理旧音频标记
import json  # 说明：用于自定义请求体处理
import time  # 说明：用于进度节流
import urllib.error  # 说明：细分 HTTP/URL 异常，输出更可诊断的错误
import urllib.request  # 说明：使用标准库发起 HTTP 请求
from concurrent.futures import ThreadPoolExecutor, as_completed  # 说明：并发下载音频
from typing import Any, Callable, Dict, List, Optional, Tuple  # 说明：类型标注所需
from urllib.parse import urlparse  # 说明：解析 URL 以做基础校验

from .addon_errors import TtsError, logger  # 说明：统一异常与日志
from .addon_models import TtsResult, TtsTask, TtsTaskPlan  # 说明：TTS 数据结构

TTS_MEDIA_PREFIX = "tts_"  # 说明：插件生成的音频文件名前缀


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


def build_audio_filename(text: str, voice_name: str, rate: str = "default", suffix: str = "mp3") -> str:  # 说明：生成稳定音频文件名
    raw = f"{voice_name}|{rate}|{text}".encode("utf-8")  # 说明：构造哈希输入
    digest = hashlib.md5(raw).hexdigest()  # 说明：生成 MD5 哈希
    return f"{TTS_MEDIA_PREFIX}{digest}.{suffix}"  # 说明：返回文件名


def ensure_audio_for_tasks(  # 说明：执行 TTS 任务（支持后台与进度回调）
    col,  # 说明：Anki 集合对象
    tasks: List[TtsTask],  # 说明：待处理任务
    config: Dict[str, Any],  # 说明：TTS 配置
    progress_callback: Optional[Callable[[int, int, str], None]] = None,  # 说明：进度回调
    should_cancel: Optional[Callable[[], bool]] = None,  # 说明：取消检查回调
) -> TtsResult:  # 说明：返回执行结果
    result = TtsResult()  # 说明：初始化结果
    if col is None:  # 说明：集合为空
        raise TtsError("集合未加载，无法执行 TTS")  # 说明：抛出异常
    provider = str(config.get("provider", "azure"))  # 说明：读取服务商配置
    if provider != "azure":  # 说明：当前仅实现 Azure
        raise TtsError("当前仅支持 Azure，其他服务商请先在配置中留空")  # 说明：抛出异常
    azure_cfg = config.get("azure", {})  # 说明：读取 Azure 配置
    overwrite = bool(config.get("overwrite_existing_audio", False))  # 说明：是否覆盖已生成音频
    concurrency = int(config.get("concurrency", 1))  # 说明：读取并发数量
    concurrency = max(1, concurrency)  # 说明：确保并发至少为 1
    total = len(tasks)  # 说明：任务总数
    processed = 0  # 说明：已处理数量
    last_progress_time = 0.0  # 说明：上次进度更新时间
    cancelled = False  # 说明：记录是否已中止

    def _report_progress(status: str) -> None:  # 说明：内部进度上报
        nonlocal last_progress_time  # 说明：声明使用外层变量
        if progress_callback is None:  # 说明：未传回调
            return  # 说明：直接返回
        now = time.time()  # 说明：读取当前时间
        if now - last_progress_time < 0.05 and processed < total:  # 说明：节流更新
            return  # 说明：跳过过于频繁的更新
        last_progress_time = now  # 说明：记录更新时间
        progress_callback(processed, total, status)  # 说明：触发回调

    def _is_cancelled() -> bool:  # 说明：检查是否请求中止
        if should_cancel is None:  # 说明：未提供取消回调
            return False  # 说明：默认不取消
        return bool(should_cancel())  # 说明：读取取消状态

    def _mark_cancelled() -> None:  # 说明：记录中止状态
        nonlocal cancelled  # 说明：使用外层变量
        if cancelled:  # 说明：避免重复记录
            return  # 说明：直接返回
        cancelled = True  # 说明：标记已中止
        result.errors.append("已中止：用户请求停止 TTS 任务")  # 说明：记录中止原因
        _report_progress("已中止")  # 说明：上报进度

    _report_progress("准备任务")  # 说明：初始进度
    pending: List[Tuple[TtsTask, str]] = []  # 说明：待合成任务列表
    for task in tasks:  # 说明：逐任务预处理
        if _is_cancelled():  # 说明：检测中止请求
            _mark_cancelled()  # 说明：记录中止
            break  # 说明：停止预处理
        try:  # 说明：单条失败不影响整体
            note = col.get_note(task.note_id)  # 说明：读取笔记对象
            if note is None:  # 说明：笔记不存在
                raise TtsError(f"笔记不存在: {task.note_id}")  # 说明：抛出异常
            if not overwrite and _field_has_audio_marker(note, task.target_field):  # 说明：已有音频标记且不覆盖
                result.skipped += 1  # 说明：统计跳过
                processed += 1  # 说明：更新计数
                _report_progress("跳过已生成")  # 说明：上报进度
                continue  # 说明：跳过该任务
            rate = str(azure_cfg.get("defaults", {}).get("rate", "1"))  # 说明：读取语速配置
            filename = build_audio_filename(task.text, task.voice_name, rate=rate)  # 说明：生成稳定文件名
            if not overwrite and col.media.have(filename):  # 说明：媒体已存在且不覆盖
                _append_audio_marker(col, task.note_id, task.target_field, filename, config)  # 说明：复用媒体并写入标记
                result.reused += 1  # 说明：统计复用数量
                processed += 1  # 说明：更新计数
                _report_progress("复用已有音频")  # 说明：上报进度
                continue  # 说明：跳过合成
            pending.append((task, filename))  # 说明：记录待合成任务
        except Exception as exc:  # 说明：捕获异常
            error_text = _format_tts_error(task, exc)  # 说明：格式化错误信息
            logger.error(f"TTS 失败: {error_text}")  # 说明：记录日志
            result.errors.append(error_text)  # 说明：记录错误
            processed += 1  # 说明：更新计数
            _report_progress("发生错误")  # 说明：上报进度
    if cancelled:  # 说明：已中止则直接返回
        return result  # 说明：返回当前结果
    if not pending:  # 说明：没有待合成任务
        _report_progress("完成")  # 说明：完成提示
        return result  # 说明：直接返回

    def _handle_audio_result(task: TtsTask, filename: str, audio_data: bytes) -> None:  # 说明：写入媒体与字段
        col.media.write_data(filename, audio_data)  # 说明：写入媒体文件
        _append_audio_marker(col, task.note_id, task.target_field, filename, config)  # 说明：写入音频标记

    if concurrency <= 1:  # 说明：单线程顺序合成
        for task, filename in pending:  # 说明：逐条合成
            if _is_cancelled():  # 说明：检测中止请求
                _mark_cancelled()  # 说明：记录中止
                break  # 说明：跳出循环
            try:  # 说明：捕获单条异常
                audio_data = azure_synthesize(azure_cfg, task.text, task.voice_name)  # 说明：调用 Azure 合成
                _handle_audio_result(task, filename, audio_data)  # 说明：写入结果
                result.generated += 1  # 说明：统计生成
            except Exception as exc:  # 说明：捕获异常
                error_text = _format_tts_error(task, exc)  # 说明：格式化错误信息
                logger.error(f"TTS 失败: {error_text}")  # 说明：记录日志
                result.errors.append(error_text)  # 说明：记录错误
            processed += 1  # 说明：更新计数
            _report_progress("生成中")  # 说明：上报进度
        if cancelled:  # 说明：中止后直接返回
            return result  # 说明：返回当前结果
        _report_progress("完成")  # 说明：完成提示
        return result  # 说明：返回结果

    with ThreadPoolExecutor(max_workers=concurrency) as executor:  # 说明：并发执行合成请求
        future_map = {}  # 说明：任务映射表
        for task, filename in pending:  # 说明：提交任务
            if _is_cancelled():  # 说明：检测中止请求
                _mark_cancelled()  # 说明：记录中止
                break  # 说明：停止提交
            future = executor.submit(azure_synthesize, azure_cfg, task.text, task.voice_name)  # 说明：提交合成任务
            future_map[future] = (task, filename)  # 说明：保存映射
        for future in as_completed(future_map):  # 说明：按完成顺序处理
            if _is_cancelled():  # 说明：检测中止请求
                _mark_cancelled()  # 说明：记录中止
                break  # 说明：停止处理剩余任务
            task, filename = future_map[future]  # 说明：取回任务信息
            try:  # 说明：捕获合成异常
                audio_data = future.result()  # 说明：获取合成结果
                _handle_audio_result(task, filename, audio_data)  # 说明：写入结果
                result.generated += 1  # 说明：统计生成
            except Exception as exc:  # 说明：捕获异常
                error_text = _format_tts_error(task, exc)  # 说明：格式化错误信息
                logger.error(f"TTS 失败: {error_text}")  # 说明：记录日志
                result.errors.append(error_text)  # 说明：记录错误
            processed += 1  # 说明：更新计数
            _report_progress("生成中")  # 说明：上报进度
    if cancelled:  # 说明：中止后直接返回
        return result  # 说明：返回当前结果
    _report_progress("完成")  # 说明：完成提示
    return result  # 说明：返回结果


def _append_audio_marker(  # 说明：向字段追加音频标记
    col,  # 说明：Anki 集合对象
    note_id: int,  # 说明：笔记 ID
    field_name: str,  # 说明：字段名
    filename: str,  # 说明：音频文件名
    config: Dict[str, Any],  # 说明：TTS 配置
) -> None:  # 说明：无返回值
    if not config.get("auto_append_marker", True):  # 说明：未启用自动追加
        return  # 说明：直接返回
    note = col.get_note(note_id)  # 说明：获取笔记
    if note is None:  # 说明：笔记不存在
        raise TtsError(f"笔记不存在: {note_id}")  # 说明：抛出异常
    if field_name not in note:  # 说明：字段不存在
        raise TtsError(f"字段不存在: {field_name}")  # 说明：抛出异常
    if config.get("overwrite_existing_audio", False):  # 说明：覆盖模式先清理旧标记
        _remove_tts_markers(note, field_name)  # 说明：移除旧标记
    marker_format = config.get("audio_marker_format", " [sound:{filename}]")  # 说明：读取标记模板
    marker = marker_format.format(filename=filename)  # 说明：生成标记文本
    if marker in note[field_name]:  # 说明：已包含标记
        return  # 说明：无需重复添加
    note[field_name] = f"{note[field_name]}{marker}"  # 说明：追加音频标记
    col.update_note(note)  # 说明：保存更新


def _remove_tts_markers(note, field_name: str) -> None:  # 说明：移除字段内旧的 TTS 标记
    if field_name not in note:  # 说明：字段不存在
        raise TtsError(f"字段不存在: {field_name}")  # 说明：抛出异常
    text = str(note[field_name])  # 说明：读取字段内容
    if not text:  # 说明：空内容无需处理
        return  # 说明：直接返回
    pattern = rf"\s*\[sound:{TTS_MEDIA_PREFIX}[^\]]+\]"  # 说明：匹配插件音频标记
    cleaned = re.sub(pattern, "", text)  # 说明：移除标记
    if cleaned != text:  # 说明：内容发生变化
        note[field_name] = cleaned  # 说明：写回清理后的内容


def build_tts_tasks(mw, note_ids: List[int], config: Dict[str, Any]) -> List[TtsTask]:  # 说明：生成 TTS 任务列表
    return plan_tts_tasks(mw, note_ids, config).tasks  # 说明：保留旧接口，实际逻辑统一交给带统计的计划函数


def plan_tts_tasks(mw, note_ids: List[int], config: Dict[str, Any]) -> TtsTaskPlan:  # 说明：生成 TTS 任务并给出扫描统计
    """根据候选笔记 ID 生成 TTS 任务计划。

    输入：
    - mw：Anki 主窗口对象，函数会通过 mw.col 读取笔记与媒体库。
    - note_ids：扫描阶段得到的候选笔记 ID，可能包含重复 ID 或已经失效的 ID。
    - config：TTS 配置，包含字段索引、默认音色、覆盖策略等。

    输出：
    - TtsTaskPlan：既包含真正要执行的任务，也包含为什么数量和牌组显示不一致的诊断统计。

    核心逻辑：
    1. 先对 note_id 去重，避免同一笔记被多个搜索条件重复计数。
    2. 逐条读取笔记，缺失、空文本、字段异常、已有音频标记都会单独计数。
    3. 媒体文件已存在但字段还没写 sound 标记时，仍保留为任务，因为执行阶段需要补标记。
    """
    plan = TtsTaskPlan(source_note_count=len(note_ids))  # 说明：创建统计对象，并记录原始输入数量
    tts_cfg = config  # 说明：直接使用传入配置
    text_field_index = int(tts_cfg.get("text_field_index", 0))  # 说明：读取文本字段索引
    audio_field_index = int(tts_cfg.get("audio_field_index", 0))  # 说明：读取音频写入字段索引
    default_voice = str(tts_cfg.get("azure", {}).get("default_voice", ""))  # 说明：读取默认音色
    if not default_voice:  # 说明：未设置默认音色则不生成任务
        logger.warning("TTS 扫描停止：尚未选择默认音色")  # 说明：写日志，避免界面只显示 0 条却不知道原因
        return plan  # 说明：直接返回空计划
    unique_note_ids = [int(note_id) for note_id in dict.fromkeys(note_ids)]  # 说明：去重并保留 Anki 搜索结果顺序
    plan.candidate_note_count = len(unique_note_ids)  # 说明：记录去重后的候选数量
    overwrite = bool(tts_cfg.get("overwrite_existing_audio", False))  # 说明：覆盖模式下已有标记也需要重新处理
    rate = str(tts_cfg.get("azure", {}).get("defaults", {}).get("rate", "1"))  # 说明：语速会参与文件名哈希，必须与执行阶段保持一致
    for note_id in unique_note_ids:  # 说明：逐笔记构建任务
        note = mw.col.get_note(note_id)  # 说明：读取笔记
        if note is None:  # 说明：笔记可能已被删除，或历史导入范围里保留了旧 ID
            plan.missing_note_count += 1  # 说明：记录缺失数量
            plan.missing_note_ids.append(note_id)  # 说明：保留 ID，方便日志定位
            continue  # 说明：缺失笔记无法生成任务
        if text_field_index < 0 or text_field_index >= len(note.fields):  # 说明：索引越界
            plan.field_error_count += 1  # 说明：记录字段配置异常
            plan.field_error_note_ids.append(note_id)  # 说明：记录问题笔记
            continue  # 说明：跳过该笔记
        text = note.fields[text_field_index]  # 说明：读取文本内容
        if not text:  # 说明：空文本无需合成
            plan.empty_text_count += 1  # 说明：记录空文本数量
            continue  # 说明：跳过该笔记
        field_names = _get_note_field_names(note)  # 说明：获取字段名列表
        if not field_names or audio_field_index < 0:  # 说明：字段名为空或写入索引非法
            plan.field_error_count += 1  # 说明：记录字段配置异常
            plan.field_error_note_ids.append(note_id)  # 说明：记录问题笔记
            continue  # 说明：跳过该笔记
        target_field = field_names[audio_field_index] if audio_field_index < len(field_names) else field_names[0]  # 说明：获取写入字段名
        if not overwrite and _field_has_audio_marker(note, target_field):  # 说明：已有音频标记时执行阶段也只会跳过
            plan.already_marked_count += 1  # 说明：扫描阶段提前说明跳过原因
            continue  # 说明：不再放入执行任务，避免“待生成”虚高
        filename = build_audio_filename(text, default_voice, rate=rate)  # 说明：计算执行阶段会使用的媒体文件名
        task = TtsTask(note_id=note_id, text=text, voice_name=default_voice, target_field=target_field)  # 说明：创建任务对象
        plan.tasks.append(task)  # 说明：加入执行列表
        if not overwrite and mw.col.media.have(filename):  # 说明：媒体已存在，执行阶段只会补 sound 标记
            plan.reusable_media_count += 1  # 说明：记录可复用数量
        else:  # 说明：媒体不存在或覆盖模式开启
            plan.needs_generation_count += 1  # 说明：记录需要真实调用 TTS 的数量
    return plan  # 说明：返回完整扫描计划


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
        logger.info(f"TTS HTTP 请求: method={method} url={url}")  # 说明：日志只记录方法和 URL，不记录 Key 等敏感请求头
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # 说明：发送请求
            return resp.read()  # 说明：读取响应内容
    except urllib.error.HTTPError as exc:  # 说明：服务端返回 4xx/5xx 时保留状态码与响应片段
        try:  # 说明：响应体可能不是文本，读取失败时也不能影响主错误
            body = exc.read().decode("utf-8", errors="replace")[:500]  # 说明：截断响应体，避免弹窗过长
        except Exception:  # 说明：响应体读取失败
            body = ""  # 说明：兜底为空
        raise TtsError(f"HTTP 请求失败: method={method} url={url} status={exc.code} response={body}")  # 说明：抛出可定位的错误
    except urllib.error.URLError as exc:  # 说明：DNS、代理、证书、系统文件等 URL 打开阶段错误
        reason = getattr(exc, "reason", exc)  # 说明：URLError 的真实原因在 reason 字段里
        raise TtsError(f"HTTP 请求失败: method={method} url={url} reason={reason}")  # 说明：保留 URL 与底层原因
    except Exception as exc:  # 说明：捕获异常
        raise TtsError(f"HTTP 请求失败: method={method} url={url} error={exc}")  # 说明：抛出统一异常


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

# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件负责配置读取/写入与默认值管理，所有可变参数都集中在这里。
"""  # 说明：文件级说明，强调配置集中管理

from __future__ import annotations  # 说明：允许前向引用类型标注

from typing import Any, Dict  # 说明：类型标注所需

from .addon_errors import ConfigError  # 说明：引入统一配置异常


def get_default_config() -> Dict[str, Any]:  # 说明：提供默认配置
    return {  # 说明：集中返回默认值字典
        "config_version": 1,  # 说明：配置版本号，方便未来迁移
        "default_import_path": "",  # 说明：默认导入文件路径（可留空）
        "deck_line_prefix": "//",  # 说明：牌堆标记行前缀
        "type_line_allow_english_colon": True,  # 说明：题型行允许英文冒号
        "allow_html": True,  # 说明：默认允许 HTML
        "duplicate_mode": "保留重复",  # 说明：默认重复处理方式（保留重复/覆盖更新/跳过重复）
        "import_session_keep_limit": 0,  # 说明：保留的导入会话数量上限（0=不限）
        "import_auto_open_browser": True,  # 说明：导入后自动打开浏览器
        "import_auto_open_duplicate_browser": False,  # 说明：导入后是否打开重复笔记浏览器
        "tags_add_chapter": True,  # 说明：自动补充章节标签
        "tags_add_note_type": True,  # 说明：自动补充题型标签
        "deck_prefix_strip_regex": r"^\d+[\-_.]+",  # 说明：去掉牌堆名前的序号前缀
        "note_type_map": {  # 说明：题型名称到 Anki 笔记类型名称的映射
            "问答题": "问答题",  # 说明：默认同名映射
            "填空题": "填空题",  # 说明：默认同名映射
            "选择题": "选择题",  # 说明：可扩展的题型
            "默写题": "默写题",  # 说明：可扩展的题型
        },
        "tags_from_extra_column": True,  # 说明：当 CSV 列数多于字段数时，最后一列视为标签
        "tags_splitter": " " ,  # 说明：标签分隔符，默认空格
        "field_extra_joiner": "\n",  # 说明：字段超出时的拼接符
        "import_scope_deck_only": True,  # 说明：重复检测只在目标牌堆内进行
        "tts": {  # 说明：TTS 相关配置入口
            "provider": "azure",  # 说明：默认使用 Azure
            "english_tag": "英文",  # 说明：识别英文卡片的标签
            "text_field_index": 0,  # 说明：用于合成的字段索引（0=第一字段）
            "audio_field_index": 0,  # 说明：写入音频标记的字段索引
            "audio_marker_format": " [sound:{filename}]",  # 说明：音频标记写入格式
            "auto_append_marker": True,  # 说明：是否自动追加音频标记
            "open_browser_after_run": True,  # 说明：TTS 完成后自动打开浏览器
            "overwrite_existing_audio": False,  # 说明：是否覆盖已生成音频
            "concurrency": 2,  # 说明：并发合成数量
            "scan_limit_decks": False,  # 说明：扫描时是否限制牌组
            "scan_decks": [],  # 说明：扫描时选中的牌组列表
            "azure": {  # 说明：Azure TTS 配置
                "base_url": "",  # 说明：Azure 端点基础 URL
                "subscription_key": "",  # 说明：Azure 订阅密钥
                "endpoints": {  # 说明：Azure API 路径配置
                    "voices_list": "/cognitiveservices/voices/list",  # 说明：音色列表接口
                    "synthesize": "/cognitiveservices/v1",  # 说明：合成接口
                },
                "headers": {  # 说明：Azure 请求头模板
                    "voices_list": {  # 说明：音色列表请求头模板
                        "Ocp-Apim-Subscription-Key": "{subscription_key}",  # 说明：订阅密钥占位符
                        "User-Agent": "anki-csv-importer",  # 说明：简单 UA
                    },
                    "synthesize": {  # 说明：合成请求头模板
                        "Ocp-Apim-Subscription-Key": "{subscription_key}",  # 说明：订阅密钥占位符
                        "Content-Type": "application/ssml+xml",  # 说明：SSML 内容类型
                        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",  # 说明：默认输出格式
                        "User-Agent": "anki-csv-importer",  # 说明：简单 UA
                    },
                },
                "ssml_template": "<speak version=\"1.0\" xml:lang=\"{lang}\"><voice name=\"{voice_name}\"><prosody rate=\"{rate}\">{text}</prosody></voice></speak>",  # 说明：默认 SSML 模板
                "defaults": {  # 说明：SSML 默认变量
                    "lang": "en-US",  # 说明：默认语言
                    "rate": "1.0",  # 说明：默认语速倍率
                },
                "timeout_seconds": 20,  # 说明：请求超时秒数
                "voice_cache": {  # 说明：本地缓存的音色列表
                    "items": [],  # 说明：缓存的音色列表
                    "last_update": "",  # 说明：上次刷新时间
                },
                "filters": {  # 说明：音色筛选条件
                    "locale": "en-GB",  # 说明：默认语言筛选
                    "gender": "Female",  # 说明：默认性别筛选
                    "voice_type": "Neural",  # 说明：默认音色类型筛选
                },
                "default_voice": "",  # 说明：默认音色 ShortName
            },
            "custom": {  # 说明：自定义兼容 API（例如 OpenAI 兼容）
                "base_url": "",  # 说明：自定义基础 URL
                "api_key": "",  # 说明：自定义 API Key
                "headers": {},  # 说明：自定义请求头
                "payload_template": "",  # 说明：自定义请求体模板（JSON 字符串）
                "timeout_seconds": 20,  # 说明：超时设置
            },
        },
    }


def merge_config(defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:  # 说明：递归合并配置
    merged: Dict[str, Any] = {}  # 说明：准备合并后的新字典
    for key, value in defaults.items():  # 说明：遍历默认值
        if key in current:  # 说明：当前配置存在该键
            if isinstance(value, dict) and isinstance(current[key], dict):  # 说明：字典则递归合并
                merged[key] = merge_config(value, current[key])  # 说明：递归合并子字典
            else:  # 说明：非字典直接覆盖
                merged[key] = current[key]  # 说明：采用当前配置值
        else:  # 说明：当前配置缺失该键
            merged[key] = value  # 说明：使用默认值
    for key, value in current.items():  # 说明：保留当前配置中默认值没有的字段
        if key not in merged:  # 说明：仅添加不存在的键
            merged[key] = value  # 说明：保留用户自定义字段
    return merged  # 说明：返回合并结果


def load_config(mw: Any, addon_name: str) -> Dict[str, Any]:  # 说明：从 Anki 读取配置
    if mw is None:  # 说明：安全检查，避免空对象
        raise ConfigError("mw 不能为空")  # 说明：抛出配置异常
    if not addon_name:  # 说明：安全检查，避免空名称
        raise ConfigError("addon_name 不能为空")  # 说明：抛出配置异常
    defaults = get_default_config()  # 说明：获取默认配置
    current = mw.addonManager.getConfig(addon_name) or {}  # 说明：读取当前配置，不存在则空字典
    merged = merge_config(defaults, current)  # 说明：合并默认与当前配置
    return merged  # 说明：返回合并后的配置


def save_config(mw: Any, addon_name: str, config: Dict[str, Any]) -> None:  # 说明：写入配置到 Anki
    if mw is None:  # 说明：安全检查
        raise ConfigError("mw 不能为空")  # 说明：抛出配置异常
    if not addon_name:  # 说明：安全检查
        raise ConfigError("addon_name 不能为空")  # 说明：抛出配置异常
    if not isinstance(config, dict):  # 说明：安全检查，确保配置为字典
        raise ConfigError("config 必须是 dict")  # 说明：抛出配置异常
    mw.addonManager.writeConfig(addon_name, config)  # 说明：写入配置并持久化

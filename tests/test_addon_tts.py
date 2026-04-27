# -*- coding: utf-8 -*-
"""
本文件测试 TTS 扫描与 HTTP 错误包装逻辑。

测试不直接导入 Anki，因为真实 Anki 运行环境很重；这里用小型假对象模拟 mw.col、note
和 media，专门覆盖“数量为什么对不上”和“HTTP 错误是否可诊断”这两个用户现场问题。
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]  # 说明：插件根目录，用于把源码当作临时包加载
PACKAGE_NAME = "csv_importer_test_pkg"  # 说明：避免导入真实 __init__.py，因为真实入口依赖 aqt


def _load_module(module_name: str):
    """按临时包名加载插件模块。

    输入：模块短名，例如 addon_tts。
    输出：导入后的模块对象。
    核心逻辑：给 Python 注册一个假的包路径，让源码里的相对导入 `.addon_models` 能正常工作。
    """
    if PACKAGE_NAME not in sys.modules:  # 说明：首次加载时创建临时包
        package = types.ModuleType(PACKAGE_NAME)  # 说明：构造轻量包对象
        package.__path__ = [str(ROOT)]  # 说明：告诉导入系统到插件根目录找子模块
        sys.modules[PACKAGE_NAME] = package  # 说明：注册临时包
    return importlib.import_module(f"{PACKAGE_NAME}.{module_name}")  # 说明：按包内模块导入


addon_tts = _load_module("addon_tts")  # 说明：加载被测模块


class FakeNote:
    """模拟 Anki Note 的最小行为。"""

    def __init__(self, fields, names=None):
        self.fields = fields  # 说明：Anki Note.fields 是字段值列表
        self._names = names or ["正面", "背面"]  # 说明：字段名用于定位写入字段

    def keys(self):
        return list(self._names)  # 说明：插件优先通过 keys() 获取字段名

    def __contains__(self, key):
        return key in self._names  # 说明：支持 `field_name in note` 判断

    def __getitem__(self, key):
        index = self._names.index(key)  # 说明：按字段名找到字段位置
        return self.fields[index]  # 说明：返回字段内容


class FakeMedia:
    """模拟 Anki 媒体库的 have() 查询。"""

    def __init__(self, existing):
        self._existing = set(existing)  # 说明：保存已存在的媒体文件名

    def have(self, filename):
        return filename in self._existing  # 说明：判断媒体是否已存在


class FakeCollection:
    """模拟 Anki Collection 的 get_note 与 media。"""

    def __init__(self, notes, existing_media):
        self._notes = notes  # 说明：note_id 到 FakeNote 的映射
        self.media = FakeMedia(existing_media)  # 说明：挂载媒体库对象

    def get_note(self, note_id):
        return self._notes.get(note_id)  # 说明：不存在时返回 None，模拟被删除的笔记


class FakeMw:
    """模拟 Anki 主窗口，只暴露 col 属性。"""

    def __init__(self, col):
        self.col = col  # 说明：插件通过 mw.col 访问集合


class TtsPlanTests(unittest.TestCase):
    """覆盖 TTS 扫描分类统计。"""

    def test_plan_dedupes_and_classifies_candidates(self):
        config = {
            "text_field_index": 0,
            "audio_field_index": 0,
            "overwrite_existing_audio": False,
            "azure": {
                "default_voice": "en-US-TestNeural",
                "defaults": {"rate": "1.0"},
            },
        }
        reusable_name = addon_tts.build_audio_filename("hello", "en-US-TestNeural", rate="1.0")
        notes = {
            1: FakeNote(["hello", "释义"]),  # 说明：媒体已存在，应归类为可复用
            2: FakeNote(["new word", "释义"]),  # 说明：媒体不存在，应归类为需合成
            3: FakeNote(["done [sound:tts_old.mp3]", "释义"]),  # 说明：已有 sound 标记，应跳过
            4: FakeNote(["", "释义"]),  # 说明：空文本，应跳过
        }
        mw = FakeMw(FakeCollection(notes, existing_media={reusable_name}))

        plan = addon_tts.plan_tts_tasks(mw, [1, 1, 2, 3, 4, 5], config)

        self.assertEqual(plan.source_note_count, 6)
        self.assertEqual(plan.candidate_note_count, 5)
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.reusable_media_count, 1)
        self.assertEqual(plan.needs_generation_count, 1)
        self.assertEqual(plan.already_marked_count, 1)
        self.assertEqual(plan.empty_text_count, 1)
        self.assertEqual(plan.missing_note_count, 1)
        self.assertEqual(plan.missing_note_ids, [5])

    def test_build_tts_tasks_keeps_backward_compatible_list_return(self):
        config = {
            "text_field_index": 0,
            "audio_field_index": 0,
            "azure": {"default_voice": "en-US-TestNeural", "defaults": {"rate": "1.0"}},
        }
        mw = FakeMw(FakeCollection({1: FakeNote(["hello", "释义"])}, existing_media=set()))

        tasks = addon_tts.build_tts_tasks(mw, [1], config)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].note_id, 1)


class HttpRequestTests(unittest.TestCase):
    """覆盖 HTTP 失败信息，确保现场日志能看出失败阶段。"""

    def test_url_error_keeps_method_url_and_reason(self):
        error = urllib.error.URLError(FileNotFoundError(2, "No such file or directory"))
        with patch.object(addon_tts.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(Exception) as ctx:
                addon_tts._http_request("https://example.invalid/cognitiveservices/v1", "POST", {}, b"x", 1)

        message = str(ctx.exception)
        self.assertIn("method=POST", message)
        self.assertIn("https://example.invalid/cognitiveservices/v1", message)
        self.assertIn("No such file or directory", message)


if __name__ == "__main__":
    unittest.main()

# AGENTS.md

本文件用于记录插件改动与当前状态，方便追踪每次更新。

## 最近更新
- 初始化 AGENTS.md，占位并开始记录。

- 新增 addon_errors.py：集中异常与日志接口。

- 新增 addon_models.py：定义解析/导入/TTS 的数据结构。

- 新增 addon_config.py：集中管理默认配置与读写逻辑。

- 新增 addon_parser.py：解析混合格式文本并输出分段结构。

- 新增 addon_anki.py：封装 Anki 集合交互操作。

- 新增 addon_importer.py：实现导入流程与重复处理。

- 新增 addon_tts.py：实现 Azure TTS 合成与媒体写入。

- 新增 addon_ui.py：实现导入与 TTS 的中文界面。

- 更新 __init__.py：注册菜单入口并打开主界面。

- 更新 README.md：补充格式示例、使用步骤与说明。

- 新增 config.json：提供默认配置模板。

- 更新 addon_tts.py：完善默认音色判断与字段名获取。

- 更新 addon_anki.py：章节标签取牌堆最后一级。

- 更新 addon_parser.py：支持题型行后紧跟内容。

- 更新 addon_importer.py：标签分隔符由配置控制。

- 更新内部模块导入：统一改为相对导入，修复插件加载时模块找不到的问题。

- 修复 Qt6 下 QLineEdit 回显模式设置：改为使用 EchoMode.Password。

- 修复题型识别误判：忽略引号内冒号，避免把 CSV 内容当题型行。

- 安全处理集合为空的情况：TTS 扫描前检测 mw.col 并提示用户。

- 忽略运行时生成的 meta.json，避免误提交。

- 优化 TTS 扫描与错误提示：按标签过滤导入范围、校验 base_url/Key、跳过已有音频并输出更详细的失败信息。

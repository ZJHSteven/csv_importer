# -*- coding: utf-8 -*-  # 说明：显式声明源码编码，避免中文注释读取异常
"""
本文件提供插件 GUI，包括导入页与 TTS 页，所有界面文案均为中文。
"""  # 说明：文件级说明，强调 GUI 作用

from __future__ import annotations  # 说明：允许前向引用类型标注

from typing import List, Optional  # 说明：类型标注所需
from threading import Event  # 说明：线程安全的取消标记

from aqt import mw  # 说明：Anki 主窗口对象
from aqt.operations import QueryOp  # 说明：后台任务封装
from aqt.qt import (  # 说明：Qt 组件
    QAbstractItemView,  # 说明：视图选择模式
    QCheckBox,  # 说明：复选框
    QComboBox,  # 说明：下拉框
    QDialog,  # 说明：对话框
    QFileDialog,  # 说明：文件选择对话框
    QFormLayout,  # 说明：表单布局
    QHBoxLayout,  # 说明：水平布局
    QLabel,  # 说明：文本标签
    QLineEdit,  # 说明：单行输入框
    QProgressBar,  # 说明：进度条
    QPushButton,  # 说明：按钮
    QSpinBox,  # 说明：数值选择
    QTabWidget,  # 说明：选项卡组件
    QTableWidget,  # 说明：表格控件
    QTableWidgetItem,  # 说明：表格单元格
    QTextEdit,  # 说明：多行文本框
    QTreeWidget,  # 说明：树形控件
    QTreeWidgetItem,  # 说明：树形节点
    QVBoxLayout,  # 说明：垂直布局
    QWidget,  # 说明：通用容器
    Qt,  # 说明：Qt 枚举
)
from aqt.utils import showInfo, showText  # 说明：Anki 提示框

from .addon_anki import get_all_deck_names, open_browser_with_note_ids, update_note_fields_and_tags  # 说明：浏览器与牌组工具
from .addon_config import get_default_config, load_config, save_config  # 说明：配置读写
from .addon_importer import import_parse_result  # 说明：导入逻辑
from .addon_parser import parse_file  # 说明：解析逻辑
from .addon_tts import azure_list_voices, build_tts_tasks, ensure_audio_for_tasks  # 说明：TTS 逻辑
from .addon_models import ImportSession, ImportSessionItem, ParseResult, TtsResult  # 说明：数据结构
from .addon_errors import logger  # 说明：日志
from .addon_session import (  # 说明：会话记录能力
    append_session_items,  # 说明：追加会话条目
    apply_duplicate_strategy,  # 说明：调整重复策略
    delete_import_session,  # 说明：删除会话
    list_import_sessions,  # 说明：列出会话
    load_import_session,  # 说明：读取会话
    load_latest_session,  # 说明：读取最新会话
    rollback_session,  # 说明：回滚会话
)


class MainDialog(QDialog):  # 说明：主对话框
    """插件入口对话框，包含导入与 TTS 两个页面。"""  # 说明：类说明

    def __init__(self, addon_name: str, parent=None) -> None:  # 说明：初始化主对话框
        super().__init__(parent)  # 说明：调用父类初始化
        self._addon_name = addon_name  # 说明：记录插件名称
        self._config = load_config(mw, addon_name)  # 说明：加载配置
        self._last_import_note_ids: List[int] = []  # 说明：保存最近一次导入的笔记 ID
        self.setWindowTitle("CSV 批量导入与 TTS")  # 说明：设置窗口标题
        self.resize(900, 600)  # 说明：设置窗口大小
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用主布局
        self._tabs = QTabWidget()  # 说明：创建选项卡
        layout.addWidget(self._tabs)  # 说明：加入主布局
        self._import_tab = ImportTab(self._config, self._addon_name, self._on_import_done)  # 说明：创建导入页
        self._tts_tab = TtsTab(self._config, self._addon_name, self._get_last_import_note_ids)  # 说明：创建 TTS 页
        self._session_tab = SessionTab(self._config, self._addon_name)  # 说明：创建会话页
        self._tabs.addTab(self._import_tab, "导入")  # 说明：添加导入页
        self._tabs.addTab(self._tts_tab, "TTS")  # 说明：添加 TTS 页
        self._tabs.addTab(self._session_tab, "会话")  # 说明：添加会话页

    def _on_import_done(self, note_ids: List[int]) -> None:  # 说明：导入完成回调
        self._last_import_note_ids = note_ids  # 说明：保存最近导入 ID
        self._tts_tab.refresh_import_scope()  # 说明：通知 TTS 页刷新状态
        self._session_tab.refresh_sessions()  # 说明：刷新会话记录

    def _get_last_import_note_ids(self) -> List[int]:  # 说明：供 TTS 页读取最近导入 ID
        return list(self._last_import_note_ids)  # 说明：返回副本，避免外部修改


class ImportTab(QWidget):  # 说明：导入页面
    """CSV 导入界面，负责文件选择、解析预览与执行导入。"""  # 说明：类说明

    def __init__(self, config: dict, addon_name: str, on_import_done) -> None:  # 说明：初始化导入页
        super().__init__()  # 说明：调用父类初始化
        self._config = config  # 说明：持有配置
        self._addon_name = addon_name  # 说明：保存插件名称
        self._on_import_done = on_import_done  # 说明：保存回调
        self._parse_result: Optional[ParseResult] = None  # 说明：保存解析结果
        self._last_import_note_ids: List[int] = []  # 说明：记录最近一次导入的笔记 ID
        self._last_duplicate_note_ids: List[int] = []  # 说明：记录最近一次重复笔记 ID
        self._last_session_id: str = ""  # 说明：记录最近一次导入会话 ID
        latest_session = load_latest_session()  # 说明：读取最近会话
        if latest_session:  # 说明：存在历史会话
            self._last_session_id = latest_session.session_id  # 说明：初始化会话 ID
            self._last_import_note_ids = _collect_import_note_ids(latest_session)  # 说明：恢复导入笔记 ID
            self._last_duplicate_note_ids = _collect_duplicate_note_ids(latest_session)  # 说明：恢复重复笔记 ID
        self._build_ui()  # 说明：搭建界面

    def _build_ui(self) -> None:  # 说明：构建 UI
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用布局
        form = QFormLayout()  # 说明：表单布局
        layout.addLayout(form)  # 说明：加入主布局
        path_layout = QHBoxLayout()  # 说明：文件路径行布局
        self._path_edit = QLineEdit(self._config.get("default_import_path", ""))  # 说明：路径输入框
        self._path_edit.textChanged.connect(self._on_path_changed)  # 说明：路径变更即保存
        path_layout.addWidget(self._path_edit)  # 说明：加入路径输入框
        browse_btn = QPushButton("选择文件")  # 说明：选择按钮
        browse_btn.clicked.connect(self._choose_file)  # 说明：绑定选择事件
        path_layout.addWidget(browse_btn)  # 说明：加入按钮
        form.addRow("导入文件路径", path_layout)  # 说明：添加表单行
        self._duplicate_combo = QComboBox()  # 说明：重复处理下拉框
        self._duplicate_combo.addItems(["保留重复", "覆盖更新", "跳过重复"])  # 说明：可选项（中文显示）
        current_duplicate = _normalize_duplicate_mode_label(self._config.get("duplicate_mode", "保留重复"))  # 说明：读取并规范化默认值
        self._duplicate_combo.setCurrentText(current_duplicate)  # 说明：设置默认
        self._duplicate_combo.currentTextChanged.connect(self._on_duplicate_mode_changed)  # 说明：保存修改
        form.addRow("重复处理", self._duplicate_combo)  # 说明：添加表单行
        self._allow_html = QCheckBox("允许 HTML")  # 说明：HTML 选项
        self._allow_html.setChecked(bool(self._config.get("allow_html", True)))  # 说明：默认勾选
        self._allow_html.stateChanged.connect(self._on_allow_html_changed)  # 说明：保存修改
        form.addRow("导入选项", self._allow_html)  # 说明：添加表单行
        btn_layout = QHBoxLayout()  # 说明：按钮行布局
        self._parse_btn = QPushButton("解析文件")  # 说明：解析按钮
        self._parse_btn.clicked.connect(self._parse_file)  # 说明：绑定解析
        btn_layout.addWidget(self._parse_btn)  # 说明：加入按钮
        self._import_btn = QPushButton("开始导入")  # 说明：导入按钮
        self._import_btn.clicked.connect(self._do_import)  # 说明：绑定导入
        btn_layout.addWidget(self._import_btn)  # 说明：加入按钮
        layout.addLayout(btn_layout)  # 说明：加入主布局
        after_layout = QHBoxLayout()  # 说明：导入后操作布局
        self._open_browser_after_import = QCheckBox("导入后打开浏览器")  # 说明：自动打开浏览器
        self._open_browser_after_import.setChecked(bool(self._config.get("import_auto_open_browser", True)))  # 说明：读取默认值
        self._open_browser_after_import.stateChanged.connect(self._on_open_browser_changed)  # 说明：保存修改
        after_layout.addWidget(self._open_browser_after_import)  # 说明：加入布局
        self._open_duplicate_browser_checkbox = QCheckBox("包含重复笔记")  # 说明：是否包含重复笔记
        self._open_duplicate_browser_checkbox.setChecked(bool(self._config.get("import_auto_open_duplicate_browser", False)))  # 说明：读取默认值
        self._open_duplicate_browser_checkbox.stateChanged.connect(self._on_open_duplicate_browser_changed)  # 说明：保存修改
        after_layout.addWidget(self._open_duplicate_browser_checkbox)  # 说明：加入布局
        layout.addLayout(after_layout)  # 说明：加入主布局
        action_layout = QHBoxLayout()  # 说明：导入后动作按钮布局
        self._open_import_browser_btn = QPushButton("打开导入结果")  # 说明：打开导入结果
        self._open_import_browser_btn.clicked.connect(self._open_import_browser)  # 说明：绑定事件
        action_layout.addWidget(self._open_import_browser_btn)  # 说明：加入布局
        self._open_duplicate_browser_btn = QPushButton("打开重复笔记")  # 说明：打开重复笔记
        self._open_duplicate_browser_btn.clicked.connect(self._open_duplicate_browser)  # 说明：绑定事件
        action_layout.addWidget(self._open_duplicate_browser_btn)  # 说明：加入布局
        self._duplicate_review_btn = QPushButton("处理重复（改策略）")  # 说明：处理重复按钮
        self._duplicate_review_btn.clicked.connect(self._open_duplicate_review)  # 说明：绑定事件
        action_layout.addWidget(self._duplicate_review_btn)  # 说明：加入布局
        self._rollback_btn = QPushButton("回滚最近一次导入")  # 说明：回滚按钮
        self._rollback_btn.clicked.connect(self._rollback_last_session)  # 说明：绑定事件
        action_layout.addWidget(self._rollback_btn)  # 说明：加入布局
        layout.addLayout(action_layout)  # 说明：加入主布局
        self._summary_label = QLabel("尚未解析文件")  # 说明：解析状态
        layout.addWidget(self._summary_label)  # 说明：加入主布局
        self._table = QTableWidget(0, 3)  # 说明：表格初始化
        self._table.setHorizontalHeaderLabels(["牌堆", "题型", "条数"])  # 说明：设置表头
        layout.addWidget(self._table)  # 说明：加入主布局
        self._warning_text = QTextEdit()  # 说明：警告文本框
        self._warning_text.setReadOnly(True)  # 说明：只读
        layout.addWidget(self._warning_text)  # 说明：加入主布局
        self._refresh_import_action_state()  # 说明：初始化按钮状态

    def _choose_file(self) -> None:  # 说明：选择文件
        path, _ = QFileDialog.getOpenFileName(self, "选择导入文件", "", "文本文件 (*.txt *.csv);;所有文件 (*.*)")  # 说明：弹出文件选择框
        if path:  # 说明：用户选择了文件
            self._path_edit.setText(path)  # 说明：写入路径输入框

    def _on_path_changed(self, value: str) -> None:  # 说明：路径变更保存配置
        self._config["default_import_path"] = value  # 说明：更新配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_duplicate_mode_changed(self, value: str) -> None:  # 说明：重复模式变更
        self._config["duplicate_mode"] = value  # 说明：直接保存中文值
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_allow_html_changed(self, _state: int) -> None:  # 说明：HTML 选项变更
        self._config["allow_html"] = self._allow_html.isChecked()  # 说明：更新配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _parse_file(self) -> None:  # 说明：解析文件按钮逻辑
        path = self._path_edit.text().strip()  # 说明：读取路径
        if not path:  # 说明：路径为空
            showInfo("请先选择导入文件")  # 说明：提示用户
            return  # 说明：结束处理
        try:  # 说明：捕获解析异常
            self._parse_result = parse_file(path, self._config)  # 说明：执行解析
            self._render_parse_result(self._parse_result)  # 说明：刷新界面
        except Exception as exc:  # 说明：捕获异常
            showInfo(f"解析失败: {exc}")  # 说明：提示错误

    def _render_parse_result(self, result: ParseResult) -> None:  # 说明：把解析结果渲染到界面
        self._table.setRowCount(0)  # 说明：清空表格
        total_rows = 0  # 说明：统计总行数
        for section in result.sections:  # 说明：遍历分段
            row_index = self._table.rowCount()  # 说明：获取表格当前行
            self._table.insertRow(row_index)  # 说明：新增一行
            self._table.setItem(row_index, 0, QTableWidgetItem(section.deck_name))  # 说明：设置牌堆单元格
            self._table.setItem(row_index, 1, QTableWidgetItem(section.note_type))  # 说明：设置题型单元格
            self._table.setItem(row_index, 2, QTableWidgetItem(str(len(section.rows))))  # 说明：设置数量
            total_rows += len(section.rows)  # 说明：累加条数
        warning_text = "\n".join([f"第 {w.line_no} 行: {w.message}" for w in result.warnings])  # 说明：整理警告文本
        self._warning_text.setPlainText(warning_text)  # 说明：显示警告
        self._summary_label.setText(f"解析完成：分段 {len(result.sections)} 个，记录 {total_rows} 条，警告 {len(result.warnings)} 条")  # 说明：更新状态

    def _do_import(self) -> None:  # 说明：执行导入
        if not self._parse_result:  # 说明：尚未解析
            showInfo("请先解析文件")  # 说明：提示用户
            return  # 说明：结束处理
        try:  # 说明：捕获导入异常
            source_path = self._path_edit.text().strip()  # 说明：读取源文件路径
            result = import_parse_result(mw, self._parse_result, self._config, source_path=source_path)  # 说明：执行导入
            message = (  # 说明：组织结果文本
                f"导入完成\n新增: {result.added}\n更新: {result.updated}\n跳过: {result.skipped}\n错误: {len(result.errors)}"
            )
            showInfo(message)  # 说明：弹窗显示
            if result.errors:  # 说明：若有错误
                showText("\n".join(result.errors))  # 说明：展示错误详情
            self._on_import_done(result.imported_note_ids)  # 说明：通知主对话框
            self._last_import_note_ids = list(result.imported_note_ids)  # 说明：保存导入 ID
            self._last_duplicate_note_ids = list(result.duplicate_note_ids)  # 说明：保存重复 ID
            self._last_session_id = result.session_id  # 说明：保存会话 ID
            self._refresh_import_action_state()  # 说明：刷新按钮状态
            self._maybe_open_browser_after_import(result)  # 说明：按配置打开浏览器
        except Exception as exc:  # 说明：捕获异常
            showInfo(f"导入失败: {exc}")  # 说明：提示错误

    def _maybe_open_browser_after_import(self, result) -> None:  # 说明：按配置打开浏览器
        if not self._open_browser_after_import.isChecked():  # 说明：未启用自动打开
            return  # 说明：直接返回
        note_ids = list(result.imported_note_ids)  # 说明：复制导入 ID 列表
        if self._open_duplicate_browser_checkbox.isChecked():  # 说明：包含重复笔记
            note_ids.extend(result.duplicate_note_ids)  # 说明：合并重复 ID
        note_ids = list(dict.fromkeys(note_ids))  # 说明：去重并保持顺序
        open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器并定位

    def _refresh_import_action_state(self) -> None:  # 说明：刷新导入后按钮状态
        has_import = bool(self._last_import_note_ids)  # 说明：是否有导入结果
        has_duplicate = bool(self._last_duplicate_note_ids)  # 说明：是否有重复结果
        self._open_import_browser_btn.setEnabled(has_import)  # 说明：更新按钮可用状态
        self._open_duplicate_browser_btn.setEnabled(has_duplicate)  # 说明：更新按钮可用状态
        self._duplicate_review_btn.setEnabled(has_duplicate)  # 说明：更新按钮可用状态
        self._rollback_btn.setEnabled(bool(self._last_session_id))  # 说明：回滚按钮状态

    def _on_open_browser_changed(self, _state: int) -> None:  # 说明：导入后打开浏览器设置变更
        self._config["import_auto_open_browser"] = self._open_browser_after_import.isChecked()  # 说明：保存配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_open_duplicate_browser_changed(self, _state: int) -> None:  # 说明：导入后包含重复设置变更
        self._config["import_auto_open_duplicate_browser"] = self._open_duplicate_browser_checkbox.isChecked()  # 说明：保存配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _open_import_browser(self) -> None:  # 说明：打开导入结果浏览器
        if not self._last_import_note_ids:  # 说明：没有导入结果
            showInfo("暂无可查看的导入结果")  # 说明：提示用户
            return  # 说明：结束处理
        note_ids = list(dict.fromkeys(self._last_import_note_ids))  # 说明：去重并保持顺序
        open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器

    def _open_duplicate_browser(self) -> None:  # 说明：打开重复笔记浏览器
        if not self._last_duplicate_note_ids:  # 说明：没有重复笔记
            showInfo("暂无可查看的重复笔记")  # 说明：提示用户
            return  # 说明：结束处理
        note_ids = list(dict.fromkeys(self._last_duplicate_note_ids))  # 说明：去重并保持顺序
        open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器

    def _open_duplicate_review(self) -> None:  # 说明：打开重复处理对话框
        session_id = self._last_session_id or _get_latest_session_id()  # 说明：优先使用最近会话
        if not session_id:  # 说明：没有会话记录
            showInfo("未找到可处理的导入会话")  # 说明：提示用户
            return  # 说明：结束处理
        try:  # 说明：捕获对话框创建异常
            dialog = DuplicateReviewDialog(session_id=session_id, parent=self)  # 说明：创建对话框
            dialog.exec()  # 说明：以模态方式显示
        except Exception as exc:  # 说明：捕获异常
            showInfo(f"打开重复处理失败: {exc}")  # 说明：提示用户

    def _rollback_last_session(self) -> None:  # 说明：回滚最近一次导入
        session = load_latest_session()  # 说明：读取最新会话
        if session is None:  # 说明：无会话记录
            showInfo("没有可回滚的导入会话")  # 说明：提示用户
            return  # 说明：结束处理
        result = rollback_session(mw, session)  # 说明：执行回滚
        message = f"回滚完成\n恢复: {result.restored}\n删除: {result.deleted}\n错误: {len(result.errors)}"  # 说明：组织提示文本
        showInfo(message)  # 说明：提示结果
        if result.errors:  # 说明：存在错误
            showText("\n".join(result.errors))  # 说明：展示错误详情


class DuplicateReviewDialog(QDialog):  # 说明：重复处理对话框
    """用于把“跳过的重复项”改为更新，支持批量选择。"""  # 说明：类说明

    def __init__(self, session_id: str, parent=None) -> None:  # 说明：初始化
        super().__init__(parent)  # 说明：调用父类初始化
        self._session_id = session_id  # 说明：保存会话 ID
        self._session = load_import_session(session_id)  # 说明：读取会话记录
        self._items = [item for item in self._session.items if item.action == "skipped"]  # 说明：筛选跳过项
        self._row_items: List[ImportSessionItem] = []  # 说明：表格行与条目映射
        self._build_ui()  # 说明：构建界面

    def _build_ui(self) -> None:  # 说明：构建界面
        self.setWindowTitle("处理重复项（改策略）")  # 说明：设置窗口标题
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用布局
        self._table = QTableWidget(0, 6)  # 说明：初始化表格
        self._table.setHorizontalHeaderLabels(["选择", "行号", "笔记ID", "字段预览", "牌堆", "题型"])  # 说明：设置表头
        layout.addWidget(self._table)  # 说明：加入主布局
        self._render_items()  # 说明：渲染重复项
        btn_layout = QHBoxLayout()  # 说明：按钮布局
        self._apply_btn = QPushButton("应用更新")  # 说明：应用按钮
        self._apply_btn.clicked.connect(self._apply_updates)  # 说明：绑定事件
        self._apply_btn.setEnabled(bool(self._items))  # 说明：无重复项时禁用按钮
        btn_layout.addWidget(self._apply_btn)  # 说明：加入布局
        self._close_btn = QPushButton("关闭")  # 说明：关闭按钮
        self._close_btn.clicked.connect(self.close)  # 说明：绑定关闭
        btn_layout.addWidget(self._close_btn)  # 说明：加入布局
        layout.addLayout(btn_layout)  # 说明：加入主布局

    def _render_items(self) -> None:  # 说明：渲染重复项
        self._table.setRowCount(0)  # 说明：清空表格
        self._row_items = []  # 说明：重置映射
        for item in self._items:  # 说明：遍历重复项
            row = self._table.rowCount()  # 说明：获取当前行号
            self._table.insertRow(row)  # 说明：插入新行
            checkbox = QCheckBox()  # 说明：复选框
            checkbox.setChecked(False)  # 说明：默认不选中
            self._table.setCellWidget(row, 0, checkbox)  # 说明：放入表格
            self._table.setItem(row, 1, QTableWidgetItem(str(item.line_no)))  # 说明：行号
            self._table.setItem(row, 2, QTableWidgetItem(str(item.note_id)))  # 说明：笔记 ID
            preview = _preview_text(item.fields)  # 说明：字段预览
            self._table.setItem(row, 3, QTableWidgetItem(preview))  # 说明：预览列
            self._table.setItem(row, 4, QTableWidgetItem(item.deck_name))  # 说明：牌堆列
            self._table.setItem(row, 5, QTableWidgetItem(item.note_type))  # 说明：题型列
            self._row_items.append(item)  # 说明：记录映射

    def _apply_updates(self) -> None:  # 说明：把选中的重复项改为更新
        if mw is None or mw.col is None:  # 说明：安全检查，避免 Anki 环境异常
            showInfo("当前无法访问 Anki 集合，请稍后再试")  # 说明：提示用户
            return  # 说明：终止处理
        selected_items = []  # 说明：初始化选中列表
        for row in range(self._table.rowCount()):  # 说明：遍历所有行
            widget = self._table.cellWidget(row, 0)  # 说明：获取复选框
            if isinstance(widget, QCheckBox) and widget.isChecked():  # 说明：判断是否选中
                selected_items.append(self._row_items[row])  # 说明：加入选中项
        if not selected_items:  # 说明：未选择任何项
            showInfo("请先选择需要更新的重复项")  # 说明：提示用户
            return  # 说明：结束处理
        new_session_items: List[ImportSessionItem] = []  # 说明：记录手动更新的会话条目
        updated_count = 0  # 说明：统计更新数量
        for item in selected_items:  # 说明：逐条更新
            note = mw.col.get_note(item.note_id)  # 说明：读取笔记对象
            if note is None:  # 说明：笔记不存在
                continue  # 说明：跳过该条
            old_fields = list(note.fields)  # 说明：保存旧字段
            old_tags = list(note.tags)  # 说明：保存旧标签
            update_note_fields_and_tags(mw, item.note_id, item.fields, item.tags)  # 说明：执行更新
            new_session_items.append(  # 说明：记录会话条目
                ImportSessionItem(
                    line_no=item.line_no,  # 说明：原始行号
                    action="manual_update",  # 说明：动作类型
                    note_id=item.note_id,  # 说明：更新的笔记 ID
                    deck_name=item.deck_name,  # 说明：牌堆名称
                    note_type=item.note_type,  # 说明：题型名称
                    fields=item.fields,  # 说明：导入字段
                    tags=item.tags,  # 说明：导入标签
                    old_fields=old_fields,  # 说明：旧字段快照
                    old_tags=old_tags,  # 说明：旧标签快照
                    duplicate_note_ids=item.duplicate_note_ids,  # 说明：重复列表
                )
            )
            updated_count += 1  # 说明：累计数量
        append_session_items(self._session_id, new_session_items)  # 说明：写入会话记录
        showInfo(f"已更新 {updated_count} 条重复项")  # 说明：提示用户


class TtsProgressDialog(QDialog):  # 说明：TTS 进度对话框
    """非阻塞展示 TTS 进度，支持隐藏与请求停止。"""  # 说明：类说明

    def __init__(self, parent=None) -> None:  # 说明：初始化对话框
        super().__init__(parent)  # 说明：调用父类初始化
        self._cancel_event = Event()  # 说明：取消标记
        self._total = 0  # 说明：记录总数
        self.setWindowTitle("TTS 进度")  # 说明：设置标题
        self.setModal(False)  # 说明：非模态，避免阻塞主界面
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用布局
        self._status_label = QLabel("准备中")  # 说明：状态文本
        layout.addWidget(self._status_label)  # 说明：加入布局
        self._count_label = QLabel("0/0")  # 说明：数量文本
        layout.addWidget(self._count_label)  # 说明：加入布局
        self._progress_bar = QProgressBar()  # 说明：进度条
        self._progress_bar.setRange(0, 1)  # 说明：设置范围避免除零
        self._progress_bar.setValue(0)  # 说明：初始化进度
        layout.addWidget(self._progress_bar)  # 说明：加入布局
        btn_layout = QHBoxLayout()  # 说明：按钮布局
        self._cancel_btn = QPushButton("停止生成")  # 说明：停止按钮
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)  # 说明：绑定停止
        btn_layout.addWidget(self._cancel_btn)  # 说明：加入布局
        self._hide_btn = QPushButton("隐藏")  # 说明：隐藏按钮
        self._hide_btn.clicked.connect(self._on_hide_clicked)  # 说明：绑定隐藏
        btn_layout.addWidget(self._hide_btn)  # 说明：加入布局
        layout.addLayout(btn_layout)  # 说明：加入主布局

    def reset(self, total: int) -> None:  # 说明：重置进度数据
        self._cancel_event.clear()  # 说明：清空中止标记
        self._total = max(0, int(total))  # 说明：记录总数
        self._status_label.setText("准备任务")  # 说明：更新状态
        self._count_label.setText(f"0/{self._total}")  # 说明：更新数量
        self._progress_bar.setRange(0, self._total if self._total > 0 else 1)  # 说明：设置范围
        self._progress_bar.setValue(0)  # 说明：进度归零
        self._cancel_btn.setEnabled(True)  # 说明：允许停止

    def update_progress(self, done: int, total: int, status: str) -> None:  # 说明：更新进度显示
        safe_total = max(0, int(total))  # 说明：安全总数
        if safe_total != self._total:  # 说明：总数变化时更新
            self._total = safe_total  # 说明：记录新总数
            self._progress_bar.setRange(0, self._total if self._total > 0 else 1)  # 说明：更新范围
        safe_done = max(0, int(done))  # 说明：安全已完成数
        if self._total > 0:  # 说明：有总数时限制上界
            safe_done = min(safe_done, self._total)  # 说明：避免超过总数
        self._status_label.setText(status)  # 说明：更新状态
        self._count_label.setText(f"{safe_done}/{self._total}")  # 说明：更新数量
        self._progress_bar.setValue(safe_done)  # 说明：更新进度条

    def mark_finished(self, cancelled: bool) -> None:  # 说明：标记完成或中止
        if cancelled:  # 说明：用户请求中止
            self._status_label.setText("已停止（等待已提交任务结束）")  # 说明：提示用户
        else:  # 说明：正常完成
            self._status_label.setText("生成完成")  # 说明：提示完成
        self._cancel_btn.setEnabled(False)  # 说明：完成后禁用停止

    def is_cancel_requested(self) -> bool:  # 说明：是否请求中止
        return self._cancel_event.is_set()  # 说明：返回标记状态

    def _on_cancel_clicked(self) -> None:  # 说明：点击停止
        self._cancel_event.set()  # 说明：设置中止标记
        self._status_label.setText("已请求停止")  # 说明：提示正在停止
        self._cancel_btn.setEnabled(False)  # 说明：避免重复点击

    def _on_hide_clicked(self) -> None:  # 说明：点击隐藏
        self.hide()  # 说明：隐藏窗口但不停止任务

    def closeEvent(self, event) -> None:  # 说明：重载关闭行为
        event.ignore()  # 说明：阻止销毁
        self.hide()  # 说明：关闭时仅隐藏


class TtsTab(QWidget):  # 说明：TTS 页面
    """TTS 配置与执行界面。"""  # 说明：类说明

    def __init__(self, config: dict, addon_name: str, get_import_ids) -> None:  # 说明：初始化
        super().__init__()  # 说明：调用父类初始化
        self._config = config  # 说明：持有配置
        self._addon_name = addon_name  # 说明：插件名称
        self._get_import_ids = get_import_ids  # 说明：回调读取最近导入 ID
        self._tasks = []  # 说明：缓存任务列表
        self._progress_dialog: Optional[TtsProgressDialog] = None  # 说明：TTS 进度对话框
        self._build_ui()  # 说明：构建 UI
        self.refresh_import_scope()  # 说明：初始化状态

    def _ensure_progress_dialog(self) -> TtsProgressDialog:  # 说明：获取或创建进度对话框
        if self._progress_dialog is None:  # 说明：首次创建
            self._progress_dialog = TtsProgressDialog(self)  # 说明：初始化进度对话框
        return self._progress_dialog  # 说明：返回对话框

    def _build_ui(self) -> None:  # 说明：构建 UI
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用布局
        form = QFormLayout()  # 说明：表单布局
        layout.addLayout(form)  # 说明：加入主布局
        self._provider_combo = QComboBox()  # 说明：服务商下拉框
        self._provider_combo.addItems(["azure"])  # 说明：当前仅支持 Azure
        self._provider_combo.setCurrentText(self._config.get("tts", {}).get("provider", "azure"))  # 说明：设置默认值
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)  # 说明：保存修改
        form.addRow("TTS 服务", self._provider_combo)  # 说明：添加表单行
        self._base_url = QLineEdit(self._config.get("tts", {}).get("azure", {}).get("base_url", ""))  # 说明：Azure base_url
        self._base_url.textChanged.connect(self._on_base_url_changed)  # 说明：保存修改
        form.addRow("Azure Base URL", self._base_url)  # 说明：添加表单行
        self._subscription_key = QLineEdit(self._config.get("tts", {}).get("azure", {}).get("subscription_key", ""))  # 说明：密钥输入框
        self._subscription_key.setEchoMode(QLineEdit.EchoMode.Password)  # 说明：Qt6 使用枚举类型，避免找不到属性
        self._subscription_key.textChanged.connect(self._on_key_changed)  # 说明：保存修改
        form.addRow("Azure Key", self._subscription_key)  # 说明：添加表单行
        filter_layout = QHBoxLayout()  # 说明：筛选布局
        self._locale_combo = QComboBox()  # 说明：语言筛选
        self._locale_combo.currentTextChanged.connect(self._on_filter_changed)  # 说明：筛选变更
        filter_layout.addWidget(self._locale_combo)  # 说明：加入布局
        self._gender_combo = QComboBox()  # 说明：性别筛选
        self._gender_combo.addItems(["", "Female", "Male"])  # 说明：默认值
        self._gender_combo.currentTextChanged.connect(self._on_filter_changed)  # 说明：筛选变更
        filter_layout.addWidget(self._gender_combo)  # 说明：加入布局
        self._voice_type_combo = QComboBox()  # 说明：音色类型筛选
        self._voice_type_combo.addItems(["", "Neural", "Standard", "HD"])  # 说明：默认值
        self._voice_type_combo.currentTextChanged.connect(self._on_filter_changed)  # 说明：筛选变更
        filter_layout.addWidget(self._voice_type_combo)  # 说明：加入布局
        form.addRow("音色筛选", filter_layout)  # 说明：添加表单行
        voice_layout = QHBoxLayout()  # 说明：音色选择布局
        self._voice_combo = QComboBox()  # 说明：音色下拉框
        self._voice_combo.currentTextChanged.connect(self._on_voice_selected)  # 说明：选择变更
        voice_layout.addWidget(self._voice_combo)  # 说明：加入布局
        self._refresh_btn = QPushButton("拉取音色列表")  # 说明：刷新按钮
        self._refresh_btn.clicked.connect(self._refresh_voices)  # 说明：绑定刷新
        voice_layout.addWidget(self._refresh_btn)  # 说明：加入布局
        form.addRow("音色选择", voice_layout)  # 说明：添加表单行
        self._rate_input = QLineEdit()  # 说明：语速倍率输入框
        self._rate_input.setPlaceholderText("例如 1.0 / 0.8 / 1.2")  # 说明：输入提示
        current_rate = str(self._config.get("tts", {}).get("azure", {}).get("defaults", {}).get("rate", "1.0"))  # 说明：读取默认语速
        self._rate_input.setText(current_rate)  # 说明：设置默认值
        self._rate_input.textChanged.connect(self._on_rate_changed)  # 说明：语速变更
        form.addRow("语速倍率", self._rate_input)  # 说明：添加表单行
        self._concurrency_spin = QSpinBox()  # 说明：并发数量选择
        self._concurrency_spin.setRange(1, 16)  # 说明：限制并发范围
        self._concurrency_spin.setValue(int(self._config.get("tts", {}).get("concurrency", 2)))  # 说明：读取默认并发
        self._concurrency_spin.valueChanged.connect(self._on_concurrency_changed)  # 说明：并发变更
        form.addRow("并发数量", self._concurrency_spin)  # 说明：添加表单行
        self._overwrite_audio = QCheckBox("覆盖已生成音频")  # 说明：覆盖开关
        self._overwrite_audio.setChecked(bool(self._config.get("tts", {}).get("overwrite_existing_audio", False)))  # 说明：读取默认值
        self._overwrite_audio.stateChanged.connect(self._on_overwrite_changed)  # 说明：保存修改
        form.addRow("覆盖模式", self._overwrite_audio)  # 说明：添加表单行
        self._ssml_editor = QTextEdit()  # 说明：SSML 编辑框
        self._ssml_editor.setPlainText(self._config.get("tts", {}).get("azure", {}).get("ssml_template", ""))  # 说明：填充模板
        self._ssml_editor.textChanged.connect(self._on_ssml_changed)  # 说明：保存修改
        form.addRow("SSML 模板", self._ssml_editor)  # 说明：添加表单行
        self._reset_ssml_btn = QPushButton("重置 SSML 为默认")  # 说明：重置按钮
        self._reset_ssml_btn.clicked.connect(self._reset_ssml_template)  # 说明：绑定重置
        form.addRow("SSML 操作", self._reset_ssml_btn)  # 说明：添加表单行
        self._use_import_scope = QCheckBox("仅处理最近导入的笔记")  # 说明：范围复选框
        self._use_import_scope.setChecked(True)  # 说明：默认启用
        layout.addWidget(self._use_import_scope)  # 说明：加入主布局
        self._limit_decks = QCheckBox("限制牌组范围")  # 说明：限制牌组复选框
        self._limit_decks.setChecked(bool(self._config.get("tts", {}).get("scan_limit_decks", False)))  # 说明：读取默认值
        self._limit_decks.stateChanged.connect(self._on_limit_decks_changed)  # 说明：保存修改
        layout.addWidget(self._limit_decks)  # 说明：加入主布局
        deck_layout = QHBoxLayout()  # 说明：牌组选择布局
        self._deck_tree = QTreeWidget()  # 说明：树状牌组列表
        self._deck_tree.setHeaderHidden(True)  # 说明：隐藏表头
        self._deck_tree.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)  # 说明：允许多选
        self._deck_tree.itemSelectionChanged.connect(self._on_deck_selection_changed)  # 说明：保存选择
        deck_layout.addWidget(self._deck_tree)  # 说明：加入布局
        self._refresh_decks_btn = QPushButton("刷新牌组")  # 说明：刷新牌组按钮
        self._refresh_decks_btn.clicked.connect(self._load_deck_list)  # 说明：绑定刷新
        deck_layout.addWidget(self._refresh_decks_btn)  # 说明：加入布局
        layout.addLayout(deck_layout)  # 说明：加入主布局
        self._open_browser_after_tts = QCheckBox("TTS 完成后打开浏览器")  # 说明：TTS 后打开浏览器
        self._open_browser_after_tts.setChecked(bool(self._config.get("tts", {}).get("open_browser_after_run", True)))  # 说明：读取默认值
        self._open_browser_after_tts.stateChanged.connect(self._on_open_browser_after_tts_changed)  # 说明：保存修改
        layout.addWidget(self._open_browser_after_tts)  # 说明：加入主布局
        action_layout = QHBoxLayout()  # 说明：按钮布局
        self._scan_btn = QPushButton("扫描待生成音频")  # 说明：扫描按钮
        self._scan_btn.clicked.connect(self._scan_tasks)  # 说明：绑定扫描
        action_layout.addWidget(self._scan_btn)  # 说明：加入布局
        self._run_btn = QPushButton("开始生成")  # 说明：执行按钮
        self._run_btn.clicked.connect(self._run_tts)  # 说明：绑定执行
        action_layout.addWidget(self._run_btn)  # 说明：加入布局
        layout.addLayout(action_layout)  # 说明：加入主布局
        self._tts_status = QLabel("尚未扫描")  # 说明：状态标签
        layout.addWidget(self._tts_status)  # 说明：加入主布局
        self._load_voice_cache()  # 说明：加载缓存音色
        self._load_deck_list()  # 说明：加载牌组列表
        self._apply_deck_limit_state()  # 说明：初始化牌组限制状态

    def refresh_import_scope(self) -> None:  # 说明：刷新导入范围提示
        count = len(self._get_import_ids())  # 说明：读取最近导入数量
        self._use_import_scope.setText(f"仅处理最近导入的笔记（{count} 条）")  # 说明：更新提示

    def _on_provider_changed(self, value: str) -> None:  # 说明：服务商变更
        self._config.setdefault("tts", {})["provider"] = value  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_base_url_changed(self, value: str) -> None:  # 说明：base_url 变更
        self._config.setdefault("tts", {}).setdefault("azure", {})["base_url"] = value  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_key_changed(self, value: str) -> None:  # 说明：Key 变更
        self._config.setdefault("tts", {}).setdefault("azure", {})["subscription_key"] = value  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_ssml_changed(self) -> None:  # 说明：SSML 模板变更
        self._config.setdefault("tts", {}).setdefault("azure", {})["ssml_template"] = self._ssml_editor.toPlainText()  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _reset_ssml_template(self) -> None:  # 说明：重置 SSML 模板为默认值
        defaults = get_default_config()  # 说明：读取默认配置
        template = defaults.get("tts", {}).get("azure", {}).get("ssml_template", "")  # 说明：读取默认模板
        self._ssml_editor.setPlainText(template)  # 说明：写入编辑框
        self._config.setdefault("tts", {}).setdefault("azure", {})["ssml_template"] = template  # 说明：同步到配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _normalize_rate_value(self, raw_text: str) -> str:  # 说明：规范化语速倍率输入
        text = str(raw_text or "").strip()  # 说明：安全获取文本并去空格
        if not text:  # 说明：空输入回退默认
            return "1.0"  # 说明：返回默认倍率
        try:  # 说明：尝试解析为浮点数
            float(text)  # 说明：验证可解析
            return text  # 说明：合法则原样返回
        except Exception:  # 说明：解析失败
            return "1.0"  # 说明：回退默认倍率

    def _on_rate_changed(self, value: str) -> None:  # 说明：语速变更
        normalized = self._normalize_rate_value(value)  # 说明：规范化输入
        if normalized != value:  # 说明：需要纠正输入
            self._rate_input.blockSignals(True)  # 说明：暂时阻断信号
            self._rate_input.setText(normalized)  # 说明：写回规范值
            self._rate_input.blockSignals(False)  # 说明：恢复信号
        defaults = self._config.setdefault("tts", {}).setdefault("azure", {}).setdefault("defaults", {})  # 说明：读取默认变量
        defaults["rate"] = normalized  # 说明：保存语速
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_concurrency_changed(self, value: int) -> None:  # 说明：并发数量变更
        self._config.setdefault("tts", {})["concurrency"] = int(value)  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_overwrite_changed(self, _state: int) -> None:  # 说明：覆盖开关变更
        self._config.setdefault("tts", {})["overwrite_existing_audio"] = self._overwrite_audio.isChecked()  # 说明：保存配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _on_limit_decks_changed(self, _state: int) -> None:  # 说明：限制牌组开关变更
        self._config.setdefault("tts", {})["scan_limit_decks"] = self._limit_decks.isChecked()  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置
        self._apply_deck_limit_state()  # 说明：同步控件状态

    def _on_deck_selection_changed(self) -> None:  # 说明：牌组选择变更
        selected = [  # 说明：读取当前选中牌组
            str(item.data(0, Qt.ItemDataRole.UserRole) or "")  # 说明：使用保存的完整牌组名
            for item in self._deck_tree.selectedItems()  # 说明：遍历选中项
        ]
        selected = [name for name in selected if name]  # 说明：过滤空值
        self._config.setdefault("tts", {})["scan_decks"] = selected  # 说明：保存到配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _load_deck_list(self) -> None:  # 说明：加载牌组列表
        decks = get_all_deck_names(mw)  # 说明：读取所有牌组名称
        selected = set(self._config.get("tts", {}).get("scan_decks", []))  # 说明：读取已选牌组
        self._deck_tree.blockSignals(True)  # 说明：阻断信号避免误触发
        self._deck_tree.clear()  # 说明：清空树
        node_map = {}  # 说明：缓存节点映射，便于复用
        for name in decks:  # 说明：遍历牌组名称
            parts = name.split("::")  # 说明：按层级拆分
            path = ""  # 说明：当前路径
            parent_item = None  # 说明：记录父节点
            for part in parts:  # 说明：逐层构建
                path = part if not path else f"{path}::{part}"  # 说明：拼接完整路径
                if path not in node_map:  # 说明：节点不存在时创建
                    node = QTreeWidgetItem([part])  # 说明：创建节点
                    node.setData(0, Qt.ItemDataRole.UserRole, path)  # 说明：保存完整牌组名
                    if parent_item is None:  # 说明：顶层节点
                        self._deck_tree.addTopLevelItem(node)  # 说明：加入顶层
                    else:  # 说明：子节点
                        parent_item.addChild(node)  # 说明：挂到父节点
                    node_map[path] = node  # 说明：缓存节点
                parent_item = node_map[path]  # 说明：更新父节点
        for name in selected:  # 说明：恢复选中状态
            item = node_map.get(name)  # 说明：查找对应节点
            if item is None:  # 说明：节点不存在
                continue  # 说明：跳过
            item.setSelected(True)  # 说明：设置为选中
            parent = item.parent()  # 说明：获取父节点
            while parent is not None:  # 说明：逐级展开
                parent.setExpanded(True)  # 说明：展开父节点
                parent = parent.parent()  # 说明：继续向上
        self._deck_tree.collapseAll()  # 说明：先整体折叠
        self._deck_tree.expandToDepth(0)  # 说明：展开第一层
        self._deck_tree.blockSignals(False)  # 说明：恢复信号

    def _apply_deck_limit_state(self) -> None:  # 说明：根据开关启用/禁用牌组控件
        enabled = self._limit_decks.isChecked()  # 说明：读取开关状态
        self._deck_tree.setEnabled(enabled)  # 说明：同步树状态
        self._refresh_decks_btn.setEnabled(enabled)  # 说明：同步按钮状态

    def _on_open_browser_after_tts_changed(self, _state: int) -> None:  # 说明：TTS 后打开浏览器开关
        self._config.setdefault("tts", {})["open_browser_after_run"] = self._open_browser_after_tts.isChecked()  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _refresh_voices(self) -> None:  # 说明：拉取音色列表
        try:  # 说明：捕获异常
            voices = azure_list_voices(self._config.get("tts", {}).get("azure", {}))  # 说明：调用 Azure API
            self._config.setdefault("tts", {}).setdefault("azure", {}).setdefault("voice_cache", {})["items"] = voices  # 说明：保存缓存
            save_config(mw, self._addon_name, self._config)  # 说明：持久化配置
            self._populate_filters(voices)  # 说明：刷新筛选项
            self._apply_voice_filter()  # 说明：刷新音色列表
        except Exception as exc:  # 说明：捕获异常
            showInfo(f"拉取音色失败: {exc}")  # 说明：提示错误

    def _load_voice_cache(self) -> None:  # 说明：加载缓存音色
        voices = self._config.get("tts", {}).get("azure", {}).get("voice_cache", {}).get("items", [])  # 说明：读取缓存
        if voices:  # 说明：缓存存在
            self._populate_filters(voices)  # 说明：填充筛选项
            self._apply_voice_filter()  # 说明：应用筛选

    def _populate_filters(self, voices: List[dict]) -> None:  # 说明：填充筛选项
        locales = sorted({voice.get("Locale", "") for voice in voices if voice.get("Locale")})  # 说明：收集 Locale
        current_locale = self._config.get("tts", {}).get("azure", {}).get("filters", {}).get("locale", "")  # 说明：读取默认 locale
        self._locale_combo.blockSignals(True)  # 说明：暂时屏蔽信号
        self._locale_combo.clear()  # 说明：清空
        self._locale_combo.addItem("")  # 说明：添加空选项
        for locale in locales:  # 说明：逐个加入
            self._locale_combo.addItem(locale)  # 说明：加入下拉框
        if current_locale:  # 说明：默认值存在
            self._locale_combo.setCurrentText(current_locale)  # 说明：设置默认
        self._locale_combo.blockSignals(False)  # 说明：恢复信号

    def _apply_voice_filter(self) -> None:  # 说明：应用筛选并刷新音色列表
        voices = self._config.get("tts", {}).get("azure", {}).get("voice_cache", {}).get("items", [])  # 说明：读取缓存
        locale = self._locale_combo.currentText()  # 说明：读取筛选语言
        gender = self._gender_combo.currentText()  # 说明：读取筛选性别
        voice_type = self._voice_type_combo.currentText()  # 说明：读取筛选类型
        filtered = []  # 说明：筛选结果
        for voice in voices:  # 说明：遍历音色
            if locale and voice.get("Locale") != locale:  # 说明：语言不匹配
                continue  # 说明：跳过
            if gender and voice.get("Gender") != gender:  # 说明：性别不匹配
                continue  # 说明：跳过
            if voice_type and voice.get("VoiceType") != voice_type:  # 说明：类型不匹配
                continue  # 说明：跳过
            filtered.append(voice)  # 说明：保留音色
        self._voice_combo.blockSignals(True)  # 说明：屏蔽信号
        self._voice_combo.clear()  # 说明：清空下拉框
        for voice in filtered:  # 说明：填充筛选结果
            display = f"{voice.get('LocaleName', '')} | {voice.get('ShortName', '')} | {voice.get('Gender', '')}"  # 说明：组合显示文本
            self._voice_combo.addItem(display, voice.get("ShortName", ""))  # 说明：存储 ShortName 为数据
        default_voice = self._config.get("tts", {}).get("azure", {}).get("default_voice", "")  # 说明：读取默认音色
        if default_voice:  # 说明：默认值存在
            for index in range(self._voice_combo.count()):  # 说明：遍历选项
                if self._voice_combo.itemData(index) == default_voice:  # 说明：匹配默认音色
                    self._voice_combo.setCurrentIndex(index)  # 说明：选中默认音色
                    break  # 说明：停止遍历
        self._voice_combo.blockSignals(False)  # 说明：恢复信号

    def _on_filter_changed(self, _value: str) -> None:  # 说明：筛选条件变更
        filters = self._config.setdefault("tts", {}).setdefault("azure", {}).setdefault("filters", {})  # 说明：读取配置节点
        filters["locale"] = self._locale_combo.currentText()  # 说明：保存 locale
        filters["gender"] = self._gender_combo.currentText()  # 说明：保存 gender
        filters["voice_type"] = self._voice_type_combo.currentText()  # 说明：保存 voice_type
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置
        self._apply_voice_filter()  # 说明：刷新音色列表

    def _on_voice_selected(self, _value: str) -> None:  # 说明：音色选择变更
        short_name = self._voice_combo.currentData() or ""  # 说明：读取 ShortName
        self._config.setdefault("tts", {}).setdefault("azure", {})["default_voice"] = short_name  # 说明：写入配置
        locale = _find_voice_locale(self._config, short_name)  # 说明：读取音色 Locale
        if locale:  # 说明：存在 Locale 时同步到默认语言
            defaults = self._config.setdefault("tts", {}).setdefault("azure", {}).setdefault("defaults", {})  # 说明：获取默认变量配置
            defaults["lang"] = locale  # 说明：同步 xml:lang
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _get_selected_decks(self) -> List[str]:  # 说明：获取需要过滤的牌组列表
        if not self._limit_decks.isChecked():  # 说明：未开启牌组限制
            return []  # 说明：返回空列表
        return [  # 说明：返回选中牌组
            str(item.data(0, Qt.ItemDataRole.UserRole) or "")  # 说明：读取完整牌组名
            for item in self._deck_tree.selectedItems()  # 说明：遍历选中项
            if str(item.data(0, Qt.ItemDataRole.UserRole) or "")  # 说明：过滤空值
        ]

    def _scan_tasks(self) -> None:  # 说明：扫描需要生成的笔记
        english_tag = self._config.get("tts", {}).get("english_tag", "英文")  # 说明：读取英文标签
        if mw.col is None:  # 说明：集合未加载或已关闭
            showInfo("当前未加载集合，无法扫描 TTS 任务。")  # 说明：提示用户
            return  # 说明：中止扫描流程
        selected_decks = self._get_selected_decks()  # 说明：读取选中的牌组
        if self._limit_decks.isChecked() and not selected_decks and not self._use_import_scope.isChecked():  # 说明：启用牌组但未选择
            showInfo("请先选择需要扫描的牌组")  # 说明：提示用户
            return  # 说明：中止扫描
        note_ids: List[int] = []  # 说明：初始化 ID 列表
        if self._use_import_scope.isChecked():  # 说明：仅使用导入范围
            note_ids = self._get_import_ids()  # 说明：读取最近导入 ID
        else:  # 说明：全库扫描
            query = _build_tts_query(english_tag, selected_decks)  # 说明：构造搜索语句
            note_ids = [int(nid) for nid in mw.col.find_notes(query)]  # 说明：按查询语句查找
        note_ids = _filter_note_ids_by_tag(mw, note_ids, english_tag)  # 说明：按英文标签二次过滤
        note_ids = _filter_note_ids_by_decks(mw, note_ids, selected_decks)  # 说明：按牌组二次过滤
        self._tasks = build_tts_tasks(mw, note_ids, self._config.get("tts", {}))  # 说明：构建任务
        self._tts_status.setText(f"待生成 {len(self._tasks)} 条")  # 说明：更新状态

    def _run_tts(self) -> None:  # 说明：执行 TTS 生成
        if not self._tasks:  # 说明：未扫描任务
            showInfo("请先扫描待生成音频")  # 说明：提示用户
            return  # 说明：结束处理
        tasks = list(self._tasks)  # 说明：复制任务，避免异步修改
        total = len(tasks)  # 说明：记录任务总数
        progress_dialog = self._ensure_progress_dialog()  # 说明：准备进度对话框
        progress_dialog.reset(total)  # 说明：重置进度数据
        progress_dialog.show()  # 说明：显示非阻塞进度对话框
        self._run_btn.setEnabled(False)  # 说明：执行期间禁用按钮
        self._scan_btn.setEnabled(False)  # 说明：执行期间禁用扫描
        self._tts_status.setText(f"后台生成中：0/{total}")  # 说明：更新状态

        def _progress_callback(done: int, total_count: int, status: str) -> None:  # 说明：进度回调
            def _update_ui() -> None:  # 说明：在主线程更新 UI
                self._tts_status.setText(f"{status}：{done}/{total_count}")  # 说明：更新状态文本
                progress_dialog.update_progress(done, total_count, status)  # 说明：更新进度对话框
            mw.taskman.run_on_main(_update_ui)  # 说明：切回主线程执行

        def _op(col):  # 说明：后台执行的操作
            try:  # 说明：捕获后台异常
                return ensure_audio_for_tasks(  # 说明：执行生成
                    col,  # 说明：集合对象
                    tasks,  # 说明：任务列表
                    self._config.get("tts", {}),  # 说明：TTS 配置
                    progress_callback=_progress_callback,  # 说明：进度回调
                    should_cancel=progress_dialog.is_cancel_requested,  # 说明：取消检查
                )
            except Exception as exc:  # 说明：捕获异常
                logger.error(f"TTS 失败: {exc}")  # 说明：记录日志
                result = TtsResult()  # 说明：构造空结果
                result.errors.append(str(exc))  # 说明：写入错误信息
                return result  # 说明：返回错误结果

        def _on_success(result) -> None:  # 说明：后台成功回调
            self._run_btn.setEnabled(True)  # 说明：恢复按钮
            self._scan_btn.setEnabled(True)  # 说明：恢复扫描按钮
            cancelled = progress_dialog.is_cancel_requested()  # 说明：读取是否中止
            self._tts_status.setText("已停止" if cancelled else "生成完成")  # 说明：更新状态
            progress_dialog.mark_finished(cancelled)  # 说明：更新进度对话框状态
            showInfo(  # 说明：提示结果
                (  # 说明：组合提示文本
                    ("TTS 已停止" if cancelled else "TTS 完成")  # 说明：状态前缀
                    + f"：生成 {result.generated} 条，复用 {result.reused} 条，跳过 {result.skipped} 条，错误 {len(result.errors)} 条"  # 说明：拼接统计信息
                )  # 说明：组合结束
            )  # 说明：显示弹窗
            if result.errors:  # 说明：若有错误
                showText("\n".join(result.errors))  # 说明：展示错误详情
            if not cancelled and self._open_browser_after_tts.isChecked():  # 说明：需要打开浏览器且未中止
                note_ids = [task.note_id for task in tasks]  # 说明：收集任务笔记 ID
                note_ids = list(dict.fromkeys(note_ids))  # 说明：去重并保持顺序
                open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器定位

        QueryOp(parent=mw, op=_op, success=_on_success).run_in_background()  # 说明：后台运行（无阻塞进度框）


class SessionTab(QWidget):  # 说明：会话记录页面
    """展示导入会话记录，并支持调整重复策略。"""  # 说明：类说明

    def __init__(self, config: dict, addon_name: str) -> None:  # 说明：初始化
        super().__init__()  # 说明：调用父类初始化
        self._config = config  # 说明：保存配置
        self._addon_name = addon_name  # 说明：保存插件名称
        self._sessions: List[ImportSession] = []  # 说明：会话列表缓存
        self._current_session: Optional[ImportSession] = None  # 说明：当前会话
        self._build_ui()  # 说明：构建 UI
        self._load_sessions()  # 说明：加载会话

    def refresh_sessions(self) -> None:  # 说明：对外刷新会话
        self._load_sessions()  # 说明：重新加载会话

    def _build_ui(self) -> None:  # 说明：搭建界面
        layout = QVBoxLayout()  # 说明：主布局
        self.setLayout(layout)  # 说明：应用布局
        session_actions = QHBoxLayout()  # 说明：会话操作行
        self._refresh_btn = QPushButton("刷新会话")  # 说明：刷新按钮
        self._refresh_btn.clicked.connect(self._load_sessions)  # 说明：绑定刷新
        session_actions.addWidget(self._refresh_btn)  # 说明：加入布局
        self._delete_btn = QPushButton("删除会话记录")  # 说明：删除按钮
        self._delete_btn.clicked.connect(self._delete_session)  # 说明：绑定删除
        session_actions.addWidget(self._delete_btn)  # 说明：加入布局
        self._rollback_btn = QPushButton("回滚该会话")  # 说明：回滚按钮
        self._rollback_btn.clicked.connect(self._rollback_session)  # 说明：绑定回滚
        session_actions.addWidget(self._rollback_btn)  # 说明：加入布局
        self._open_import_btn = QPushButton("打开导入结果")  # 说明：打开导入按钮
        self._open_import_btn.clicked.connect(self._open_import_browser)  # 说明：绑定打开
        session_actions.addWidget(self._open_import_btn)  # 说明：加入布局
        self._open_duplicate_btn = QPushButton("打开重复笔记")  # 说明：打开重复按钮
        self._open_duplicate_btn.clicked.connect(self._open_duplicate_browser)  # 说明：绑定打开
        session_actions.addWidget(self._open_duplicate_btn)  # 说明：加入布局
        self._keep_limit_label = QLabel("保留会话数量(0=不限)")  # 说明：保留数量提示
        session_actions.addWidget(self._keep_limit_label)  # 说明：加入布局
        self._keep_limit_spin = QSpinBox()  # 说明：保留数量设置
        self._keep_limit_spin.setRange(0, 9999)  # 说明：设置范围
        self._keep_limit_spin.setValue(int(self._config.get("import_session_keep_limit", 0)))  # 说明：读取默认值
        self._keep_limit_spin.valueChanged.connect(self._on_keep_limit_changed)  # 说明：绑定变更
        session_actions.addWidget(self._keep_limit_spin)  # 说明：加入布局
        layout.addLayout(session_actions)  # 说明：加入主布局
        self._session_table = QTableWidget(0, 6)  # 说明：会话表格
        self._session_table.setHorizontalHeaderLabels(["会话ID", "源文件", "新增", "更新", "跳过", "重复"])  # 说明：表头
        self._session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 说明：整行选择
        self._session_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 说明：单选
        self._session_table.itemSelectionChanged.connect(self._on_session_selected)  # 说明：绑定选择事件
        layout.addWidget(self._session_table)  # 说明：加入主布局
        strategy_layout = QHBoxLayout()  # 说明：策略操作行
        strategy_layout.addWidget(QLabel("选中行改策略为"))  # 说明：提示标签
        self._strategy_combo = QComboBox()  # 说明：策略下拉框
        self._strategy_combo.addItems(["保留重复", "覆盖更新", "跳过重复"])  # 说明：策略选项
        strategy_layout.addWidget(self._strategy_combo)  # 说明：加入布局
        self._apply_strategy_btn = QPushButton("应用到选中项")  # 说明：应用按钮
        self._apply_strategy_btn.clicked.connect(self._apply_strategy)  # 说明：绑定应用
        strategy_layout.addWidget(self._apply_strategy_btn)  # 说明：加入布局
        layout.addLayout(strategy_layout)  # 说明：加入主布局
        self._item_table = QTableWidget(0, 7)  # 说明：条目表格
        self._item_table.setHorizontalHeaderLabels(["行号", "当前策略", "笔记ID", "牌堆", "题型", "重复ID", "字段预览"])  # 说明：表头
        self._item_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 说明：整行选择
        self._item_table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)  # 说明：允许多选
        layout.addWidget(self._item_table)  # 说明：加入主布局
        self._update_action_state()  # 说明：初始化按钮状态

    def _on_keep_limit_changed(self, value: int) -> None:  # 说明：保留数量变更
        self._config["import_session_keep_limit"] = int(value)  # 说明：写入配置
        save_config(mw, self._addon_name, self._config)  # 说明：持久化配置

    def _load_sessions(self) -> None:  # 说明：加载会话列表
        self._sessions = list_import_sessions()  # 说明：读取会话
        self._session_table.setRowCount(0)  # 说明：清空表格
        for session in self._sessions:  # 说明：逐会话填充
            row = self._session_table.rowCount()  # 说明：获取行号
            self._session_table.insertRow(row)  # 说明：插入新行
            added, updated, skipped, duplicated = self._summarize_session(session)  # 说明：统计数量
            self._session_table.setItem(row, 0, QTableWidgetItem(session.session_id))  # 说明：会话 ID
            self._session_table.setItem(row, 1, QTableWidgetItem(session.source_path))  # 说明：源文件
            self._session_table.setItem(row, 2, QTableWidgetItem(str(added)))  # 说明：新增数量
            self._session_table.setItem(row, 3, QTableWidgetItem(str(updated)))  # 说明：更新数量
            self._session_table.setItem(row, 4, QTableWidgetItem(str(skipped)))  # 说明：跳过数量
            self._session_table.setItem(row, 5, QTableWidgetItem(str(duplicated)))  # 说明：重复数量
        if self._session_table.rowCount() > 0:  # 说明：自动选择第一行
            self._session_table.selectRow(0)  # 说明：选中首行
        else:  # 说明：无会话记录
            self._current_session = None  # 说明：清空当前会话
            self._item_table.setRowCount(0)  # 说明：清空条目表格
        self._update_action_state()  # 说明：更新按钮状态

    def _on_session_selected(self) -> None:  # 说明：会话选择变更
        self._current_session = self._get_selected_session()  # 说明：读取当前会话
        self._render_session_items()  # 说明：渲染条目
        self._update_action_state()  # 说明：更新按钮状态

    def _get_selected_session(self) -> Optional[ImportSession]:  # 说明：获取选中的会话
        selected = self._session_table.selectedItems()  # 说明：获取选中项
        if not selected:  # 说明：未选中
            return None  # 说明：返回空
        row = selected[0].row()  # 说明：读取行号
        if row < 0 or row >= len(self._sessions):  # 说明：越界保护
            return None  # 说明：返回空
        return self._sessions[row]  # 说明：返回对应会话

    def _summarize_session(self, session: ImportSession) -> tuple:  # 说明：统计会话条目
        base_items = [item for item in session.items if item.action in ("added", "updated", "skipped")]  # 说明：仅统计基础项
        added = sum(1 for item in base_items if item.action == "added")  # 说明：统计新增
        updated = sum(1 for item in base_items if item.action == "updated")  # 说明：统计更新
        skipped = sum(1 for item in base_items if item.action == "skipped")  # 说明：统计跳过
        duplicate_ids = set()  # 说明：重复 ID 集合
        for item in base_items:  # 说明：遍历条目
            duplicate_ids.update(item.duplicate_note_ids)  # 说明：合并重复 ID
        return added, updated, skipped, len(duplicate_ids)  # 说明：返回统计值

    def _render_session_items(self) -> None:  # 说明：渲染会话条目
        self._item_table.setRowCount(0)  # 说明：清空表格
        if self._current_session is None:  # 说明：无会话
            return  # 说明：直接返回
        base_items = [item for item in self._current_session.items if item.action in ("added", "updated", "skipped")]  # 说明：基础条目
        base_items.sort(key=lambda item: item.line_no)  # 说明：按行号排序
        for item in base_items:  # 说明：逐条渲染
            row = self._item_table.rowCount()  # 说明：获取当前行
            self._item_table.insertRow(row)  # 说明：插入新行
            strategy_label = self._resolve_strategy_label(self._current_session, item)  # 说明：计算当前策略
            duplicate_ids = ",".join([str(note_id) for note_id in item.duplicate_note_ids])  # 说明：拼接重复 ID
            self._item_table.setItem(row, 0, QTableWidgetItem(str(item.line_no)))  # 说明：行号
            self._item_table.setItem(row, 1, QTableWidgetItem(strategy_label))  # 说明：策略
            self._item_table.setItem(row, 2, QTableWidgetItem(str(item.note_id)))  # 说明：笔记 ID
            self._item_table.setItem(row, 3, QTableWidgetItem(item.deck_name))  # 说明：牌堆
            self._item_table.setItem(row, 4, QTableWidgetItem(item.note_type))  # 说明：题型
            self._item_table.setItem(row, 5, QTableWidgetItem(duplicate_ids))  # 说明：重复 ID
            self._item_table.setItem(row, 6, QTableWidgetItem(_preview_text(item.fields)))  # 说明：字段预览

    def _resolve_strategy_label(self, session: ImportSession, item: ImportSessionItem) -> str:  # 说明：解析策略显示
        override = session.strategy_overrides.get(str(item.line_no), "")  # 说明：读取覆盖策略
        if override:  # 说明：存在覆盖
            return self._mode_to_label(override)  # 说明：返回覆盖策略文本
        return self._action_to_label(item.action)  # 说明：使用原始动作

    def _mode_to_label(self, mode: str) -> str:  # 说明：内部策略转中文
        mapping = {  # 说明：映射表
            "duplicate": "保留重复",  # 说明：保留重复
            "update": "覆盖更新",  # 说明：覆盖更新
            "skip": "跳过重复",  # 说明：跳过重复
        }  # 说明：映射表结束
        return mapping.get(str(mode), "保留重复")  # 说明：未知值回退

    def _action_to_label(self, action: str) -> str:  # 说明：动作转中文
        mapping = {  # 说明：映射表
            "added": "保留重复",  # 说明：新增视为重复
            "updated": "覆盖更新",  # 说明：更新动作
            "skipped": "跳过重复",  # 说明：跳过动作
            "manual_update": "覆盖更新",  # 说明：手动更新
            "manual_duplicate": "保留重复",  # 说明：手动复制
        }  # 说明：映射表结束
        return mapping.get(str(action), "保留重复")  # 说明：默认回退

    def _selected_line_numbers(self) -> List[int]:  # 说明：获取选中的行号
        selected_rows = {item.row() for item in self._item_table.selectedItems()}  # 说明：收集选中行
        line_numbers = []  # 说明：初始化行号列表
        for row in sorted(selected_rows):  # 说明：逐行处理
            item = self._item_table.item(row, 0)  # 说明：读取行号列
            if item is None:  # 说明：空项保护
                continue  # 说明：跳过
            try:  # 说明：捕获转换异常
                line_numbers.append(int(item.text()))  # 说明：转换为数字
            except Exception:  # 说明：转换失败
                continue  # 说明：跳过异常行
        return line_numbers  # 说明：返回行号列表

    def _apply_strategy(self) -> None:  # 说明：应用策略
        if self._current_session is None:  # 说明：未选择会话
            showInfo("请先选择会话记录")  # 说明：提示用户
            return  # 说明：结束处理
        line_numbers = self._selected_line_numbers()  # 说明：读取选中行号
        if not line_numbers:  # 说明：未选择条目
            showInfo("请先选择需要调整的条目")  # 说明：提示用户
            return  # 说明：结束处理
        target_label = self._strategy_combo.currentText()  # 说明：读取目标策略
        target_mode = {"保留重复": "duplicate", "覆盖更新": "update", "跳过重复": "skip"}.get(target_label, "duplicate")  # 说明：转内部值
        result = apply_duplicate_strategy(mw, self._current_session.session_id, line_numbers, target_mode)  # 说明：执行调整
        showInfo(f"调整完成：成功 {result.applied} 条，跳过 {result.skipped} 条，错误 {len(result.errors)} 条")  # 说明：提示结果
        if result.errors:  # 说明：存在错误
            showText("\n".join(result.errors))  # 说明：展示错误详情
        self._current_session = load_import_session(self._current_session.session_id)  # 说明：刷新当前会话
        self._render_session_items()  # 说明：刷新表格

    def _open_import_browser(self) -> None:  # 说明：打开导入结果浏览器
        if self._current_session is None:  # 说明：未选择会话
            showInfo("请先选择会话记录")  # 说明：提示用户
            return  # 说明：结束处理
        note_ids = _collect_import_note_ids(self._current_session)  # 说明：收集导入笔记
        if not note_ids:  # 说明：没有可打开的笔记
            showInfo("当前会话没有导入结果")  # 说明：提示用户
            return  # 说明：结束处理
        open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器

    def _open_duplicate_browser(self) -> None:  # 说明：打开重复笔记浏览器
        if self._current_session is None:  # 说明：未选择会话
            showInfo("请先选择会话记录")  # 说明：提示用户
            return  # 说明：结束处理
        note_ids = _collect_duplicate_note_ids(self._current_session)  # 说明：收集重复笔记
        if not note_ids:  # 说明：没有重复笔记
            showInfo("当前会话没有重复笔记")  # 说明：提示用户
            return  # 说明：结束处理
        open_browser_with_note_ids(mw, note_ids)  # 说明：打开浏览器

    def _rollback_session(self) -> None:  # 说明：回滚选中会话
        if self._current_session is None:  # 说明：未选择会话
            showInfo("请先选择会话记录")  # 说明：提示用户
            return  # 说明：结束处理
        result = rollback_session(mw, self._current_session)  # 说明：执行回滚
        showInfo(f"回滚完成：恢复 {result.restored} 条，删除 {result.deleted} 条，错误 {len(result.errors)} 条")  # 说明：提示结果
        if result.errors:  # 说明：存在错误
            showText("\n".join(result.errors))  # 说明：展示错误详情

    def _delete_session(self) -> None:  # 说明：删除会话记录
        if self._current_session is None:  # 说明：未选择会话
            showInfo("请先选择会话记录")  # 说明：提示用户
            return  # 说明：结束处理
        delete_import_session(self._current_session.session_id)  # 说明：删除会话文件
        self._load_sessions()  # 说明：刷新列表

    def _update_action_state(self) -> None:  # 说明：更新按钮状态
        has_session = self._current_session is not None  # 说明：是否有会话
        self._delete_btn.setEnabled(has_session)  # 说明：删除按钮状态
        self._rollback_btn.setEnabled(has_session)  # 说明：回滚按钮状态
        self._open_import_btn.setEnabled(has_session)  # 说明：打开导入按钮状态
        self._open_duplicate_btn.setEnabled(has_session)  # 说明：打开重复按钮状态
        self._apply_strategy_btn.setEnabled(has_session)  # 说明：应用策略按钮状态


def _filter_note_ids_by_tag(mw, note_ids: List[int], tag_name: str) -> List[int]:  # 说明：按标签过滤笔记 ID
    if not tag_name:  # 说明：未设置标签则不做过滤
        return note_ids  # 说明：直接返回原始列表
    if mw is None or mw.col is None:  # 说明：集合不可用
        return note_ids  # 说明：兜底返回原始列表
    tagged_ids = set(mw.col.find_notes(f'tag:"{tag_name}"'))  # 说明：查询包含指定标签的笔记
    return [note_id for note_id in note_ids if note_id in tagged_ids]  # 说明：保留交集


def _filter_note_ids_by_decks(mw, note_ids: List[int], decks: List[str]) -> List[int]:  # 说明：按牌组过滤笔记 ID
    if not decks:  # 说明：未选择牌组
        return note_ids  # 说明：直接返回原始列表
    if mw is None or mw.col is None:  # 说明：集合不可用
        return note_ids  # 说明：兜底返回原始列表
    deck_query = " or ".join([f'deck:"{_escape_query_text(name)}"' for name in decks])  # 说明：构造牌组查询
    deck_ids = set(mw.col.find_notes(deck_query))  # 说明：查询牌组内笔记
    return [note_id for note_id in note_ids if note_id in deck_ids]  # 说明：保留交集


def _build_tts_query(tag_name: str, decks: List[str]) -> str:  # 说明：构造 TTS 查询语句
    parts = []  # 说明：初始化查询片段
    if tag_name:  # 说明：有标签条件
        parts.append(f'tag:"{_escape_query_text(tag_name)}"')  # 说明：添加标签查询
    if decks:  # 说明：有牌组限制
        deck_part = " or ".join([f'deck:"{_escape_query_text(name)}"' for name in decks])  # 说明：拼接牌组查询
        parts.append(f"({deck_part})")  # 说明：组合为子表达式
    return " ".join(parts) if parts else ""  # 说明：返回最终查询


def _escape_query_text(text: str) -> str:  # 说明：转义查询字符串中的双引号
    return text.replace('"', '\\"')  # 说明：替换为转义形式


def _normalize_duplicate_mode_label(value: str) -> str:  # 说明：将重复模式统一为中文显示
    mapping = {  # 说明：兼容旧英文与中文配置
        "duplicate": "保留重复",  # 说明：旧英文值映射
        "update": "覆盖更新",  # 说明：旧英文值映射
        "skip": "跳过重复",  # 说明：旧英文值映射
        "保留重复": "保留重复",  # 说明：已是中文
        "覆盖更新": "覆盖更新",  # 说明：已是中文
        "跳过重复": "跳过重复",  # 说明：已是中文
    }  # 说明：映射表结束
    return mapping.get(str(value), "保留重复")  # 说明：未知值回退默认


def _select_combo_by_data(combo: QComboBox, value: str) -> None:  # 说明：按 data 选中下拉框
    for index in range(combo.count()):  # 说明：遍历所有选项
        if combo.itemData(index) == value:  # 说明：找到匹配值
            combo.setCurrentIndex(index)  # 说明：设置选中项
            return  # 说明：命中后直接返回


def _find_voice_locale(config: dict, short_name: str) -> str:  # 说明：根据音色 ShortName 查找 Locale
    voices = config.get("tts", {}).get("azure", {}).get("voice_cache", {}).get("items", [])  # 说明：读取缓存音色
    for voice in voices:  # 说明：遍历音色列表
        if voice.get("ShortName") == short_name:  # 说明：匹配 ShortName
            return str(voice.get("Locale", "")).strip()  # 说明：返回 Locale
    return ""  # 说明：未找到则返回空字符串


def _get_latest_session_id() -> str:  # 说明：读取最新会话 ID
    session = load_latest_session()  # 说明：读取最新会话
    return session.session_id if session else ""  # 说明：返回会话 ID


def _preview_text(fields: List[str], limit: int = 60) -> str:  # 说明：生成字段预览文本
    if not fields:  # 说明：无字段时返回空
        return ""  # 说明：直接返回
    text = str(fields[0]).replace("\n", " ").strip()  # 说明：使用第一个字段并清理换行
    return text if len(text) <= limit else text[:limit] + "..."  # 说明：超长则截断


def _collect_import_note_ids(session) -> List[int]:  # 说明：从会话中收集导入笔记 ID
    ids: List[int] = []  # 说明：初始化列表
    for item in session.items:  # 说明：遍历会话条目
        if item.action in ("added", "updated", "manual_update", "manual_duplicate"):  # 说明：只收集写入动作
            ids.append(int(item.note_id))  # 说明：追加 ID
    return list(dict.fromkeys(ids))  # 说明：去重并保持顺序


def _collect_duplicate_note_ids(session) -> List[int]:  # 说明：从会话中收集重复笔记 ID
    ids: List[int] = []  # 说明：初始化列表
    for item in session.items:  # 说明：遍历会话条目
        ids.extend([int(note_id) for note_id in item.duplicate_note_ids])  # 说明：合并重复列表
    return list(dict.fromkeys(ids))  # 说明：去重并保持顺序

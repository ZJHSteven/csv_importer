import csv
import os
from pathlib import Path
from aqt import mw
from aqt.utils import showInfo, qconnect, getFile
from aqt.qt import *
from anki.collection import ImportCsvRequest

class ImportConfigDialog(QDialog):
    """CSV导入配置对话框 - 支持自动选择牌堆和题型"""
    
    def __init__(self, parent, csv_path: str):
        super().__init__(parent)
        self.csv_path = csv_path
        self.col = mw.col
        self.setWindowTitle("CSV导入配置")
        self.setMinimumWidth(500)
        
        self.init_ui()
        self.parse_csv_header()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        
        # 牌堆选择
        deck_layout = QHBoxLayout()
        deck_label = QLabel("选择牌堆:")
        self.deck_combo = QComboBox()
        self.deck_combo.addItems(self.get_deck_names())
        deck_layout.addWidget(deck_label)
        deck_layout.addWidget(self.deck_combo)
        layout.addLayout(deck_layout)
        
        # 题型选择
        notetype_layout = QHBoxLayout()
        notetype_label = QLabel("选择题型:")
        self.notetype_combo = QComboBox()
        self.notetype_combo.addItems(self.get_notetype_names())
        self.notetype_combo.currentTextChanged.connect(self.on_notetype_changed)
        notetype_layout.addWidget(notetype_label)
        notetype_layout.addWidget(self.notetype_combo)
        layout.addLayout(notetype_layout)
        
        # CSV字段映射
        mapping_label = QLabel("CSV列与字段映射:")
        layout.addWidget(mapping_label)
        
        # 映射表格
        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["CSV列", "Anki字段"])
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.mapping_table)
        
        # 按钮
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("导入")
        cancel_btn = QPushButton("取消")
        qconnect(ok_btn.clicked, self.accept)
        qconnect(cancel_btn.clicked, self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_deck_names(self) -> list:
        """获取所有牌堆名称"""
        decks = self.col.decks.all()
        return [deck['name'] for deck in decks]
    
    def get_notetype_names(self) -> list:
        """获取所有题型名称"""
        notetypes = self.col.models.all()
        return [model['name'] for model in notetypes]
    
    def get_notetype_fields(self, notetype_name: str) -> list:
        """获取指定题型的所有字段"""
        model = self.col.models.by_name(notetype_name)
        if model:
            return [field['name'] for field in model['flds']]
        return []
    
    def parse_csv_header(self):
        """解析CSV头部并初始化映射表"""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)  # 读取第一行作为列名
                
                # 根据第一行自动检测题型
                self.detect_note_type_by_header(header)
                self.setup_mapping_table(header)
        except Exception as e:
            showInfo(f"错误：无法读取CSV文件: {str(e)}")
    
    def detect_note_type_by_header(self, csv_header: list):
        """根据CSV列名自动检测题型"""
        # 尝试匹配已有的题型字段
        for notetype_name in self.get_notetype_names():
            fields = self.get_notetype_fields(notetype_name)
            # 如果CSV列数与题型字段数匹配，则选中该题型
            if len(csv_header) == len(fields):
                index = self.notetype_combo.findText(notetype_name)
                if index >= 0:
                    self.notetype_combo.setCurrentIndex(index)
                    return
    
    def on_notetype_changed(self):
        """题型改变时更新字段映射"""
        notetype_name = self.notetype_combo.currentText()
        fields = self.get_notetype_fields(notetype_name)
        
        # 重新填充映射表
        self.mapping_table.setRowCount(len(fields))
        for i, field in enumerate(fields):
            # CSV列号
            csv_col_item = QTableWidgetItem(f"列 {i+1}")
            csv_col_item.setFlags(csv_col_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.mapping_table.setItem(i, 0, csv_col_item)
            
            # Anki字段名
            field_item = QTableWidgetItem(field)
            field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.mapping_table.setItem(i, 1, field_item)
    
    def setup_mapping_table(self, csv_header: list):
        """设置映射表"""
        notetype_name = self.notetype_combo.currentText()
        fields = self.get_notetype_fields(notetype_name)
        
        # 设置行数为CSV列数和Anki字段数的最大值
        row_count = max(len(csv_header), len(fields))
        self.mapping_table.setRowCount(row_count)
        
        # 填充CSV列
        for i, col_name in enumerate(csv_header):
            col_item = QTableWidgetItem(col_name)
            col_item.setFlags(col_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.mapping_table.setItem(i, 0, col_item)
        
        # 填充Anki字段
        for i, field in enumerate(fields):
            field_item = QTableWidgetItem(field)
            field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.mapping_table.setItem(i, 1, field_item)
    
    def get_selected_deck(self) -> str:
        """获取选中的牌堆"""
        return self.deck_combo.currentText()
    
    def get_selected_notetype(self) -> str:
        """获取选中的题型"""
        return self.notetype_combo.currentText()


def import_csv_file():
    """打开文件选择器并导入CSV"""
    csv_file = getFile(
        mw,
        "选择CSV文件",
        None,
        "CSV files (*.csv)"
    )
    
    if not csv_file:
        return
    
    # 打开配置对话框
    dialog = ImportConfigDialog(mw, csv_file)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    
    # 执行导入
    try:
        perform_import(
            csv_file,
            dialog.get_selected_deck(),
            dialog.get_selected_notetype()
        )
    except Exception as e:
        showInfo(f"导入失败: {str(e)}")


def perform_import(csv_path: str, deck_name: str, notetype_name: str):
    """执行CSV导入"""
    col = mw.col
    
    try:
        # 获取牌堆ID
        deck = col.decks.by_name(deck_name)
        if not deck:
            showInfo(f"错误：未找到牌堆 '{deck_name}'")
            return
        
        # 获取题型
        model = col.models.by_name(notetype_name)
        if not model:
            showInfo(f"错误：未找到题型 '{notetype_name}'")
            return
        
        # 获取CSV元数据并执行导入
        metadata = col.get_csv_metadata(path=csv_path, delimiter=None)
        
        # 设置牌堆和题型
        metadata.deck_id = deck['id']
        metadata.notetype_id = model['id']
        
        # 创建导入请求
        request = ImportCsvRequest(path=csv_path, metadata=metadata)
        response = col.import_csv(request)
        
        # 显示导入结果
        log = response.log
        msg = f"""导入完成！
        
找到卡片数: {log.found_notes}
新增卡片: {len(log.new)}
更新卡片: {len(log.updated)}
"""
        showInfo(msg)
        
    except Exception as e:
        showInfo(f"导入错误: {str(e)}")


# 添加菜单项
def setup_menu():
    """设置菜单"""
    action = QAction("导入CSV文件", mw)
    qconnect(action.triggered, import_csv_file)
    mw.form.menuTools.addAction(action)


# 初始化插件
setup_menu()
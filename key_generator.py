import sys
import random
import json
import requests  # 必须导入
import http.client
import urllib.parse
from datetime import datetime, timedelta

# Crypto 库依赖
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import hashlib
import base64
import secrets

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QHeaderView, QFrame, QGraphicsDropShadowEffect, QAbstractItemView,
                             QDialog, QFormLayout, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QFont, QBrush, QPen

# ================= 配置 =================
# 你的 FastAPI 服务器地址 (api.py 运行的地方)
LICENSE_SERVER_URL = "http://127.0.0.1:9000"

THEME_PRIMARY = QColor(0, 255, 65)
THEME_SECONDARY = QColor(0, 243, 255)
THEME_ALERT = QColor(255, 0, 85)
FONT_FAMILY = "Consolas"


# ... (这里省略了 CardKeyEncryption 类，和你之前的保持一致即可) ...
# 为了代码完整，简写一下加密类
class CardKeyEncryption:
    def __init__(self):
        self.seed = "yunmangongfang_2024_secret"
        self.secret_key = hashlib.sha256(self.seed.encode()).digest()

    def encrypt_api_key(self, real_api_key):
        try:
            iv = secrets.token_bytes(16)
            cipher = AES.new(self.secret_key, AES.MODE_CBC, iv)
            encrypted = cipher.encrypt(pad(real_api_key.encode('utf-8'), AES.block_size))
            return f"ymgfjc-{base64.urlsafe_b64encode(iv + encrypted).decode('utf-8')}"
        except:
            return None


card_encryptor = CardKeyEncryption()


# =========================================================
# 🔥🔥🔥 这就是你在找的 AddCardDialog 🔥🔥🔥
# =========================================================
class AddCardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ADD CARD")
        self.setFixedSize(600, 600)
        self.setStyleSheet("background-color: #050505; color: #00ff65;")
        self.setup_ui()

    def _input_style(self, readonly=False, color_hex="#00ff65"):
        return f"border: 1px solid #333; padding: 5px; color: {color_hex}; background: {'#111' if not readonly else '#000'};"

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 1. 令牌ID
        self.token_id_input = QLineEdit()
        self.token_id_input.setStyleSheet(self._input_style())
        form.addRow("TOKEN ID:", self.token_id_input)

        # 2. 原始 Key
        self.original_card_input = QLineEdit()
        self.original_card_input.setPlaceholderText("sk-...")
        self.original_card_input.setStyleSheet(self._input_style())
        self.original_card_input.textChanged.connect(self.encrypt_api_key)
        form.addRow("RAW KEY:", self.original_card_input)

        # 3. 加密后 Key
        self.encrypted_card_input = QLineEdit()
        self.encrypted_card_input.setReadOnly(True)
        self.encrypted_card_input.setStyleSheet(self._input_style(readonly=True))
        form.addRow("ENCRYPTED:", self.encrypted_card_input)

        # 🔥🔥🔥 4. 最大设备数 (新增逻辑) 🔥🔥🔥
        self.max_devices_input = QLineEdit("1")
        self.max_devices_input.setStyleSheet(self._input_style(color_hex="#ffff00"))  # 黄色高亮
        form.addRow("MAX DEVICES:", self.max_devices_input)

        # 5. 金额
        self.amount_input = QLineEdit("399")
        self.amount_input.setStyleSheet(self._input_style(color_hex="#ff0055"))
        form.addRow("AMOUNT:", self.amount_input)

        layout.addLayout(form)

        # 按钮
        self.btn_ok = QPushButton("CONFIRM && UPLOAD")
        self.btn_ok.setStyleSheet("background: #00ff65; color: #000; padding: 10px; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        layout.addWidget(self.btn_ok)

    def encrypt_api_key(self):
        key = self.original_card_input.text().strip()
        if key:
            enc = card_encryptor.encrypt_api_key(key)
            self.encrypted_card_input.setText(enc)

    def get_card_data(self):
        return {
            'token_id': self.token_id_input.text().strip(),
            'original_key': self.original_card_input.text().strip(),
            'encrypted_key': self.encrypted_card_input.text().strip(),
            'amount': self.amount_input.text().strip(),
            # 🔥 获取设备数
            'max_devices': self.max_devices_input.text().strip()
        }


# ================= 主窗口 (简略版，只展示核心逻辑) =================
class CyberCardSystem(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KEY GENERATOR")
        self.resize(800, 600)

        # 简单弄个按钮触发弹窗
        btn = QPushButton("CREATE NEW KEY", self)
        btn.setGeometry(50, 50, 200, 50)
        btn.clicked.connect(self.show_add_card_dialog)

        # 表格初始化(略)...
        self.table = QTableWidget(self)
        self.table.setGeometry(50, 120, 700, 400)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Encrypted Key", "Raw Key", "Max Devices"])

    # 🔥🔥🔥 核心：点击确认后，发给服务器入库 🔥🔥🔥
    def show_add_card_dialog(self):
        dialog = AddCardDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            card_data = dialog.get_card_data()

            if not card_data['original_key']: return

            # 1. 准备数据
            try:
                max_d = int(card_data['max_devices'])
            except:
                max_d = 1

            payload = {
                "card_key": card_data['encrypted_key'],  # 存入 ymgfjc-...
                "raw_key": card_data['original_key'],  # 存入 sk-...
                "max_devices": max_d,  # 限制数量
                "amount": float(card_data['amount'] or 0)
            }

            # 2. 发送给 api.py
            try:
                url = f"{LICENSE_SERVER_URL}/admin/add_card"
                print(f"Post to: {url}")
                resp = requests.post(url, json=payload, timeout=5)
                res_json = resp.json()

                if resp.status_code == 200 and res_json.get('code') == 200:
                    QMessageBox.information(self, "SUCCESS", "入库成功！")
                    self.add_row_to_table(card_data, max_d)
                else:
                    QMessageBox.warning(self, "FAIL", f"入库失败: {res_json.get('msg')}")
            except Exception as e:
                QMessageBox.critical(self, "ERROR", f"连接服务器失败: {e}")

    def add_row_to_table(self, data, max_d):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(data['token_id']))
        self.table.setItem(row, 1, QTableWidgetItem(data['encrypted_key']))
        self.table.setItem(row, 2, QTableWidgetItem(data['original_key']))
        self.table.setItem(row, 3, QTableWidgetItem(str(max_d)))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CyberCardSystem()
    win.show()
    sys.exit(app.exec_())
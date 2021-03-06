# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QFile
from PyQt5.QtGui import QFont, QFontDatabase


class ParsecApp(QApplication):
    connected_devices = []

    def __init__(self):
        super().__init__(["-stylesheet"])
        self.setOrganizationName("Scille")
        self.setOrganizationDomain("parsec.cloud")
        self.setApplicationName("Parsec")

    def load_stylesheet(self, res=":/styles/styles/main.css"):
        rc = QFile(res)
        rc.open(QFile.ReadOnly)
        content = rc.readAll().data()
        self.setStyleSheet(str(content, "utf-8"))

    def load_font(self, font="Montserrat"):
        QFontDatabase.addApplicationFont(":/fonts/fonts/Montserrat.ttf")
        QFontDatabase.addApplicationFont(":/fonts/fonts/Roboto-Regular.ttf")
        f = QFont(font)
        self.setFont(f)

    @classmethod
    def add_connected_device(cls, org_id, device_id):
        if not cls.is_device_connected(org_id, device_id):
            cls.connected_devices.append(f"{org_id}:{device_id}")

    @classmethod
    def remove_connected_device(cls, org_id, device_id):
        cls.connected_devices.remove(f"{org_id}:{device_id}")

    @classmethod
    def is_device_connected(cls, org_id, device_id):
        return f"{org_id}:{device_id}" in cls.connected_devices

    @classmethod
    def has_active_modal(cls):
        if cls.activeModalWidget():
            return True
        mw = cls.get_main_window()
        if not mw:
            return False
        for win in mw.children():
            if win.objectName() == "GreyedDialog":
                return True
        return False

    @classmethod
    def get_main_window(cls):
        for win in cls.topLevelWidgets():
            if win.objectName() == "MainWindow":
                return win
        return None

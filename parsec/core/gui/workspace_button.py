# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect, QMenu
from PyQt5.QtGui import QColor, QCursor

from parsec.core.fs import WorkspaceFS, WorkspaceFSTimestamped
from parsec.core.types import EntryID

from parsec.core.gui.lang import translate as _, format_datetime
from parsec.core.gui.custom_dialogs import show_info

from parsec.core.gui.ui.workspace_button import Ui_WorkspaceButton
from parsec.core.gui.ui.empty_workspace_widget import Ui_EmptyWorkspaceWidget


# Only used because we can't hide widgets in QtDesigner and adding the empty workspace
# button changes the minimum size we can set for the workspace button.
class EmptyWorkspaceWidget(QWidget, Ui_EmptyWorkspaceWidget):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.label_icon.apply_style()


class WorkspaceButton(QWidget, Ui_WorkspaceButton):
    clicked = pyqtSignal(WorkspaceFS)
    share_clicked = pyqtSignal(WorkspaceFS)
    reencrypt_clicked = pyqtSignal(EntryID, bool, bool)
    delete_clicked = pyqtSignal(WorkspaceFS)
    rename_clicked = pyqtSignal(QWidget)
    remount_ts_clicked = pyqtSignal(WorkspaceFS)
    open_clicked = pyqtSignal(WorkspaceFS)

    def __init__(
        self,
        workspace_name,
        workspace_fs,
        is_shared,
        is_creator,
        files=None,
        reencryption_needs=None,
        timestamped=False,
    ):
        super().__init__()
        self.setupUi(self)
        self.is_creator = is_creator
        self.workspace_name = workspace_name
        self.workspace_fs = workspace_fs
        self.reencryption_needs = reencryption_needs
        self.timestamped = timestamped
        self.is_shared = is_shared
        self.reencrypting = None
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.widget_empty.layout().addWidget(EmptyWorkspaceWidget())
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        files = files or []

        if not len(files):
            self.widget_empty.show()
            self.widget_files.hide()
        else:
            for i, f in enumerate(files, 1):
                if i > 4:
                    break
                label = getattr(self, "file{}_name".format(i))
                label.setText(f)
            self.widget_files.show()
            self.widget_empty.hide()

        if self.timestamped:
            self.widget_title.setStyleSheet(
                "background-color: #E3E3E3; border-top-left-radius: 8px; border-top-right-radius: 8px;"
            )
            self.widget_actions.setStyleSheet(
                "background-color: #E3E3E3; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"
            )
            self.setStyleSheet("background-color: #E3E3E3; border-radius: 8px;")
            self.button_reencrypt.hide()
            self.button_remount_ts.hide()
            self.button_share.hide()
            self.button_rename.hide()
            self.label_shared.hide()
            self.label_owner.hide()
        else:
            self.widget_title.setStyleSheet(
                "background-color: #FFFFFF; border-top-left-radius: 8px; border-top-right-radius: 8px;"
            )
            self.widget_actions.setStyleSheet(
                "background-color: #FFFFFF; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"
            )
            self.setStyleSheet("background-color: #FFFFFF; border-radius: 8px;")
            self.button_delete.hide()

        effect = QGraphicsDropShadowEffect(self)
        effect.setColor(QColor(0x99, 0x99, 0x99))
        effect.setBlurRadius(10)
        effect.setXOffset(2)
        effect.setYOffset(2)
        self.setGraphicsEffect(effect)
        if not self.is_creator:
            self.button_reencrypt.hide()
        self.label_reencrypting.hide()
        self.button_share.clicked.connect(self.button_share_clicked)
        self.button_share.apply_style()
        self.button_reencrypt.clicked.connect(self.button_reencrypt_clicked)
        self.button_reencrypt.apply_style()
        self.button_delete.clicked.connect(self.button_delete_clicked)
        self.button_delete.apply_style()
        self.button_rename.clicked.connect(self.button_rename_clicked)
        self.button_rename.apply_style()
        self.button_remount_ts.clicked.connect(self.button_remount_ts_clicked)
        self.button_remount_ts.apply_style()
        self.button_open.clicked.connect(self.button_open_workspace_clicked)
        self.button_open.apply_style()
        self.label_owner.apply_style()
        self.label_shared.apply_style()
        self.label_reencrypting.apply_style()
        if not self.is_creator:
            self.label_owner.hide()
        if not self.is_shared:
            self.label_shared.hide()
        self.reload_workspace_name(self.workspace_name)

    def show_context_menu(self, pos):
        global_pos = self.mapToGlobal(pos)
        menu = QMenu(self)

        action = menu.addAction(_("ACTION_WORKSPACE_OPEN_IN_FILE_EXPLORER"))
        action.triggered.connect(self.button_open_workspace_clicked)
        if not self.timestamped:
            action = menu.addAction(_("ACTION_WORKSPACE_RENAME"))
            action.triggered.connect(self.button_rename_clicked)
            action = menu.addAction(_("ACTION_WORKSPACE_SHARE"))
            action.triggered.connect(self.button_share_clicked)
            action = menu.addAction(_("ACTION_WORKSPACE_SEE_IN_THE_PAST"))
            action.triggered.connect(self.button_remount_ts_clicked)
            if self.reencryption_needs and self.reencryption_needs.need_reencryption:
                action = menu.addAction(_("ACTION_WORKSPACE_REENCRYPT"))
                action.triggered.connect(self.button_reencrypt_clicked)
        else:
            action = menu.addAction(_("ACTION_WORKSPACE_DELETE"))
            action.triggered.connect(self.button_delete_clicked)

        menu.exec_(global_pos)

    def button_open_workspace_clicked(self):
        self.open_clicked.emit(self.workspace_fs)

    def button_share_clicked(self):
        self.share_clicked.emit(self.workspace_fs)

    def button_reencrypt_clicked(self):
        if self.reencryption_needs:
            if not self.is_creator:
                show_info(self.parent(), message=_("TEXT_WORKSPACE_ONLY_OWNER_CAN_REENCRYPT"))
                return
            self.reencrypt_clicked.emit(
                self.workspace_fs.workspace_id,
                bool(self.reencryption_needs.user_revoked),
                bool(self.reencryption_needs.role_revoked),
            )

    def button_delete_clicked(self):
        self.delete_clicked.emit(self.workspace_fs)

    def button_rename_clicked(self):
        self.rename_clicked.emit(self)

    def button_remount_ts_clicked(self):
        self.remount_ts_clicked.emit(self.workspace_fs)

    @property
    def name(self):
        return self.workspace_name

    @property
    def reencryption_needs(self):
        return self._reencryption_needs

    @reencryption_needs.setter
    def reencryption_needs(self, val):
        self._reencryption_needs = val
        if not self.is_creator:
            return
        if self.reencryption_needs and self.reencryption_needs.need_reencryption:
            self.button_reencrypt.show()
        else:
            self.button_reencrypt.hide()

    @property
    def reencrypting(self):
        return self._reencrypting

    @reencrypting.setter
    def reencrypting(self, val):
        def _start_reencrypting():
            self.button_reencrypt.hide()
            self.label_reencrypting.show()

        def _stop_reencrypting():
            self.button_reencrypt.hide()
            self.label_reencrypting.hide()

        self._reencrypting = val
        if not self.is_creator:
            return
        if self._reencrypting:
            _start_reencrypting()
            total, done = self._reencrypting
            self.label_reencrypting.setToolTip(
                "{} {}%".format(
                    _("TEXT_WORKSPACE_CURRENTLY_REENCRYPTING_TOOLTIP"), int(done / total * 100)
                )
            )
        else:
            _stop_reencrypting()

    def reload_workspace_name(self, workspace_name):
        self.workspace_name = workspace_name
        display = workspace_name
        if self.is_shared and self.is_creator:
            display += " ({})".format(_("TEXT_WORKSPACE_IS_SHARED"))
        if isinstance(self.workspace_fs, WorkspaceFSTimestamped):
            display += "-" + _("TEXT_WORKSPACE_IS_TIMESTAMPED_date").format(
                date=format_datetime(self.workspace_fs.timestamp)
            )
        self.label_title.setToolTip(display)
        if len(display) > 20:
            display = display[:20] + "..."
        self.label_title.setText(display)

    def mousePressEvent(self, event):
        if event.button() & Qt.LeftButton:
            self.clicked.emit(self.workspace_fs)

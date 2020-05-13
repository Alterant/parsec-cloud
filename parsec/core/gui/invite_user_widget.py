# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from uuid import UUID

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QWidget, QApplication, QMenu

from structlog import get_logger

from parsec.api.protocol import InvitationType, InvitationStatus, InvitationDeletedReason
from parsec.core.types import BackendInvitationAddr

from parsec.core.backend_connection import backend_authenticated_cmds_factory
from parsec.core.gui import desktop
from parsec.core.gui.greet_user_widget import GreetUserWidget
from parsec.core.gui.custom_dialogs import show_error, GreyedDialog, ask_question
from parsec.core.gui.lang import translate as _
from parsec.core.gui.trio_thread import JobResultError, ThreadSafeQtSignal, QtToTrioJob
from parsec.core.gui.ui.invite_user_widget import Ui_InviteUserWidget
from parsec.core.gui.ui.user_invitation_widget import Ui_UserInvitationWidget


logger = get_logger()


async def _do_invite_user(device, config, email):
    async with backend_authenticated_cmds_factory(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
        keepalive=config.backend_connection_keepalive,
    ) as cmds:
        rep = await cmds.invite_new(type=InvitationType.USER, claimer_email=email, send_email=False)
        if rep["status"] != "ok":
            raise JobResultError(rep["status"])
        action_addr = BackendInvitationAddr.build(
            backend_addr=device.organization_addr,
            organization_id=device.organization_id,
            invitation_type=InvitationType.USER,
            token=rep["token"],
        )
        return action_addr


async def _do_list_invitations(device, config):
    async with backend_authenticated_cmds_factory(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
        keepalive=config.backend_connection_keepalive,
    ) as cmds:
        rep = await cmds.invite_list()
        if rep["status"] != "ok":
            raise JobResultError(rep["status"])
        return [inv for inv in rep["invitations"] if inv["type"] == InvitationType.USER]


async def _do_cancel_invitation(device, config, token):
    async with backend_authenticated_cmds_factory(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
        keepalive=config.backend_connection_keepalive,
    ) as cmds:
        rep = await cmds.invite_delete(token=token, reason=InvitationDeletedReason.CANCELLED)
        if rep["status"] != "ok":
            raise JobResultError(rep["status"])


class UserInvitationWidget(QWidget, Ui_UserInvitationWidget):
    cancel_invitation_clicked = pyqtSignal(UUID)
    greet_clicked = pyqtSignal(UUID)

    def __init__(self, email, invite_addr, status):
        super().__init__()
        self.setupUi(self)
        STATUS_TEXTS = {
            InvitationStatus.READY: (
                _("TEXT_INVITATION_STATUS_READY"),
                _("TEXT_INVITATION_STATUS_READY_TOOLTIP"),
            ),
            InvitationStatus.IDLE: (
                _("TEXT_INVITATION_STATUS_IDLE"),
                _("TEXT_INVITATION_STATUS_IDLE_TOOLTIP"),
            ),
            InvitationStatus.DELETED: (
                _("TEXT_INVITATION_STATUS_CANCELLED"),
                _("TEXT_INVITATION_STATUS_CANCELLED_TOOLTIP"),
            ),
        }
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.email = email
        self.invite_addr = invite_addr

        self.label_email.setToolTip(self.email)
        self.label_invite_addr.setToolTip(str(self.invite_addr))
        self.label_status.setText(STATUS_TEXTS[status][0])
        self.label_status.setToolTip(STATUS_TEXTS[status][1])
        if status == InvitationStatus.DELETED:
            self.button_cancel.hide()
            self.button_greet.hide()
        self.button_cancel.clicked.connect(self._on_cancel_invitation_clicked)
        self.button_cancel.apply_style()
        self.button_greet.clicked.connect(self._on_greet_clicked)

    def show_context_menu(self, pos):
        global_pos = self.mapToGlobal(pos)
        menu = QMenu(self)

        action = menu.addAction(_("ACTION_USER_INVITE_COPY_ADDR"))
        action.triggered.connect(self.copy_addr)
        action = menu.addAction(_("ACTION_USER_INVITE_COPY_EMAIL"))
        action.triggered.connect(self.copy_email)
        menu.exec_(global_pos)

    def copy_addr(self):
        desktop.copy_to_clipboard(str(self.invite_addr))

    def copy_email(self):
        desktop.copy_to_clipboard(self.email)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        font = QApplication.font()
        metrics = QFontMetrics(font)

        email = self.email
        invite_addr = str(self.invite_addr)

        if metrics.horizontalAdvance(email) > self.label_email.width():
            while metrics.horizontalAdvance(email + "...") > self.label_email.width():
                email = email[: len(email) - 1]
            email += "..."
        self.label_email.setText(email)

        if metrics.horizontalAdvance(invite_addr) > self.label_invite_addr.width():
            while metrics.horizontalAdvance(invite_addr + "...") > self.label_invite_addr.width():
                invite_addr = invite_addr[: len(invite_addr) - 1]
            invite_addr += "..."
        self.label_invite_addr.setText(invite_addr)

    def _on_cancel_invitation_clicked(self):
        self.cancel_invitation_clicked.emit(self.invite_addr.token)

    def _on_greet_clicked(self):
        self.greet_clicked.emit(self.invite_addr.token)


class InviteUserWidget(QWidget, Ui_InviteUserWidget):
    invite_user_success = pyqtSignal(QtToTrioJob)
    invite_user_error = pyqtSignal(QtToTrioJob)
    list_invitations_success = pyqtSignal(QtToTrioJob)
    list_invitations_error = pyqtSignal(QtToTrioJob)
    cancel_invitation_success = pyqtSignal(QtToTrioJob)
    cancel_invitation_error = pyqtSignal(QtToTrioJob)

    def __init__(self, core, jobs_ctx):
        super().__init__()
        self.setupUi(self)
        self.core = core
        self.dialog = None
        self.jobs_ctx = jobs_ctx
        self.list_invitations_success.connect(self._on_list_invitations_success)
        self.list_invitations_error.connect(self._on_list_invitations_error)
        self.invite_user_success.connect(self._on_invite_user_success)
        self.invite_user_error.connect(self._on_invite_user_error)
        self.cancel_invitation_success.connect(self._on_cancel_invitation_success)
        self.cancel_invitation_error.connect(self._on_cancel_invitation_error)
        self.button_invite_user.clicked.connect(self.invite_user)
        self.line_edit_user_email.textChanged.connect(self.check_infos)
        self.list_invitations()

    def list_invitations(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_invitations_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_invitations_error", QtToTrioJob),
            _do_list_invitations,
            device=self.core.device,
            config=self.core.config,
        )

    def invite_user(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "invite_user_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "invite_user_error", QtToTrioJob),
            _do_invite_user,
            device=self.core.device,
            config=self.core.config,
            email=self.line_edit_user_email.text(),
        )

    def cancel_invitation(self, token):
        r = ask_question(
            self,
            _("TEXT_USER_INVITE_CANCEL_INVITE_QUESTION_TITLE"),
            _("TEXT_USER_INVITE_CANCEL_INVITE_QUESTION_CONTENT"),
            [_("TEXT_USER_INVITE_CANCEL_INVITE_ACCEPT"), _("ACTION_NO")],
        )
        if r != _("TEXT_USER_INVITE_CANCEL_INVITE_ACCEPT"):
            return
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "cancel_invitation_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "cancel_invitation_error", QtToTrioJob),
            _do_cancel_invitation,
            device=self.core.device,
            config=self.core.config,
            token=token,
        )

    def greet(self, token):
        GreetUserWidget.exec_modal(core=self.core, jobs_ctx=self.jobs_ctx, token=token, parent=self)
        self.list_invitations()

    def _on_cancel_invitation_success(self, job):
        self.list_invitations()

    def _on_cancel_invitation_error(self, job):
        assert job.is_finished()
        assert job.status != "ok"
        show_error(self, _("TEXT_INVITE_USER_CANCEL_ERROR"), exception=job.exc)

    def _on_invite_user_success(self, job):
        self.list_invitations()

    def _on_invite_user_error(self, job):
        assert job.is_finished()
        assert job.status != "ok"
        show_error(self, _("TEXT_INVITE_USER_INVITE_ERROR"), exception=job.exc)

    def _on_list_invitations_success(self, job):
        self._clear_invitations_list()
        if job.ret:
            self.label_no_invitations.hide()
            self.widget_invitations.show()
            for invitation in job.ret:
                addr = BackendInvitationAddr.build(
                    backend_addr=self.core.device.organization_addr,
                    organization_id=self.core.device.organization_id,
                    invitation_type=InvitationType.USER,
                    token=invitation["token"],
                )
                w = UserInvitationWidget(invitation["claimer_email"], addr, invitation["status"])
                w.cancel_invitation_clicked.connect(self.cancel_invitation)
                w.greet_clicked.connect(self.greet)
                self.layout_invitations.insertWidget(0, w)
        else:
            self.label_no_invitations.show()
            self.widget_invitations.hide()

    def _on_list_invitations_error(self, job):
        pass

    def _clear_invitations_list(self):
        while self.layout_invitations.count() > 1:
            item = self.layout_invitations.takeAt(0)
            if item:
                w = item.widget()
                self.layout_invitations.removeWidget(w)
                w.hide()
                w.setParent(None)

    def check_infos(self, text):
        if not text:
            self.button_invite_user.setDisabled(True)
        else:
            self.button_invite_user.setDisabled(False)

    @classmethod
    def exec_modal(cls, core, jobs_ctx, parent):
        w = cls(core=core, jobs_ctx=jobs_ctx)
        d = GreyedDialog(w, title=_("TEXT_INVITE_USER_TITLE"), parent=parent, width=1000)
        w.dialog = d
        return d.exec_()

# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

from uuid import UUID

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QWidget, QApplication

from structlog import get_logger

from parsec.api.protocol import InvitationType, InvitationStatus, InvitationDeletedReason
from parsec.core.types import BackendInvitationAddr

from parsec.core.backend_connection import backend_authenticated_cmds_factory
from parsec.core.gui import desktop
from parsec.core.gui.custom_dialogs import show_error, GreyedDialog
from parsec.core.gui.lang import translate as _
from parsec.core.gui.trio_thread import JobResultError, ThreadSafeQtSignal, QtToTrioJob
from parsec.core.gui.ui.invite_device_widget import Ui_InviteDeviceWidget
from parsec.core.gui.ui.device_invitation_widget import Ui_DeviceInvitationWidget


logger = get_logger()


async def _do_invite_device(device, config):
    async with backend_authenticated_cmds_factory(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
        keepalive=config.backend_connection_keepalive,
    ) as cmds:
        rep = await cmds.invite_new(type=InvitationType.DEVICE)
        if rep["status"] != "ok":
            raise JobResultError(rep["status"])
        action_addr = BackendInvitationAddr.build(
            backend_addr=device.organization_addr,
            organization_id=device.organization_id,
            invitation_type=InvitationType.DEVICE,
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
        invs = [inv for inv in rep["invitations"] if inv["type"] == InvitationType.DEVICE]
        if len(invs):
            return invs[0]
        return None


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


class InviteDeviceWidget(QWidget, Ui_InviteDeviceWidget):
    invite_device_success = pyqtSignal(QtToTrioJob)
    invite_device_error = pyqtSignal(QtToTrioJob)
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
        self.invite_device_success.connect(self._on_invite_device_success)
        self.invite_device_error.connect(self._on_invite_device_error)
        self.cancel_invitation_success.connect(self._on_cancel_invitation_success)
        self.cancel_invitation_error.connect(self._on_cancel_invitation_error)
        self.button_invite_device.clicked.connect(self.invite_device)
        self.invite_addr = None
        self.button_copy_to_clipboard.clicked.connect(self._on_copy_invitation_clicked)
        self.button_cancel_invite.clicked.connect(self._on_cancel_invitation_clicked)
        self.list_invitations()

    def list_invitations(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "list_invitations_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "list_invitations_error", QtToTrioJob),
            _do_list_invitations,
            device=self.core.device,
            config=self.core.config,
        )

    def invite_device(self):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "invite_device_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "invite_device_error", QtToTrioJob),
            _do_invite_device,
            device=self.core.device,
            config=self.core.config,
        )

    def cancel_invitation(self, token):
        self.jobs_ctx.submit_job(
            ThreadSafeQtSignal(self, "cancel_invitation_success", QtToTrioJob),
            ThreadSafeQtSignal(self, "cancel_invitation_error", QtToTrioJob),
            _do_cancel_invitation,
            device=self.core.device,
            config=self.core.config,
            token=token,
        )

    def _on_cancel_invitation_success(self, job):
        self.list_invitations()

    def _on_cancel_invitation_error(self, job):
        pass

    def _on_invite_device_success(self, job):
        self.list_invitations()

    def _on_invite_device_error(self, job):
        pass

    def _on_list_invitations_success(self, job):
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

        invitation = job.ret

        if not invitation:
            self.widget_invitation.hide()
            return

        self.widget_invitation.show()
        self.invite_addr = BackendInvitationAddr.build(
            backend_addr=self.core.device.organization_addr,
            organization_id=self.core.device.organization_id,
            invitation_type=InvitationType.DEVICE,
            token=invitation["token"],
        )
        font = QApplication.font()
        metrics = QFontMetrics(font)
        invite_addr = str(self.invite_addr)
        if metrics.horizontalAdvance(invite_addr) > self.label_invite_addr.width():
            while metrics.horizontalAdvance(invite_addr + "...") > self.label_invite_addr.width():
                invite_addr = invite_addr[: len(invite_addr) - 1]
            invite_addr += "..."
        self.label_invite_addr.setText(invite_addr)
        self.label_invite_addr.setToolTip(str(self.invite_addr))
        self.label_invite_status.setText(STATUS_TEXTS[invitation["status"]][0])
        self.label_invite_status.setToolTip(STATUS_TEXTS[invitation["status"]][1])

    def _on_list_invitations_error(self, job):
        show_error(self, "List failed")

    def _on_copy_invitation_clicked(self):
        desktop.copy_to_clipboard(str(self.invite_addr))

    def _on_cancel_invitation_clicked(self):
        self.cancel_invitation(self.invite_addr.token)

    @classmethod
    def exec_modal(cls, core, jobs_ctx, parent):
        w = cls(core=core, jobs_ctx=jobs_ctx)
        d = GreyedDialog(w, title=_("TEXT_INVITE_DEVICE_TITLE"), parent=parent, width=1000)
        w.dialog = d
        return d.exec_()

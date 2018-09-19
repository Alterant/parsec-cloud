import trio
import logbook

from parsec.core.fs.sharing import SharingError
from parsec.core.backend_connection import BackendNotAvailable


logger = logbook.Logger("parsec.core.messages_monitor")


async def monitor_messages(fs, event_bus):
    msg_arrived = trio.Event()
    backend_online_event = trio.Event()
    process_message_cancel_scope = None

    def _on_msg_arrived(event, index):
        msg_arrived.set()

    event_bus.connect("backend.message.received", _on_msg_arrived, weak=True)
    event_bus.connect("backend.message.polling_needed", _on_msg_arrived, weak=True)

    def _on_backend_online(self, event):
        backend_online_event.set()

    def _on_backend_offline(self, event):
        backend_online_event.clear()
        if process_message_cancel_scope:
            process_message_cancel_scope.cancel()

    event_bus.connect("backend.online", _on_backend_online, weak=True)
    event_bus.connect("backend.offline", _on_backend_offline, weak=True)

    while True:
        await backend_online_event.wait()
        try:

            with trio.open_cancel_scope() as process_message_cancel_scope:
                while True:
                    try:
                        await fs.process_messages()
                    except SharingError:
                        logger.exception("Invalid message from backend")
                    await msg_arrived.wait()
                    msg_arrived.clear()

        except BackendNotAvailable:
            pass
        process_message_cancel_scope = None
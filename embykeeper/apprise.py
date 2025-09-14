import apprise
from loguru import logger
import asyncio

from rich.text import Text

logger = logger.bind(scheme="apprise", nonotify=True)


class AppriseStream:
    def __init__(self, uri: str):
        self.apobj = apprise.Apprise()
        self.apobj.add(uri)
        self.loop = asyncio.get_event_loop()

    def write(self, message):
        # The message from loguru has a newline at the end, remove it.
        message = message.strip()
        # The message is formatted as "LEVEL#MESSAGE"
        level, _, body = message.partition("#")
        level = level.lower()
        body = Text.from_markup(body).plain

        # Map loguru levels to apprise levels
        notify_type = apprise.NotifyType.INFO
        if level == "warning":
            notify_type = apprise.NotifyType.WARNING
        elif level == "error" or level == "critical":
            notify_type = apprise.NotifyType.FAILURE
        elif level == "success":
            notify_type = apprise.NotifyType.SUCCESS

        async def notify():
            if not await self.apobj.async_notify(body=body, title="Embykeeper", notify_type=notify_type):
                logger.warning(f"Failed to send notification via Apprise.")

        self.loop.create_task(notify())

    def close(self):
        pass

    async def join(self):
        pass

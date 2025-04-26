import asyncio
from . import BotCheckin

from pyrogram.types import Message
from pyrogram.errors import ChatWriteForbidden

__ignore__ = True


class EPubGroupCheckin(BotCheckin):
    name = "EPub 电子书库群组签到"
    chat_name = "libhsulife"
    bot_username = "zhruonanbot"

    async def send_checkin(self, retry=False):
        try:
            msg = await self.send("签到")
            if msg:
                self.mid = msg.id
        except ChatWriteForbidden:
            self.log.info('被禁言, 准备 2 分钟后重新签到.')
            await asyncio.sleep(120)
            await self.retry()

    async def on_text(self, message: Message, text: str):
        mid = getattr(self, "mid", None)
        if mid and message.reply_to_message_id == mid:
            return await super().on_text(message, text)

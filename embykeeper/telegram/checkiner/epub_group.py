from . import BotCheckin

from pyrogram.types import Message

__ignore__ = True


class EPubGroupCheckin(BotCheckin):
    name = "EPub 电子书库群组签到"
    chat_name = "libhsulife"
    bot_username = "zhruonanbot"

    async def send_checkin(self, retry=False):
        msg = await self.send("签到")
        if msg:
            self.mid = msg.id

    async def on_text(self, message: Message, text: str):
        mid = getattr(self, "mid", None)
        if mid and message.reply_to_message_id == mid:
            return await super().on_text(message, text)

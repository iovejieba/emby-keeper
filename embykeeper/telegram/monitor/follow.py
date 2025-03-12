import asyncio

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message
from pyrogram.errors import RPCError
from cachetools import TTLCache

from embykeeper.runinfo import RunStatus

from . import Monitor

__ignore__ = True


class FollowMonitor(Monitor):
    name = "全部群组从众"
    lock = asyncio.Lock()
    cache = TTLCache(maxsize=2048, ttl=300)
    chat_follow_user = 5
    allow_same_user = False

    async def start(self):
        self.ctx.start(RunStatus.RUNNING)
        async with self.listener():
            self.log.info(f"开始监视: {self.name}.")
            await self.failed.wait()
            self.log.error(f"发生错误, 不再监视: {self.name}.")

            return False

    async def message_handler(self, client: Client, message: Message):
        if not message.text:
            return
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        if len(message.text) > 50:
            return
        if message.text.startswith("/"):
            return
        if not message.from_user:
            return
        if message.from_user.is_bot:
            return
        ident = (message.chat.id, message.text)
        async with self.lock:
            if ident not in self.cache:
                self.cache[ident] = {message.from_user.id} if not self.allow_same_user else 1
                return

            if self.allow_same_user:
                self.cache[ident] += 1
                count = self.cache[ident]
            else:
                self.cache[ident].add(message.from_user.id)
                count = len(self.cache[ident])

            if count == self.chat_follow_user:
                try:
                    chat_id, text = ident
                    await self.client.send_message(chat_id, text)
                except RPCError as e:
                    self.log.warning(f"发送从众信息到群组 {message.chat.title} 失败: {e}.")
                else:
                    self.log.info(f"已发送从众信息到群组 {message.chat.title}: {text}.")

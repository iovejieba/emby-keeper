from ._templ_a import TemplateACheckin

from pyrogram.types import Message

__ignore__ = True


class BibiCheckin(TemplateACheckin):
    name = "比比"
    bot_username = "BBFreeFilm_bot"

    async def message_handler(self, client, message: Message):
        if message.text and "开始签到验证" not in message.text:
            return
        if message.text and "签到验证" in message.text:
            if not await self.gpt_handle_message(message, unexpected=False):
                self.log.info(f"签到失败: 智能解析错误, 正在重试.")
                return await self.retry()
            else:
                return
        await super().message_handler(client, message)

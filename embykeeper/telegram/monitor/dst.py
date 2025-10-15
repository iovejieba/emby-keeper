from pyrogram.types import Message

from . import Monitor


class DSTMonitor(Monitor):
    name = "ic电视台"
    chat_name = "xjdjdjxjfjjfl"
    chat_keyword = r"已开启"
    bot_username = "ichinose123_bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        await self.client.send_message(self.bot_username, "/create")
        await self.client.send_message(self.bot_username, self.unique_name)
        self.log.bind(msg=True).info(f'已向 Bot @{self.bot_username} 发送了用户注册申请: "{self.unique_name}", 请查看.')

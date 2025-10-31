import asyncio
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid

from embykeeper.utils import async_partial

from . import Monitor

__ignore__ = True


class WebshellMonitor(Monitor):
    name = "叔服"
    chat_name = -1003202963047
    chat_keyword = r"FYEMBY-\d+-Register_[\w]+"
    bot_username = "webshell666666bot"
    notify_create_name = True
    additional_auth = ["prime"]
    
    # 测试模式开关 - 设置为True时监听自己发送的信息，便于调试
    test_mode = True

    async def on_trigger(self, message: Message, key, reply):
        # 如果不是测试模式，并且消息是自己发送的，则忽略
        if not self.test_mode and message.from_user and message.from_user.id == self.client.me.id:
            return
            
        # 获取消息中的所有邀请码
        import re
        pattern = re.compile(self.chat_keyword)
        all_codes = pattern.findall(message.text or message.caption or "")
        
        if not all_codes:
            return
            
        self.log.info(f"检测到 {len(all_codes)} 个邀请码: {', '.join(all_codes)}")
        
        wr = async_partial(self.client.wait_reply, self.bot_username)
        
        # 按顺序尝试每个邀请码，直到成功获取一个注册资格
        for code in all_codes:
            for attempt in range(3):
                try:
                    msg = await wr("/start")
                    if "请确认好重试" in (msg.text or msg.caption):
                        continue
                    elif "欢迎进入用户面板" in (msg.text or msg.caption) and msg.reply_markup:
                        keys = [k.text for r in msg.reply_markup.inline_keyboard for k in r]
                        for k in keys:
                            if "使用注册码" in k:
                                async with self.client.catch_reply(
                                    self.bot_username, filter=filters.regex(".*对我发送.*")
                                ) as f:
                                    try:
                                        await msg.click(k)
                                    except (TimeoutError, MessageIdInvalid):
                                        pass
                                    try:
                                        await asyncio.wait_for(f, 10)
                                    except asyncio.TimeoutError:
                                        continue
                                    else:
                                        break
                        else:
                            continue
                        msg = await wr(code)
                        
                        # 去掉emoji和多余空格，提取纯文本进行判断
                        response_text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', msg.text or msg.caption or '')
                        response_text = re.sub(r'\s+', ' ', response_text).strip()
                        
                        # 检查是否成功获取注册资格 - 使用关键词判断
                        if any(keyword in response_text for keyword in ["少年郎恭喜你", "已经收到了", "邀请注册资格"]):
                            self.log.bind(msg=True).info(
                                f'成功获取注册资格! 邀请码: "{code}", 请继续完成注册.'
                            )
                            return  # 成功获取资格，直接返回，不再尝试其他邀请码
                        elif "注册码已被使用" in response_text:
                            self.log.info(f'邀请码 "{code}" 已被使用，尝试下一个.')
                            break  # 这个码已被使用，跳出重试循环，尝试下一个码
                        else:
                            # 其他情况，继续重试当前码
                            continue
                    else:
                        continue
                except asyncio.TimeoutError:
                    if attempt == 2:  # 最后一次尝试也超时
                        self.log.warning(f'处理邀请码 "{code}" 时超时')
        
        # 所有邀请码都尝试失败
        self.log.bind(msg=True).warning(
            f"已监控到{self.name}的邀请码, 但自动使用失败, 请自行查看."
        )
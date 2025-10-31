import asyncio
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid

from embykeeper.utils import async_partial

from . import Monitor

__ignore__ = True


class TestMonitor(Monitor):
    name = "测试抢码"
    chat_name = "webshell666666"
    chat_keyword = r"FYEMBY-\d+-Register_[\w]+"
    bot_username = "webshell666666bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        # 处理多个邀请码的情况
        if isinstance(key, str):
            # 如果 key 是字符串，按换行符分割
            keys = [k.strip() for k in key.split('\n') if k.strip()]
        elif isinstance(key, list):
            # 如果 key 是列表，直接使用
            keys = key
        else:
            keys = [key]
        
        self.log.info(f"检测到 {len(keys)} 个邀请码，开始尝试注册...")
        
        wr = async_partial(self.client.wait_reply, self.bot_username)
        used_keys = []
        success_keys = []
        
        for current_key in keys:
            if current_key in used_keys:
                continue
                
            self.log.info(f"正在尝试邀请码: {current_key}")
            
            for attempt in range(3):  # 每个邀请码最多尝试3次
                try:
                    msg = await wr("/start")
                    msg_text = msg.text or msg.caption or ""
                    
                    if "请确认好重试" in msg_text:
                        continue
                    elif "你好鸭" in msg_text and msg.reply_markup:
                        keys_buttons = [k.text for r in msg.reply_markup.inline_keyboard for k in r]
                        for k in keys_buttons:
                            if "使用注册码" in k:
                                async with self.client.catch_reply(
                                    self.bot_username, filter=filters.regex(".*对我发送.*")
                                ) as f:
                                    try:
                                        await msg.click(k)
                                    except (TimeoutError, MessageIdInvalid):
                                        continue
                                    
                                    try:
                                        await asyncio.wait_for(f, 10)
                                    except asyncio.TimeoutError:
                                        continue
                                    else:
                                        break
                        else:
                            continue
                        
                        # 发送当前邀请码
                        msg = await wr(current_key)
                        msg_text = msg.text or msg.caption or ""
                        
                        # 检查回复消息
                        if "注册码已被使用" in msg_text or "的形状了喔" in msg_text:
                            self.log.info(f'邀请码 "{current_key}" 已被使用，跳过并尝试下一个.')
                            used_keys.append(current_key)
                            break  # 跳出当前邀请码的尝试循环
                        elif "恭喜" in msg_text and "邀请注册资格" in msg_text:
                            self.log.bind(msg=True).info(
                                f'成功使用邀请码: "{current_key}" 注册 {self.name} 账户.'
                            )
                            success_keys.append(current_key)
                            # 成功注册一个后继续尝试其他邀请码
                            break
                        else:
                            # 未知响应，记录并继续尝试下一个邀请码
                            self.log.info(f'邀请码 "{current_key}" 返回未知响应: {msg_text}')
                            break
                    else:
                        continue
                except asyncio.TimeoutError:
                    if attempt == 2:  # 最后一次尝试也超时
                        self.log.warning(f'尝试邀请码 "{current_key}" 时超时，跳过此邀请码.')
                    continue
            else:
                self.log.warning(f'邀请码 "{current_key}" 尝试失败，跳过.')
        
        # 所有邀请码尝试完成后的处理
        if success_keys:
            self.log.bind(msg=True).info(f'成功注册了 {len(success_keys)} 个 {self.name} 账户.')
            if len(success_keys) > 1:
                self.log.bind(msg=True).info(f'成功的邀请码: {", ".join(success_keys)}')
        elif used_keys:
            self.log.bind(msg=True).warning(
                f'检测到 {len(keys)} 个 {self.name} 邀请码，但全部已被使用.'
            )
        else:
            self.log.bind(msg=True).warning(
                f'检测到 {len(keys)} 个 {self.name} 邀请码，但自动使用全部失败.'
            )
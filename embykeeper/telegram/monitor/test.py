import asyncio
import re
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid

from embykeeper.utils import async_partial
from embykeeper.utils import to_iterable

from . import Monitor

__ignore__ = True


class TestMonitor(Monitor):
    name = "测试抢码"
    chat_name = "webshell666666"
    chat_keyword = r"FYEMBY-\d+-Register_[\w]+"
    bot_username = "webshell666666bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def message_handler(self, client, message: Message):
        """重写消息处理器添加详细调试"""
        # 添加详细的调试信息
        chat_info = f"{message.chat.username or message.chat.id} ({message.chat.title})"
        self.log.info(f"收到消息 - 聊天: {chat_info}")
        self.log.info(f"消息内容: {message.text}")
        self.log.info(f"消息类型: text={bool(message.text)}, caption={bool(message.caption)}")
        self.log.info(f"是否 outgoing: {message.outgoing}")
        
        # 检查聊天匹配
        chat_matched = False
        if self.chat_name:
            chat_ids = [self.chat_name] if isinstance(self.chat_name, (str, int)) else self.chat_name
            current_chat_id = message.chat.username or message.chat.id
            chat_matched = any(str(chat_id) == str(current_chat_id) for chat_id in chat_ids)
            self.log.info(f"聊天匹配: {chat_matched} (期望: {chat_ids}, 实际: {current_chat_id})")
        
        # 检查关键词匹配
        keys_found = []
        for key in self.keys(message):
            keys_found.append(key)
        
        self.log.info(f"关键词匹配结果: {keys_found}")
        
        if keys_found:
            self.log.info("!!! 准备触发监控器 !!!")
        
        # 调用父类处理
        await super().message_handler(client, message)

    def keys(self, message: Message):
        """重写 keys 方法添加调试"""
        sender = message.from_user
        self.log.info(f"发送者: {sender.username if sender else 'None'} (ID: {sender.id if sender else 'None'})")
        
        # 检查用户过滤
        if sender and self.chat_user:
            user_matched = any(i in to_iterable(self.chat_user) for i in (sender.id, sender.username))
            self.log.info(f"用户过滤: {user_matched} (期望用户: {self.chat_user})")
            if not user_matched:
                return
        
        text = message.text or message.caption
        self.log.info(f"处理文本: {text}")
        
        # 检查排除关键词
        if text and self.chat_except_keyword:
            for k in to_iterable(self.chat_except_keyword):
                if re.search(k, text, re.IGNORECASE):
                    self.log.info(f"被排除关键词过滤: {k}")
                    return
        
        # 检查目标关键词
        if self.chat_keyword:
            for k in to_iterable(self.chat_keyword):
                self.log.info(f"检查关键词模式: {k}")
                if k is None or text is None:
                    if k is None and text is None:
                        self.log.info("匹配: 双方均为 None")
                        yield None
                else:
                    matches = list(re.findall(k, text, re.IGNORECASE))
                    self.log.info(f"正则匹配结果: {matches}")
                    for m in matches:
                        yield m
        else:
            self.log.info("无关键词过滤，返回完整文本")
            yield text

    async def on_trigger(self, message: Message, key, reply):
        """触发时的处理"""
        self.log.info(f"!!! 监控器正式触发 !!!")
        self.log.info(f"触发消息: {message.text}")
        self.log.info(f"提取的key: {key}")
        
        # 原有的处理逻辑...
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
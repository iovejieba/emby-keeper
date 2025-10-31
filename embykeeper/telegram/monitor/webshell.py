import asyncio
import re
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid

from embykeeper.utils import async_partial, to_iterable

from . import Monitor

__ignore__ = True


class WebshellMonitor(Monitor):
    name = "测试抢码"
    chat_name = "webshell666666"
    chat_keyword = r"FYEMBY-\d+-Register_[\w]+"
    bot_username = "webshell666666bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def start(self):
        """重写 start 方法添加调试信息"""
        self.log.info("!!! TestMonitor 开始启动 !!!")
        self.log.info(f"配置的聊天名称: {self.chat_name}")
        self.log.info(f"配置的关键词: {self.chat_keyword}")
        
        # 添加一个简单的全局消息监听器用于测试
        @self.client.on_message()
        async def debug_handler(client, message):
            # 只记录目标聊天的消息
            target_chats = [self.chat_name] if isinstance(self.chat_name, (str, int)) else self.chat_name
            current_chat = message.chat.username or message.chat.id
            
            if any(str(target) == str(current_chat) for target in target_chats):
                self.log.info(f"[调试] 收到目标聊天消息: {message.text}")
        
        result = await super().start()
        self.log.info(f"!!! TestMonitor 启动完成 !!!")
        return result

    def keys(self, message: Message):
        """重写 keys 方法添加详细调试信息"""
        # 首先检查是否来自目标聊天
        target_chats = [self.chat_name] if isinstance(self.chat_name, (str, int)) else self.chat_name
        current_chat = message.chat.username or message.chat.id
        chat_matched = any(str(target) == str(current_chat) for target in target_chats)
        
        if not chat_matched:
            return
        
        self.log.info(f"[调试] 开始处理消息: {message.text}")
        
        # 调用父类的 keys 方法
        for key in super().keys(message):
            self.log.info(f"[调试] 找到匹配的key: {key}")
            yield key
        else:
            self.log.info("[调试] 没有找到匹配的key")

    async def message_handler(self, client, message: Message):
        """重写消息处理器添加调试信息"""
        self.log.info(f"[调试] 进入消息处理器 - 聊天: {message.chat.username}, 消息: {message.text}")
        
        # 调用父类处理
        await super().message_handler(client, message)
        
        self.log.info("[调试] 消息处理器执行完成")

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
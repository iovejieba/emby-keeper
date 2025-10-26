import asyncio
import re
from typing import List, Optional, Union

from cachetools import TTLCache
from loguru import logger
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram.errors import RPCError, FloodWaitError, MessageIdInvalid
from pydantic import BaseModel, ValidationError

from embykeeper.utils import to_iterable, truncate_str

from . import Monitor

__ignore__ = True


class TemplateCMonitorConfig(BaseModel):
    name: str = "红包监控器"
    # 监控的群聊（支持：群ID整数、显示名称字符串、用户名@xxx字符串）
    chat_name: Optional[Union[str, int, List[Union[str, int]]]] = None
    red_keywords: Union[str, List[str]] = ["🧧", "红包"]  # 红包关键词
    open_button_text: str = "開"  # 红包打开按钮文本（如“開”“领取”）
    trigger_interval: float = 1.0  # 抢红包间隔（秒）
    max_retry: int = 3  # 点击失败重试次数
    allow_same_sender: bool = True  # 允许抢同一发送者的多个红包
    ttl: int = 60  # 红包消息有效期（秒）


class TemplateCMonitor(Monitor):
    """TemplateC 红包监控器，支持群ID/显示名称/用户名配置"""
    init_first = True
    additional_auth = ["prime"]
    allow_caption = True  # 红包通常带图片，允许带标题的消息
    allow_text = False  # 关闭纯文本消息监控

    async def init(self):
        try:
            self.t_config = TemplateCMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败：TemplateC 配置错误\n{e}")
            return False

        # 初始化参数
        self.name = self.t_config.name
        self.chat_name = self.t_config.chat_name
        self.red_keywords = to_iterable(self.t_config.red_keywords)
        self.open_button_text = self.t_config.open_button_text
        self.trigger_interval = self.t_config.trigger_interval
        self.max_retry = self.t_config.max_retry
        self.allow_same_sender = self.t_config.allow_same_sender
        self.ttl = self.t_config.ttl

        # 缓存已处理的红包消息（避免重复抢）
        self.processed_ids = TTLCache(maxsize=1024, ttl=self.ttl)
        self.lock = asyncio.Lock()
        self.last_grab_time = 0.0  # 上次抢红包时间（防频率限制）

        self.log = logger.bind(scheme="template_c", name=self.name, username=self.client.me.full_name)
        self.log.info("TemplateC 监控器初始化完成，支持群ID/名称/用户名配置")
        return True

    async def message_handler(self, client: Client, message: Message):
        """识别红包消息并抢取"""
        # 过滤非群聊
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return

        # 过滤已处理或过期消息
        if message.id in self.processed_ids:
            self.log.debug(f"消息 {message.id} 已处理，跳过")
            return
        if (asyncio.get_event_loop().time() - message.date.timestamp()) > self.ttl:
            self.log.debug(f"消息 {message.id} 已过期（> {self.ttl}秒），跳过")
            return

        # 提取消息内容（文本或图片标题）
        content = (message.text or message.caption or "").strip()

        # 匹配红包关键词
        if not any(re.search(kw, content, re.IGNORECASE) for kw in self.red_keywords):
            return

        # 查找红包按钮（如“開”）
        open_button = self._find_open_button(message)
        if not open_button:
            self.log.debug(f"消息 {message.id} 含关键词但无按钮“{self.open_button_text}”，跳过")
            return

        # 标记为已处理
        async with self.lock:
            self.processed_ids[message.id] = True

        # 执行抢红包
        self.log.info(
            f"发现红包：群聊「{message.chat.title}」，发送者「{message.from_user.full_name if message.from_user else '未知'}」"
        )
        await self._grab_red_envelope(message, open_button)

    def _find_open_button(self, message: Message) -> Optional[InlineKeyboardButton]:
        """查找        查找红包按钮（支持“開”“领取”等文本）
        """
        if not message.reply_markup or not message.reply_markup.inline_keyboard:
            return None

        for row in message.reply_markup.inline_keyboard:
            for button in row:
                if self.open_button_text in (button.text or ""):
                    return button
        return None

    async def _grab_red_envelope(self, message: Message, button: InlineKeyboardButton):
        """点击红包按钮，带频率控制和重试"""
        # 频率控制
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_grab_time < self.trigger_interval:
            wait_time = self.trigger_interval - (current_time - self.last_grab_time)
            self.log.debug(f"频率控制，等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)

        # 重试逻辑
        for retry in range(self.max_retry):
            try:
                self.log.info(f"第 {retry+1}/{self.max_retry} 次尝试抢...")
                await message.click(button.text)  # 点击按钮
                self.last_grab_time = current_time
                self.log.success(f"抢成功！消息ID：{message.id}")
                return
            except FloodWaitError as e:
                self.log.warning(f"触发限制，等待 {e.x} 秒")
                await asyncio.sleep(e.x)
            except (MessageIdInvalid, RPCError) as e:
                self.log.warning(f"第 {retry+1} 次失败：{e}")
                if retry < self.max_retry - 1:
                    await asyncio.sleep(0.5)

        self.log.error(f"超过最大重试次数（{self.max_retry}次），抢失败")

    async def on_trigger(self, message: Message, key, reply):
        pass  # 无需额外操作


def use(**kw):
    return type("TemplatedClass", (TemplateCMonitor,), kw)
from __future__ import annotations

import asyncio
import random
import re
from typing import TYPE_CHECKING

from pyrogram.errors import MessageIdInvalid
from pyrogram.types import Message
from pyrogram.raw.types.messages import BotCallbackAnswer

from .pyrogram import Client

if TYPE_CHECKING:
    from loguru import Logger


class EmbybossRegister:
    def __init__(self, client: Client, logger: Logger, username: str, password: str):
        self.client = client
        self.log = logger
        self.username = username
        self.password = password  # 保留原变量名，兼容关联代码
        # 注册状态检测：适度模糊的多特征规则（核心优化）
        self.REGISTER_PATTERNS = {
            # 核心关键词：允许前后空格、忽略大小写（应对标点/空格变化）
            "keyword": re.compile(r"\s*您已进入注册状态\s*", re.IGNORECASE),
            # 时间限制：允许"min"或"分钟"，数字部分精确（应对单位变化）
            "time_limit": re.compile(r"(\d+)(min|分钟)内输入", re.IGNORECASE),
            # 示例格式：允许示例前后有其他内容，保留"举个例子+用户名+数字"结构
            "example": re.compile(r"举个例子.*?\s+[\S]+\s+\d+", re.DOTALL)
        }

    async def run(self, bot: str):
        """单次注册尝试"""
        return await self._register_once(bot)

    async def run_continuous(self, bot: str, interval_seconds: int = 1):
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应, 无法注册.")
            return False

        while True:
            try:
                result = await self._attempt_with_panel(panel)
                if result:
                    self.log.info(f"注册成功")
                    return True

                if interval_seconds:
                    self.log.debug(f"注册失败, {interval_seconds} 秒后重试.")
                    await asyncio.sleep(interval_seconds)
                else:
                    self.log.debug(f"注册失败, 即将重试.")
                    return False
            except (MessageIdInvalid, ValueError, AttributeError):
                self.log.debug("面板失效, 正在重新获取...")
                try:
                    panel = await self.client.wait_reply(bot, "/start")
                except asyncio.TimeoutError:
                    if interval_seconds:
                        self.log.warning("重新获取面板失败, 等待后重试.")
                        await asyncio.sleep(interval_seconds)
                        continue
                    else:
                        self.log.warning("重新获取面板失败, 无法注册.")
                        return False
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"注册异常: {e}")
                await asyncio.sleep(5)
        return False

    async def _register_once(self, bot: str):
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应, 无法注册.")
            return False

        text = panel.text or panel.caption
        try:
            current_status = re.search(r"当前状态 \| ([^\n]+)", text).group(1).strip()
            register_status = re.search(r"注册状态 \| (True|False)", text).group(1) == "True"
            available_slots = int(re.search(r"可注册席位 \| (\d+)", text).group(1))
        except (AttributeError, ValueError):
            self.log.warning("无法解析界面, 无法注册, 可能您已注册.")
            return False

        if current_status != "未注册":
            self.log.warning("当前状态不是未注册, 无法注册.")
            return False
        if not register_status:
            self.log.debug(f"未开注, 将继续监控.")
            return False
        if available_slots <= 0:
            self.log.debug("可注册席位不足, 将继续监控.")
            return False

        return await self._attempt_with_panel(panel)

    async def _attempt_with_panel(self, panel: Message):
        # 查找并点击"创建账户"按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到创建账户按钮, 无法注册.")
            return False

        await asyncio.sleep(random.uniform(0.5, 1.5))  # 随机延迟，模拟人工操作

        # 点击按钮并处理即时反馈
        try:
            answer: BotCallbackAnswer = await panel.click(create_button)
            if "已关闭" in (answer.message or "") or answer.alert:
                self.log.debug(f"创建账户功能未开放: {answer.alert or answer.message}")
                return False
        except (TimeoutError, MessageIdInvalid) as e:
            self.log.warning(f"点击创建账户按钮异常: {e}")
            return False

        # 循环检测注册状态提示（核心优化：避免单次超时）
        register_prompt_msg = None
        total_timeout = 30  # 总等待时间（秒），可根据机器人响应速度调整
        check_interval = 3  # 每次检测间隔（秒）
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < total_timeout:
            try:
                # 等待新消息（每次超时后重试，避免阻塞）
                msg = await asyncio.wait_for(
                    self.client.wait_reply(chat_id=panel.chat.id),
                    timeout=check_interval
                )
                msg_text = msg.text or msg.caption or ""
                self.log.debug(f"收到新消息: {msg_text[:50]}...")  # 打印前50字符便于调试

                # 用多特征模糊匹配判断是否为注册状态
                if self._is_register_state(msg):
                    register_prompt_msg = msg
                    self.log.debug("成功匹配注册状态提示，准备发送凭据")
                    break

            except asyncio.TimeoutError:
                # 本次间隔无消息，继续等待
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                self.log.debug(f"等待注册状态中...（已等待{elapsed}/{total_timeout}秒）")
                continue
            except Exception as e:
                self.log.warning(f"检测消息时异常: {e}，将继续等待")
                continue

        # 检查是否成功检测到注册状态
        if not register_prompt_msg:
            self.log.warning(f"超过{total_timeout}秒未检测到有效注册状态提示，注册失败")
            return False

        # 校验用户名和password（安全码）格式
        if not self._validate_credentials():
            return False

        # 发送用户名和password
        try:
            send_msg = await self.client.send_message(
                chat_id=panel.chat.id,
                text=f"{self.username} {self.password}"
            )
            self.log.debug(f"已发送凭据: {self.username} **** (消息ID: {send_msg.id})")
        except Exception as e:
            self.log.error(f"发送凭据失败: {e}")
            return False

        # 等待机器人处理结果（超时120秒，匹配2分钟输入窗口）
        try:
            response_msg = await asyncio.wait_for(
                self.client.wait_reply(chat_id=panel.chat.id),
                timeout=120
            )
        except asyncio.TimeoutError:
            self.log.warning("发送凭据后超时（2分钟），会话被自动取消")
            return False

        # 解析机器人回复
        response_text = response_msg.text or response_msg.caption or ""
        self.log.debug(f"机器人回复: {response_text}")

        if "创建用户成功" in response_text:
            self.log.info("注册成功!")
            return True
        elif "没有获取到您的输入" in response_text:
            self.log.warning("机器人未收到输入，可能发送时机或格式错误")
            return False
        else:
            self.log.warning(f"注册失败，机器人反馈: {response_text}")
            return False

    def _is_register_state(self, msg: Message) -> bool:
        """多特征模糊匹配：判断是否为注册状态提示"""
        text = msg.text or msg.caption or ""
        if not text:
            return False

        # 1. 匹配核心关键词（允许前后空格、忽略大小写）
        if not self.REGISTER_PATTERNS["keyword"].search(text):
            self.log.debug(f"未匹配核心关键词: {text[:30]}...")
            return False

        # 2. 匹配时间限制（允许min/分钟）
        if not self.REGISTER_PATTERNS["time_limit"].search(text):
            self.log.debug(f"未匹配时间限制: {text[:30]}...")
            return False

        # 3. 匹配示例格式（允许灵活结构）
        if not self.REGISTER_PATTERNS["example"].search(text):
            self.log.debug(f"未匹配示例格式: {text[:30]}...")
            return False

        return True  # 所有特征匹配，确认为注册状态

    def _validate_credentials(self) -> bool:
        """验证用户名和password（安全码）格式"""
        # 验证安全码（4-6位数字）
        if not re.fullmatch(r"\d{4,6}", self.password):
            self.log.error(f"安全码格式错误: {self.password}（需4-6位数字）")
            return False

        # 验证用户名（允许中文、英文、emoji、空格，禁止其他特殊字符）
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 表情符号
            "\U0001F300-\U0001F5FF"  # 符号&图案
            "\U0001F680-\U0001F6FF"  # 运输&地图符号
            "\U0001F1E0-\U0001F1FF"  # 国旗
            "]+",
            flags=re.UNICODE
        )
        # 移除emoji后检查剩余字符是否含特殊符号
        cleaned_username = emoji_pattern.sub(r'', self.username)
        if re.search(r"[^\w\s\u4e00-\u9fa5]", cleaned_username):
            self.log.error(f"用户名包含特殊字符: {self.username}")
            return False

        self.log.debug("用户名和安全码格式验证通过")
        return True
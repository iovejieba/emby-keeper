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
        self.password = password
        self.max_retries = 3

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
                    return True

                if interval_seconds:
                    self.log.debug(f"注册失败, {interval_seconds} 秒后重试.")
                    await asyncio.sleep(interval_seconds)
                else:
                    self.log.debug(f"注册失败, 即将重试.")
                    return False
            except (MessageIdInvalid, ValueError, AttributeError):
                # 面板失效或结构变化, 重新获取
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
        # 点击创建账户按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button.text
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到创建账户按钮, 无法注册.")
            return False

        await asyncio.sleep(random.uniform(0.5, 1.5))

        async with self.client.catch_reply(panel.chat.id) as f:
            try:
                answer: BotCallbackAnswer = await panel.click(create_button)
                if answer and ("已关闭" in getattr(answer, 'message', '') or getattr(answer, 'alert', False)):
                    self.log.debug("未开注, 将继续监控.")
                    return False
            except (TimeoutError, MessageIdInvalid) as e:
                self.log.warning(f"点击按钮失败: {e}")
                # 继续尝试，可能仍然会收到回复
            
            try:
                msg: Message = await asyncio.wait_for(f, 15)  # 增加超时时间
            except asyncio.TimeoutError:
                self.log.warning("创建账户按钮点击无响应, 无法注册.")
                return False

        text = msg.text or msg.caption
        if not text or "您已进入注册状态" not in text:
            self.log.warning(f"未能正常进入注册状态, 注册失败. 收到: {text}")
            return False

        # 自动发送用户名和安全码
        self.log.info(f"自动发送注册信息: {self.username} {self.password}")
        try:
            # 直接发送注册信息，不使用wait_reply
            await self.client.send_message(msg.chat.id, f"{self.username} {self.password}")
            
            # 等待机器人处理并回复
            await asyncio.sleep(3)
            
            # 获取最新的消息来检查注册结果
            return await self._check_registration_result(msg.chat.id)
                
        except Exception as e:
            self.log.error(f"发送注册信息时出错: {e}")
            return False

    async def _check_registration_result(self, chat_id: int) -> bool:
        """检查注册结果"""
        try:
            # 获取最近的消息检查结果
            async for message in self.client.get_chat_history(chat_id, limit=10):
                result_text = message.text or message.caption
                if not result_text:
                    continue
                    
                # 成功关键词
                success_keywords = [
                    "创建用户成功", "注册成功", "创建成功", "恭喜",
                    "成功创建", "账户创建成功", "注册完成"
                ]
                
                # 失败关键词  
                failure_keywords = [
                    "失败", "错误", "无效", "不符合", "已满",
                    "名额已满", "已注册", "重复", "已存在"
                ]
                
                if any(keyword in result_text for keyword in success_keywords):
                    self.log.info("🎉 注册成功!")
                    return True
                elif any(keyword in result_text for keyword in failure_keywords):
                    self.log.warning(f"注册失败: {result_text}")
                    return False
            
            self.log.warning("无法确定注册结果，可能失败")
            return False
            
        except Exception as e:
            self.log.error(f"检查注册结果时出错: {e}")
            return False
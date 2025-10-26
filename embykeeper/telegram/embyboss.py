from __future__ import annotations

import asyncio
import random
import re
from typing import TYPE_CHECKING

# 只保留确认存在的异常（若仍报错，可进一步删除）
from pyrogram.errors import FloodWait

from pyrogram.types import Message
from pyrogram.raw.types.messages import BotCallbackAnswer

from .pyrogram import Client

if TYPE_CHECKING:
    from loguru import Logger


class EmbybossRegister:
    def __init__(self, client: Client, logger: Logger, username: str, password: str,
                 max_attempts: int = 10, accelerate_threshold: int = 5):
        self.client = client
        self.log = logger
        self.username = username
        self.password = password
        self.max_attempts = max_attempts  # 最大总重试次数
        self.current_attempt = 0  # 当前总尝试次数
        self.accelerate_threshold = accelerate_threshold  # 抢注加速阈值（席位≤该值触发）
        self.registration_timeout = 120  # 机器人要求的2分钟注册时限（秒）
        self.status_prompt_timeout = 30  # 等待"进入注册状态"提示的超时时间（秒）
        self.short_retry_limit = 3  # 短期快速重试上限


    async def run(self, bot: str) -> bool:
        """单次注册尝试"""
        return await self._register_once(bot)


    async def run_continuous(self, bot: str, interval_seconds: int = 1) -> bool:
        """带重试的持续注册"""
        self.current_attempt = 0
        
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应，无法注册")
            return False

        while self.current_attempt < self.max_attempts:
            self.current_attempt += 1
            self.log.debug(f"第 {self.current_attempt}/{self.max_attempts} 次尝试")
            
            try:
                available_slots = await self._get_available_slots(panel)
                result = await self._attempt_with_panel(panel, available_slots)
                if result:
                    return True

                if interval_seconds > 0:
                    self.log.debug(f"{interval_seconds}秒后重试")
                    await asyncio.sleep(interval_seconds)
                else:
                    return False

            except Exception as e:  # 通用捕获，避免特定异常类问题
                self.log.debug(f"面板异常，重新获取: {e}")
                try:
                    panel = await self.client.wait_reply(bot, "/start")
                except asyncio.TimeoutError:
                    self.log.warning("重新获取面板超时")
                    await asyncio.sleep(interval_seconds)
                    continue
            except asyncio.CancelledError:
                self.log.debug("任务被取消")
                break
        
        self.log.warning(f"达到最大最大重试次数 ({self.max_attempts}次)")
        return False


    async def _register_once(self, bot: str) -> bool:
        """单次注册流程"""
        try:
            panel = await self.client.client.wait.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应")
            return False

        try:
            current_status = re.search(r"当前状态 \| ([^\n]+)", panel.text or panel.caption).group(1).strip()
            register_status = re.search(r"注册状态 \| (True|False)", panel.text or panel.caption).group(1) == "True"
            available_slots = int(re.search(r"可注册席位 \| (\d+)", panel.text or panel.caption).group(1))
        except Exception:
            self.log.warning("无法解析解析面板面板状态")
            return False

        if current_status != "未注册":
            self.log.warning("非未注册状态，无法注册")
            return False
        if not register_status:
            self.log.debug("注册未开启")
            return False
        if available_slots <= 0:
            self.log.debug("席位不足")
            return False

        return await self._attempt_with_panel(panel, available_slots)


    async def _attempt_with_panel(self, panel: Message, available_slots: int) -> bool:
        """核心心注册尝试逻辑
        """
        short_retry_count = 0

        while short_retry_count < self.short_retry_limit:
            try:
                # 查找"创建账户"按钮
                create_button = None
                for row in panel.reply_markup.inline_keyboard:
                    for button in row:
                        if "创建账户" in button.text:
                            create_button = button.text
                            break
                    if create_button:
                        break

                if not create_button:
                    self.log.warning("未找到创建账户按钮")
                    return False

                # 动态延迟
                click_delay = random.uniform(0.3, 0.8) if available_slots <= self.accelerate_threshold else random.uniform(0.5, 1.5)
                self.log.debug(f"延迟 {click_delay:.2f} 秒点击")
                await asyncio.sleep(click_delay)

                # 点击按钮并等待响应
                async with self.client.catch_reply(panel.chat.id) as f:
                    try:
                        answer: BotCallbackAnswer = await panel.click(create_button)
                        if answer and ("已关闭" in getattr(answer, 'message', '') or getattr(answer, 'alert', False)):
                            self.log.debug("注册已关闭")
                            return False
                    except Exception as e:
                        self.log.warning(f"按钮点击失败: {e}")
                        return False

                    try:
                        msg: Message = await asyncio.waitait_for(f, self.status_prompt_timeout)
                    except asyncio.TimeoutError:
                        self.log.warning("等待注册状态超时")
                        return False

                # 验证注册状态
                text = (msg.text or msg.caption or "").strip()
                if not re.search(r"进入注册状态", text):
                    self.log.warning(f"未进入注册状态: {text}")
                    return False

                # 校验用户名和安全码
                if not self._validate_username():
                    self.log.error(f"用户名 '{self.username}' 不符合要求（仅字母、数字、下划线）")
                    return False
                if not self._validate_password():
                    self.log.error(f"安全码 '{self.password}' 不符合要求（4-6位数字）")
                    return False

                # 发送注册信息
                register_msg = f"{self.username} {self.password}"
                self.log.info(f"发送注册信息: {register_msg}")
                await self.client.send_message(msg.chat.id, register_msg)

                # 检查结果
                check_delay = 0.5 if available_slots <= self.accelerate_threshold else 1
                await asyncio.sleep(check_delay)
                remaining_time = self.registration_timeout - (click_delay + check_delay + 5)
                return await self._check_registration_result(
                    msg.chat.id,
                    timeout=max(10, remaining_time),
                    is_accelerate=available_slots <= self.accelerate_threshold
                )

            # 仅保留FloodWait（若仍报错，可删除此块）
            except FloodWait as e:
                self.log.warning(f"频率限制，等待 {e.x} 秒")
                await asyncio.sleep(e.x)
                self.current_attempt += 1
                if self.current_attempt >= self.max_attempts:
                    self.log.warning("已达最大重试次数")
                    return False
                continue

            # 其他错误统一捕获（不区分类型，避免导入问题）
            except Exception as e:
                short_retry_count += 1
                self.log.warning(f"尝试失败（{short_retry_count}/{self.short_retry_limit}）: {e}")
                await asyncio.sleep(2)
                if short_retry_count >= self.short_retry_limit:
                    self.log.error("重试次数耗尽")
                    return False
                continue

        self.log.warning(f"短期重试次数耗尽")
        return False


    async def _get_available_slots(self, panel: Message) -> int:
        """解析可注册席位"""
        try:
            text = panel.text or panel.caption
            return int(re.search(r"可注册席位 \| (\d+)", text).group(1))
        except Exception:
            self.log.warning("无法解析席位，使用默认阈值")
            return self.accelerate_threshold


    def _validate_username(self) -> bool:
        """验证用户名"""
        return bool(re.fullmatch(r'^\w+$', self.username))


    def _validate_password(self) -> bool:
        """验证安全码"""
        return bool(re.fullmatch(r'^\d{4,6}$', self.password))


    async def _check_registration_result(self, chat_id: int, timeout: int, is_accelerate: bool) -> bool:
        """检查注册结果"""
        try:
            end_time = asyncio.get_event_loop().time() + timeout
            limit = 5 if is_accelerate else 10
            async for message in self.client.get_chat_history(chat_id, limit=limit):
                if asyncio.get_event_loop().time() > end_time:
                    self.log.warning("检查结果超时")
                    return False

                result_text = (message.text or message.caption or "").lower()
                if "成功" in result_text:
                    self.log.info("🎉 注册成功！")
                    return True
                elif any(k in result_text for k in ["失败", "错误", "无效", "重复", "已满"]):
                    self.log.warning(f"注册失败: {message.text or message.caption}")
                    return False

            self.log.warning("未匹配到明确结果")
            return False

        except Exception as e:
            self.log.error(f"检查结果出错: {e}")
            return False
from __future__ import annotations

import asyncio
import random
import re
from typing import TYPE_CHECKING

from pyrogram.errors import (
    FloodWaitError,
    NetworkError,
    MessageIdInvalid,
    PeerIdInvalid,
    BotTimeout
)
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
        self.short_retry_limit = 3  # 短期快速重试上限（针对网络波动等瞬时错误）

    async def run(self, bot: str) -> bool:
        """单次注册尝试"""
        return await self._register_once(bot)

    async def run_continuous(self, bot: str, interval_seconds: int = 1) -> bool:
        """带重试的持续注册（直到成功或达到最大次数）"""
        self.current_attempt = 0  # 重置总尝试次数
        
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应，无法注册")
            return False

        while self.current_attempt < self.max_attempts:
            self.current_attempt += 1
            self.log.debug(f"正在进行第 {self.current_attempt}/{self.max_attempts} 次注册尝试")
            
            try:
                # 解析当前面板的席位信息，用于判断是否加速
                available_slots = await self._get_available_slots(panel)
                result = await self._attempt_with_panel(panel, available_slots)
                if result:
                    return True

                # 重试间隔
                if interval_seconds > 0:
                    self.log.debug(f"注册失败，{interval_seconds}秒后重试")
                    await asyncio.sleep(interval_seconds)
                else:
                    self.log.debug("注册失败，终止重试")
                    return False

            except (MessageIdInvalid, ValueError, AttributeError):
                # 面板失效，重新获取
                self.log.debug("面板失效，重新获取...")
                try:
                    panel = await self.client.wait_reply(bot, "/start")
                except asyncio.TimeoutError:
                    self.log.warning("重新获取面板超时，等待后重试")
                    await asyncio.sleep(interval_seconds)
                    continue
            except asyncio.CancelledError:
                self.log.debug("注册任务被取消")
                break
            except Exception as e:
                self.log.error(f"注册过程异常: {e}")
                await asyncio.sleep(5)  # 异常后稍作等待
        
        self.log.warning(f"已达到最大重试次数 ({self.max_attempts}次)，注册失败")
        return False

    async def _register_once(self, bot: str) -> bool:
        """单次注册流程（独立调用）"""
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应，无法注册")
            return False

        # 解析面板状态
        try:
            current_status = re.search(r"当前状态 \| ([^\n]+)", panel.text or panel.caption).group(1).strip()
            register_status = re.search(r"注册状态 \| (True|False)", panel.text or panel.caption).group(1) == "True"
            available_slots = int(re.search(r"可注册席位 \| (\d+)", panel.text or panel.caption).group(1))
        except (AttributeError, ValueError):
            self.log.warning("无法解析面板状态，可能已注册或格式变更")
            return False

        # 状态校验
        if current_status != "未注册":
            self.log.warning("当前状态不是未注册，无法注册")
            return False
        if not register_status:
            self.log.debug("注册未开启，监控中")
            return False
        if available_slots <= 0:
            self.log.debug("可注册席位不足，监控中")
            return False

        return await self._attempt_with_panel(panel, available_slots)

    async def _attempt_with_panel(self, panel: Message, available_slots: int) -> bool:
        """核心注册尝试逻辑（含异常重试）"""
        short_retry_count = 0  # 短期重试计数器

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
                    self.log.warning("未找到创建账户按钮，无法注册")
                    return False

                # 抢注加速：根据席位动态调整点击延迟
                if available_slots <= self.accelerate_threshold:
                    click_delay = random.uniform(0.3, 0.8)
                    self.log.debug(f"抢注加速模式（席位{available_slots}≤{self.accelerate_threshold}），延迟{click_delay:.2f}秒")
                else:
                    click_delay = random.uniform(0.5, 1.5)
                    self.log.debug(f"正常模式，点击延迟{click_delay:.2f}秒")
                await asyncio.sleep(click_delay)

                # 点击按钮并等待注册状态提示
                async with self.client.catch_reply(panel.chat.id) as f:
                    try:
                        answer: BotCallbackAnswer = await panel.click(create_button)
                        if answer and ("已关闭" in getattr(answer, 'message', '') or getattr(answer, 'alert', False)):
                            self.log.debug("注册已关闭，终止尝试")
                            return False
                    except (MessageIdInvalid, PeerIdInvalid):
                        self.log.warning("按钮已失效，无法点击")
                        return False

                    try:
                        msg: Message = await asyncio.wait_for(f, self.status_prompt_timeout)
                    except asyncio.TimeoutError:
                        self.log.warning("等待注册状态提示超时（30秒）")
                        return False

                # 验证是否进入注册状态（模糊匹配）
                text = (msg.text or msg.caption or "").strip()
                if not re.search(r"进入注册状态", text):
                    self.log.warning(f"未进入注册状态，收到消息: {text}")
                    return False

                # 格式预校验
                if not self._validate_username():
                    self.log.error(f"用户名 '{self.username}' 包含禁止的特殊字符")
                    return False
                if not self._validate_password():
                    self.log.error(f"安全码 '{self.password}' 不符合要求（需4-6位数字）")
                    return False

                # 发送注册信息（即时发送）
                register_msg = f"{self.username} {self.password}"
                self.log.info(f"发送注册信息: {register_msg}")
                await self.client.send_message(msg.chat.id, register_msg)

                # 检查注册结果
                check_delay = 0.5 if available_slots <= self.accelerate_threshold else 1
                await asyncio.sleep(check_delay)
                remaining_time = self.registration_timeout - (click_delay + check_delay + 5)  # 预留缓冲
                return await self._check_registration_result(
                    msg.chat.id,
                    timeout=max(10, remaining_time),  # 至少保留10秒检查时间
                    is_accelerate=available_slots <= self.accelerate_threshold
                )

            # 处理Telegram频率限制（必须等待）
            except FloodWaitError as e:
                self.log.warning(f"触发频率限制，需等待 {e.x} 秒")
                await asyncio.sleep(e.x)
                self.current_attempt += 1  # 消耗总重试次数
                if self.current_attempt >= self.max_attempts:
                    self.log.warning("已达最大重试次数，终止")
                    return False
                continue

            # 处理网络波动（短期重试）
            except NetworkError as e:
                short_retry_count += 1
                self.log.warning(f"网络异常（{short_retry_count}/{self.short_retry_limit}）: {e}，1秒后重试")
                await asyncio.sleep(1)
                if short_retry_count >= self.short_retry_limit:
                    self.log.error("网络重试次数耗尽，终止当前尝试")
                    return False
                continue

            # 处理机器人超时（短期重试）
            except BotTimeout as e:
                short_retry_count += 1
                self.log.warning(f"机器人超时（{short_retry_count}/{self.short_retry_limit}）: {e}，2秒后重试")
                await asyncio.sleep(2)
                if short_retry_count >= self.short_retry_limit:
                    self.log.error("超时重试次数耗尽，终止当前尝试")
                    return False
                continue

            # 其他不可恢复错误
            except Exception as e:
                self.log.error(f"注册失败（不可恢复错误）: {e}")
                return False

        self.log.warning(f"短期重试次数耗尽（{self.short_retry_limit}次），终止当前尝试")
        return False

    async def _get_available_slots(self, panel: Message) -> int:
        """从面板中解析可注册席位数量"""
        try:
            text = panel.text or panel.caption
            return int(re.search(r"可注册席位 \| (\d+)", text).group(1))
        except (AttributeError, ValueError):
            self.log.warning("无法解析可注册席位，默认使用加速阈值")
            return self.accelerate_threshold  # 解析失败时默认触发加速

    def _validate_username(self) -> bool:
        """验证用户名：禁止特殊字符（允许中文、英文、emoji、数字、下划线）"""
        forbidden_chars = r'[\\/*?:"<>|`~!@#$%^&()+=【】{};'\[\]]'
        return not re.search(forbidden_chars, self.username)

    def _validate_password(self) -> bool:
        """验证安全码：4-6位纯数字"""
        return bool(re.fullmatch(r'^\d{4,6}$', self.password))

    async def _check_registration_result(self, chat_id: int, timeout: int, is_accelerate: bool) -> bool:
        """检查注册结果（模糊匹配）"""
        try:
            end_time = asyncio.get_event_loop().time() + timeout
            limit = 5 if is_accelerate else 10  # 加速模式下减少遍历数量
            async for message in self.client.get_chat_history(chat_id, limit=limit):
                if asyncio.get_event_loop().time() > end_time:
                    self.log.warning(f"检查结果超时（剩余{timeout}秒用尽）")
                    return False

                result_text = (message.text or message.caption or "").lower()
                if "成功" in result_text:
                    self.log.info("🎉 注册成功！")
                    return True
                elif any(keyword in result_text for keyword in ["失败", "错误", "无效", "重复", "已满"]):
                    self.log.warning(f"注册失败: {message.text or message.caption}")
                    return False

            self.log.warning("未匹配到明确结果，注册可能失败")
            return False

        except Exception as e:
            self.log.error(f"检查结果时出错: {e}")
            return False
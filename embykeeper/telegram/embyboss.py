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

        # 初始化时校验注册信息格式
        self._validate_credentials()

    def _validate_credentials(self):
        """校验用户名和安全码格式是否符合机器人要求"""
        # 校验安全码（4-6位数字）
        if not re.match(r"^\d{4,6}$", self.password):
            self.log.warning(f"安全码「{self.password}」不符合要求（需4-6位数字），可能导致注册失败！")
        # 校验用户名（不含特殊字符，根据机器人提示）
        if re.search(r'[^\w\u4e00-\u9fa5\s]', self.username):  # 允许字母、数字、中文、空格、下划线
            self.log.warning(f"用户名「{self.username}」包含特殊字符，可能被机器人拒绝！")

    async def run(self, bot: str):
        """单次注册尝试"""
        return await self._register_once(bot)

    async def run_continuous(self, bot: str, interval_seconds: int = 1):
        """持续监控并尝试注册，直到成功或被取消"""
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
        """单次注册流程：获取面板 -> 检查状态 -> 尝试注册"""
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

        # 状态校验
        if current_status != "未注册":
            self.log.warning(f"当前状态为「{current_status}」，不是未注册，无法注册.")
            return False
        if not register_status:
            self.log.debug(f"未开注（注册状态为False），将继续监控.")
            return False
        if available_slots <= 0:
            self.log.debug(f"可注册席位不足（{available_slots}个），将继续监控.")
            return False

        self.log.debug(f"状态校验通过（当前状态：未注册，开注状态：True，可注册席位：{available_slots}），开始尝试注册")
        return await self._attempt_with_panel(panel)

    async def _attempt_with_panel(self, panel: Message):
        """核心注册操作：点击按钮 -> 监听注册状态 -> 发送注册信息"""
        # 查找"创建账户"按钮（获取按钮对象而非文本）
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button  # 保存按钮对象（关键修复）
                    self.log.debug(f"找到【创建账户】按钮：{button.text}")
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到【创建账户】按钮，无法注册.")
            return False

        # 模拟人工延迟点击
        click_delay = random.uniform(0.5, 1.2)
        self.log.debug(f"等待{click_delay:.2f}秒后点击【创建账户】按钮...")
        await asyncio.sleep(click_delay)

        # 点击按钮（使用按钮对象，确保交互有效）
        try:
            self.log.debug(f"点击【创建账户】按钮...")
            answer: BotCallbackAnswer = await panel.click(create_button)
            # 处理按钮点击后的直接反馈（如"已关闭"提示）
            if answer:
                if answer.alert:
                    self.log.warning(f"按钮点击提示：{answer.message}（可能未开放注册）")
                    return False
                if "已关闭" in getattr(answer, "message", ""):
                    self.log.debug("注册已关闭，终止尝试")
                    return False
        except Exception as e:
            self.log.error(f"点击【创建账户】按钮失败：{e}")
            return False

        # 监听机器人发送的"进入注册状态"消息（可靠方式）
        self.log.debug(f"开始监听【进入注册状态】提示（目标对话ID：{panel.chat.id}）...")
        try:
            # 精准匹配包含目标关键词的消息，超时30秒
            msg: Message = await self.client.wait_for_message(
                chat_id=panel.chat.id,
                timeout=30,
                filters=lambda m: "您已进入注册状态" in (m.text or m.caption or "")
            )
        except asyncio.TimeoutError:
            self.log.warning("等待30秒未收到【进入注册状态】消息，可能机器人未响应")
            return False

        # 确认消息内容
        received_text = msg.text or msg.caption or "无内容"
        self.log.info(f"成功捕获注册状态消息：\n{received_text}")

        # 双重验证消息关键词
        if "您已进入注册状态" not in received_text:
            self.log.warning(f"消息不包含注册状态提示，内容：{received_text}")
            return False

        # 发送用户名和安全码
        register_info = f"{self.username} {self.password}"
        self.log.info(f"发送注册信息：{register_info}（目标对话ID：{msg.chat.id}）")
        try:
            sent_msg = await self.client.send_message(
                chat_id=msg.chat.id,
                text=register_info
            )
            self.log.debug(f"注册信息发送成功（消息ID：{sent_msg.id}）")
        except Exception as e:
            self.log.error(f"发送注册信息失败：{e}")
            return False

        # 等待机器人处理结果（延长等待时间）
        await asyncio.sleep(8)
        return await self._check_registration_result(msg.chat.id)

    async def _check_registration_result(self, chat_id: int) -> bool:
        """检查注册结果（成功/失败）"""
        try:
            self.log.debug(f"检查聊天ID {chat_id} 的注册结果...")
            # 遍历最近20条消息，确保覆盖机器人回复
            async for message in self.client.get_chat_history(chat_id, limit=20):
                result_text = message.text or message.caption or ""
                self.log.debug(f"检测历史消息：{result_text}")

                # 成功关键词匹配
                success_keywords = [
                    "创建用户成功", "注册成功", "创建成功", "恭喜",
                    "成功创建", "账户创建成功", "注册完成"
                ]
                if any(kw in result_text for kw in success_keywords):
                    self.log.info("🎉 注册成功!")
                    return True

                # 失败关键词匹配
                failure_keywords = [
                    "失败", "错误", "无效", "不符合", "已满",
                    "名额已满", "已注册", "重复", "已存在", "超时"
                ]
                if any(kw in result_text for kw in failure_keywords):
                    self.log.warning(f"注册失败: {result_text}")
                    return False

            self.log.warning("未找到明确的注册结果，可能失败")
            return False

        except Exception as e:
            self.log.error(f"检查注册结果时出错: {e}")
            return False
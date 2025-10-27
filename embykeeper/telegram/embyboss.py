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
        
        # 注册状态检测规则
        self.REGISTER_PATTERNS = {
            "keyword": re.compile(r"您已进入注册状态", re.IGNORECASE),
            "time_limit": re.compile(r"(\d+)\s*min内输入", re.IGNORECASE),
            "example": re.compile(r"举个例子[^：]*[:：]\s*[\S]+\s+\d+", re.IGNORECASE),
            "username_rule": re.compile(r"用户名.*不限制.*中/英文/emoji", re.IGNORECASE),
            "security_code": re.compile(r"安全码.*\d+~?\d*位", re.IGNORECASE)
        }
        
        # 注册成功检测规则
        self.SUCCESS_PATTERNS = [
            re.compile(r"创建用户成功🎉", re.IGNORECASE),
            re.compile(r"用户名称\s*\|", re.IGNORECASE),
            re.compile(r"用户密码\s*\|", re.IGNORECASE),
            re.compile(r"安全密码\s*\|", re.IGNORECASE),
            re.compile(r"到期时间\s*\|", re.IGNORECASE)
        ]

    async def run(self, bot: str):
        """单次注册尝试"""
        return await self._register_once(bot)

    async def run_continuous(self, bot: str, interval_seconds: int = 1):
        """连续注册尝试"""
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应, 无法注册.")
            return False

        while True:
            try:
                result = await self._attempt_with_panel(panel)
                if result:
                    self.log.info("注册成功")
                    return True

                if interval_seconds:
                    self.log.debug(f"注册失败, {interval_seconds} 秒后重试.")
                    await asyncio.sleep(interval_seconds)
                else:
                    self.log.debug("注册失败, 即将重试.")
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
        """单次注册流程"""
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
            self.log.debug("未开注, 将继续监控.")
            return False
        if available_slots <= 0:
            self.log.debug("可注册席位不足, 将继续监控.")
            return False

        return await self._attempt_with_panel(panel)

    async def _attempt_with_panel(self, panel: Message):
        """使用面板进行注册尝试"""
        # 查找创建账户按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button  # 存储按钮对象
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到创建账户按钮, 无法注册.")
            return False

        # 随机延迟模拟人工操作
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # 点击创建账户按钮
        async with self.client.catch_reply(panel.chat.id) as f:
            try:
                answer: BotCallbackAnswer = await panel.click(create_button)
                # 检查回调答案
                answer_message = answer.message or ""
                answer_alert = answer.alert or ""
                if "已关闭" in answer_message or "已关闭" in answer_alert:
                    self.log.debug("创建账户功能未开放.")
                    return False
            except (TimeoutError, MessageIdInvalid) as e:
                self.log.warning(f"点击创建账户按钮异常: {e}")
                # 不立即返回，可能仍然能收到回复
            
            try:
                # 等待按钮点击响应
                msg: Message = await asyncio.wait_for(f, 10)
            except asyncio.TimeoutError:
                self.log.warning("创建账户按钮点击无响应, 无法注册.")
                return False

        # 循环检测注册状态提示
        register_prompt_msg = await self._wait_for_register_state(panel)
        if not register_prompt_msg:
            return False

        # 验证凭据格式
        if not self._validate_credentials():
            return False

        # 发送凭据
        try:
            await self.client.send_message(
                chat_id=panel.chat.id,
                text=f"{self.username} {self.password}"
            )
            self.log.debug(f"已发送凭据: {self.username} ****")
        except Exception as e:
            self.log.error(f"发送凭据失败: {e}")
            return False

        # 等待并检查注册结果
        return await self._wait_for_register_result(panel)

    async def _wait_for_register_state(self, panel: Message) -> Message | None:
        """等待注册状态提示"""
        total_timeout = 100  # 总等待时间（秒）
        check_interval = 3  # 每次检测间隔（秒）
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < total_timeout:
            try:
                # 等待新消息
                current_msg = await asyncio.wait_for(
                    self.client.wait_reply(chat_id=panel.chat.id),
                    timeout=check_interval
                )
                msg_text = current_msg.text or current_msg.caption or ""
                self.log.debug(f"收到新消息: {msg_text[:50]}...")

                # 判断是否为注册状态
                if self._is_register_state(current_msg):
                    self.log.info("成功检测到注册状态提示，准备发送凭据")
                    return current_msg

            except asyncio.TimeoutError:
                # 本次间隔无消息，继续等待
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                self.log.debug(f"等待注册状态中...（已等待{elapsed}/{total_timeout}秒）")
                continue
            except Exception as e:
                self.log.warning(f"检测消息时异常: {e}，将继续等待")
                continue

        self.log.warning(f"超过{total_timeout}秒未检测到有效注册状态提示，注册失败")
        return None

    async def _wait_for_register_result(self, panel: Message) -> bool:
        """等待注册结果"""
        try:
            # 等待机器人回复结果
            result_msg = await self.client.wait_reply(panel.chat.id, timeout=60)
            result_text = result_msg.text or result_msg.caption or ""
            self.log.debug(f"收到结果: {result_text}")
            
            # 检查注册结果
            if self._is_register_success(result_text):
                self.log.info("注册成功!")
                # 提取并记录注册详情
                self._log_registration_details(result_text)
                return True
            elif "退出" in result_text or "cancel" in result_text.lower():
                self.log.warning("用户取消了注册")
                return False
            else:
                self.log.warning(f"注册失败: {result_text}")
                return False
                
        except asyncio.TimeoutError:
            self.log.warning("等待注册结果超时.")
            return False

    def _is_register_state(self, msg: Message) -> bool:
        """判断是否为注册状态提示"""
        text = msg.text or msg.caption or ""
        if not text:
            return False

        # 使用评分制提高容错性
        score = 0
        
        # 核心关键词匹配
        if self.REGISTER_PATTERNS["keyword"].search(text):
            score += 2
            
        # 时间限制匹配
        if self.REGISTER_PATTERNS["time_limit"].search(text):
            score += 1
            
        # 示例格式匹配
        if self.REGISTER_PATTERNS["example"].search(text):
            score += 1
            
        # 用户名规则匹配
        if self.REGISTER_PATTERNS["username_rule"].search(text):
            score += 1
            
        # 安全码规则匹配
        if self.REGISTER_PATTERNS["security_code"].search(text):
            score += 1

        # 总分达到3分即认为匹配
        if score >= 3:
            self.log.debug(f"状态检测通过，得分: {score}")
            return True
        
        # 回退匹配：包含核心关键词和示例格式
        if (self.REGISTER_PATTERNS["keyword"].search(text) and 
            self.REGISTER_PATTERNS["example"].search(text)):
            self.log.debug("使用回退匹配：包含核心关键词和示例")
            return True
            
        self.log.debug(f"状态检测失败，得分: {score}")
        return False

    def _is_register_success(self, text: str) -> bool:
        """判断是否为注册成功消息"""
        if not text:
            return False
            
        # 计算匹配特征数量
        matched_patterns = 0
        for pattern in self.SUCCESS_PATTERNS:
            if pattern.search(text):
                matched_patterns += 1
                
        # 如果匹配到3个或更多特征，认为是成功消息
        if matched_patterns >= 3:
            self.log.debug(f"成功检测到注册成功消息，匹配特征: {matched_patterns}")
            return True
            
        # 回退匹配：包含"创建用户成功"核心关键词
        if "创建用户成功" in text:
            self.log.debug("使用回退匹配：包含'创建用户成功'")
            return True
            
        return False

    def _log_registration_details(self, text: str):
        """提取并记录注册详情"""
        try:
            # 提取用户名
            username_match = re.search(r"用户名称\s*\|\s*([^\n]+)", text)
            if username_match:
                username = username_match.group(1).strip()
                self.log.info(f"注册用户名: {username}")
                
            # 提取用户密码
            password_match = re.search(r"用户密码\s*\|\s*([^\n]+)", text)
            if password_match:
                password = password_match.group(1).strip()
                self.log.info(f"用户密码: {password}")
                
            # 提取安全密码
            security_match = re.search(r"安全密码\s*\|\s*([^\n]+)", text)
            if security_match:
                security_code = security_match.group(1).strip()
                self.log.info(f"安全密码: {security_code} (仅发送一次，请妥善保存)")
                
            # 提取到期时间
            expiry_match = re.search(r"到期时间\s*\|\s*([^\n]+)", text)
            if expiry_match:
                expiry_time = expiry_match.group(1).strip()
                self.log.info(f"到期时间: {expiry_time}")
                
        except Exception as e:
            self.log.warning(f"提取注册详情时出错: {e}")

    def _validate_credentials(self) -> bool:
        """验证用户名和安全码格式"""
        # 安全码验证：4-6位数字
        if not re.fullmatch(r"\d{4,6}", self.password):
            self.log.error(f"安全码格式错误: {self.password}（需4-6位数字）")
            return False

        # 用户名验证
        if len(self.username) < 1 or len(self.username) > 30:
            self.log.error(f"用户名长度无效: {self.username}（1-30个字符）")
            return False

        # 检查是否包含明显危险字符
        dangerous_chars = ['@', '#', '$', '%', '&', '*', '\\', '/', '<', '>']
        if any(char in self.username for char in dangerous_chars):
            self.log.error(f"用户名包含危险字符: {self.username}")
            return False

        self.log.debug("用户名和安全码格式验证通过")
        return True
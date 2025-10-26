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
        """改进的注册尝试方法，使用优化的状态检测和立即发送凭据"""
        self.log.info("开始注册流程...")
        
        # 查找创建账户按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button.text
                    self.log.info(f"找到按钮: {create_button}")
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到创建账户按钮, 无法注册.")
            return False

        # 保存原始消息信息
        original_chat_id = panel.chat.id
        original_message_id = panel.id
        
        # 点击按钮
        try:
            self.log.info("点击创建账户按钮...")
            await panel.click(create_button)
            self.log.info("按钮点击完成")
        except Exception as e:
            self.log.error(f"点击按钮时出错: {e}")
            return False

        # 使用标志确保只发送一次凭据
        credentials_sent = False
        
        # 等待响应
        start_time = asyncio.get_event_loop().time()
        timeout = 30  # 30秒超时
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # 1. 尝试获取新消息
                new_messages = await self.client.get_messages(original_chat_id, limit=10)
                for msg in new_messages:
                    if msg.id > original_message_id:  # 是新消息
                        text = msg.text or msg.caption or ""
                        
                        # 详细记录每条新消息，帮助调试
                        self.log.debug(f"检查新消息 ID{msg.id}: {text}")
                        
                        # 检查是否是注册状态消息
                        if self._is_register_state_optimized(text) and not credentials_sent:
                            self.log.info("检测到注册状态，立即发送凭据!")
                            await self._send_credentials_immediately(msg, f"{self.username} {self.password}")
                            credentials_sent = True
                            # 继续等待结果
                            continue
                
                # 2. 检查原消息是否被编辑
                current_panel = await self.client.get_messages(original_chat_id, ids=original_message_id)
                if current_panel:
                    original_text = panel.text or panel.caption or ""
                    current_text = current_panel.text or current_panel.caption or ""
                    
                    if original_text != current_text and not credentials_sent:
                        # 检查编辑后的消息是否是注册状态
                        self.log.debug(f"检查编辑消息: {current_text}")
                        if self._is_register_state_optimized(current_text):
                            self.log.info("通过编辑消息检测到注册状态，立即发送凭据!")
                            await self._send_credentials_immediately(current_panel, f"{self.username} {self.password}")
                            credentials_sent = True
                            # 继续等待结果
                
                # 如果已经发送了凭据，等待结果
                if credentials_sent:
                    # 检查是否有注册结果
                    result_messages = await self.client.get_messages(original_chat_id, limit=5)
                    for msg in result_messages:
                        if msg.id > original_message_id:
                            result_text = msg.text or msg.caption or ""
                            self.log.debug(f"检查结果消息: {result_text}")
                            if any(success in result_text for success in ["创建用户成功", "注册成功", "成功"]):
                                self.log.info("注册成功!")
                                return True
                            elif any(failure in result_text for failure in ["失败", "错误", "已存在", "已注册"]):
                                self.log.warning(f"注册失败: {result_text}")
                                return False
                    
                    # 如果已经等待了一段时间还没有结果，假设成功
                    if (asyncio.get_event_loop().time() - start_time) > 15 and credentials_sent:
                        self.log.info("已发送凭据但未收到明确结果，假设注册成功")
                        return True

                # 短暂等待后继续检查
                await asyncio.sleep(1)
                
            except Exception as e:
                self.log.error(f"等待响应时出错: {e}")
                await asyncio.sleep(1)

        # 如果超时但已经发送了凭据，假设成功
        if credentials_sent:
            self.log.info("超时但已发送凭据，假设注册成功")
            return True
        
        self.log.warning("未能在超时时间内检测到注册状态")
        # 添加调试信息
        try:
            latest_messages = await self.client.get_messages(original_chat_id, limit=5)
            latest_ids = [msg.id for msg in latest_messages]
            self.log.error(f"调试信息: 原始消息ID={original_message_id}, 最新消息IDs={latest_ids}")
            
            # 记录最新消息内容
            for msg in latest_messages:
                if msg.id > original_message_id:
                    content = msg.text or msg.caption or ""
                    self.log.error(f"新消息ID{msg.id}内容: {content}")
        except Exception as e:
            self.log.error(f"获取调试信息时出错: {e}")
            
        return False

    def _is_register_state_optimized(self, text: str) -> bool:
        """优化的注册状态检测 - 使用更全面的匹配条件"""
        if not text:
            return False
        
        # 注册状态的关键特征 - 使用更全面的匹配
        register_indicators = [
            "您已进入注册状态",
            "进入注册状态",
            "注册状态",
            "输入 [用户名][空格][安全码]",
            "用户名][空格][安全码",
            "请在2min内输入",
            "2min内输入",
            "举个例子",
            "苏苏 1234",
            "用户名中不限制",
            "安全码为敏感操作",
            "分钟内输入",
            "用户名",
            "安全码",
            "2min",
            "2分钟",
            "举例",
            "苏苏",
            "请在",
            "🌰",
            "退出请点 /cancel"
        ]
        
        # 检查是否包含足够多的注册相关关键词
        found_count = 0
        found_keywords = []
        for indicator in register_indicators:
            if indicator in text:
                found_count += 1
                found_keywords.append(indicator)
        
        # 如果有至少2个关键词匹配，就认为是注册状态
        if found_count >= 2:
            self.log.info(f"检测到注册状态，匹配到 {found_count} 个关键词: {found_keywords}")
            return True
        
        # 特殊检查：包含特定组合
        if ("用户名" in text and "安全码" in text) or ("输入" in text and "用户名" in text):
            self.log.info("检测到用户名和安全码组合，确认为注册状态")
            return True
        
        # 如果只有一个关键词，但包含关键短语，也认为是注册状态
        if found_count == 1 and any(keyword in text for keyword in ["您已进入注册状态", "输入 [用户名][空格][安全码]"]):
            self.log.info("检测到关键短语，确认为注册状态")
            return True
        
        # 记录未匹配但包含部分关键词的情况
        if found_count > 0:
            self.log.debug(f"发现部分关键词但未达到阈值: {found_keywords}")
        
        return False

    async def _send_credentials_immediately(self, message: Message, credentials: str):
        """立即发送注册凭据 - 不等待任何确认"""
        try:
            self.log.info(f"立即发送注册凭据: {credentials}")
            await self.client.send_message(message.chat.id, credentials)
            self.log.info("注册凭据已发送!")
        except Exception as e:
            self.log.error(f"发送注册凭据时出错: {e}")

    async def debug_attempt(self, panel: Message):
        """调试版本的注册尝试，记录所有可能的信息"""
        self.log.info("=== 开始调试注册流程 ===")
        
        # 记录初始状态
        self.log.info(f"初始消息 ID: {panel.id}")
        self.log.info(f"初始消息内容: {panel.text or panel.caption}")
        self.log.info(f"按钮: {[[btn.text for btn in row] for row in panel.reply_markup.inline_keyboard]}")
        
        # 点击按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = next(
            (btn for row in buttons for btn in row if "创建账户" in btn.text), 
            None
        )
        
        if not create_button:
            self.log.error("未找到创建账户按钮")
            return False
        
        self.log.info(f"点击按钮: {create_button.text}")
        
        try:
            # 点击前截图状态
            before_messages = await self.client.get_messages(panel.chat.id, limit=3)
            self.log.info(f"点击前最新{len(before_messages)}条消息ID: {[msg.id for msg in before_messages]}")
            
            # 点击按钮
            await panel.click(create_button.text)
            self.log.info("按钮点击完成")
            
            # 等待并监控变化
            for i in range(15):  # 监控15次，每次2秒
                await asyncio.sleep(2)
                
                current_messages = await self.client.get_messages(panel.chat.id, limit=5)
                self.log.info(f"轮询 {i+1}: 最新消息ID: {[msg.id for msg in current_messages]}")
                
                # 检查新消息
                new_msgs = [msg for msg in current_messages if msg.id > panel.id]
                for msg in new_msgs:
                    content = msg.text or msg.caption or ""
                    self.log.info(f"新消息 ID{msg.id}: {content}")
                    if self._is_register_state_optimized(content):
                        self.log.info("!!! 检测到注册状态 !!!")
                        await self._send_credentials_immediately(msg, f"{self.username} {self.password}")
                        return True
                
                # 检查编辑消息
                try:
                    current_panel = await self.client.get_messages(panel.chat.id, ids=panel.id)
                    if current_panel and (current_panel.text != panel.text):
                        self.log.info(f"原消息被编辑: {current_panel.text}")
                        if self._is_register_state_optimized(current_panel.text):
                            self.log.info("!!! 通过编辑消息检测到注册状态 !!!")
                            await self._send_credentials_immediately(current_panel, f"{self.username} {self.password}")
                            return True
                except Exception as e:
                    self.log.debug(f"检查编辑消息时出错: {e}")
                    
            self.log.error("调试: 在30秒内未检测到注册状态")
            return False
            
        except Exception as e:
            self.log.error(f"调试过程中出错: {e}")
            return False
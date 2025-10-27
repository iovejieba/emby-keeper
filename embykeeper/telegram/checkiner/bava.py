import asyncio
import random
import re
from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid, FloodWait

from ._templ_a import TemplateACheckin

class BavaCheckin(TemplateACheckin):
    name = "ME"
    bot_username = "hibavabot"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._remaining_times = 0  # 剩余签到次数
        self._completed_times = 0  # 已签到次数
        self._has_sent_start = False  # 防止重复发送start
        self._waiting_for_f1 = False  # 等待F1按钮出现
    
    async def message_handler(self, client, message: Message):
        # 只处理来自目标机器人的消息
        if message.from_user and message.from_user.username != self.bot_username:
            return
            
        chat_id = message.chat.id
        
        # 发送 /start 命令（只在初始状态）
        if not self._has_sent_start:
            await self._send_start_command(client, chat_id)
            self._has_sent_start = True
            self._waiting_for_f1 = True
            return
        
        # 如果正在等待F1按钮，检查消息中是否有F1按钮
        if self._waiting_for_f1:
            await self._check_for_f1_button(client, message)
            return
        
        # 解析剩余次数
        self._parse_remaining_times(message)
        
        # 检查是否已完成所有签到
        if self._remaining_times <= 0 and self._completed_times > 0:
            self.log.info("今日签到已完成")
            return await self.on_checkin_success(client, message)
        
        # 处理其他按钮
        await self._handle_other_buttons(client, message)
    
    async def _send_start_command(self, client, chat_id):
        """发送 /start 命令"""
        try:
            await client.send_message(chat_id, "/start")
            self.log.info("已发送 /start 命令，等待F1按钮出现...")
        except Exception as e:
            self.log.error(f"发送 /start 命令失败: {e}")
            await self.fail()
    
    async def _check_for_f1_button(self, client, message: Message):
        """检查消息中是否有F1按钮"""
        if not message.reply_markup:
            return
            
        buttons = self._get_all_buttons(message)
        self.log.debug(f"检查F1按钮，当前按钮: {buttons}")
        
        # 模糊查找F1按钮
        f1_button = self._find_f1_button(buttons)
        if f1_button:
            self.log.info(f"找到F1按钮: {f1_button}")
            self._waiting_for_f1 = False
            await self._click_button(client, message, f1_button, "F1")
        else:
            self.log.debug("未找到F1按钮，继续等待...")
    
    def _find_f1_button(self, buttons):
        """模糊查找F1按钮，可能包含表情符号"""
        for button_text in buttons:
            # 检查是否包含F1（不区分大小写）
            if "f1" in button_text.lower():
                return button_text
            
            # 检查是否包含常见的赛车或签到相关表情符号
            racing_emojis = ["🏎", "🏁", "🚗", "🚙", "🚘", "🚀", "⭐", "🌟", "✨"]
            for emoji in racing_emojis:
                if emoji in button_text and any(word in button_text.lower() for word in ["签到", "签", "check", "start"]):
                    return button_text
            
            # 检查是否包含签到相关词汇
            if any(word in button_text.lower() for word in ["签到", "签", "check", "start", "begin"]):
                return button_text
        
        return None
    
    async def _handle_other_buttons(self, client, message: Message):
        """处理F1之外的其他按钮"""
        if not message.reply_markup:
            return
            
        buttons = self._get_all_buttons(message)
        
        # 检测"准备好了"按钮
        ready_button = self._find_button(buttons, ["准备好了", "开始"])
        if ready_button:
            await self._click_button(client, message, ready_button, "准备好了")
            return
        
        # 检测"加速吧"按钮
        accelerate_button = self._find_button(buttons, ["加速吧", "加速"])
        if accelerate_button:
            await self._continuous_click(client, message, accelerate_button)
            return
        
        # 检测"继续冲刺"按钮
        continue_button = self._find_button(buttons, ["继续冲刺", "继续"])
        if continue_button:
            await self._click_button(client, message, continue_button, "继续冲刺")
            return
    
    def _get_all_buttons(self, message: Message):
        """提取所有按钮文本"""
        buttons = []
        if message.reply_markup and message.reply_markup.inline_keyboard:
            for row in message.reply_markup.inline_keyboard:
                for button in row:
                    if button.text:
                        buttons.append(button.text)
        return buttons
    
    def _find_button(self, buttons, keywords):
        """根据关键词列表查找按钮"""
        for button_text in buttons:
            for keyword in keywords:
                if keyword in button_text:
                    return button_text
        return None
    
    async def _click_button(self, client, message: Message, button_text, button_name):
        """点击按钮"""
        await asyncio.sleep(random.uniform(1.0, 2.0))
        try:
            await message.click(button_text)
            self.log.info(f"已点击 {button_name} 按钮")
            # 等待机器人响应
            await asyncio.sleep(4)
        except (TimeoutError, MessageIdInvalid) as e:
            self.log.debug(f"点击 {button_name} 按钮时出现异常: {e}")
        except Exception as e:
            self.log.error(f"点击 {button_name} 按钮失败: {e}")
            await self.fail()
    
    def _parse_remaining_times(self, message: Message):
        """从消息中解析剩余签到次数"""
        text = message.text or message.caption or ""
        
        # 多种可能的格式
        patterns = [
            r'剩余次数[:：]\s*(\d+)/(\d+)',
            r'今日剩余次数[:：]\s*(\d+)/(\d+)',
            r'剩余[:：]\s*(\d+)/(\d+)',
            r'可签到[:：]\s*(\d+)/(\d+)',
            r'(\d+)\s*/\s*(\d+)\s*次'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                remaining = int(match.group(1))
                total = int(match.group(2))
                if remaining != self._remaining_times:  # 只在次数变化时记录
                    self.log.info(f"解析到剩余签到次数: {remaining}/{total}")
                    self._remaining_times = remaining
                return
        
        # 如果没有找到剩余次数，但文本包含特定关键词，尝试其他方式解析
        if "剩余" in text or "次数" in text:
            self.log.debug(f"可能包含次数信息的文本: {text[:100]}")
    
    async def _continuous_click(self, client, message: Message, button_text: str):
        """连续点击按钮"""
        self.log.info(f"第 {self._completed_times + 1} 次签到 - 开始快速连点")
        
        click_count = 0
        max_clicks = 50  # 最大点击次数，避免无限循环
        
        while click_count < max_clicks:
            try:
                # 快速连点，间隔较短
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await message.click(button_text)
                click_count += 1
                
                if click_count % 10 == 0:  # 每10次点击记录一次
                    self.log.info(f"第 {self._completed_times + 1} 次签到 - 已连续点击 {click_count} 次")
                    
            except MessageIdInvalid:
                self.log.info("消息已失效，停止点击")
                break
            except FloodWait as e:
                self.log.warning(f"触发 FloodWait，等待 {e.value} 秒")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                self.log.error(f"点击过程中出现错误: {e}")
                break
        
        self.log.info(f"第 {self._completed_times + 1} 次签到 - 连续点击完成，总共点击 {click_count} 次")
        
        # 完成一次签到
        self._completed_times += 1
        self._remaining_times -= 1
        
        # 等待机器人响应
        await asyncio.sleep(4)
        
        # 检查是否还有更多签到次数
        if self._remaining_times > 0:
            self.log.info(f"准备第 {self._completed_times + 1} 次签到，剩余 {self._remaining_times} 次")
        else:
            # 所有签到完成
            self.log.info(f"已完成所有 {self._completed_times} 次签到")
            await self.on_checkin_success(client, message)
    
    async def on_checkin_success(self, client, message: Message):
        """签到成功回调"""
        # 重置状态，以备下次使用
        self._remaining_times = 0
        self._completed_times = 0
        self._has_sent_start = False
        self._waiting_for_f1 = False
        await super().on_checkin_success(client, message)
    
    async def on_checkin_failed(self, client, message: Message):
        """签到失败回调"""
        # 重置状态，以备下次使用
        self._remaining_times = 0
        self._completed_times = 0
        self._has_sent_start = False
        self._waiting_for_f1 = False
        await super().on_checkin_failed(client, message)
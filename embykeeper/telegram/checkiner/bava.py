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
        # 状态跟踪
        self._current_state = "start"  # start -> f1_clicked -> ready_clicked -> clicking -> waiting_for_continue
        self._remaining_times = 0  # 剩余签到次数
        self._completed_times = 0  # 已签到次数
    
    async def message_handler(self, client, message: Message):
        chat_id = message.chat.id
        
        # 发送 /start 命令（只在初始状态）
        if self._current_state == "start":
            await self._send_start_command(client, chat_id)
            self._current_state = "waiting_for_panel"
            return
        
        # 处理面板信息和按钮
        await self._handle_panel_flow(client, message)
    
    async def _send_start_command(self, client, chat_id):
        """发送 /start 命令"""
        try:
            await client.send_message(chat_id, "/start")
            self.log.info("已发送 /start 命令")
            # 等待机器人响应
            await asyncio.sleep(2)
        except Exception as e:
            self.log.error(f"发送 /start 命令失败: {e}")
            await self.fail()
    
    async def _handle_panel_flow(self, client, message: Message):
        """处理面板流程"""
        if not message.reply_markup:
            return await super().message_handler(client, message)
        
        # 获取所有按钮文本
        buttons = self._get_all_buttons(message)
        
        # 解析剩余次数
        self._parse_remaining_times(message)
        
        # 检查是否已完成所有签到
        if self._remaining_times <= 0 and self._completed_times > 0:
            self.log.info("今日剩余次数为0，签到完成")
            self._current_state = "completed"
            return await self.on_checkin_success(client, message)
        
        # 根据当前状态处理不同的按钮
        if self._current_state == "waiting_for_panel":
            await self._handle_f1_button(message, buttons)
        
        elif self._current_state == "f1_clicked":
            await self._handle_ready_button(message, buttons)
        
        elif self._current_state == "ready_clicked":
            await self._handle_accelerate_button(message, buttons)
        
        elif self._current_state == "waiting_for_continue":
            await self._handle_continue_button(message, buttons)
    
    def _get_all_buttons(self, message: Message):
        """提取所有按钮文本"""
        buttons = []
        if message.reply_markup and message.reply_markup.inline_keyboard:
            for row in message.reply_markup.inline_keyboard:
                for button in row:
                    if button.text:
                        buttons.append(button.text)
        return buttons
    
    def _parse_remaining_times(self, message: Message):
        """从消息中解析剩余签到次数"""
        # 获取消息文本
        text = message.text or message.caption or ""
        
        # 使用正则表达式匹配剩余次数模式，如 "今日剩余次数: 3/3" 或 "剩余次数: 2/3"
        pattern = r'剩余次数[:：]\s*(\d+)/(\d+)'
        match = re.search(pattern, text)
        
        if match:
            remaining = int(match.group(1))  # 剩余次数
            total = int(match.group(2))      # 总次数
            self.log.info(f"解析到剩余签到次数: {remaining}/{total}")
            self._remaining_times = remaining
            return remaining
        else:
            # 尝试其他可能的格式
            patterns = [
                r'今日剩余次数[:：]\s*(\d+)/(\d+)',
                r'剩余[:：]\s*(\d+)/(\d+)',
                r'可签到[:：]\s*(\d+)/(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    remaining = int(match.group(1))
                    total = int(match.group(2))
                    self.log.info(f"解析到剩余签到次数: {remaining}/{total}")
                    self._remaining_times = remaining
                    return remaining
            
            self.log.warning("未找到剩余次数信息")
            return 0
    
    async def _handle_f1_button(self, message: Message, buttons: list):
        """处理 F1 按钮"""
        f1_button = None
        for button_text in buttons:
            if "F1" in button_text.upper():
                f1_button = button_text
                break
        
        if f1_button:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            try:
                await message.click(f1_button)
                self.log.info(f"已点击 F1 按钮，今日剩余签到次数: {self._remaining_times}")
                self._current_state = "f1_clicked"
                # 等待按钮状态更新
                await asyncio.sleep(2)
            except (TimeoutError, MessageIdInvalid) as e:
                self.log.debug(f"点击 F1 按钮时出现异常: {e}")
            except Exception as e:
                self.log.error(f"点击 F1 按钮失败: {e}")
                await self.fail()
        else:
            self.log.debug("未找到 F1 按钮，继续等待...")
    
    async def _handle_ready_button(self, message: Message, buttons: list):
        """处理 '准备好了' 按钮"""
        ready_button = None
        for button_text in buttons:
            if "准备好了" in button_text:
                ready_button = button_text
                break
        
        if ready_button:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            try:
                await message.click(ready_button)
                self.log.info(f"第 {self._completed_times + 1} 次签到 - 已点击 '准备好了' 按钮")
                self._current_state = "ready_clicked"
                # 等待按钮变成 '加速吧'
                await asyncio.sleep(3)
            except (TimeoutError, MessageIdInvalid) as e:
                self.log.debug(f"点击 '准备好了' 按钮时出现异常: {e}")
            except Exception as e:
                self.log.error(f"点击 '准备好了' 按钮失败: {e}")
                await self.fail()
        else:
            self.log.debug("未找到 '准备好了' 按钮，继续等待...")
    
    async def _handle_accelerate_button(self, message: Message, buttons: list):
        """处理 '加速吧' 按钮并进行快速连点"""
        accelerate_button = None
        for button_text in buttons:
            if "加速吧" in button_text:
                accelerate_button = button_text
                break
        
        if accelerate_button:
            self.log.info(f"第 {self._completed_times + 1} 次签到 - 开始快速连点 '加速吧' 按钮...")
            await self._continuous_click(message, accelerate_button)
        else:
            self.log.debug("未找到 '加速吧' 按钮，继续等待...")
    
    async def _handle_continue_button(self, message: Message, buttons: list):
        """处理 '继续冲刺' 按钮"""
        continue_button = None
        for button_text in buttons:
            if "继续冲刺" in button_text:
                continue_button = button_text
                break
        
        if continue_button:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            try:
                await message.click(continue_button)
                self.log.info(f"已点击 '继续冲刺' 按钮，准备第 {self._completed_times + 1} 次签到")
                self._current_state = "ready_clicked"
                # 等待按钮变成 '加速吧'
                await asyncio.sleep(3)
            except (TimeoutError, MessageIdInvalid) as e:
                self.log.debug(f"点击 '继续冲刺' 按钮时出现异常: {e}")
            except Exception as e:
                self.log.error(f"点击 '继续冲刺' 按钮失败: {e}")
                await self.fail()
        else:
            self.log.debug("未找到 '继续冲刺' 按钮，继续等待...")
    
    async def _continuous_click(self, message: Message, button_text: str):
        """连续点击按钮"""
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
        
        # 检查是否还有更多签到次数
        if self._remaining_times > 0:
            self.log.info(f"准备第 {self._completed_times + 1} 次签到，剩余 {self._remaining_times} 次")
            # 设置状态为等待继续冲刺按钮
            self._current_state = "waiting_for_continue"
            # 等待按钮更新为"继续冲刺"
            await asyncio.sleep(3)
        else:
            # 所有签到完成
            self._current_state = "completed"
            self.log.info(f"已完成所有 {self._completed_times} 次签到")
            await self.on_checkin_success(client, message)
    
    async def on_checkin_success(self, client, message: Message):
        """签到成功回调"""
        # 重置状态，以备下次使用
        self._current_state = "start"
        self._remaining_times = 0
        self._completed_times = 0
        await super().on_checkin_success(client, message)
    
    async def on_checkin_failed(self, client, message: Message):
        """签到失败回调"""
        # 重置状态，以备下次使用
        self._current_state = "start"
        self._remaining_times = 0
        self._completed_times = 0
        await super().on_checkin_failed(client, message)
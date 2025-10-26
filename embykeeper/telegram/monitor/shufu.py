import asyncio
import re
from typing import Optional, Union, List, Tuple
from pydantic import BaseModel, ValidationError
from loguru import logger
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid, FloodWait

from embykeeper.utils import async_partial, show_exception

from . import Monitor

__ignore__ = True


class ShufuMonitorConfig(BaseModel):
    name: str = "叔服"
    chat_name: Union[str, int] = -1001890341413  # 监控群聊
    chat_keyword: str = r"SHUFU-\d+-Register_[\w]+"  # 注册码正则
    bot_username: str = "dashu660_bot"  # 机器人用户名
    notify_create_name: bool = True
    additional_auth: List[str] = ["prime"]
    security_code: Optional[str] = None  # 自定义安全码
    register_max_attempts: int = 3  # 单个个码重试次数（可配置）
    code_send_timeout: int = 10  # 发送送注册码超时（可配置）
    post_code_wait: float = 1.5  # 等待响应时间（可配置）
    register_btn_keywords: List[str] = ["注册", "开始注册", "确认注册"]  # 按钮关键词（可配置）


class ShufuMonitor(Monitor):
    init_first = True  # 优先加载配置

    async def init(self) -> bool:
        """初始化配置，支持从config.ini读取参数"""
        try:
            self.t_config = ShufuMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"叔服监控器配置错误\n{e}")
            return False

        # 加载配置参数（覆盖默认值）
        self.name = self.t_config.name
        self.chat_name = self.t_config.chat_name
        self.chat_keyword = self.t_config.chat_keyword
        self.bot_username = self.t_config.bot_username
        self.security_code = self.t_config.security_code
        self.register_max_attempts = self.t_config.register_max_attempts
        self.code_send_timeout = self.t_config.code_send_timeout
        self.post_code_wait = self.t_config.post_code_wait
        self.register_btn_keywords = self.t_config.register_btn_keywords

        # 初始化注册ID信息
        self.unique_name = self.get_unique_name()
        unique_type = "自定义" if self.config.get("unique_name") else "自动生成"
        self.log.info(
            f"叔服监控器初始化完成：\n"
            f"- 注册ID（{unique_type}）：{self.unique_name}\n"
            f"- 安全码：{'已配置' if self.security_code else '未配置'}\n"
            f"- 单个码重试次数：{self.register_max_attempts}\n"
            f"- 发送超时时间：{self.code_send_timeout}秒\n"
            f"- 响应等待时间：{self.post_code_wait}秒"
        )
        return True

    def _extract_valid_codes(self, raw_key: str) -> List[str]:
        """提取所有有效注册码（多行文本处理）"""
        if not raw_key:
            return []
        lines = [line.strip() for line in raw_key.split("\n") if line.strip()]
        valid_codes = []
        seen = set()
        for line in lines:
            if re.match(self.chat_keyword, line, re.IGNORECASE) and line not in seen:
                valid_codes.append(line)
                seen.add(line)
        return valid_codes

    async def on_trigger(self, message: Message, key: str, reply: str) -> None:
        """多注册码依次尝试入口"""
        valid_codes = self._extract_valid_codes(key)
        if not valid_codes:
            self.log.warning(f"未提取到有效注册码（原始内容：{key[:50]}...）")
            return

        self.log.info(f"共提取到 {len(valid_codes)} 个有效注册码，依次依次尝试：")
        for i, code in enumerate(valid_codes, 1):
            self.log.info(f"  第{i}个：{code}")

        # 依次尝试每个注册码
        for code_idx, code in enumerate(valid_codes, 1):
            self.log.info(f"\n===== 开始尝试第 {code_idx}/{len(valid_codes)} 个注册码：{code} =====")
            wr = async_partial(self.client.wait_reply, self.bot_username)

            if await self._try_single_code(code, wr):
                self.log.success(f"第 {code_idx} 个注册码抢注成功，流程结束")
                return
            else:
                self.log.info(f"第 {code_idx} 个注册码尝试失败，准备下一个（间隔0.3秒）")
                await asyncio.sleep(0.3)

        self.log.bind(msg=True).warning(f"所有 {len(valid_codes)} 个注册码均尝试失败，请手动操作")

    async def _try_single_code(self, code: str, wr) -> bool:
        """尝试单个注册码的完整流程"""
        for attempt in range(1, self.register_max_attempts + 1):
            self.log.debug(f"当前码第 {attempt}/{self.register_max_attempts} 次尝试")
            try:
                # 步骤1：发送/start初始化
                start_msg: Message = await wr("/start", timeout=5)
                if "请确认好重试" in (start_msg.text or start_msg.caption):
                    self.log.debug("机器人要求重试，跳过本次")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤2：查找“使用注册码”按钮
                use_code_btn = self._find_use_code_button(start_msg)
                if not use_code_btn:
                    self.log.warning("未找到“使用注册码”按钮，重试...")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤3：点击按钮并等待输入提示（使用配置的超时）
                prompt_msg = await self._click_and_wait_prompt(use_code_btn, start_msg)
                if not prompt_msg:
                    self.log.warning("未收到输入提示，重试...")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤4：发送注册码
                if not await self._send_registration_code(code, wr):
                    continue

                # 步骤5：判断注册码状态（使用配置的等待时间）
                code_status, btn_msg = await self._check_code_status(wr)
                if code_status == "used":
                    self.log.info(f"当前注册码 {code} 已被使用，停止尝试")
                    return False
                elif code_status == "valid" and btn_msg:
                    self.log.info(f"当前注册码 {code} 有效，检测到注册按钮")
                    if not await self._click_register_button(btn_msg):
                        self.log.warning("点击注册按钮失败，重试...")
                        continue
                    await self._complete_registration(wr)
                    return True
                else:
                    self.log.warning(f"当前注册码 {code} 无效，重试...")
                    continue

            except FloodWait as e:
                self.log.warning(f"频率限制，等待 {e.x} 秒")
                await asyncio.sleep(e.x)
            except Exception as e:
                self.log.error(f"当前码第 {attempt} 次异常：")
                show_exception(e, regular=False)
                await asyncio.sleep(0.5)

        self.log.info(f"当前注册码 {code} 尝试 {self.register_max_attempts} 次失败")
        return False

    def _find_use_code_button(self, msg: Message) -> Optional[str]:
        """查找“使用注册码”按钮"""
        if not msg.reply_markup or not msg.reply_markup.inline_keyboard:
            return None
        for row in msg.reply_markup.inline_keyboard:
            for btn in row:
                if "使用注册码" in btn.text or "注册/续期码" in btn.text:
                    return btn.text
        return None

    async def _click_and_wait_prompt(self, btn_text: str, msg: Message) -> Optional[Message]:
        """点击按钮并等待输入提示（使用配置的超时）"""
        try:
            async with self.client.catch_reply(
                self.bot_username,
                filter=filters.regex(r"请发送注册码|120s内发送|形如SHUFU-"),
                timeout=self.code_send_timeout
            ) as f:
                await msg.click(btn_text)
                return await f
        except asyncio.TimeoutError:
            self.log.warning(f"点击按钮后 {self.code_send_timeout} 秒未收到提示，超时")
            return None
        except MessageIdInvalid:
            self.log.warning("按钮已失效，无法点击")
            return None

    async def _send_registration_code(self, code: str, wr) -> bool:
        """发送注册码"""
        try:
            self.log.info(f"发送注册码：{code}")
            await self.client.send_message(self.bot_username, code)
            return True
        except Exception as e:
            self.log.error(f"发送注册码失败：{e}")
            return False

    async def _check_code_status(self, wr) -> Tuple[str, Optional[Message]]:
        """判断注册码状态（使用配置的等待时间）"""
        await asyncio.sleep(self.post_code_wait)
        try:
            resp: Message = await wr(timeout=3)
            text = (resp.text or resp.caption or "").lower()
            has_buttons = bool(resp.reply_markup and resp.reply_markup.inline_keyboard)
            self.log.debug(f"机器人响应：{text}，是否有按钮：{has_buttons}")

            if has_buttons:
                has_register_btn = any(
                    any(kw in btn.text.lower() for kw in self.register_btn_keywords)
                    for row in resp.reply_markup.inline_keyboard
                    for btn in row
                )
                return ("valid", resp) if has_register_btn else ("invalid", None)
            else:
                self.log.debug("机器人回复无按钮，确认注册码已被使用")
                return ("used", None)

        except asyncio.TimeoutError:
            self.log.debug(f"等待{self.post_code_wait}秒+响应超时，疑似注册码已被使用（可能网络延迟）")
            return ("used", None)

    async def _click_register_button(self, btn_msg: Message) -> bool:
        """点击注册按钮"""
        try:
            target_btn = None
            for row in btn_msg_msg.reply_markup.inline_keyboard:
                for btn in row:
                    if any(kw in btn.text.lower() for kw in self.register_btn_keywords):
                        target_btn = btn.text
                        break
                if target_btn:
                    break

            if not target_btn:
                self.log.warning(f"未找到注册按钮（关键词：{self.register_btn_keywords}）")
                return False

            self.log.info(f"点击“{target_btn}”按钮，进入注册流程")
            async with self.client.catch_reply(
                self.bot_username,
                filter=filters.regex(r"请输入用户名|设置安全码|下一步"),
                timeout=10
            ) as f:
                await btn_msg.click(target_btn)
                await f
                return True

        except asyncio.TimeoutError:
            self.log.warning("点击注册按钮后10秒超时")
            return False
        except MessageIdInvalid:
            self.log.warning("注册按钮已失效")
            return False
        except Exception as e:
            self.log.error(f"点击注册按钮异常：{e}")
            return False

    async def _complete_registration(self, wr) -> None:
        """完成注册（用户名+安全码）"""
        try:
            # 输入用户名
            self.log.info("等待输入用户名提示...")
            username_prompt = await wr(timeout=8)
            if "请输入用户名" in (username_prompt.text or username_prompt.caption):
                self.log.info(f"发送用户名：{self.unique_name}")
                resp = await wr(self.unique_name, timeout=8)
                if "用户名已存在" in (resp.text or resp.caption):
                    self.log.warning(f"用户名 {self.unique_name} 已存在")
                    return

            # 输入安全码
            if self.security_code:
                self.log.info("等待输入安全码提示...")
                security_prompt = await wr(timeout=8)
                if "安全码" in (security_prompt.text or security_prompt.caption):
                    self.log.info(f"发送安全码：{self.security_code}")
                    resp = await wr(self.security_code, timeout=8)
                    if "安全码不符合要求" in (resp.text or resp.caption):
                        self.log.warning(f"安全码 {self.security_code} 不符合要求")
                        return

            # 确认结果
            final_resp = await wr(timeout=10)
            if "注册成功" in (final_resp.text or final_resp.caption):
                self.log.bind(msg=True).success(
                    f"✅ 叔服注册成功！\n"
                    f"- 注册ID：{self.unique_name}\n"
                    f"- 安全码：{self.security_code or '未配置'}"
                )
            else:
                self.log.bind(msg=True).warning(
                    f"❌ 注册流程完成，响应：{final_resp.text or final_resp.caption}"
                )
        except Exception as e:
            self.log.error(f"注册流程异常：")
            show_exception(e, regular=False)
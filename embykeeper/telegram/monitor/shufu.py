import asyncio
import re
import random
import string
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
    name: str = "叔服"  # 确保默认值为有效字符串
    chat_name: Union[str, int] = -1001890341413  # 监控群聊
    chat_keyword: str = r"SHUFU-\d+-Register_[\w]+"  # 注册码正则
    bot_username: str = "dashu660_bot"  # 机器人用户名
    security_code: Optional[str] = None  # 自定义安全码
    register_max_attempts: int = 3  # 单个码重试次数
    code_send_timeout: int = 10  # 发送注册码超时
    post_code_wait: float = 1.5  # 响应等待时间
    register_btn_keywords: List[str] = ["注册", "开始注册", "确认注册"]  # 按钮关键词
    username_retry_count: int = 2  # 用户名重复重试次数
    random_suffix_length: int = 4  # 用户名随机后缀长度


class ShufuMonitor(Monitor):
    init_first = True  # 优先加载配置

    async def init(self) -> bool:
        """初始化配置，强制确保name为有效字符串（核心修复）"""
        # 1. 初始化兜底name，防止任何流程导致name为None
        self.name = "叔服"  # 最终保底值

        try:
            # 2. 验证配置
            self.t_config = ShufuMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"叔服监控器配置错误，使用默认名称\n{e}")
            return False

        # 3. 严格校验name有效性（非空字符串）
        config_name = self.t_config.name
        if isinstance(config_name, str) and config_name.strip():
            self.name = config_name.strip()  # 有效则使用配置值
        else:
            self.log.warning(f"配置中name无效（值：{config_name}），使用默认名称“叔服”")
            self.name = "叔服"  # 无效则强制用默认值

        # 加载其他配置参数
        self.chat_name = self.t_config.chat_name
        self.chat_keyword = self.t_config.chat_keyword
        self.bot_username = self.t_config.bot_username
        self.security_code = self.t_config.security_code
        self.register_max_attempts = self.t_config.register_max_attempts
        self.code_send_timeout = self.t_config.code_send_timeout
        self.post_code_wait = self.t_config.post_code_wait
        self.register_btn_keywords = self.t_config.register_btn_keywords
        self.username_retry_count = self.t_config.username_retry_count
        self.random_suffix_length = self.t_config.random_suffix_length

        # 初始化注册ID信息
        self.base_unique_name = self.get_unique_name()
        self.unique_name = self.base_unique_name
        unique_type = "自定义" if self.config.get("unique_name") else "自动生成"
        self.log.info(
            f"叔服监控器初始化完成：\n"
            f"- 监控器名称：{self.name}\n"  # 显式打印name，确认有效性
            f"- 基础注册ID（{unique_type}）：{self.base_unique_name}\n"
            f"- 安全码：{'已配置' if self.security_code else '未配置'}\n"
            f"- 单个码重试次数：{self.register_max_attempts}\n"
            f"- 发送超时时间：{self.code_send_timeout}秒\n"
            f"- 响应等待时间：{self.post_code_wait}秒\n"
            f"- 用户名重试次数：{self.username_retry_count}"
        )
        return True

    def _generate_random_suffix(self) -> str:
        """生成随机字符串后缀（字母+数字）"""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(self.random_suffix_length))

    def _get_alternative_username(self, retry_idx: int) -> str:
        """获取备选用户名（基础名+随机后缀）"""
        suffix = self._generate_random_suffix()
        return f"{self.base_unique_name}_{suffix}"

    def _extract_valid_codes(self, raw_key: str) -> List[str]:
        """提取所有有效注册码（修正变量名，避免与name混淆）"""
        if not raw_key:
            return []
        lines = [line.strip() for line in raw_key.split("\n") if line.strip()]
        valid_codes = []  # 原变量名valid_names易混淆，改为valid_codes
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

        self.log.info(f"共提取到 {len(valid_codes)} 个有效注册码，依次尝试：")
        for i, code in enumerate(valid_codes, 1):
            self.log.info(f"  第{i}个：{code}")

        # 依次尝试每个注册码
        for code_idx, code in enumerate(valid_codes, 1):
            self.log.info(f"\n===== 开始尝试第 {code_idx}/{len(valid_codes)} 个注册码：{code} =====")
            wr = async_partial(self.client.wait_reply, self.bot_username)

            # 每次尝试新注册码时重置用户名
            self.unique_name = self.base_unique_name
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
                start_content = start_msg.text or start_msg.caption or ""
                if "请确认好重试" in start_content:
                    self.log.debug("机器人要求重试，跳过本次")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤2：查找“使用注册码”按钮
                use_code_btn = self._find_use_code_button(start_msg)
                if not use_code_btn:
                    self.log.warning("未找到“使用注册码”或“注册/续期码”按钮，重试...")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤3：点击按钮并等待输入提示
                prompt_msg = await self._click_and_wait_prompt(use_code_btn, start_msg)
                if not prompt_msg:
                    self.log.warning("未收到输入注册码提示，重试...")
                    await asyncio.sleep(0.5)
                    continue

                # 步骤4：发送注册码
                if not await self._send_registration_code(code, wr):
                    continue

                # 步骤5：判断注册码状态
                code_status, btn_msg = await self._check_code_status(wr)
                if code_status == "used":
                    self.log.info(f"当前注册码 {code} 已被使用，停止尝试")
                    return False
                elif code_status == "valid" and btn_msg:
                    self.log.info(f"当前注册码 {code} 有效，检测到注册按钮")
                    if not await self._click_register_button(btn_msg):
                        self.log.warning("点击注册按钮失败，重试...")
                        continue
                    if await self._complete_registration(wr):
                        return True
                    else:
                        self.log.warning("注册流程未完成，重试当前注册码...")
                        continue
                else:
                    self.log.warning(f"当前注册码 {code} 无效或状态异常，重试...")
                    continue

            except FloodWait as e:
                self.log.warning(f"频率限制，等待 {e.x} 秒后继续")
                await asyncio.sleep(e.x)
            except Exception as e:
                self.log.error(f"当前码第 {attempt} 次尝试异常：")
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
        """点击按钮并等待输入提示"""
        try:
            async with self.client.catch_reply(
                self.bot_username,
                filter=filters.regex(r"请发送注册码|120s内发送|形如SHUFU-"),
                timeout=self.code_send_timeout
            ) as f:
                await msg.click(btn_text)
                prompt_msg = await f
                self.log.debug(f"收到输入提示：{prompt_msg.text or prompt_msg.caption}")
                return prompt_msg
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
            self.log.error(f"发送注册码失败：{str(e)[:50]}...")
            return False

    async def _check_code_status(self, wr) -> Tuple[str, Optional[Message]]:
        """判断注册码状态"""
        await asyncio.sleep(self.post_code_wait)
        try:
            resp: Message = await wr(timeout=3)
            resp_text = (resp.text or resp.caption or "").lower()
            has_buttons = bool(resp.reply_markup and resp.reply_markup.inline_keyboard)
            self.log.debug(f"机器人响应：{resp_text[:100]}，是否有按钮：{has_buttons}")

            # 优先通过文本判断状态
            if "已被使用" in resp_text or "已失效" in resp_text or "已过期" in resp_text:
                return ("used", None)
            if "无效" in resp_text or "错误" in resp_text or "格式不对" in resp_text:
                return ("invalid", None)

            # 文本无明确提示时，结合按钮判断
            if has_buttons:
                has_register_btn = any(
                    any(kw.lower() in (btn.text or "").lower() for kw in self.register_btn_keywords)
                    for row in resp.reply_markup.inline_keyboard
                    for btn in row
                )
                return ("valid", resp) if has_register_btn else ("invalid", None)
            else:
                self.log.debug("无按钮且无有效提示，判定注册码已被使用")
                return ("used", None)

        except asyncio.TimeoutError:
            self.log.debug(f"等待{self.post_code_wait}秒+响应超时，判定注册码已被使用")
            return ("used", None)

    async def _click_register_button(self, btn_msg: Message) -> bool:
        """点击注册按钮"""
        try:
            target_btn = None
            for row in btn_msg.reply_markup.inline_keyboard:
                for btn in row:
                    btn_text = btn.text or ""
                    if any(kw.lower() in btn_text.lower() for kw in self.register_btn_keywords):
                        target_btn = btn_text
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
            self.log.error(f"点击注册按钮异常：{str(e)[:50]}...")
            return False

    async def _complete_registration(self, wr) -> bool:
        """完成注册（用户名+安全码）"""
        try:
            # 输入用户名（支持重试）
            username_success = False
            for username_retry in range(self.username_retry_count + 1):
                self.log.info(f"等待输入用户名提示（第{username_retry+1}次尝试）...")
                username_prompt = await wr(timeout=8)
                prompt_content = username_prompt.text or username_prompt.caption or ""

                if "请输入用户名" in prompt_content:
                    self.log.info(f"发送用户名：{self.unique_name}")
                    resp = await wr(self.unique_name, timeout=8)
                    resp_content = resp.text or resp.caption or ""

                    if "用户名已存在" in resp_content:
                        if username_retry < self.username_retry_count:
                            self.unique_name = self._get_alternative_username(username_retry)
                            self.log.warning(f"用户名已存在，尝试备选：{self.unique_name}")
                            continue
                        else:
                            self.log.error(f"用户名重试 {self.username_retry_count} 次均失败")
                            return False
                    else:
                        self.log.debug(f"用户名验证通过：{resp_content[:50]}...")
                        username_success = True
                        break

            if not username_success:
                return False

            # 输入安全码（如有）
            if self.security_code:
                self.log.info("等待输入安全码提示...")
                security_prompt = await wr(timeout=8)
                prompt_content = security_prompt.text or security_prompt.caption or ""

                if "安全码" in prompt_content:
                    self.log.info(f"发送安全码：{self.security_code}")
                    resp = await wr(self.security_code, timeout=8)
                    resp_content = resp.text or resp.caption or ""

                    if "安全码不符合要求" in resp_content:
                        self.log.error(f"安全码 {self.security_code} 不符合要求")
                        return False
                    self.log.debug(f"安全码验证通过：{resp_content[:50]}...")

            # 确认最终注册结果
            final_resp = await wr(timeout=10)
            final_content = final_resp.text or final_resp.caption or ""
            if "注册成功" in final_content or "注册完成" in final_content:
                self.log.bind(msg=True).success(
                    f"✅ 叔服注册成功！\n"
                    f"- 注册ID：{self.unique_name}\n"
                    f"- 安全码：{self.security_code or '未配置'}"
                )
                return True
            else:
                self.log.bind(msg=True).warning(
                    f"❌ 注册流程完成但未检测到成功提示：{final_content[:100]}..."
                )
                return False

        except Exception as e:
            self.log.error(f"注册流程异常：")
            show_exception(e, regular=False)
            return False
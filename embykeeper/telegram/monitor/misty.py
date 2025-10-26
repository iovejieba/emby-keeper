import asyncio
import random
import string
from typing import Optional, Union, List

from pydantic import BaseModel, ValidationError
from pyrogram.types import Message
from loguru import logger

from embykeeper.ocr import OCRService
from embykeeper.utils import async_partial, nonblocking

from ..lock import misty_locks
from . import Monitor

misty_monitor_pool = {}


class MistyMonitorConfig(BaseModel):
    name: str = "Misty"
    chat_name: Union[str, int] = "FreeEmbyGroup"
    chat_keyword: str = r"空余名额数: (?!0$)"
    bot_username: str = "EmbyMistyBot"
    notify_create_name: bool = True
    additional_auth: List[str] = ["prime"]
    security_code: Optional[str] = None  # 自定义安全码
    register_max_attempts: int = 3  # 注册重试次数
    init_retry_count: int = 2  # 初始化重试次数


class MistyMonitor(Monitor):
    ocr = "digit5-large@v1"
    ocr_lock = asyncio.Lock()
    init_first = True

    async def init(self, initial=True, force_lock=True):
        try:
            self.t_config = MistyMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"Misty监控器配置错误\n{e}")
            return False

        # 初始化参数
        self.name = self.t_config.name
        self.chat_name = self.t_config.chat_name
        self.chat_keyword = self.t_config.chat_keyword
        self.bot_username = self.t_config.bot_username
        self.notify_create_name = self.t_config.notify_create_name
        self.additional_auth = self.t_config.additional_auth
        self.security_code = self.t_config.security_code
        self.register_max_attempts = self.t_config.register_max_attempts
        self.init_retry_count = self.t_config.init_retry_count

        misty_monitor_pool[self.client.me.id] = self
        self.captcha = None
        self.log = logger.bind(scheme="telemonitor", name=self.name, username=self.client.me.full_name)
        self.log.info(f"正在初始化Misty机器人状态...")

        wr = async_partial(self.client.wait_reply, self.bot_username)
        misty_locks.setdefault(self.client.me.id, asyncio.Lock())
        lock = misty_locks.get(self.client.me.id, None)
        if not force_lock:
            lock = nonblocking(lock)

        async with lock:
            for _ in range(self.init_retry_count if initial else 3):
                try:
                    msg: Message = await wr("/cancel")
                    if "选择您要使用的功能" in (msg.caption or msg.text):
                        await asyncio.sleep(random.uniform(2, 4))
                        msg = await wr("⚡️账号功能")
                    if "请选择功能" in (msg.text or msg.caption):
                        await asyncio.sleep(random.uniform(2, 4))
                        msg = await wr("⚡️注册账号")
                        if "请输入验证码" in (msg.caption or msg.text):
                            # 优先使用自定义安全码
                            if self.security_code:
                                self.captcha = self.security_code
                                self.log.info(f"使用配置的自定义安全码: {self.captcha}")
                            else:
                                # OCR识别逻辑
                                data = await self.client.download_media(msg, in_memory=True)
                                ocr = await OCRService.get(self.ocr)
                                try:
                                    with ocr:
                                        ocr_text = await ocr.run(data)
                                except asyncio.TimeoutError:
                                    self.log.info(f"OCR识别超时，重试...")
                                    continue
                                self.captcha = ocr_text.translate(
                                    str.maketrans("", "", string.punctuation)
                                ).replace(" ", "")
                                self.log.debug(f"OCR识别到验证码: {self.captcha}")
                except (asyncio.TimeoutError, TypeError):
                    continue
                else:
                    if self.captcha and len(self.captcha) == 5:
                        # 新增：显示注册ID来源（自定义/自动生成）
                        unique_type = "自定义" if self.config.get("unique_name") else "自动生成"
                        self.log.info(
                            f"机器人状态初始化完成，将使用：\n"
                            f"- 注册ID（{unique_type}）：{self.unique_name}\n"
                            f"- 验证码（{'自定义' if self.security_code else 'OCR识别'}）：{self.captcha}"
                        )
                        return True
                    else:
                        self.log.info(f"验证码格式错误（需5位），重试...")
            else:
                self.log.bind(log=True).warning(f"Misty机器人初始化失败，监控停止")
                return False

    async def on_trigger(self, message: Message, key, reply):
        wr = async_partial(self.client.wait_reply, self.bot_username)
        misty_locks.setdefault(self.client.me.id, asyncio.Lock())
        lock = misty_locks.get(self.client.me.id, None)

        async with lock:
            for _ in range(self.register_max_attempts):
                try:
                    msg = await wr(self.captcha)
                    if "验证码错误" in msg.text:
                        self.log.info(f"验证码错误，重新初始化...")
                        if not await self.init(force_lock=False):
                            self.failed.set()
                        return
                    elif "暂时停止注册" in msg.text:
                        self.log.info(f"注册名额已满，重新初始化继续监控...")
                        if not await self.init(force_lock=False):
                            self.failed.set()
                        return
                    elif "用户名" in msg.text or "账号" in msg.text:
                        msg = await wr(self.unique_name)
                        if "注册成功" in msg.text:
                            # 新增：注册成功时显示注册ID
                            unique_type = "自定义" if self.config.get("unique_name") else "自动生成"
                            self.log.bind(msg=True).info(
                                f"✅ 向Bot @{self.bot_username} 注册成功：\n"
                                f"- 注册ID（{unique_type}）：{self.unique_name}\n"
                                f"- 安全码：{self.captcha}"
                            )
                            return
                    else:
                        self.log.bind(msg=True).info(f"❌ 异常输出，抢注失败：{msg.text}")
                        self.failed.set()
                        return
                except asyncio.TimeoutError:
                    self.log.debug(f"第 {_+1} 次注册超时，重试...")
            else:
                self.log.info(f"已尝试 {self.register_max_attempts} 次，注册未成功")
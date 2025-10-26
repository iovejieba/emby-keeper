import asyncio
import random
import re
import string
from typing import List, Optional, Union
from loguru import logger
from pydantic import BaseModel, ValidationError
from pyrogram.types import Message

from . import Monitor
from ..embyboss import EmbybossRegister

__ignore__ = True


class TemplateAMonitorConfig(BaseModel):
    name: str = None
    chat_name: Optional[Union[str, int]] = None  # 监控的群聊名称
    chat_allow_outgoing: bool = False  # 是否支持自己发言触发
    chat_user: Union[str, List[str]] = []  # 仅被列表中用户的发言触发 (支持 username / userid)
    chat_keyword: Union[str, List[str]] = []  # 仅当消息含有列表中的关键词时触发, 支持 regex
    chat_except_keyword: Union[str, List[str]] = []  # 消息含有列表中的关键词时不触发, 支持 regex
    chat_probability: float = 1.0  # 发信概率 (0最低, 1最高)
    chat_delay: int = 0  # 发信延迟 (s)
    chat_follow_user: int = 0  # 需要等待 N 个用户发送 {chat_reply} 方可回复
    chat_reply: Optional[str] = None  # 回复的内容, 可以为恒定字符串或函数或异步函数
    allow_edit: bool = False  # 编辑消息内容后也触发
    trigger_interval: float = 2  # 每次触发的最低时间间隔
    trigger_sim: int = 1  # 同时触发的最大并行数
    trigger_max_time: float = 120  # 触发后处理的最长时间
    allow_caption: bool = True  # 是否允许带照片的消息
    allow_text: bool = True  # 是否允许不带照片的消息
    send: bool = True  # 是否发送通知
    send_immediately: bool = True  # 是否发送即时日志, 不等待每日推送时间
    try_register_bot: Optional[str] = (
        None  # 尝试注册的机器人名称 (需为: https://github.com/berry8838/Sakura_embyboss)
    )
    # 注册相关配置
    register_max_attempts: int = 3  # 注册最大重试次数
    register_accelerate_threshold: int = 5  # 抢注加速阈值（席位≤该值触发加速）
    register_interval_seconds: int = 1  # 注册重试间隔（秒）
    security_code: Optional[str] = None  # 自定义安全码（未指定则随机生成）


class TemplateAMonitor(Monitor):
    init_first = True
    additional_auth = ["prime"]
    notify_create_name = True

    async def init(self):
        try:
            self.t_config = TemplateAMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 监控器自定义模板 A 的配置错误:\n{e}")
            return False
        self.name = self.t_config.name or "自定义"
        self.chat_name = self.t_config.chat_name
        self.chat_allow_outgoing = self.t_config.chat_allow_outgoing
        self.chat_user = self.t_config.chat_user
        self.chat_keyword = self.t_config.chat_keyword
        self.chat_except_keyword = self.t_config.chat_except_keyword
        self.chat_probability = self.t_config.chat_probability
        self.chat_delay = self.t_config.chat_delay
        self.chat_follow_user = self.t_config.chat_follow_user
        self.chat_reply = self.t_config.chat_reply
        self.allow_edit = self.t_config.allow_edit
        self.trigger_interval = self.t_config.trigger_interval
        self.trigger_sim = self.t_config.trigger_sim
        self.trigger_max_time = self.t_config.trigger_max_time
        self.allow_caption = self.t_config.allow_caption
        self.allow_text = self.t_config.allow_text
        # 初始化注册相关配置
        self.register_max_attempts = self.t_config.register_max_attempts
        self.register_accelerate_threshold = self.t_config.register_accelerate_threshold
        self.register_interval_seconds = self.t_config.register_interval_seconds
        self.security_code = self.t_config.security_code  # 自定义安全码
        if (not self.chat_keyword) and (not self.chat_user) and (not self.chat_name):
            self.log.warning(f"初始化失败: 没有定义任何监控项, 请参考教程进行配置.")
            return False
        self.log = logger.bind(scheme="telemonitor", name=self.name, username=self.client.me.full_name)
        # 预校验自定义安全码格式（若配置）
        if self.security_code:
            self._log_security_code_info()  # 输出安全码配置日志
            if not self._validate_security_code(self.security_code):
                self.log.warning(f"自定义安全码 '{self.security_code}' 不符合要求（需4-6位数字），可能导致注册失败！")
        else:
            self.log.info(f"未配置自定义安全码，当监控到开注时，将自动生成4-6位数字安全码.")
        return True

    async def on_trigger(self, message: Message, key, reply):
        content = message.text or message.caption
        if self.t_config.send:
            if message.from_user:
                msg = f'监控器收到来自 "{message.from_user.full_name}" 的关键消息: {content}'
            else:
                msg = f"监控器收到关键消息: {content}"
            if self.t_config.send_immediately:
                self.log.bind(msg=True).info(msg)
            else:
                self.log.bind(log=True).info(msg)
        
        if self.t_config.try_register_bot:
            # 1. 获取预注册的用户名并校验格式（严格验证）
            unique_name = self.get_unique_name()
            if not unique_name:
                error_msg = "无法获取有效的用户名（格式不符合要求），注册失败"
                self._send_notification(error_msg, is_error=True)
                return
            
            # 2. 获取安全码（优先使用自定义，否则随机生成）
            security_code = self._get_security_code()
            if not security_code:
                error_msg = "安全码生成失败（格式不符合要求），注册终止"
                self._send_notification(error_msg, is_error=True)
                return
            
            self.log.info(f"开始自动注册: 用户名={unique_name}, 安全码={security_code}")
            
            # 3. 触发后延迟（可通过配置关闭）
            if self.t_config.chat_delay > 0:
                self.log.debug(f"触发后延迟 {self.t_config.chat_delay} 秒执行注册")
                await asyncio.sleep(self.t_config.chat_delay)
            
            # 4. 调用注册器（支持抢注加速、重试）
            register = EmbybossRegister(
                client=self.client,
                logger=self.log,
                username=unique_name,
                password=security_code,
                max_attempts=self.register_max_attempts
            )
            if hasattr(register, "accelerate_threshold"):
                register.accelerate_threshold = self.register_accelerate_threshold
            
            # 5. 执行持续注册
            self.log.info(f"开始尝试注册到 {self.t_config.try_register_bot}（最多{self.register_max_attempts}次重试）")
            success = await register.run_continuous(
                bot=self.t_config.try_register_bot,
                interval_seconds=self.register_interval_seconds
            )
            
            # 6. 发送注册结果通知
            if success:
                success_msg = f"✅ 成功注册到 {self.t_config.try_register_bot}！用户名：{unique_name}，安全码：{security_code}"
                self._send_notification(success_msg, is_error=False)
                self.log.bind(log=True).info(f"监控器成功注册机器人 {self.t_config.try_register_bot} (用户名: {unique_name}).")
            else:
                error_msg = f"❌ 注册 {self.t_config.try_register_bot} 失败（已尝试{self.register_max_attempts}次）"
                self._send_notification(error_msg, is_error=True)
                self.log.warning(f"注册机器人 {self.t_config.try_register_bot} 失败（用户名: {unique_name}）")
        else:
            if reply:
                if self.t_config.chat_delay > 0:
                    await asyncio.sleep(self.t_config.chat_delay)
                await self.client.send_message(message.chat.id, reply)
                self.log.info(f"已向 {message.chat.username or message.chat.full_name} 发送: {reply}.")
                return

    def _get_security_code(self) -> Optional[str]:
        """获取安全码：优先使用自定义，未指定则随机生成（确保符合4-7位数字要求）"""
        # 1. 优先使用配置的安全码
        if self.security_code:
            if self._validate_security_code(self.security_code):
                return self.security_code
            self.log.error(f"自定义安全码 '{self.security_code}' 不符合要求（需4-7位数字）")
            return None
        
        # 2. 随机生成4-7位数字
        return "".join(random.choices(string.digits, k=random.randint(4, 7)))

    def _log_security_code_info(self):
        """输出安全码配置日志，与用户名日志格式保持一致"""
        self.log.info(f'根据您的设置, 当监控到开注时, 该站点将使用安全码 "{self.security_code}" 注册.')

    @staticmethod
    def _validate_security_code(code: str) -> bool:
        """验证安全码是否符合要求：4-6位纯数字"""
        return bool(re.fullmatch(r'^\d{4,7}$', code))

    def _send_notification(self, message: str, is_error: bool = False):
        """发送通知消息"""
        if self.t_config.send:
            if self.t_config.send_immediately:
                if is_error:
                    self.log.bind(msg=True).error(message)
                else:
                    self.log.bind(msg=True).info(message)
            else:
                if is_error:
                    self.log.bind(log=True).error(message)
                else:
                    self.log.bind(log=True).info(message)

    def get_unique_name(self):
        """获取并验证用户名（仅允许字母、数字、下划线）"""
        if not self.t_config.try_register_bot:
            return None
        
        unique_name = self.config.get("unique_name", None)
        if unique_name:
            # 使用^\w+$正则严格验证用户名
            if not self._validate_username(unique_name):
                self.log.error(
                    f"用户名 '{unique_name}' 不符合要求！"
                    "仅允许字母（a-z/A-Z）、数字（0-9）、下划线（_）"
                )
                return None  # 验证失败则终止注册
            
            self.log.info(f'根据您的设置, 当监控到开注时, 该站点将以用户名 "{unique_name}" 注册.')
            return unique_name
        else:
            # 从缓存获取默认用户名并验证
            default_name = Monitor.unique_cache.get(self.client.me)
            if default_name and self._validate_username(default_name):
                return default_name
            self.log.error(
                "默认用户名不符合要求（仅允许字母、数字、下划线），"
                "请在配置中指定 valid 的 unique_name"
            )
            return None

    @staticmethod
    def _validate_username(username: str) -> bool:
        """验证用户名：仅允许字母、数字、下划线（等价于^\w+$）"""
        return bool(re.fullmatch(r'^\w+$', username))


def use(**kw):
    return type("TemplatedClass", (TemplateAMonitor,), kw)
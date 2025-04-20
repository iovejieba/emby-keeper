from typing import List, Optional, Union
from loguru import logger
from pydantic import BaseModel, ValidationError

from ._smart import SmartMessager

__ignore__ = True


class TemplateBMessagerConfig(BaseModel):
    name: str = None
    chat_name: Union[str, int] = None  # 发送群聊名称
    style_messages: List[str] = None  # 使用的风格语料, 与 style_message_list 二选一
    style_message_list: str = (
        None  # 使用的风格语料列表, 例如 "some-wl@v1.yaml", 放置在 basedir 中, 且 @v1.yaml 尾缀是必须的
    )
    min_interval: int = None  # 发送最小间隔 (秒)
    max_interval: int = None  # 发送最大间隔 (秒)
    at: Optional[List[str]] = None  # 时间区间, 例如 ["5:00AM", "9:00PM"]
    msg_per_day: Optional[int] = None  # 每日发送次数
    min_msg_gap: int = 5  # 最小消息间隔
    force_day: bool = False  # 强制每条时间线在每个自然日运行
    prompt: Optional[str] = None  # 使用的提示词
    extra_prompt: Optional[str] = None  # 追加的提示词

    # Backward compatibility
    interval: Optional[int] = None


class TemplateAMessager(SmartMessager):
    additional_auth = ["prime"]

    async def init(self):
        try:
            self.t_config = TemplateBMessagerConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 水群器自定义模板 B 的配置错误:\n{e}")
            return False
        self.name = self.t_config.name or "自定义"
        self.chat_name = self.t_config.chat_name
        self.default_messages = self.t_config.style_message_list
        self.at = self.t_config.at
        self.msg_per_day = self.t_config.msg_per_day or self.msg_per_day
        self.min_msg_gap = self.t_config.min_msg_gap
        self.force_day = self.t_config.force_day
        # style_messages/ min_interval / max_interval / msg_per_day / prompt / extra_prompt 由 config 读取
        if not self.chat_name:
            self.log.warning(f"初始化失败: 没有定义任何目标群组, 请参考教程进行配置.")
            return False
        self.log = logger.bind(scheme="telemessager", name=self.name, username=self.me.name)
        return True


def use(**kw):
    return type("TemplatedClass", (TemplateAMessager,), kw)

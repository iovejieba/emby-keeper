from typing import List, Literal, Optional, Union
from loguru import logger
from pydantic import BaseModel, ValidationError

from . import Messager

__ignore__ = True


class TemplateAMessagerConfig(BaseModel):
    name: str = None
    chat_name: Union[str, int] = None   # 监控的群聊名称
    word_lists: Union[str, List[str]] = []  # 使用的语料列表, 例如 ["some-wl@v1.yaml * 1000"], 放置在 basedir 中, 且 @v1.yaml 尾缀是必须的
    min_interval: int = None  # 发送最小间隔 (秒)
    max_interval: int = None  # 发送最大间隔 (秒)
    at: Optional[List[str]] = None  # 时间区间, 例如 ["5:00AM", "9:00PM"]
    possibility: Optional[float] = None  # 发送概率, 例如 1.00
    only: Optional[Literal["weekday", "weekend"]] = None  # 仅在周末/周中发送

class TemplateAMessager(Messager):
    additional_auth = ["prime"]

    async def init(self):
        try:
            self.t_config = TemplateAMessagerConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 监控器自定义模板 A 的配置错误:\n{e}")
            return False
        self.name = self.t_config.name or "自定义"
        self.chat_name = self.t_config.chat_name
        self.default_messages = self.t_config.word_lists
        self.min_interval = self.t_config.min_interval or self.min_interval
        self.max_interval = self.t_config.max_interval or self.max_interval
        self.at = self.t_config.at
        self.possibility = self.t_config.possibility
        self.only = self.t_config.only
        if not self.chat_name:
            self.log.warning(f"初始化失败: 没有定义任何目标群组, 请参考教程进行配置.")
            return False
        self.log = logger.bind(scheme="telemessager", name=self.name, username=self.me.name)
        return True

def use(**kw):
    return type("TemplatedClass", (TemplateAMessager,), kw)

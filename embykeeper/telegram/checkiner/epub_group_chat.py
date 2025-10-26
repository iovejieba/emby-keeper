import asyncio
import aiohttp
import json
import random

from embykeeper.utils import to_iterable

from ..link import Link
from . import BotCheckin

__ignore__ = True


class EPubGroupChatCheckin(BotCheckin):
    name = "EPub 电子书库群组每日发言"
    chat_name = "libhsulife"
    additional_auth = ["prime"]
    bot_use_captcha = False

    async def get_jinrishici_poetry(self):
        """调用今日诗词 API 获取随机诗句"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://v2.jinrishici.com/sentence",
                    headers={"X-User-Token": "你的今日诗词Token"},  # 可选，如果没有可以留空
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result["status"] == "success":
                            return result["data"]["content"]
                        else:
                            self.log.error(f"今日诗词 API 返回错误: {result}")
                            return None
                    else:
                        self.log.error(f"今日诗词 API 调用失败: {response.status}")
                        return None
        except asyncio.TimeoutError:
            self.log.error("调用今日诗词 API 超时")
            return None
        except Exception as e:
            self.log.error(f"调用今日诗词 API 时出错: {e}")
            return None

    async def send_checkin(self, retry=False):
        for _ in range(3):
            # 固定为4条古诗消息
            times = 4
            min_letters = self.config.get("letters", 7)
            
            # 生成诗句列表
            poetry_lines = []
            for i in range(times + 2):  # 多生成几行以防有不符合要求的
                line = await self.get_jinrishici_poetry()
                if line:
                    # 清理诗句，去除标点符号
                    cleaned_line = line.replace('，', ' ').replace('。', ' ').replace('！', ' ').replace('？', ' ').replace('、', ' ').strip()
                    poetry_lines.append(cleaned_line)
            
            # 过滤出符合字数要求的行
            lines = [
                line for line in poetry_lines
                if len(line.replace(' ', '')) >= min_letters
            ]
            
            # 如果符合要求的行数不够，尝试从已有的行中组合
            if len(lines) < times:
                # 尝试将短句组合成长句
                combined_lines = []
                current_line = ""
                for line in poetry_lines:
                    if len(current_line + line) <= 14:  # 限制最大长度
                        current_line += line + " "
                    else:
                        if current_line:
                            combined_lines.append(current_line.strip())
                        current_line = line + " "
                if current_line:
                    combined_lines.append(current_line.strip())
                
                # 再次过滤
                lines = [
                    line for line in combined_lines
                    if len(line.replace(' ', '')) >= min_letters
                ]
            
            # 随机选择需要的行数
            if len(lines) >= times:
                selected_lines = random.sample(lines, times)
                for l in selected_lines:
                    self.log.info(f"即将向群组发送水群消息: {l}.")
                await asyncio.sleep(10)
                
                # 发送四条独立的古诗消息
                cmds = to_iterable(selected_lines)
                for i, cmd in enumerate(cmds):
                    if retry and not i:
                        await asyncio.sleep(self.bot_retry_wait)
                    if i < len(cmds):
                        await asyncio.sleep(self.bot_send_interval)
                    await self.send(cmd)
                await self.finish(message="已发送四条古诗消息")
                return
            else:
                self.log.warning(f"生成的行数不符合要求: {len(lines)}行, 期望{times}行")
                continue
        else:
            return await self.fail(message="无法生成发言内容")

    async def message_handler(*args, **kw):
        return
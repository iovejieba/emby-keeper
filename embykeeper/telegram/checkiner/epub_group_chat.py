import asyncio
import httpx
import re
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
    
    # 扩充本地备用诗句库（约150条，涵盖多朝代、多主题，降低重复率）
    LOCAL_POETRY = [
        # 唐诗
        "床前明月光 疑是地上霜",
        "举头望明月 低头思故乡",
        "白日依山尽 黄河入海流",
        "欲穷千里目 更上一层楼",
        "春眠不觉晓 处处闻啼鸟",
        "夜来风雨声 花落知多少",
        "红豆生南国 春来发几枝",
        "愿君多采撷 此物最相思",
        "空山新雨后 天气晚来秋",
        "明月松间照 清泉石上流",
        "大漠孤烟直 长河落日圆",
        "萧关逢候骑 都护在燕然",
        "慈母手中线 游子身上衣",
        "临行密密缝 意恐迟迟归",
        "独在异乡为异客 每逢佳节倍思亲",
        "遥知兄弟登高处 遍插茱萸少一人",
        "朝辞白帝彩云间 千里江陵一日还",
        "两岸猿声啼不住 轻舟已过万重山",
        "黄河之水天上来 奔流到海不复回",
        "天生我材必有用 千金散尽还复来",
        "飞流直下三千尺 疑是银河落九天",
        "两岸青山相对出 孤帆一片日边来",
        "两个黄鹂鸣翠柳 一行白鹭上青天",
        "窗含西岭千秋雪 门泊东吴万里船",
        "随风潜入夜 润物细无声",
        "野火烧不尽 春风吹又生",
        "采菊东篱下 悠然见南山",
        "大漠有灵人处 柴门闻犬吠",
        "青海长云暗雪山 孤城遥望玉门关",
        "黄沙百战穿金甲 不破楼兰终不还",
        "千山鸟飞绝 万径人踪灭",
        "孤舟蓑笠翁 独钓寒江雪",
        "海内存知己 天涯若比邻",
        "无为在歧路 儿女共沾巾",
        "会当凌绝顶 一览众山小",
        "感时花溅泪 恨别鸟惊心",
        "烽火连三月 家书抵万金",
        "露从今夜白 月是故乡明",
        "星垂平野阔 月涌大江流",
        "名岂文章著 官应老病休",
        "劝君更尽一杯酒 西出阳关无故人",
        "独坐幽篁里 弹琴复长啸",
        "深林人不知 明月来相照",
        "葡萄美酒夜光杯 欲饮琵琶马上催",
        "醉卧沙场君莫笑 古来征战几人回",
        "月落乌啼霜满天 江枫渔火对愁眠",
        "姑苏城外寒山寺 夜半钟声到客船",
        "故人西辞黄鹤楼 烟花三月下扬州",
        "孤帆远影碧空尽 唯见长江天际流",
        "羌笛何须怨杨柳 春风不度玉门关",
        
        # 宋词
        "明月几时有 把酒问青天",
        "但愿人长久 千里共婵娟",
        "大江东去 浪淘尽 千古风流人物",
        "会挽雕弓如满月 西北望 射天狼",
        "无可奈何花落去 似曾相识燕归来",
        "昨夜雨疏风骤 浓睡不消残酒",
        "寻寻觅觅 冷冷清清 凄凄惨惨戚戚",
        "生当作人杰 死亦为鬼雄",
        "春风又绿江南岸 明月何时照我还",
        "不识庐山真面目 只缘身在此山中",
        "枝上柳绵吹又少 天涯何处无芳草",
        "两情若是久长时 又岂在朝朝暮暮",
        "衣带渐宽终不悔 为伊消得人憔悴",
        "众里寻他千百度 蓦然回首 那人却在灯火阑珊处",
        "庭院深深深几许 杨柳堆烟 帘幕无重数",
        "泪眼问花花不语 乱红飞过秋千去",
        "多情自古伤离别 更那堪冷落清秋节",
        "今宵酒醒何处 杨柳岸晓风残月",
        "此去经年 应是良辰好景虚设",
        "三十功名尘与土 八千里路云和月",
        "莫等闲白了少年头 空悲切",
        "醉里挑灯看剑 梦回吹角连营",
        "了却君王天下事 赢得生前身后名",
        "少年不识愁滋味 爱上层楼",
        "而今识尽愁滋味 欲说还休",
        "我见青山多妩媚 料青山见我应如是",
        "情知已被山遮断 频倚阑干不自由",
        "当年万里觅封侯 匹马戍梁州",
        "胡未灭 鬓先秋 泪空流",
        
        # 元曲与古诗
        "枯藤老树昏鸦 小桥流水人家",
        "夕阳西下 断肠人在天涯",
        "人生自古谁无死 留取丹心照汗青",
        "落红不是无情物 化作春泥更护花",
        "海内存知己 天涯若比邻",
        "落霞与孤鹜齐飞 秋水共长天一色",
        "天苍苍 野茫茫 风吹草低见牛羊",
        "日出江花红胜火 春来江水绿如蓝",
        "接天莲叶无穷碧 映日荷花别样红",
        "等闲识得东风面 万紫千红总是春",
        "沾衣欲湿杏花雨 吹面不寒杨柳风",
        "草长莺飞二月天 拂堤杨柳醉春烟",
        "稻花香里说丰年 听取蛙声一片",
        "问渠那得清如许 为有源头活水来",
        "纸上得来终觉浅 绝知此事要躬行",
        "不畏浮云遮望眼 自缘身在最高层",
        "梅须逊雪三分白 雪却输梅一段香",
        "长江后浪推前浪 世上新人赶旧人",
        "一寸光阴一寸金 寸金难买寸光阴",
        "少壮不努力 老大徒伤悲",
        "宝剑锋从磨砺出 梅花香自苦寒来",
        "书山有路勤为径 学海无涯苦作舟",
        "沉舟侧畔千帆过 病树前头万木春",
        "忽如一夜春风来 千树万树梨花开",
        "春蚕到死丝方尽 蜡炬成灰泪始干",
        "近朱者赤 近墨者黑",
        "路遥知马力 日久见人心",
        "抽刀断水水更流 举杯消愁愁更愁",
        "出师未捷身先死 长使英雄泪满襟",
        "清水出芙蓉 天然去雕饰",
        "大漠沙如雪 燕山月似钩",
        "何当金络脑 快走踏清秋",
        "荷叶罗裙一色裁 芙蓉向脸两边开",
        "乱入池中看不见 闻歌始觉有人来",
        
        # 新增元明清诗词
        "不要人夸好颜色 只留清气满乾坤",
        "粉身碎骨全不怕 要留清白在人间",
        "千磨万击还坚劲 任尔东西南北风",
        "江山代有才人出 各领风骚数百年",
        "我自横刀向天笑 去留肝胆两昆仑",
        "苟利国家生死以 岂因祸福避趋之",
        "身无彩凤双飞翼 心有灵犀一点通",
        "此情可待成追忆 只是当时已惘然",
        "曾经沧海难为水 除却巫山不是云",
        "取次花丛懒回顾 半缘修道半缘君",
        "东边日出西边雨 道是无晴却有晴",
        "旧时王谢堂前燕 飞入寻常百姓家",
        "同是天涯沦落人 相逢何必曾相识",
        "天长地久有时尽 此恨绵绵无绝期",
        
        # 新增乐府民歌
        "山无陵 江水为竭 冬雷震震 夏雨雪",
        "天地合 乃敢与君绝",
        "百川东到海 何时复西归",
        "青青园中葵 朝露待日晞",
        "阳春布德泽 万物生光辉",
        "常恐秋节至 焜黄华叶衰",
        "江南可采莲 莲叶何田田",
        "鱼戏莲叶间 鱼戏莲叶东",
        "鱼戏莲叶西 鱼戏莲叶南 鱼戏莲叶北",
        
        # 新增其他经典
        "关关雎鸠 在河之洲 窈窕淑女 君子好逑",
        "蒹葭苍苍 白露为霜 所谓伊人 在水一方",
        "路漫漫其修远兮 吾将上下而求索",
        "老骥伏枥 志在千里 烈士暮年 壮心不已",
        "采菊东篱下 悠然见南山 山气日夕佳 飞鸟相与还",
        "问君何能尔 心远地自偏",
        "盛年不重来 一日难再晨",
        "及时当勉励 岁月不待人",
        "奇文共欣赏 疑义相与析",
        "刑天舞干戚 猛志固常在"
    ]

    def __init__(self):
        super().__init__()
        self.used_poetry_indices = set()  # 记录已使用的诗句索引，避免短期重复

    async def get_jinrishici_poetry(self):
        """调用今日诗词API获取诗句，失败时自动降级到本地诗句库（带去重逻辑）"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"X-User-Token": self.config.get("jinrishici_token", "")}
                response = await client.get(
                    "https://v2.jinrishici.com/sentence",
                    headers=headers
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("status") == "success":
                        return result["data"]["content"]
                    self.log.error(f"今日诗词API返回错误: {result}")
                else:
                    self.log.error(f"今日诗词API调用失败: {response.status_code}")
        except (asyncio.TimeoutError, httpx.RequestError) as e:
            self.log.warning(f"API调用异常，自动切换到本地诗句: {e}")
        
        # 本地诗句带去重逻辑
        return self._get_unique_local_poetry()

    def _get_unique_local_poetry(self):
        """从本地库选择未使用过的诗句，避免短期重复"""
        total = len(self.LOCAL_POETRY)
        if len(self.used_poetry_indices) >= total * 0.8:  # 使用率达80%时重置
            self.used_poetry_indices.clear()
            self.log.debug("本地诗句已循环一轮，重置使用记录")
        
        # 随机选择未使用的诗句
        while True:
            idx = random.randint(0, total - 1)
            if idx not in self.used_poetry_indices:
                self.used_poetry_indices.add(idx)
                return self.LOCAL_POETRY[idx]

    async def send_checkin(self, retry=False):
        # 从配置读取参数（默认值兜底）
        send_count = self.config.get("send_count", 4)  # 支持自定义发送数量（默认4条）
        min_letters = self.config.get("min_letters", 7)  # 最小字数
        max_length = self.config.get("max_length", 18)  # 最大长度（放宽至18，适配长句）
        init_wait = self.config.get("init_wait", 10)  # 初始等待时间（秒）
        send_interval = self.config.get("send_interval", self.bot_send_interval)  # 消息间隔

        # 一次性获取足够诗句（减少API调用）
        all_poetry = []
        for _ in range(send_count * 3):  # 按发送量的3倍获取，确保有足够筛选空间
            line = await self.get_jinrishici_poetry()
            if line:
                # 清理所有标点符号（替换为空格）
                cleaned_line = re.sub(r'[^\w\s]', ' ', line).strip()
                all_poetry.append(cleaned_line)

        # 最多尝试3次组合有效诗句
        for attempt in range(3):
            # 筛选符合长度要求的诗句
            valid_lines = [
                line for line in all_poetry
                if min_letters <= len(line.replace(' ', '')) <= max_length
            ]

            # 若数量不足，尝试组合短句（确保组合后仍符合长度）
            if len(valid_lines) < send_count:
                combined_lines = []
                temp_line = ""
                for line in all_poetry:
                    candidate = f"{temp_line} {line}".strip()
                    candidate_len = len(candidate.replace(' ', ''))
                    if min_letters <= candidate_len <= max_length:
                        temp_line = candidate
                    else:
                        if temp_line and min_letters <= len(temp_line.replace(' ', '')) <= max_length:
                            combined_lines.append(temp_line)
                        temp_line = line if len(line.replace(' ', '')) <= max_length else ""
                if temp_line and min_letters <= len(temp_line.replace(' ', '')) <= max_length:
                    combined_lines.append(temp_line)
                valid_lines = list(set(valid_lines + combined_lines))  # 去重

            # 若满足数量，发送消息
            if len(valid_lines) >= send_count:
                selected_lines = random.sample(valid_lines, send_count)
                self.log.info(f"准备发送{send_count}条消息: {selected_lines}")
                await asyncio.sleep(init_wait)  # 初始等待，模拟人工操作

                for i, cmd in enumerate(selected_lines):
                    if retry and i == 0:
                        await asyncio.sleep(self.bot_retry_wait)
                    if i > 0:  # 第一条不间隔，后续按配置间隔发送
                        await asyncio.sleep(send_interval)
                    await self.send(cmd)
                
                await self.finish(message=f"已成功发送{send_count}条签到消息")
                return

            self.log.warning(f"第{attempt+1}次尝试失败，有效诗句不足{send_count}条")

        # 所有尝试失败
        await self.fail(message=f"无法生成{send_count}条有效签到消息")

    async def message_handler(*args, **kw):
        return
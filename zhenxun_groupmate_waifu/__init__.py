from nonebot import require
from nonebot.plugin.on import on_command, on_regex
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GROUP,
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from zhenxun.configs.utils import PluginExtraData, RegisterConfig

import nonebot
import os
import random
import asyncio
import time
import re 

from pathlib import Path

try:
    import ujson as json
except ModuleNotFoundError:
    import json

from .utils import *
from .config import Config, BREAKUP_SUCCESS_RATE, BREAKUP_COOLDOWN

# ==================== 插件元数据 ====================
__plugin_meta__ = PluginMetadata(
    name="娶群友",
    description="""
    群内娶群友、透群友、分手等互动娱乐插件。
    包含分手财产结算、闪离惩罚、小黑屋与连续闪离封禁机制。
    """.strip(),
    usage="""
    指令：
        娶群友 ?[@某人]
        透群友 ?[@某人]
        离婚 / 分手
        查看群友卡池
        本群cp
    """.strip(),
    homepage="https://github.com/ATTomatoo/zhenxun_groupmate_waifu",
    extra=PluginExtraData(
        author="ATTomatoo",
        version="0.0.3",
        menu_type="群内小游戏",
        configs=[
            RegisterConfig(
                key="waifu_cd_bye",
                value=3600,
                help="分手命令开关与冷却判定，-1 表示禁用分手",
                default_value=3600,
                type=int,
            ),
            RegisterConfig(
                key="waifu_save",
                value=True,
                help="是否持久化保存娶群友插件数据",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="waifu_reset",
                value=True,
                help="是否在每天零点重置 CP 关系和惩罚记录",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="waifu_he",
                value=65,
                help="娶指定群友的成功概率",
                default_value=65,
                type=int,
            ),
            RegisterConfig(
                key="waifu_be",
                value=35,
                help="娶指定群友的失败概率",
                default_value=35,
                type=int,
            ),
            RegisterConfig(
                key="waifu_ntr",
                value=80,
                help="尝试娶已有 CP 群友时的 NTR 成功概率",
                default_value=80,
                type=int,
            ),
            RegisterConfig(
                key="yinpa_he",
                value=15,
                help="透非 CP 群友的成功概率",
                default_value=15,
                type=int,
            ),
            RegisterConfig(
                key="yinpa_be",
                value=60,
                help="透非 CP 群友的失败概率",
                default_value=60,
                type=int,
            ),
            RegisterConfig(
                key="yinpa_cp",
                value=65,
                help="透自己 CP 的成功概率",
                default_value=65,
                type=int,
            ),
            RegisterConfig(
                key="waifu_fee_ratio",
                value=0.05,
                help="分手扣款时收取的手续费比例",
                default_value=0.05,
                type=float,
            ),
            RegisterConfig(
                key="waifu_punish_min_ratio",
                value=0.10,
                help="正常分手触发财产纠纷时的最低扣款比例",
                default_value=0.10,
                type=float,
            ),
            RegisterConfig(
                key="waifu_punish_max_ratio",
                value=0.50,
                help="正常分手触发财产纠纷时的最高扣款比例",
                default_value=0.50,
                type=float,
            ),
        ],
    ).to_dict(),
)

# ==================== 配置加载 ====================

global_config = nonebot.get_driver().config
waifu_config = Config.parse_obj(global_config.dict())

waifu_cd_bye = waifu_config.waifu_cd_bye
waifu_save = waifu_config.waifu_save
waifu_reset = waifu_config.waifu_reset

HE = waifu_config.waifu_he
BE = HE + waifu_config.waifu_be
NTR = waifu_config.waifu_ntr

yinpa_HE = waifu_config.yinpa_he
yinpa_BE = yinpa_HE + waifu_config.yinpa_be
yinpa_CP = waifu_config.yinpa_cp
yinpa_CP = yinpa_HE if yinpa_CP == 0 else yinpa_CP

# 读取新增参数
waifu_fee_ratio = getattr(waifu_config, "waifu_fee_ratio", 0.05)
waifu_punish_min = getattr(waifu_config, "waifu_punish_min_ratio", 0.10)
waifu_punish_max = getattr(waifu_config, "waifu_punish_max_ratio", 0.50)

waifu_file = Path() / "data" / "waifu"
if not waifu_file.exists():
    os.makedirs(waifu_file)

record_waifu_file = waifu_file / "record_waifu"
record_yinpa1_file = waifu_file / "record_yinpa1"
record_yinpa2_file = waifu_file / "record_yinpa2"
record_marry_time_file = waifu_file / "record_marry_time"
record_punish_file = waifu_file / "record_punish"

if waifu_save:
    def save(file, data):
        with open(file, "w", encoding="utf8") as f:
            f.write(str(data))
else:
    def save(file, data):
        pass

# ==================== 辅助函数 ====================

async def get_target_id(bot: Bot, event: GroupMessageEvent) -> int | None:
    for seg in event.message:
        if seg.type == "at":
            return int(seg.data.get("qq"))
            
    msg = event.get_plaintext().strip()
    msg = re.sub(r"^[/\.!]?(娶群友|透群友|离婚|分手|涩涩|色色)\s*", "", msg)
    
    if msg.startswith("@"):
        msg = msg[1:].strip()
        
    if msg:
        try:
            member_list = await bot.get_group_member_list(group_id=event.group_id)
            for m in member_list:
                if msg == (m['card'] or m['nickname']):
                    return int(m['user_id'])
        except:
            pass
    return None

# ==================== 数据初始化 ====================

scheduler = require("nonebot_plugin_apscheduler").scheduler

record_waifu = {}
record_yinpa1 = {}
record_yinpa2 = {}
cd_bye = {}
record_marry_time = {}
record_punish = {} 

if record_marry_time_file.exists():
    with open(record_marry_time_file, 'r') as f:
        record_marry_time = eval(f.read())
if record_punish_file.exists():
    with open(record_punish_file, 'r') as f:
        record_punish = eval(f.read())

if waifu_reset:
    timestr = time.strftime('%Y-%m-%d',time.localtime(time.time()))
    timeArray = time.strptime(timestr,'%Y-%m-%d')
    Zero_today = time.mktime(timeArray)

    if record_waifu_file.exists() and os.path.getmtime(record_waifu_file) > Zero_today:
        with open(record_waifu_file,'r') as f:
            record_waifu = eval(f.read())

    if record_yinpa1_file.exists() and os.path.getmtime(record_yinpa1_file) > Zero_today:
        with open(record_yinpa1_file,'r') as f:
            record_yinpa1 = eval(f.read())

    if record_yinpa2_file.exists() and os.path.getmtime(record_yinpa2_file) > Zero_today:
        with open(record_yinpa2_file,'r') as f:
            record_yinpa2 = eval(f.read())

    @scheduler.scheduled_job("cron", hour=0)
    def _():
        global record_waifu, record_yinpa1, record_yinpa2, cd_bye, record_marry_time, record_punish
        record_waifu = {}
        record_yinpa1 = {}
        record_yinpa2 = {}
        cd_bye = {} 
        record_marry_time = {}
        record_punish = {}
        save(record_punish_file, record_punish)
        save(record_marry_time_file, record_marry_time)
else:
    if record_waifu_file.exists():
        with open(record_waifu_file,'r') as f:
            record_waifu = eval(f.read())

    if record_yinpa1_file.exists():
        with open(record_yinpa1_file,'r') as f:
            record_yinpa1 = eval(f.read())

    if record_yinpa2_file.exists():
        with open(record_yinpa2_file,'r') as f:
            record_yinpa2 = eval(f.read())

    @scheduler.scheduled_job("cron", hour=0)
    def _():
        global record_waifu, record_yinpa1, record_yinpa2, cd_bye, record_marry_time, record_punish
        for group_id in record_waifu:
            for user_id in record_waifu[group_id]:
                if record_waifu[group_id][user_id] == user_id:
                    record_waifu[group_id][user_id] = 0
        record_yinpa1 = {}
        record_yinpa2 = {}
        cd_bye = {}
        record_marry_time = {}
        record_punish = {}
        save(record_punish_file, record_punish)
        save(record_marry_time_file, record_marry_time)

# ==================== 指令处理器 ====================

waifu = on_regex(r"^[/\.!]?娶群友", permission=GROUP, priority=90, block=True)

no_waifu = [
    "你没有娶到群友，强者注定孤独，加油！",
    "找不到对象.jpg",
    "雪花飘飘北风萧萧～天地一片苍茫。",
    "要不等着分配一个对象？",
    "醒醒，你没有老婆。",
    "智者不入爱河，建设美丽中国。"
]
happy_end= [
    "好耶~",
    "婚礼？启动！",
    "(响起婚礼进行曲♪)",
    "愿天下有情人终成眷属。"
]

@waifu.handle()
async def _(bot:Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    global record_waifu, record_marry_time, record_punish
    record_waifu.setdefault(group_id,{})
    record_marry_time.setdefault(group_id, {})
    
    # 小黑屋拦截验证
    punish_data = record_punish.setdefault(user_id, {"count": 0, "black_room": 0.0})
    if time.time() < punish_data["black_room"]:
        remain = int((punish_data["black_room"] - time.time()) / 60)
        await waifu.finish(f"你还在小黑屋反省中，剩余{remain}分钟，暂不能娶群友！", at_sender=True)

    at = await get_target_id(bot, event)
    now = time.time()
    
    # === 如果携带了具体的群友艾特目标 ===
    if at and at != user_id:
        if record_waifu[group_id].get(user_id,0) == 0:
            if record_waifu[group_id].get(at,0) in (0, at):
                X = random.randint(1,100)
                if 0 < X <= HE:
                    record_waifu[group_id].update({user_id: at, at: user_id})
                    record_marry_time[group_id].update({user_id: {"time": now, "initiator": user_id}, at: {"time": now, "initiator": user_id}})
                    
                    try:
                        member = await bot.get_group_member_info(group_id=group_id, user_id=at)
                        nickname = member['card'] or member['nickname']
                    except:
                        nickname = str(at)
                        
                    msg = Message([
                        MessageSegment.text("恭喜你娶到了群友 "),
                        MessageSegment.at(at),
                        MessageSegment.text("！\n你的群友結婚对象是、\n"),
                        MessageSegment.image(file=await user_img(at)),
                        MessageSegment.text(f"『{nickname}』！")
                    ])
                    save(record_waifu_file, record_waifu)
                    save(record_marry_time_file, record_marry_time)
                    await waifu.finish(msg, at_sender=True)
                    
                elif HE < X <= BE:
                    record_waifu[group_id][user_id] = user_id
                    save(record_waifu_file, record_waifu)
                    save(record_marry_time_file, record_marry_time)
                    await waifu.finish(random.choice(no_waifu), at_sender=True)
                else:
                    await waifu.finish(random.choice(no_waifu), at_sender=True)
            else:
                try:
                    target_cp_id = record_waifu[group_id][at]
                    member = await bot.get_group_member_info(group_id=group_id, user_id=target_cp_id)
                except:
                    member = None
                    
                if random.randint(1,100) <= NTR:
                    record_waifu[group_id].pop(target_cp_id, None)
                    record_waifu[group_id].update({user_id: at, at: user_id})
                    record_marry_time[group_id].update({user_id: {"time": now, "initiator": user_id}, at: {"time": now, "initiator": user_id}})
                    
                    try:
                        member_at = await bot.get_group_member_info(group_id=group_id, user_id=at)
                        nickname = member_at['card'] or member_at['nickname']
                    except:
                        nickname = str(at)
                        
                    msg = Message([
                        MessageSegment.text("人家已经名花有主了~但你成功将其牛头人！\n你的群友結婚对象是、\n"),
                        MessageSegment.image(file=await user_img(at)),
                        MessageSegment.text(f"『{nickname}』！")
                    ])
                    save(record_waifu_file, record_waifu)
                    save(record_marry_time_file, record_marry_time)
                    await waifu.finish(msg, at_sender=True)
                else:
                    name = (member['card'] or member['nickname']) if member else "神秘人"
                    await waifu.finish(f"人家已经名花有主啦！ta的CP：{name}", at_sender=True)
        elif record_waifu[group_id][user_id] == at:
            await waifu.finish("这是你的CP！"+ MessageSegment.at(at) + '\n' + random.choice(happy_end), at_sender=True)
        else:
            cp_id = record_waifu[group_id][user_id]
            # 修复点：如果记录的对象是自己或1（今天已经单身/失败过了），不再显示自己为对象
            if cp_id == user_id or cp_id == 1:
                await waifu.finish(random.choice(no_waifu), at_sender=True)
            else:
                try:
                    member = await bot.get_group_member_info(group_id=group_id, user_id=cp_id)
                except:
                    member = None
                if member:
                    await waifu.finish(f"你已经有CP了，不许花心哦~ 你的CP：{member['card'] or member['nickname']}", at_sender=True)
                else:
                    record_waifu[group_id][user_id] = user_id
                    save(record_waifu_file, record_waifu)
                    await waifu.finish(random.choice(no_waifu), at_sender=True)

    # === 原有：如果不指定具体人选，随机分配群友的兜底处理分支 ===
    if record_waifu[group_id].get(user_id,0) == 0:
        member_list = await bot.get_group_member_list(group_id=event.group_id)
        i = 0
        while i < len(member_list):
            if member_list[i]['user_id'] in record_waifu[group_id].keys():
                del member_list[i]
            else:
                i += 1
        else:
            if member_list:
                member_list.sort(key=lambda x:x["last_sent_time"], reverse=True)
                member = random.choice(member_list[:80])
                record_waifu[group_id].update({user_id: member['user_id'], member['user_id']: user_id})
                record_marry_time[group_id].update({user_id: {"time": now, "initiator": user_id}, member['user_id']: {"time": now, "initiator": user_id}})
                nickname = member['card'] or member['nickname']
                if record_waifu[group_id][user_id] == user_id:
                    msg = random.choice(no_waifu)
                else:
                    msg = Message([
                        MessageSegment.text("的群友結婚对象是、\n"),
                        MessageSegment.image(file=await user_img(record_waifu[group_id][user_id])),
                        MessageSegment.text(f"『{nickname}』！")
                    ])
            else:
                record_waifu[group_id][user_id] = 1
                msg = "群友已经被娶光了、\n" + random.choice(no_waifu)
    else:
        uid = record_waifu[group_id][user_id]
        if uid == user_id or uid == 1:
            msg = random.choice(no_waifu)
        else:
            try:
                member = await bot.get_group_member_info(group_id=group_id, user_id=uid)
                nickname = member['card'] or member['nickname']
                msg = Message([
                    MessageSegment.text("的群友結婚对象是、\n"),
                    MessageSegment.image(file=await user_img(uid)),
                    MessageSegment.text(f"『{nickname}』！")
                ])
            except:
                msg = random.choice(no_waifu)

    save(record_waifu_file, record_waifu)
    save(record_marry_time_file, record_marry_time)
    await waifu.finish(msg, at_sender=True)

async def FACTOR(bot: Bot, event: GroupMessageEvent) -> bool:
    global record_waifu
    record_waifu.setdefault(event.group_id,{})
    return record_waifu[event.group_id].get(event.user_id,0) not in (0, 1, event.user_id) and waifu_cd_bye != -1

bye = on_regex(r"^[/\.!]?(离婚|分手)", permission=FACTOR, priority=90, block=True)

@bye.handle()
async def _(bot:Bot, event: GroupMessageEvent):
    global record_waifu, cd_bye, record_marry_time, record_punish
    user_id = event.user_id
    group_id = event.group_id
    Now = time.time()
    
    bot_name = list(bot.config.nickname)[0] if bot.config.nickname else "我"
    
    # 小黑屋拦截验证
    punish_data = record_punish.setdefault(user_id, {"count": 0, "black_room": 0.0})
    if Now < punish_data["black_room"]:
        remain = int((punish_data["black_room"] - Now) / 60)
        await bye.finish(f"你还在小黑屋反省中，剩余{remain}分钟，暂不能分手！", at_sender=True)

    cd_bye.setdefault(group_id,{})
    flag = cd_bye[group_id].setdefault(user_id,[0,0])
    cd = flag[0] - Now
    
    if cd <= 0:
        cd_bye[group_id][user_id][0] = Now + BREAKUP_COOLDOWN
        A = user_id
        B = int(record_waifu[group_id][user_id])
        
        # 读取婚姻数据
        marry_data = record_marry_time.get(group_id, {}).get(A, {})
        if isinstance(marry_data, dict):
            marry_time = marry_data.get("time", 0)
            initiator = marry_data.get("initiator", 0)
        else:
            marry_time = marry_data
            initiator = 0
            
        is_quick = (Now - marry_time) <= 300
        is_initiator = (initiator == A)
        is_quick_and_initiator = is_quick and is_initiator
        
        from .utils import breakup
        result = await breakup(A, B, is_quick_and_initiator, bot_name, waifu_fee_ratio, waifu_punish_min, waifu_punish_max)
        msg = result["msg"]
        
        # 机制 3: 如果是恶意闪离，增加计数，满3次关小黑屋120分钟并系统Ban
        if is_quick_and_initiator:
            punish_data["count"] += 1
            if punish_data["count"] >= 3:
                punish_data["black_room"] = Now + (120 * 60)
                try:
                    from plugins.ban._data_source import call_ban
                    await call_ban(user_id=str(A), reason="频繁娶群友并闪离，渣男行为！", duration=120)
                except ImportError:
                    from zhenxun.models.ban_console import BanConsole
                    await BanConsole.ban(str(A), None, 9, "频繁娶群友并闪离，渣男行为！", 120 * 60)
                    
                msg += MessageSegment.text("\n\n警告：你今天闪离次数已达3次，不仅被扣钱，还已被系统直接封禁 120 分钟！渣男必须受到惩罚！")
                
            save(record_punish_file, record_punish)
        
        # 清除 CP 记录和结婚时间记录
        del record_waifu[group_id][A]
        del record_waifu[group_id][B]
        record_marry_time.get(group_id, {}).pop(A, None)
        record_marry_time.get(group_id, {}).pop(B, None)
        
        save(record_waifu_file, record_waifu)
        save(record_marry_time_file, record_marry_time)
        
        await bye.finish(msg)
    else:
        flag[1] += 1
        await bye.finish(f"你的cd还有{round(cd/60,1)}分钟。", at_sender=True)

yinpa = on_regex(r"^[/\.!]?透群友", permission=GROUP, priority=90, block=True)

@yinpa.handle()
async def _(bot:Bot, event: GroupMessageEvent):
    group_id = event.group_id
    user_id = event.user_id
    global record_yinpa1, record_yinpa2, record_waifu
    record_waifu.setdefault(group_id, {})
    
    at_id = await get_target_id(bot, event)
    msg = ""
    
    if at_id:
        if at_id == user_id:
            pass
        elif at_id == record_waifu[group_id].get(user_id,0):
            X = random.randint(1,100)
            if 0 < X <= yinpa_CP:
                member = await bot.get_group_member_info(group_id=group_id, user_id=at_id)
                nickname = member['card'] or member['nickname']
                record_yinpa1[user_id] = record_yinpa1.get(user_id, 0) + 1
                record_yinpa2[at_id] = record_yinpa2.get(at_id, 0) + 1
                msg = Message([
                    MessageSegment.text(f"恭喜你涩到了你的老婆\n"),
                    MessageSegment.image(file=await user_img(at_id)),
                    MessageSegment.text(f"『{nickname}』！")
                ])
            else:
                msg = "你的老婆拒绝和你涩涩！"
        else:
            X = random.randint(1,100)
            if 0 < X <= yinpa_HE:
                member = await bot.get_group_member_info(group_id=group_id, user_id=at_id)
                nickname = member['card'] or member['nickname']
                record_yinpa1[user_id] = record_yinpa1.get(user_id, 0) + 1
                record_yinpa2[at_id] = record_yinpa2.get(at_id, 0) + 1
                msg = Message([
                    MessageSegment.text(f"恭喜你涩到了群友\n"),
                    MessageSegment.image(file=await user_img(at_id)),
                    MessageSegment.text(f"『{nickname}』！")
                ])
            elif yinpa_HE < X < yinpa_BE:
                msg = "不可以涩涩！"
    
    if not msg:
        member_list = await bot.get_group_member_list(group_id=event.group_id)
        member_list.sort(key=lambda x:x["last_sent_time"], reverse=True)
        member = random.choice(member_list[:80])
        if member["user_id"] == event.user_id:
            msg = "不可以涩涩！"
        else:
            nickname = member['card'] or member['nickname']
            record_yinpa1[user_id] = record_yinpa1.get(user_id, 0) + 1
            record_yinpa2[member['user_id']] = record_yinpa2.get(member['user_id'], 0) + 1
            msg = Message([
                MessageSegment.text("的涩涩对象是、\n"),
                MessageSegment.image(file=await user_img(member["user_id"])),
                MessageSegment.text(f"『{nickname}』！")
            ])

    save(record_yinpa1_file, record_yinpa1)
    save(record_yinpa2_file, record_yinpa2)
    await yinpa.finish(msg, at_sender=True)

waifu_list = on_command("查看群友卡池", aliases={"群友卡池"}, permission=GROUP, priority=90, block=True)
@waifu_list.handle()
async def _(bot:Bot, event: GroupMessageEvent):
    member_list = await bot.get_group_member_list(group_id=event.group_id)
    i = 0
    while i < len(member_list):
        if member_list[i]['user_id'] in record_waifu.setdefault(event.group_id,{}).keys():
            del member_list[i]
        else:
            i += 1
    if member_list:
        member_list.sort(key=lambda x:x["last_sent_time"], reverse=True)
        msg ="卡池：\n——————————————\n"
        for member in member_list[:80]:
            msg += f"{member['card'] or member['nickname']}\n"
        output = text_to_png(msg[:-1])
        await waifu_list.finish(MessageSegment.image(output))
    else:
        await waifu_list.finish("群友已经被娶光了。")

cp_list = on_command("本群CP", aliases={"本群cp"}, permission=GROUP, priority=90, block=True)
@cp_list.handle()
async def _(bot:Bot, event: GroupMessageEvent):
    group_id = event.group_id
    record_waifu.setdefault(group_id,{})
    lst = list(record_waifu[group_id].keys())
    if lst:
        listA, listB = [], []
        for A in lst:
            listA.append(A)
            B = record_waifu[group_id][A]
            if B not in listA and B != A:
                listB.append(B)
        msg = ""
        for user_id in listB:
            try:
                memberA = await bot.get_group_member_info(group_id=group_id, user_id=record_waifu[group_id][user_id])
                memberB = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
                msg += f"♥ {memberA['card'] or memberA['nickname']} | {memberB['card'] or memberB['nickname']}\n"
            except:
                pass
        if msg:
            output = text_to_png("本群CP：\n——————————————\n" + msg[:-1])
            await cp_list.finish(MessageSegment.image(output))
    await cp_list.finish("本群暂无cp哦~")

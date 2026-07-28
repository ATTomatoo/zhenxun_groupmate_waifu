import io
import httpx
import hashlib
import asyncio
import random

from pil_utils import BuildImage,Text2Image
from .config import BREAKUP_SUCCESS_RATE
from zhenxun.models.user_console import UserConsole
from zhenxun.utils.enum import GoldHandle
from nonebot.adapters.onebot.v11 import Message, MessageSegment

QUICK_BREAKUP_PUNISH_PROMPTS = (
    "不爱为什么还要结婚？渣男！",
    "刚结婚就急着分手，婚姻可不是儿戏！",
    "闪婚又闪离？喜新厌旧是要付出代价的！",
    "说好的白头偕老呢？这笔渣男税你逃不掉！",
    "感情不是一次性用品，闪离惩罚已执行！",
)

try:
    import ujson as json
except ModuleNotFoundError:
    import json

async def download_avatar(user_id: int) -> bytes:
    url = f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
    data = await download_url(url)
    if hashlib.md5(data).hexdigest() == "acef72340ac0e914090bd35799f5594e":
        url = f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"
        data = await download_url(url)
    return data

async def download_url(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        for i in range(3):
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
                return resp.content
            except Exception:
                await asyncio.sleep(3)
    raise Exception(f"{url} 下载失败！")

async def download_user_img(user_id: int):
    data = await download_avatar(user_id)
    img = BuildImage.open(io.BytesIO(data))
    return img.save_png()

async def user_img(user_id: int) -> bytes:
    url = f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
    data = await download_url(url)
    if hashlib.md5(data).hexdigest() == "acef72340ac0e914090bd35799f5594e":
        url = f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"
    return url

def text_to_png(msg):
    output = io.BytesIO()
    Text2Image.from_text(msg, 50).to_image(
        max_width=1024,
        padding=(20, 20),
        bg_color=(255, 255, 255, 255)
    ).save(output, format="png")
    return output

def bbcode_to_png(msg):
    output = io.BytesIO()
    Text2Image.from_bbcode_text(msg, 50).to_image(
        max_width=1024,
        padding=(20, 20),
        bg_color=(255, 255, 255, 255)
    ).save(output, format="png")
    return output

def get_message_at(data: str) -> list:
    qq_list = []
    data = json.loads(data)
    try:
        for msg in data['message']:
            if msg['type'] == 'at':
                qq_list.append(int(msg['data']['qq']))
        return qq_list
    except Exception:
        return []

async def breakup(user_id: int, partner_id: int, is_quick_and_initiator: bool, bot_name: str, fee_ratio: float, min_ratio: float, max_ratio: float):
    """
    分手逻辑：
    - is_quick_and_initiator 为 True：A发起的闪离（条件1），百分百触发扣A 50%，抽手续费，余下给对方。
    - 否则：正常分手或B发起的闪离（条件2），先按概率判定是否和平分手，若触发财产纠纷则随机扣一方，抽手续费，余下给对方。
    """
    if is_quick_and_initiator:
        # 条件 1：渣男判定 (主动结婚且5分钟内分手)，必定触发全额惩罚
        user = await UserConsole.get_user(str(user_id))
        user_gold = user.gold if user else 0
        
        deduct_amount = int(user_gold * 0.50)
        fee = int(deduct_amount * fee_ratio)
        give_amount = deduct_amount - fee
        
        if deduct_amount > 0:
            await UserConsole.reduce_gold(str(user_id), deduct_amount, GoldHandle.PLUGIN, 'waifu_plugin')
        if give_amount > 0:
            await UserConsole.add_gold(str(partner_id), give_amount, 'waifu_plugin')
            
        msg = Message(
            [
                MessageSegment.text(
                    f"{random.choice(QUICK_BREAKUP_PUNISH_PROMPTS)}\n闪离惩罚："
                ),
                MessageSegment.at(user_id),
                MessageSegment.text(
                    f" 被扣除了 {deduct_amount} 金币，"
                    f"{bot_name}收取 {fee} 金币手续费，剩余 {give_amount} 金币赔偿给 "
                ),
                MessageSegment.at(partner_id),
                MessageSegment.text("！"),
            ]
        )
            
        return {"success": True, "msg": msg}
        
    else:
        # 条件 2：正常分手
        # 引入 config 中的分手成功率 (和平分手的概率)
        if random.random() < BREAKUP_SUCCESS_RATE:
            # 概率内：和平分手，不扣除任何人金币
            msg = Message([
                MessageSegment.text("分手成功！你们和平分手了，一别两宽，各生欢喜，没有产生任何财产纠纷。")
            ])
            return {"success": True, "msg": msg}
            
        else:
            # 概率外：进入财产纠纷，50% 随机选择扣款方
            loser_id, winner_id = random.choice([(user_id, partner_id), (partner_id, user_id)])
            loser = await UserConsole.get_user(str(loser_id))
            loser_gold = loser.gold if loser else 0
            
            percent = random.uniform(min_ratio, max_ratio)
            deduct_amount = int(loser_gold * percent)
            fee = int(deduct_amount * fee_ratio)
            give_amount = deduct_amount - fee
            
            if deduct_amount > 0:
                await UserConsole.reduce_gold(str(loser_id), deduct_amount, GoldHandle.PLUGIN, 'waifu_plugin')
            if give_amount > 0:
                await UserConsole.add_gold(str(winner_id), give_amount, 'waifu_plugin')
                
            msg = Message([
                MessageSegment.text("分手失败引发财产纠纷！随机扣除了 "),
                MessageSegment.at(loser_id),
                MessageSegment.text(f" {deduct_amount} 金币给 "),
                MessageSegment.at(winner_id),
                MessageSegment.text(f"，{bot_name}收取了{fee}手续费，实际{give_amount}金币落入了 "),
                MessageSegment.at(winner_id),
                MessageSegment.text(" 的口袋！")
            ])
            
            return {"success": True, "msg": msg}

from pydantic import BaseModel, Extra

class Config(BaseModel, extra=Extra.ignore):
    waifu_cd_bye :int = 3600
    waifu_save:bool = True
    waifu_reset:bool = True
    waifu_he :int = 65
    waifu_be :int = 35
    waifu_ntr :int = 80
    yinpa_he :int = 15
    yinpa_be :int = 60
    yinpa_cp :int = 65
    
    # === 新增配置 ===
    waifu_fee_ratio: float = 0.05          # 手续费比例 (默认5%)
    waifu_punish_min_ratio: float = 0.10   # 正常分手随机扣除下限 (默认10%)
    waifu_punish_max_ratio: float = 0.50   # 正常分手随机扣除上限 (默认50%)

# 分手成功率（0~1之间的小数，可以为0）
BREAKUP_SUCCESS_RATE = 0.7  # 设置为0表示每次分手都会瓜分金币,70%和平分手

# 分手命令冷却时间（单位：秒）
BREAKUP_COOLDOWN = 3600  # 例如1小时
# -*- coding: utf-8 -*-
"""从存档R.grp读取道具/秘籍定义表"""
import struct
import os

RECORD_SIZE = 190
NAME_SIZE = 20   # 10 u16
DESC_SIZE = 30   # 15 u16
FIELD_OFFSET = 50  # 固定字段从名称后50字节开始

# 固定字段偏移(相对于记录起始, 字节)
# 根据JsEditor界面字段顺序
FIELD_MAP = {
    'skill_id':       50,   # 可练武功
    'unknown2':       52,
    'unknown3':       54,
    'unknown4':       56,
    'unknown5':       58,
    'unknown6':       60,
    'need_family':    62,   # 需要家族
    'need_school':    64,   # 需要门派
    'unknown7':       66,
    'hp':             68,   # 生命
    'hp_max':         70,   # 生命最大
    'poison':         72,   # 中毒
    'stamina':        74,   # 体力
    'inner_type':     76,   # 内力性质(-1=不限)
    'inner':          78,   # 内力
    'inner_max':      80,   # 内力最大
    'attack':         82,   # 攻击加成
    'dodge':          84,   # 轻功加成
    'defense':        86,   # 防御加成
    'medical':        88,   # 医疗加成
    'use_poison':     90,   # 用毒加成
    'detox':          92,   # 解毒加成
    'anti_poison':    94,   # 抗毒加成
    'fist':           96,   # 拳掌加成
    'sword':          98,   # 御剑加成
    'weapon':        100,   # 兵器加成
    'finger':        102,   # 指腿加成
    'dark':          104,   # 暗毒加成
    'wuxue':         106,   # 武学常识
    'cost_qi':       108,   # 耗费气力
    'left_right':    110,   # 左右互搏
    'attack_poison': 112,   # 攻击带毒
    'limit_person':  114,   # 专属人物(65535=不限)
    'need_gender':   116,   # 需要性别(65535=不限)
    'need_inner':    118,   # 需要内力性质
    'need_maxmax':   120,   # 需要最大最大
    'need_attack':   122,   # 需要攻击
    'need_dodge':    124,   # 需要轻功
    'need_use_poison': 126, # 需要用毒
    'need_medical':  128,   # 需要医疗
    'need_detox':    130,   # 需要解毒
    'need_fist':     132,   # 需要拳掌
    'need_sword':    134,   # 需要御剑
    'need_weapon':   136,   # 需要兵器
    'need_finger':   138,   # 需要指腿
    'need_dark':     140,   # 需要暗毒
    'need_qual':     142,   # 需要资质
    'unknown8':      144,
    'unknown9':      146,
    'need_type':     148,   # 需要类型
    'item1':         150,
    'item2':         152,
    'item3':         154,
    'item4':         156,
    'need_num1':     158,
    'need_num2':     160,
    'need_num3':     162,
    'need_num4':     164,
    'price':         166,   # 价格
    'unknown10':     168,
    'unknown11':     170,
    'unknown12':     172,
    'unknown13':     174,
    'extra':         176,   # 附带
    'limit_person2': 182,   # 专属人物2
}

def read_gbk_string(data, offset, max_len):
    """读取GBK字符串(到00结束)"""
    end = offset
    while end < offset + max_len and end < len(data):
        if data[end] == 0 and (end+1 >= len(data) or data[end+1] == 0):
            break
        if data[end] >= 0x81:
            end += 2
        else:
            end += 1
    try:
        return data[offset:end].decode('gbk', errors='ignore').strip('\x00').strip()
    except:
        return ''

def parse_item_record(data, rec_offset):
    """解析一条道具记录"""
    rec = {}
    rec['name'] = read_gbk_string(data, rec_offset, NAME_SIZE)
    rec['desc'] = read_gbk_string(data, rec_offset + NAME_SIZE, DESC_SIZE)
    for field, offset in FIELD_MAP.items():
        if rec_offset + offset + 2 <= len(data):
            rec[field] = struct.unpack_from('<H', data, rec_offset + offset)[0]
        else:
            rec[field] = 0
    return rec

def find_table_start(data):
    """动态搜索秘籍表起始位置: 通过已知秘籍名称定位"""
    # 已知的几个秘籍名称(GBK)和对应的物品编号
    known_books = [
        ('雪遁掠行身法', 918),
        ('太极拳经', 376),
        ('修罗刀谱', 830),
        ('太极剑谱', 275),
        ('玉女剑谱', 260),
        ('越女剑谱', 251),
    ]
    for name, item_id in known_books:
        encoded = name.encode('gbk')
        pos = data.find(encoded)
        if pos >= 0:
            # 名称在记录起始位置, 所以 start = pos - item_id * RECORD_SIZE
            start = pos - item_id * RECORD_SIZE
            if start >= 0 and start + 934 * RECORD_SIZE <= len(data):
                print(f'通过"{name}"(#{item_id})定位秘籍表起始: {start}')
                return start
    # 兜底: 用默认位置
    print('警告: 未通过名称定位, 使用默认位置798724')
    return 798724

def load_items_from_save(r_grp_path):
    """从R.grp加载所有道具定义"""
    data = open(r_grp_path, 'rb').read()
    start = find_table_start(data)
    
    items = []
    for i in range(934):  # 0-933
        rec_offset = start + i * RECORD_SIZE
        if rec_offset + RECORD_SIZE > len(data):
            break
        rec = parse_item_record(data, rec_offset)
        rec['item_id'] = i
        items.append(rec)
    
    # 筛选秘籍(有可练武功且skill_id > 0)
    books = [item for item in items if item.get('skill_id', 0) > 0 and item.get('skill_id', 0) < 10000]
    # 特殊道具: 无skill_id但属于特殊类秘籍(洗髓经/医毒书籍/宝典等)
    special_item_names = {'琅寰宝典', '遁甲天书', '左右互搏之术',
                         '洗髓经', '子午针灸经', '药王神篇', '神龙秘籍', '蝶谷毒经',
                         '恒山药理', '崆峒药理', '桃花药理', '武当药理', '黑玉药理', '少林药理', '日月药理', '逍遥药理',
                         '昆仑药理', '全真药理', '华山药理', '白驼毒经', '金蛇秘笈'}
    for item in items:
        if item.get('name', '') in special_item_names and item not in books:
            books.append(item)
    print(f'从存档读取 {len(items)} 个道具, 其中 {len(books)} 个秘籍')
    return items, books

def load_kungfu_from_save(r_grp_path, kfid_to_name=None):
    """从存档R.grp加载秘籍, 转换为Kungfu对象列表"""
    from kungfu_db import Kungfu
    import json
    
    # 加载配置(分类+等级, 从武功列表.xlsx和武功秘籍.xlsx提取)
    from kungfu_db import resource_path
    config_path = resource_path('book_config.json')
    inner_names = set()
    dodge_names = set()
    kfid_to_level = {}
    # 特殊类秘籍(用户指定)
    special_names = {'斗转先天一阳指', '鹤嘴劲秘要', '武穆遗书', '星云剑气功谱', '琅寰宝典', '遁甲天书', '左右互搏之术',
                    '洗髓经', '子午针灸经', '药王神篇', '神龙秘籍', '蝶谷毒经',
                    '恒山药理', '崆峒药理', '桃花药理', '武当药理', '黑玉药理', '少林药理', '日月药理', '逍遥药理',
                    '昆仑药理', '全真药理', '华山药理', '白驼毒经', '金蛇秘笈'}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            inner_names = set(cfg.get('inner_books', []))
            dodge_names = set(cfg.get('dodge_books', []))
            kfid_to_level = {int(k): v for k, v in cfg.get('kfid_to_level', {}).items()}
    print(f'配置: 内功{len(inner_names)}个, 轻功{len(dodge_names)}个, 武功等级{len(kfid_to_level)}个')
    
    items, books = load_items_from_save(r_grp_path)
    kfid_to_name = kfid_to_name or {}
    
    kungfus = []
    special_no_skill = {'琅寰宝典', '遁甲天书', '左右互搏之术',
                       '洗髓经', '子午针灸经', '药王神篇', '神龙秘籍', '蝶谷毒经',
                       '恒山药理', '崆峒药理', '桃花药理', '武当药理', '黑玉药理', '少林药理', '日月药理', '逍遥药理',
                       '昆仑药理', '全真药理', '华山药理', '白驼毒经', '金蛇秘笈'}
    for item in books:
        kf = Kungfu()
        kf.item_id = item['item_id']
        kf.name = item['name']
        kf.desc = item['desc']
        kf.price = item['price']
        kf.skill_id = item['skill_id']
        # 无练出武功的特殊书籍(医毒书/宝典), 不占武功格子但加成生效
        kf.no_skill = (item['skill_id'] == 65535)
        # 特殊道具无skill_id, 练出武功名用道具名
        if item['name'] in special_no_skill:
            kf.skill_name = item['name']
        else:
            kf.skill_name = kfid_to_name.get(item['skill_id'], f'武功#{item["skill_id"]}')
        
        # 加成(每级) - u16转有符号(负数如-1存为65535), 过滤异常值
        bonus_map = {
            'attack': '攻击', 'dodge': '轻功', 'defense': '防御',
            'fist': '拳掌', 'sword': '御剑', 'weapon': '兵器',
            'finger': '指腿', 'dark': '暗毒',
            'medical': '医疗', 'use_poison': '用毒', 'detox': '解毒',
            'anti_poison': '抗毒', 'wuxue': '武常',
            'hp': '生命', 'inner': '内力', 'inner_max': '内力最大',
        }
        for src, dst in bonus_map.items():
            v = item.get(src, 0)
            if v > 32767:
                v -= 65536  # u16转有符号整数
            if v != 0 and abs(v) < 60000:
                kf.bonuses[dst] = v
        
        # 分类: 优先用名称匹配(参考Excel分类), 否则按五系加成
        skill_bonuses = {k: kf.bonuses.get(k, 0) for k in ['拳掌', '御剑', '兵器', '指腿', '暗毒']}
        max_skill = max(skill_bonuses.values()) if skill_bonuses else 0
        
        # 强制分类(五系加成相同时指定类别)
        force_category = {'三阴蜈蚣爪法': '指腿'}
        
        if kf.name in special_names:
            kf.category = '特殊'
        elif kf.name in force_category:
            kf.category = force_category[kf.name]
        elif kf.name in inner_names:
            kf.category = '内功'
        elif kf.name in dodge_names:
            kf.category = '轻功'
        elif max_skill > 0:
            kf.category = max(skill_bonuses, key=skill_bonuses.get)
        else:
            kf.category = '特殊'
        
        # 学习后改变内力性质: 从数据块inner_type[76]读取 (0=阴,1=阳,2=调和,65535=不变)
        inner_type_val = item.get('inner_type', 65535)
        if inner_type_val == 0:
            kf.change_inner = '阴'
        elif inner_type_val == 1:
            kf.change_inner = '阳'
        elif inner_type_val == 2:
            kf.change_inner = '调和'
        else:
            kf.change_inner = None
        
        # 品阶/等级: 内功/轻功用武功等级(1-5级/防功), 五系用系数加成
        level_str = kfid_to_level.get(item['skill_id'])
        if kf.category in ('内功', '轻功') and level_str:
            kf.level_str = level_str
            # tier用数字排序: 1级=1...5级=5, 防功=0
            if level_str.startswith('防'):
                kf.tier = 0
            else:
                try:
                    kf.tier = int(level_str.replace('级', ''))
                except:
                    kf.tier = 0
        else:
            kf.level_str = ''
            kf.tier = max_skill
        
        # 需求资质 - 特殊值: 65535=不限, >60000=低于(65535-x)
        q = item.get('need_qual', 65535)
        if q == 65535:
            kf.qualification = None
        elif q > 60000:
            kf.qualification = -(65535 - q)  # 负数表示低于
        else:
            kf.qualification = q
        
        # 需求五系
        need_map = {
            'need_fist': '拳掌', 'need_sword': '御剑', 'need_weapon': '兵器',
            'need_finger': '指腿', 'need_dark': '暗毒',
        }
        for src, dst in need_map.items():
            v = item.get(src, 0)
            if v > 0 and v < 60000:
                kf.need_skills[dst] = v
        
        # 其他需求
        if item.get('need_attack', 0) > 0 and item['need_attack'] < 60000:
            kf.need_attack = item['need_attack']
        if item.get('need_dodge', 0) > 0 and item['need_dodge'] < 60000:
            kf.need_dodge = item['need_dodge']
        
        # 内力性质需求: -1(65535)=不限, 0=阴, 1=阳, 2=调和
        it = item.get('need_inner', 65535)
        if it == 65535:
            kf.inner_type = ''
        elif it == 0:
            kf.inner_type = '阴'
        elif it == 1:
            kf.inner_type = '阳'
        elif it == 2:
            kf.inner_type = '调和'
        
        # 专属人物(存整数编号)
        lp = item.get('limit_person', 65535)
        if lp != 65535:
            kf.limit_person = lp
        lp2 = item.get('limit_person2', 65535)
        if lp2 != 65535:
            kf.limit_person2 = lp2
        
        # 性别需求: 0=男, 1=女, 2=妖, 3=妖(葵花神针), 65535=不限
        ng = item.get('need_gender', 65535)
        if ng != 65535:
            gender_map = {0: '男', 1: '女', 2: '妖', 3: '妖'}
            kf.gender = gender_map.get(ng, '')
        
        # 家族/门派需求(65535=不限)
        nf = item.get('need_family', 65535)
        if nf != 65535:
            kf.need_family = nf
        ns = item.get('need_school', 65535)
        if ns != 65535:
            kf.need_school = ns
        
        kungfus.append(kf)
    
    # 按品阶排序
    kungfus.sort(key=lambda k: (k.tier, k.category, k.item_id))
    print(f'转换为 {len(kungfus)} 个Kungfu对象')
    return kungfus

if __name__ == '__main__':
    r_grp = r'E:\game\金书红颜录修改\jshyl5.60版\JsEditor\_m\jshyl_save1\save\R.grp'
    items, books = load_items_from_save(r_grp)
    
    # 验证几个已知秘籍
    for item_id in [918, 830, 275, 376, 260, 269]:
        if item_id < len(items):
            item = items[item_id]
            print(f"\n#{item_id} {item['name']}")
            print(f"  说明: {item['desc']}")
            print(f"  可练武功: {item['skill_id']}")
            print(f"  加成: 攻{item['attack']} 轻{item['dodge']} 防{item['defense']} 拳{item['fist']} 剑{item['sword']} 兵{item['weapon']} 指{item['finger']} 暗{item['dark']}")
            print(f"  需求: 资质{item['need_qual']} 内力性质{item['need_inner']} 攻击{item['need_attack']} 轻{item['need_dodge']} 兵{item['need_weapon']}")
            print(f"  价格: {item['price']}")

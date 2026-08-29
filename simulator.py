# -*- coding: utf-8 -*-
"""武功学习规划模拟器核心"""
from kungfu_db import Kungfu, load_kungfu_db, get_categories

# 升级点数: 资质 -> 每级点数
LEVEL_POINTS_TABLE = [
    (100, 20),
    (90, 18),
    (80, 16),
    (60, 14),
    (40, 12),
    (20, 10),
    (0, 8),
]

# 分配消耗: 属性 -> 每点属性需要的升级点数
ASSIGN_COST = {
    '攻击': 1,
    '防御': 2,
    '轻功': 3,
    '拳掌': 6, '御剑': 6, '兵器': 6, '指腿': 6, '暗毒': 6,
}

def get_level_points_per_level(qualification):
    """根据资质获取每级升级点数"""
    for threshold, points in LEVEL_POINTS_TABLE:
        if qualification >= threshold:
            return points
    return 8

class Simulator:
    def __init__(self, kungfu_db, kfid_to_itemid=None, week=1, tianshu=15):
        self.db = kungfu_db
        self.db_by_id = {kf.item_id: kf for kf in kungfu_db}
        self.db_by_name = {kf.name: kf for kf in kungfu_db}
        self.kfid_to_itemid = kfid_to_itemid or {}
        self.current_char = None
        self.learned = []      # 已修炼武功 [(Kungfu, 等级), ...]
        self.washed = []       # 洗武功 [(Kungfu, 等级), ...]
        self.special_books = []  # 无练出武功的特殊书籍(医毒书/宝典), 不占格子但加成生效
        self.special_books = [] # 特殊书籍(无练出武功, 不占格子) [(Kungfu, 等级), ...]
        self.base_attrs = {}   # 基础属性
        self.level_bonus = 0   # 等级加成(额外等级, 每级攻防轻+2)
        self.assigned = {}     # 自由属性点分配: {'攻击':0, '防御':0, ...}
        self.week = week       # 周目
        self.tianshu = tianshu  # 已获得天书数量(0-15)
        self.kfid_to_name = {}  # 武功编号->名称映射
        self.special_kungfu_names = []  # 特技/天赋名称列表(未映射到秘籍的)
        self.mingyu_total = 0   # 明玉丹数量(额外武功格)
        self.initial_count = 0  # 初始技能数量(不可删除)
        self.attr_cap = 999 + (week - 1) * 40       # 属性上限(攻防轻五系)
        self.max_kungfu = 20 + (week - 1) * 2       # 武功格上限
        self.wuchang_cap = 200 + (week - 1) * 30    # 武常上限
        self.level_cap = self._calc_level_cap()     # 等级上限

    def _calc_level_cap(self):
        """计算等级上限: 25+(周目-2)*5 + 天书分段加成
        前5本每本+5, 第6-10本每本+3, 第11-15本每本+1
        """
        base = 25 + (self.week - 2) * 5
        ts = min(self.tianshu, 15)
        bonus = 0
        if ts > 0:
            bonus += min(ts, 5) * 5
        if ts > 5:
            bonus += min(ts - 5, 5) * 3
        if ts > 10:
            bonus += (ts - 10) * 1
        return base + bonus

    def load_character(self, char):
        """加载角色"""
        self.current_char = char
        self.learned = []
        self.washed = []
        self.level_bonus = 0
        self.assigned = {k: 0 for k in ASSIGN_COST.keys()}
        self.base_attrs = {
            '攻击': char.attack,
            '防御': char.defense,
            '轻功': char.dodge,
            '拳掌': char.skills.get('拳掌', 0),
            '御剑': char.skills.get('御剑', 0),
            '兵器': char.skills.get('兵器', 0),
            '指腿': char.skills.get('指腿', 0),
            '暗毒': char.skills.get('暗毒', 0),
            '资质': char.qualification,
            '体质': char.body,
            '武常': char.wuchang,
            '血量': char.hp_max,
            '内力': char.mp_max,
            '医疗': char.medical,
            '用毒': char.use_poison,
            '抗毒': char.anti_poison,
            '解毒': char.detox,
            '生命': 0,
            '功力': 0,
            '攻击带毒': 0,
        }
        # 自动载入已学武功(通过武功编号->秘籍物品编号映射)
        self.special_kungfu_names = []  # 未映射到秘籍的特技/天赋名称
        self.initial_count = 0  # 初始技能数量
        if hasattr(char, 'learned_kungfu_ids') and char.learned_kungfu_ids:
            for kid in char.learned_kungfu_ids:
                item_id = self.kfid_to_itemid.get(kid)
                if item_id:
                    kf = self.db_by_id.get(item_id)
                    if kf:
                        self.learned.append((kf, 10))
                        self.initial_count += 1
                        continue
                # 未映射到秘籍的, 作为特技
                name = getattr(self, 'kfid_to_name', {}).get(kid, f'#{kid}')
                self.special_kungfu_names.append(name)
        self.special_count = len(self.special_kungfu_names)
        # 计算明玉丹数量(额外武功格)
        # 原始主角(称号"惜花六如")固定7颗, 其他按资质
        is_primary = ('惜花六如' in (char.nickname or ''))
        if is_primary:
            self.mingyu_total = 7  # 原始主角7颗
        else:
            # 复制人主角及队友: 12 - (资质//10)
            self.mingyu_total = max(2, 12 - (char.qualification // 10))
        # 武功格上限 = 周目上限 + 明玉丹数量
        self.max_kungfu = 20 + (self.week - 1) * 2 + self.mingyu_total

    def adjust_level(self, delta):
        """调整等级(每级攻防轻+2, 并获得升级点数)，受等级上限限制"""
        old_level = self.level_bonus
        self.level_bonus += delta
        if self.level_bonus < 0:
            self.level_bonus = 0
        # 等级上限: 实际等级=1+level_bonus, 不超过level_cap
        max_bonus = self.level_cap - 1
        if self.level_bonus > max_bonus:
            self.level_bonus = max_bonus
        # 如果等级降低, 需要确保已分配点数不超过总点数
        if self.level_bonus < old_level:
            self._clamp_assigned()

    def reset_level(self):
        """重置等级加成和分配"""
        self.level_bonus = 0
        self.assigned = {k: 0 for k in ASSIGN_COST.keys()}

    def get_total_level_points(self):
        """获取总升级点数"""
        if not self.current_char or self.level_bonus <= 0:
            return 0
        per = get_level_points_per_level(self.current_char.qualification)
        return per * self.level_bonus

    def get_used_level_points(self):
        """获取已使用的升级点数"""
        used = 0
        for attr, count in self.assigned.items():
            used += count * ASSIGN_COST.get(attr, 1)
        return used

    def get_free_level_points(self):
        """获取剩余升级点数"""
        return self.get_total_level_points() - self.get_used_level_points()

    def assign_attr(self, attr, points=1):
        """分配自由属性点"""
        if attr not in ASSIGN_COST:
            return False, '不支持的属性'
        cost = ASSIGN_COST[attr] * points
        if cost > self.get_free_level_points():
            return False, f'升级点数不足(需要{cost}, 剩余{self.get_free_level_points()})'
        self.assigned[attr] = self.assigned.get(attr, 0) + points
        return True, '分配成功'

    def unassign_attr(self, attr, points=1):
        """取消分配自由属性点"""
        if attr not in ASSIGN_COST:
            return False, '不支持的属性'
        if self.assigned.get(attr, 0) < points:
            return False, '分配点数不足'
        self.assigned[attr] -= points
        return True, '取消成功'

    def set_assign(self, attr, target):
        """设置属性分配点数为指定值"""
        if attr not in ASSIGN_COST:
            return False, '不支持的属性'
        target = max(0, int(target))
        current = self.assigned.get(attr, 0)
        if target == current:
            return True, '无变化'
        if target > current:
            return self.assign_attr(attr, target - current)
        else:
            return self.unassign_attr(attr, current - target)

    def _clamp_assigned(self):
        """等级降低时, 自动削减超出的分配"""
        while self.get_used_level_points() > self.get_total_level_points():
            reduced = False
            for attr in reversed(list(ASSIGN_COST.keys())):
                if self.assigned.get(attr, 0) > 0:
                    self.assigned[attr] -= 1
                    reduced = True
                    break
            if not reduced:
                break

    def can_learn(self, kf):
        """检查是否可以修炼某武功"""
        if kf is None:
            return False, '武功不存在'
        # 无练出武功的特殊书籍(医毒书/宝典)不占格子, 跳过格子检查
        if not (hasattr(kf, 'no_skill') and kf.no_skill):
            # 总已学格子 = 特技 + 修炼武功
            total_used = len(self.learned) + getattr(self, 'special_count', 0)
            if total_used >= self.max_kungfu:
                return False, '武功格子已满'
        if (kf.limit_person is not None or kf.limit_person2 is not None) and self.current_char:
            char_seq = getattr(self.current_char, 'seq', -1)
            allowed = []
            if kf.limit_person is not None:
                allowed.append(kf.limit_person)
            if kf.limit_person2 is not None:
                allowed.append(kf.limit_person2)
            if char_seq not in allowed:
                from save_reader import get_seq_to_name
                name_map = get_seq_to_name()
                names = []
                for s in allowed:
                    n = name_map.get(s, f'#{s}')
                    if s == 0: n = '主角'
                    names.append(n)
                return False, f'仅限{"或".join(names)}'
        if kf.gender and self.current_char:
            g = kf.gender
            cg = self.current_char.gender
            if g == '男' and cg != '男':
                return False, '仅限男性'
            if g == '女' and cg != '女':
                return False, '仅限女性'
            if g == '妖' and cg != '妖':
                return False, '仅限妖(需自宫)'
        if kf.need_family is not None and self.current_char:
            if getattr(self.current_char, 'family', 65535) != kf.need_family:
                from save_reader import FAMILY_MAP
                return False, f'需{FAMILY_MAP.get(kf.need_family, f"家族#{kf.need_family}")}'
        if kf.need_school is not None and self.current_char:
            if getattr(self.current_char, 'sect', 65535) != kf.need_school:
                from save_reader import SECT_MAP
                return False, f'需{SECT_MAP.get(kf.need_school, f"门派#{kf.need_school}")}'
        if kf.qualification is not None and self.current_char:
            q = self.current_char.qualification
            if kf.qualification > 0 and q < kf.qualification:
                return False, f'资质不足(需≥{kf.qualification})'
            if kf.qualification < 0 and q >= abs(kf.qualification):
                return False, f'资质过高(需<{abs(kf.qualification)})'
        if kf.inner_type and kf.inner_type != '调和' and self.current_char:
            if self.current_char.inner_type != '调和' and self.current_char.inner_type != kf.inner_type:
                return False, f'需{kf.inner_type}内'
        attrs = self.get_current_attrs()
        if kf.need_inner and attrs.get('内力', 0) < kf.need_inner:
            return False, f'内力不足(需{kf.need_inner})'
        if kf.need_attack and attrs.get('攻击', 0) < kf.need_attack:
            return False, f'攻击不足(需{kf.need_attack})'
        if kf.need_dodge and attrs.get('轻功', 0) < kf.need_dodge:
            return False, f'轻功不足(需{kf.need_dodge})'
        if kf.need_use_poison and attrs.get('用毒', 0) < kf.need_use_poison:
            return False, f'用毒不足(需{kf.need_use_poison})'
        if kf.need_medical and attrs.get('医疗', 0) < kf.need_medical:
            return False, f'医疗不足(需{kf.need_medical})'
        for skill, need in kf.need_skills.items():
            if attrs.get(skill, 0) < need:
                return False, f'{skill}不足(需{need})'
        return True, '可以修炼'

    def add_kungfu(self, kf, level=10, is_washed=False):
        """添加武功"""
        if not is_washed:
            ok, reason = self.can_learn(kf)
            if not ok:
                return False, reason
        # 无练出武功的特殊书籍(医毒书/宝典): 不占格子, 加入special_books
        if hasattr(kf, 'no_skill') and kf.no_skill and not is_washed:
            self.special_books.append((kf, level))
        elif is_washed:
            self.washed.append((kf, level))
        else:
            self.learned.append((kf, level))
        # 学习和洗武功后都改变内属
        if hasattr(kf, 'change_inner') and kf.change_inner:
            self.current_char.inner_type = kf.change_inner
        return True, '添加成功'

    def remove_kungfu(self, index, is_washed=False):
        """移除武功"""
        try:
            if is_washed:
                self.washed.pop(index)
            else:
                self.learned.pop(index)
            return True
        except:
            return False

    def remove_special_book(self, index):
        """移除已学特殊书籍(医毒书/宝典)"""
        try:
            self.special_books.pop(index)
            return True
        except:
            return False

    def get_current_attrs(self):
        """计算当前属性（基础+等级+自由分配+武功加成），应用周目上限"""
        attrs = dict(self.base_attrs)

        # 等级自动加成: 每级攻防轻+2
        if self.level_bonus > 0:
            attrs['攻击'] += self.level_bonus * 2
            attrs['防御'] += self.level_bonus * 2
            attrs['轻功'] += self.level_bonus * 2

        # 自由属性点分配
        for attr, count in self.assigned.items():
            if count > 0:
                attrs[attr] = attrs.get(attr, 0) + count

        # 已学武功加成(学习升10级)
        for kf, level in self.learned:
            if hasattr(kf, 'is_special') and kf.is_special:
                continue
            for k, v in kf.bonuses.items():
                if v != 0:
                    attrs[k] = attrs.get(k, 0) + v * level

        # 无练出武功的特殊书籍加成(医毒书/宝典, 不占格子但加成生效)
        for kf, level in self.special_books:
            for k, v in kf.bonuses.items():
                if v != 0:
                    attrs[k] = attrs.get(k, 0) + v * level

        # 洗武功加成(洗武功升9级)
        for kf, level in self.washed:
            for k, v in kf.bonuses.items():
                if v != 0:
                    attrs[k] = attrs.get(k, 0) + v * level

        # 应用周目属性上限(攻防轻五系)
        capped_attrs = ['攻击', '防御', '轻功', '拳掌', '御剑', '兵器', '指腿', '暗毒']
        for a in capped_attrs:
            if attrs.get(a, 0) > self.attr_cap:
                attrs[a] = self.attr_cap

        # 武常上限
        if attrs.get('武常', 0) > self.wuchang_cap:
            attrs['武常'] = self.wuchang_cap

        return attrs

    def get_available_kungfus(self, category=None):
        """获取可修炼的武功列表"""
        result = []
        for kf in self.db:
            if category and kf.category != category:
                continue
            ok, reason = self.can_learn(kf)
            result.append((kf, ok, reason))
        return result

    def get_bonus_summary(self):
        """获取加成汇总"""
        total = {}
        if self.level_bonus > 0:
            total['等级'] = f'+{self.level_bonus}(攻防轻各+{self.level_bonus*2})'
        assigned_str = []
        for attr, count in self.assigned.items():
            if count > 0:
                assigned_str.append(f'{attr}+{count}')
        if assigned_str:
            total['根骨'] = ' '.join(assigned_str)
        return total

    def reset(self):
        """重置所有"""
        self.learned = []
        self.washed = []
        self.special_books = []
        self.level_bonus = 0
        self.assigned = {k: 0 for k in ASSIGN_COST.keys()}

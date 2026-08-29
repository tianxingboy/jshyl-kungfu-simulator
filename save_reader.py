# -*- coding: utf-8 -*-
"""存档读取器 - 从.zx5存档读取角色数据"""
import struct
import os
import subprocess
import shutil
import tempfile

# 家族/门派编号→名称映射(从游戏数据提取, 硬编码)
FAMILY_MAP = {
    0: '', 1: '慕容世家', 2: '大理段氏', 3: '蒙古', 4: '天波杨府',
}
SECT_MAP = {
    0: '', 1: '峨眉派', 2: '武当派', 3: '逍遥派', 4: '丐帮',
    5: '桃花岛', 6: '日月神教', 7: '华山派', 8: '明教', 9: '古墓派',
}

# 可加入队友名单, 从JSON加载
def _get_teammate_json():
    from kungfu_db import resource_path
    return resource_path('teammates.json')

_head_to_seq_cache = None   # 头像代号 -> 人物序号
_seq_to_name_cache = None   # 人物序号 -> 姓名

def load_teammate_list():
    """从teammates.json加载可加入队友名单"""
    global _head_to_seq_cache, _seq_to_name_cache
    if _head_to_seq_cache is not None:
        return _head_to_seq_cache
    try:
        import json
        with open(_get_teammate_json(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        _head_to_seq_cache = {int(k): v for k, v in data.get('head_to_seq', {}).items()}
        _seq_to_name_cache = {int(k): v for k, v in data.get('seq_to_name', {}).items()}
        return _head_to_seq_cache
    except Exception as e:
        print(f'加载可加入队友名单失败: {e}')
        return {}

def get_seq_to_name():
    """获取人物序号->姓名映射"""
    if _seq_to_name_cache is None:
        load_teammate_list()
    return _seq_to_name_cache or {}

class Character:
    def __init__(self):
        self.name = ''
        self.nickname = ''
        self.code = 0       # 头像代号
        self.seq = 0        # 人物序号(Excel第一列)
        self.qualification = 0  # 资质
        self.level = 1
        self.hp = 0
        self.hp_max = 0
        self.mp = 0
        self.mp_max = 0
        self.attack = 0
        self.defense = 0
        self.dodge = 0      # 轻功
        self.body = 0       # 体质
        self.wuchang = 0    # 武常
        self.skills = {     # 五系系数
            '拳掌': 0, '御剑': 0, '兵器': 0, '指腿': 0, '暗毒': 0
        }
        self.medical = 0    # 医疗
        self.use_poison = 0 # 用毒
        self.anti_poison = 0 # 抗毒
        self.detox = 0      # 解毒
        self.inner_type = '调和'  # 内力性质
        self.gender = '男'
        self.left_right = False  # 左右互搏
        self.learned_kungfu_ids = []  # 已学武功编号列表
        self.remaining_points = 0  # 剩余根骨值(升级点数)
        self.raw_offset = 0  # 在R.grp中的偏移
        self.char_index = 0  # 存档索引0-2479
        self.teammate_seq = 0  # 可加入队友表人物编号(u16s[16])
        self.family = 65535  # 家族(数值)
        self.sect = 65535    # 门派(数值)
        self.family_name = ''  # 血族名称(从Excel)
        self.sect_name = ''    # 门派名称(从Excel)
        self.is_main = False   # 是否为主角(第一个人物)

# 解包缓存: {zx5_path: (mtime, r_grp_path, work_dir)}
_unpack_cache = {}

def unpack_save(zx5_path, unpack_exe):
    """用unpack.exe解包存档，返回R.grp路径(带缓存: 存档未修改则复用)"""
    global _unpack_cache
    # 检查缓存
    try:
        mtime = os.path.getmtime(zx5_path)
    except:
        mtime = 0
    if zx5_path in _unpack_cache:
        cached_mtime, cached_r_grp, cached_work = _unpack_cache[zx5_path]
        if cached_mtime == mtime and os.path.exists(cached_r_grp):
            return cached_r_grp, cached_work

    # 工作目录: 存档所在目录(打包后初始存档在_internal只读目录, 用临时目录)
    save_dir = os.path.dirname(os.path.abspath(zx5_path))
    save_name = os.path.basename(zx5_path)
    base_name = os.path.splitext(save_name)[0]
    # 检测是否在打包后的只读目录
    import sys
    if hasattr(sys, '_MEIPASS') and save_dir.startswith(sys._MEIPASS):
        import tempfile
        work_dir = os.path.join(tempfile.gettempdir(), 'jshyl_unpack', base_name)
        os.makedirs(work_dir, exist_ok=True)
        # 复制存档到临时目录
        shutil.copy2(zx5_path, os.path.join(work_dir, save_name))
    else:
        work_dir = save_dir

    # 把unpack.exe复制到工作目录再调用(避免打包后从_internal目录调用的杀毒扫描开销)
    local_unpack = os.path.join(work_dir, 'unpack.exe')
    if not os.path.exists(local_unpack):
        try:
            shutil.copy2(unpack_exe, local_unpack)
        except:
            local_unpack = unpack_exe  # 复制失败则用原路径

    # 解包(subprocess + CREATE_NO_WINDOW, 避免打包后创建控制台的开销)
    CREATE_NO_WINDOW = 0x08000000
    try:
        with open(os.devnull, 'w') as devnull:
            subprocess.run(
                [local_unpack, 'unpack_zx5', save_name],
                cwd=work_dir, stdout=devnull, stderr=devnull,
                creationflags=CREATE_NO_WINDOW
            )
    except:
        # 备用: 原路径调用
        try:
            with open(os.devnull, 'w') as devnull:
                subprocess.run(
                    [unpack_exe, 'unpack_zx5', save_name],
                    cwd=work_dir, stdout=devnull, stderr=devnull,
                    creationflags=CREATE_NO_WINDOW
                )
        except:
            pass

    # 找R.grp
    r_grp = os.path.join(work_dir, base_name, 'save', 'R.grp')
    if os.path.exists(r_grp):
        _unpack_cache[zx5_path] = (mtime, r_grp, work_dir)
        return r_grp, work_dir
    return None, work_dir

def read_gbk_string(data, offset, max_len=20):
    """从offset读取GBK字符串，遇到00结束"""
    end = offset
    while end < offset + max_len and end < len(data):
        if data[end] == 0:
            break
        # GBK中文字符占2字节
        if data[end] >= 0x81:
            end += 2
        else:
            end += 1
    try:
        return data[offset:end].decode('gbk', errors='ignore')
    except:
        return ''

def parse_r_grp(r_grp_path):
    """解析R.grp，返回角色列表
    人物数据块固定322字节, 共2480人(索引0-2479)
    FIRST_OFFSET动态检测: 人物总数2480(0x09b0)的位置 + 12
    初始存档: 2480在68 -> FIRST_OFFSET=80
    正常存档: 2480在76 -> FIRST_OFFSET=88
    """
    with open(r_grp_path, 'rb') as f:
        data = f.read()

    CHAR_SIZE = 322
    TOTAL_CHARS = 2480

    # 动态检测FIRST_OFFSET: 搜索人物总数2480(0x09b0)在头部的位置
    FIRST_OFFSET = 88  # 默认值
    found_2480 = False
    for off in range(60, 90, 2):
        if off + 2 <= len(data) and struct.unpack_from('<H', data, off)[0] == 2480:
            FIRST_OFFSET = off + 12
            found_2480 = True
            break
    # 备用方案: 初始存档/空存档头部没有2480, 通过搜索已知人物名字反推
    if not found_2480:
        # 搜索"胡斐"GBK编码, 胡斐通常是idx=1, 所以FIRST_OFFSET = 胡斐位置 - 322
        try:
            hufei_bytes = '胡斐'.encode('gbk')
            hf_idx = data.find(hufei_bytes, 100, 10000)
            if hf_idx > 0:
                # 验证: 胡斐前322字节应该是主角(idx=0)
                candidate = hf_idx - 322
                if candidate > 0:
                    FIRST_OFFSET = candidate
                    print(f'  备用检测: 胡斐在{hf_idx}, 反推FIRST_OFFSET={FIRST_OFFSET}')
        except:
            pass
    print(f'  人物数据起始偏移: {FIRST_OFFSET}')

    # 可加入队友映射: head_to_seq(头像代号->序号), seq_to_name(序号->姓名)
    head_to_seq = {}
    seq_to_name = {}
    try:
        import json, os
        from kungfu_db import resource_path
        with open(resource_path('teammates.json'), 'r', encoding='utf-8') as f:
            tdata = json.load(f)
        head_to_seq = {int(k): v for k, v in tdata.get('head_to_seq', {}).items()}
        seq_to_name = {int(k): v.lstrip('&') for k, v in tdata.get('seq_to_name', {}).items()}
    except:
        pass

    characters = []

    for idx in range(TOTAL_CHARS):
        offset = FIRST_OFFSET + idx * CHAR_SIZE
        if offset + 4 >= len(data):
            break

        # ===== 第一阶段: 只解析名字, 快速筛选 =====
        pos = offset
        name_bytes = b''
        while pos < len(data) and data[pos] != 0 and len(name_bytes) < 12:
            if data[pos] >= 0x81 and pos+1 < len(data) and 0x40 <= data[pos+1] <= 0xFE:
                name_bytes += data[pos:pos+2]
                pos += 2
            elif 0x20 <= data[pos] <= 0x7E:
                name_bytes += data[pos:pos+1]
                pos += 1
            else:
                break
        name = name_bytes.decode('gbk', errors='ignore').strip()
        if not name:
            continue

        # 快速筛选: idx=0为主角, 其他需匹配可加入队友表姓名
        expected_name = seq_to_name.get(idx, '').lstrip('&')
        is_main = (idx == 0)
        if not is_main and not (expected_name and name.lstrip('&') == expected_name):
            continue  # 非可加入队友, 跳过完整解析

        # ===== 第二阶段: 匹配成功, 解析完整属性 =====
        char = Character()
        char.raw_offset = offset
        char.char_index = idx
        char.is_main = is_main
        char.name = name
        char.seq = idx

        # 头像代号在名字前8字节
        char.code = struct.unpack_from('<H', data, offset-8)[0] if offset >= 8 else 0

        # 跳过名字后00填充, 读外号
        while pos < len(data) and data[pos] == 0:
            pos += 1
        nick_start = pos
        while pos < len(data) and data[pos] != 0:
            if data[pos] >= 0x81 and pos+1 < len(data) and 0x40 <= data[pos+1] <= 0xFE:
                pos += 2
            else:
                pos += 1
        try:
            char.nickname = data[nick_start:pos].decode('gbk', errors='ignore').strip()
        except:
            char.nickname = ''

        # 性别
        gender_val = struct.unpack_from('<H', data, offset + 20)[0] if offset + 22 <= len(data) else 0
        char.gender = {0: '男', 1: '女', 2: '妖'}.get(gender_val, '男')

        # 解析属性u16数组
        attr_start = offset + 22
        if attr_start + 160 < len(data):
            u16s = [struct.unpack_from('<H', data, attr_start + i*2)[0] for i in range(80)]
            char.level = u16s[0] if u16s[0] > 0 else 1
            char.hp = u16s[2]
            char.hp_max = u16s[3]
            char.qualification = u16s[45]
            char.body = u16s[44]
            char.mp = u16s[26]
            char.mp_max = u16s[27]
            char.inner_type = {0: '阴', 1: '阳', 2: '调和'}.get(u16s[25], '阴')
            char.attack = u16s[28]
            char.dodge = u16s[29]
            char.defense = u16s[30]
            char.wuchang = u16s[40]
            char.skills['拳掌'] = u16s[35] if u16s[35] <= 999 else 0
            char.skills['御剑'] = u16s[36] if u16s[36] <= 999 else 0
            char.skills['兵器'] = u16s[37] if u16s[37] <= 999 else 0
            char.skills['指腿'] = u16s[38] if u16s[38] <= 999 else 0
            char.skills['暗毒'] = u16s[39] if u16s[39] <= 999 else 0
            char.medical = u16s[31] if u16s[31] <= 999 else 0
            char.use_poison = u16s[32] if u16s[32] <= 999 else 0
            char.detox = u16s[33] if u16s[33] <= 999 else 0
            char.anti_poison = u16s[34] if u16s[34] <= 999 else 0
            char.family = u16s[13]
            char.sect = u16s[14]
            char.family_name = FAMILY_MAP.get(char.family, '')
            char.sect_name = SECT_MAP.get(char.sect, '')
            char.teammate_seq = u16s[16]
            char.remaining_points = u16s[15]
            # 已学武功: u16s[48]开始共30格
            char.learned_kungfu_ids = [u16s[i] for i in range(48, 78) if 0 < u16s[i] < 10000]

        characters.append(char)

    print(f'  固定步长遍历2480人, 筛选出可加入队友 {len(characters)} 人(含主角)')

    return characters

def parse_characters_from_r_grp(r_grp_path):
    """从已解包的R.grp加载角色列表(不解包)"""
    return parse_r_grp(r_grp_path)

def load_characters_from_save(zx5_path, unpack_exe):
    """从存档文件加载角色列表"""
    r_grp, work_dir = unpack_save(zx5_path, unpack_exe)
    if r_grp is None:
        return [], work_dir
    chars = parse_r_grp(r_grp)
    return chars, work_dir

def read_save_meta(r_grp_path):
    """从R.grp读取存档元信息
    周目: 文件末尾前1356字节 (offset = filesize - 1356), u8
    难度: 文件末尾前1352字节 (offset = filesize - 1352), u8
    游戏模式: R.grp头部 u16[13] (offset 26)
    """
    DIFFICULTY_NAMES = {0: '简单', 1: '普通', 2: '困难', 3: '苦战', 4: '自虐'}
    MODE_NAMES = {0: '回合制', 1: '半即时', 2: '即时'}
    try:
        with open(r_grp_path, 'rb') as f:
            data = f.read()
        fsize = len(data)
        # 周目和难度在文件末尾
        week_off = fsize - 1356
        diff_off = fsize - 1352
        week = data[week_off] if week_off >= 0 else 0
        diff = data[diff_off] if diff_off >= 0 else 0
        # 游戏模式在头部
        mode = struct.unpack_from('<H', data, 26)[0] if fsize >= 28 else 0
        WEEK_NAMES = {1:'一周目',2:'二周目',3:'三周目',4:'四周目',5:'五周目',6:'六周目',7:'七周目',8:'八周目',9:'九周目',10:'十周目'}
        return {
            'week': week,
            'week_name': WEEK_NAMES.get(week, f'{week}周目'),
            'difficulty': diff,
            'difficulty_name': DIFFICULTY_NAMES.get(diff, f'未知({diff})'),
            'mode': mode,
            'mode_name': MODE_NAMES.get(mode, f'未知({mode})'),
        }
    except:
        pass
    return {'week': 0, 'week_name': '未知', 'difficulty': 0, 'difficulty_name': '未知', 'mode': 0, 'mode_name': '未知'}

if __name__ == '__main__':
    unpack_exe = r'E:\game\金书红颜录修改\jshyl5.60版\JsEditor\unpack.exe'
    save_path = r'E:\game\金书红颜录修改\jshyl5.60版\JsEditor\_m\jshyl_save1.zx5'
    chars, wd = load_characters_from_save(save_path, unpack_exe)
    print(f'读取到 {len(chars)} 个角色')
    for c in chars[:20]:
        print(f'  [{c.code}] {c.name}({c.nickname}) 资质{c.qualification} 攻{c.attack} 防{c.defense} 轻{c.dodge}')

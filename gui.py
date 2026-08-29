# -*- coding: utf-8 -*-
"""武功学习规划模拟器 GUI - 参考JSData5布局"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kungfu_db import get_categories, Kungfu
from save_reader import load_characters_from_save, parse_characters_from_r_grp, unpack_save, Character, read_save_meta
from simulator import Simulator
from item_reader import load_kungfu_from_save
from kf_mapper import build_map_from_books, load_kfid_name_map

class KungfuSimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('金书红颜录5.60 武功学习规划模拟器')
        self.root.geometry('1400x850')
        self.root.minsize(1200, 700)

        from kungfu_db import resource_path
        self.unpack_exe = resource_path('unpack.exe')
        # 默认存档: 优先exe同目录下的save文件夹(用户当前存档), 没有则用打包的初始存档
        self.default_save = None
        exe_dir = os.path.dirname(os.path.abspath(__file__))
        for cand in [
            os.path.join(exe_dir, 'save', 'jshyl_save1.zx5'),
            os.path.join(exe_dir, 'jshyl_save1.zx5'),
            resource_path('jshyl_save0.zx5'),
        ]:
            if os.path.exists(cand):
                self.default_save = cand
                break

        print('加载武功编号->名称映射...')
        self.kfid_to_name = load_kfid_name_map()

        if self.default_save:
            print('从存档读取秘籍库...')
            r_grp, wd = unpack_save(self.default_save, self.unpack_exe)
            self.r_grp_path = r_grp
            self.work_dir = wd
            if r_grp:
                self.kungfu_db, self.kfid_to_itemid = self._load_books_from_r_grp(r_grp)
            else:
                self.kungfu_db = []
                self.kfid_to_itemid = {}
            print(f'加载 {len(self.kungfu_db)} 条秘籍')
        else:
            print('未找到默认存档, 请点击"读取存档"加载')
            self.kungfu_db = []
            self.kfid_to_itemid = {}
            self.r_grp_path = None

        self.sim = Simulator(self.kungfu_db, self.kfid_to_itemid)
        self.characters = []
        self.current_category = '拳掌'
        self.work_dir = None
        self.char_states = {}  # 每个人物的模拟状态: {name: {'learned':..., 'washed':..., 'level_bonus':..., 'assigned':...}}
        self._current_char_name = None
        self._updating = False  # 防止输入框trace循环

        self._build_ui()
        self._load_default_save()

    def _build_ui(self):
        # 设置Treeview字体
        style = ttk.Style()
        style.configure('Treeview', font=('TkDefaultFont', 12))
        style.configure('Treeview.Heading', font=('TkDefaultFont', 12, 'bold'))

        # 顶部工具栏
        toolbar = ttk.Frame(self.root, padding=5)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text='打开存档', command=self.open_save).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='导出模拟', command=self.export_sim).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='导入模拟', command=self.import_sim).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='人物模板', command=self.load_char_template).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text='全部重置', command=self.reset_sim).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.meta_var = tk.StringVar(value='周目: - 难度: -')
        ttk.Label(toolbar, textvariable=self.meta_var, font=('TkDefaultFont', 12, 'bold'), foreground='darkred').pack(side=tk.LEFT, padx=10)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        self.status_var = tk.StringVar(value='就绪')
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.LEFT, padx=10)

        # 主区域 - 四列布局
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        # === 第1列: 角色列表 ===
        left = ttk.LabelFrame(main, text='队友', padding=3)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        left.configure(width=130)
        left.pack_propagate(False)

        self.char_count_var = tk.StringVar(value='共(0)')
        ttk.Label(left, textvariable=self.char_count_var, font=('TkDefaultFont', 12)).pack(anchor=tk.W)
        search_frame = ttk.Frame(left)
        search_frame.pack(fill=tk.X, pady=(0, 3))
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *a: self._filter_chars())
        ttk.Entry(search_frame, textvariable=self.search_var, width=14).pack(fill=tk.X)

        self.char_listbox = tk.Listbox(left, width=14, font=('TkDefaultFont', 12))
        self.char_listbox.pack(fill=tk.BOTH, expand=True)
        self.char_listbox.bind('<<ListboxSelect>>', self._on_char_select)

        # === 第2列: 属性面板 ===
        attr_panel = ttk.Frame(main)
        attr_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        attr_panel.configure(width=340)

        # 名字外号
        name_frame = ttk.Frame(attr_panel)
        name_frame.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(name_frame, text='名字:', font=('TkDefaultFont', 12)).pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value='-')
        ttk.Label(name_frame, textvariable=self.name_var, font=('TkDefaultFont', 12, 'bold'), foreground='blue').pack(side=tk.LEFT, padx=5)
        ttk.Label(name_frame, text='称号:', font=('TkDefaultFont', 12)).pack(side=tk.LEFT, padx=(10,0))
        self.nick_var = tk.StringVar(value='-')
        ttk.Label(name_frame, textvariable=self.nick_var, font=('TkDefaultFont', 12)).pack(side=tk.LEFT, padx=5)

        # 属性表 (两列: 左列基础属性只读, 右列可加点属性带输入框)
        attr_frame = ttk.LabelFrame(attr_panel, text='角色属性', padding=3)
        attr_frame.pack(fill=tk.X)

        # 左列: 基础属性(只读)
        left_col = ttk.Frame(attr_frame)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        self.base_labels = {}
        base_rows = [
            ('性别', 'gender'), ('等级', 'level'),
            ('医疗', 'medical'), ('用毒', 'use_poison'),
            ('解毒', 'detox'), ('抗毒', 'anti_poison'),
            ('武常', 'wuchang'), ('血量', 'hp_max'),
            ('内力', 'mp_max'), ('资质', 'qualification'),
            ('体质', 'body'), ('左右', 'left_right'),
            ('内属', 'inner_type'), ('血族', 'family_name'),
            ('门派', 'sect_name'),
        ]
        for i, (label, key) in enumerate(base_rows):
            row_f = ttk.Frame(left_col)
            row_f.pack(fill=tk.X, pady=1)
            ttk.Label(row_f, text=label, font=('TkDefaultFont', 12), width=6).pack(side=tk.LEFT)
            lbl = ttk.Label(row_f, text='-', font=('TkDefaultFont', 12), width=8, anchor=tk.W)
            lbl.pack(side=tk.LEFT, padx=(2,0))
            self.base_labels[key] = lbl

        # 右列: 可加点属性(属性名 + 原始值 + 输入框)
        right_col = ttk.Frame(attr_frame)
        right_col.pack(side=tk.LEFT, fill=tk.Y)
        self.assign_labels = {}
        self.assign_entries = {}
        self.assign_vars = {}
        self.final_labels = {}
        assign_rows = [
            ('攻击', 'attack'), ('防御', 'defense'), ('轻功', 'dodge'),
            ('拳掌', '拳掌'), ('御剑', '御剑'), ('兵器', '兵器'),
            ('指腿', '指腿'), ('暗毒', '暗毒'),
        ]
        for i, (label, key) in enumerate(assign_rows):
            r = i
            ttk.Label(right_col, text=label, font=('TkDefaultFont', 12), width=5).grid(row=r, column=0, sticky=tk.W, pady=1)
            cur_lbl = ttk.Label(right_col, text='0', font=('TkDefaultFont', 12), width=5, anchor=tk.E)
            cur_lbl.grid(row=r, column=1, sticky=tk.E, padx=(0,2), pady=1)
            self.assign_labels[key] = cur_lbl
            ttk.Label(right_col, text='+', font=('TkDefaultFont', 12), width=2).grid(row=r, column=2)
            var = tk.StringVar(value='0')
            ent = ttk.Entry(right_col, textvariable=var, width=5, font=('TkDefaultFont', 12))
            ent.grid(row=r, column=3, sticky=tk.W, pady=1)
            ent.bind('<Return>', lambda e, k=key: self._on_assign_entry(k))
            ent.bind('<FocusOut>', lambda e, k=key: self._on_assign_entry(k))
            self.assign_entries[key] = ent
            self.assign_vars[key] = var
            # 最终值标签
            final_lbl = ttk.Label(right_col, text='= 0', font=('TkDefaultFont', 12), width=8, anchor=tk.W)
            final_lbl.grid(row=r, column=4, sticky=tk.W, padx=(2,0), pady=1)
            self.final_labels[key] = final_lbl
            self._assign_after_ids = {}

        # 根骨点显示(加点列下方, 分两行)
        root_row = len(assign_rows) + 1
        ttk.Label(right_col, text='剩余根骨', font=('TkDefaultFont', 12, 'bold'), foreground='darkgreen', width=8).grid(row=root_row, column=0, sticky=tk.W, pady=(8,1))
        self.root_points_var = tk.StringVar(value='0')
        ttk.Label(right_col, textvariable=self.root_points_var, font=('TkDefaultFont', 12, 'bold'), foreground='darkgreen', width=6, anchor=tk.W).grid(row=root_row, column=1, sticky=tk.W, pady=(8,1))
        # 单独重置加点按钮(下一行)
        ttk.Button(right_col, text='重置加点', command=self._reset_assigned, width=8).grid(row=root_row+1, column=0, columnspan=3, sticky=tk.W, pady=(1,3))

        # 升级规划按钮区
        level_frame = ttk.LabelFrame(attr_panel, text='升级规划', padding=3)
        level_frame.pack(fill=tk.X, pady=(3,0))

        # 升级到输入框
        row1 = ttk.Frame(level_frame)
        row1.pack(fill=tk.X, pady=1)
        ttk.Label(row1, text='升级到:', font=('TkDefaultFont', 12)).pack(side=tk.LEFT)
        self.level_to_var = tk.StringVar(value='1')
        level_ent = ttk.Entry(row1, textvariable=self.level_to_var, width=6, font=('TkDefaultFont', 12))
        level_ent.pack(side=tk.LEFT, padx=3)
        level_ent.bind('<Return>', lambda e: self._on_level_to())
        ttk.Button(row1, text='应用', command=self._on_level_to, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text='重置等级', command=self._reset_level, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text='升至满级', command=self._level_to_cap, width=8).pack(side=tk.LEFT, padx=2)

        row2 = ttk.Frame(level_frame)
        row2.pack(fill=tk.X, pady=1)
        ttk.Button(row2, text='所有武功升到10级', command=self._all_kungfu_to_10).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text='重置当前人物状态', command=self.reset_current_char).pack(side=tk.LEFT, padx=2)

        # 已学特殊书籍(医毒书/宝典, 不占武功格子, 双击删除)
        special_frame = ttk.LabelFrame(attr_panel, text='已学特殊书籍(双击删除)', padding=3)
        special_frame.pack(fill=tk.BOTH, expand=True, pady=(3,0))
        self.special_tree = ttk.Treeview(special_frame, columns=('name','bonus'), show='headings', height=8)
        self.special_tree.heading('name', text='书籍')
        self.special_tree.heading('bonus', text='加成')
        self.special_tree.column('name', width=120)
        self.special_tree.column('bonus', width=180)
        self.special_tree.pack(fill=tk.BOTH, expand=True)
        self.special_tree.bind('<Double-Button-1>', self._remove_special_book)

        # === 第3列: 修炼武功 ===
        learn_panel = ttk.LabelFrame(main, text='修炼武功(双击删除)', padding=3)
        learn_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        learn_panel.configure(width=220)

        self.learn_tree = ttk.Treeview(learn_panel, columns=('num','name','level'), show='headings', height=25)
        self.learn_tree.heading('num', text='#')
        self.learn_tree.heading('name', text='武功')
        self.learn_tree.heading('level', text='等级')
        self.learn_tree.column('num', width=30, anchor=tk.CENTER)
        self.learn_tree.column('name', width=130)
        self.learn_tree.column('level', width=40, anchor=tk.CENTER)
        self.learn_tree.pack(fill=tk.BOTH, expand=True)
        self.learn_tree.bind('<Double-Button-1>', lambda e: self._remove_kungfu(False))

        # === 第4列: 洗武功 ===
        wash_panel = ttk.LabelFrame(main, text='洗武功(双击删除)', padding=3)
        wash_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        wash_panel.configure(width=200)

        self.wash_tree = ttk.Treeview(wash_panel, columns=('num','name','level'), show='headings', height=25)
        self.wash_tree.heading('num', text='#')
        self.wash_tree.heading('name', text='武功')
        self.wash_tree.heading('level', text='等级')
        self.wash_tree.column('num', width=30, anchor=tk.CENTER)
        self.wash_tree.column('name', width=120)
        self.wash_tree.column('level', width=40, anchor=tk.CENTER)
        self.wash_tree.pack(fill=tk.BOTH, expand=True)
        self.wash_tree.bind('<Double-Button-1>', lambda e: self._remove_kungfu(True))

        # === 第5列: 武功库 ===
        right = ttk.LabelFrame(main, text='武功库(双击修炼, Ctrl+双击洗武功)', padding=3)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right.configure(width=380)

        # 分类标签
        cat_frame = ttk.Frame(right)
        cat_frame.pack(fill=tk.X, pady=(0, 3))
        self.cat_buttons = {}
        cats = get_categories()
        for i, cat in enumerate(cats):
            btn = ttk.Button(cat_frame, text=cat, width=5,
                           command=lambda c=cat: self._select_category(c))
            btn.grid(row=i//4, column=i%4, padx=1, pady=1)
            self.cat_buttons[cat] = btn

        # 武功列表: 等级、秘笈名称、练出武功
        self.kungfu_tree = ttk.Treeview(right, columns=('tier','book','skill'), show='headings', height=10)
        self.kungfu_tree.heading('tier', text='等级')
        self.kungfu_tree.heading('book', text='秘笈名称')
        self.kungfu_tree.heading('skill', text='练出武功')
        self.kungfu_tree.column('tier', width=40, anchor=tk.CENTER)
        self.kungfu_tree.column('book', width=100)
        self.kungfu_tree.column('skill', width=85)
        self.kungfu_tree.pack(fill=tk.BOTH, expand=True)
        self.kungfu_tree.bind('<Double-Button-1>', self._on_kungfu_double)
        self.kungfu_tree.bind('<Control-Double-Button-1>', lambda e: self._on_kungfu_double(e, washed=True))
        self.kungfu_tree.bind('<<TreeviewSelect>>', self._on_kungfu_select)

        # 需求效果显示
        req_frame = ttk.LabelFrame(right, text='需求 / 效果', padding=3)
        req_frame.pack(fill=tk.X, pady=(3,0))
        req_inner = tk.Frame(req_frame, height=320)
        req_inner.pack(fill=tk.X, expand=False)
        req_inner.pack_propagate(False)
        self.req_var = tk.StringVar(value='选择武功查看需求和效果')
        ttk.Label(req_inner, textvariable=self.req_var, font=('TkDefaultFont', 14), wraplength=340, justify=tk.LEFT, anchor='nw').pack(fill=tk.BOTH, expand=True)

        # 底部: 加成汇总
        bottom = ttk.LabelFrame(self.root, text='加成汇总', padding=3)
        bottom.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.bonus_var = tk.StringVar(value='暂无加成')
        ttk.Label(bottom, textvariable=self.bonus_var, font=('TkDefaultFont', 12)).pack(anchor=tk.W)

    def _load_books_from_r_grp(self, r_grp):
        """从已解包的R.grp读取秘籍库(不解包)"""
        books = load_kungfu_from_save(r_grp, self.kfid_to_name)
        kfid_to_itemid, _ = build_map_from_books(books=books)
        return books, kfid_to_itemid

    def _load_default_save(self):
        if self.default_save and os.path.exists(self.default_save):
            self._load_save(self.default_save)

    def open_save(self):
        path = filedialog.askopenfilename(
            title='选择存档文件',
            filetypes=[('存档文件', '*.zx5'), ('所有文件', '*.*')],
            initialdir=r'E:\game\金书红颜录修改\jshyl5.60版\save'
        )
        if path:
            self._load_save(path)

    def _load_save(self, path):
        self.status_var.set('正在读取存档...')
        self.root.update()
        try:
            # 解包一次, 复用R.grp分别解析秘籍和人物
            r_grp, wd = unpack_save(path, self.unpack_exe)
            if not r_grp:
                raise Exception('解包存档失败，未找到R.grp')
            self.r_grp_path = r_grp
            self.work_dir = wd

            # 解析秘籍库
            self.kungfu_db, self.kfid_to_itemid = self._load_books_from_r_grp(r_grp)
            self.sim.db = self.kungfu_db
            self.sim.db_by_id = {kf.item_id: kf for kf in self.kungfu_db}
            self.sim.db_by_name = {kf.name: kf for kf in self.kungfu_db}
            self.sim.kfid_to_itemid = self.kfid_to_itemid

            # 解析人物(复用已解包的R.grp)
            chars = parse_characters_from_r_grp(r_grp)
            self.characters = chars
            self.char_states = {}
            self._current_char_name = None
            # 读取存档元信息(周目/难度)
            meta = read_save_meta(self.r_grp_path)
            self.save_meta = meta
            week = meta['week']
            attr_cap = 999 + (week - 1) * 40
            wf_slots = 20 + (week - 1) * 2
            wc_cap = 200 + (week - 1) * 30
            # 等级上限(默认满天书15本)
            ts = 15
            lvl_base = 25 + (week - 2) * 5
            lvl_bonus = min(ts,5)*5 + max(0,min(ts-5,5))*3 + max(0,ts-10)*1
            lvl_cap = lvl_base + lvl_bonus
            # 武功格 = 周目上限 + 明玉丹数量(主角7, 队友按资质)
            wf_slots = 20 + (week - 1) * 2
            self.meta_var.set(f'{meta["week_name"]} | {meta["difficulty_name"]} | 属性上限{attr_cap} | 武功格{wf_slots}+明玉丹 | 等级上限{lvl_cap}')
            # 更新Simulator周目上限
            self.sim.week = week
            self.sim.tianshu = ts
            self.sim.attr_cap = attr_cap
            self.sim.max_kungfu = wf_slots
            self.sim.wuchang_cap = wc_cap
            self.sim.level_cap = self.sim._calc_level_cap()
            self._refresh_char_list()
            self.status_var.set(f'已加载 {len(chars)} 个可加入队友, {len(self.kungfu_db)} 条秘籍')
            if chars:
                self.char_listbox.selection_set(0)
                self._on_char_select(None)
            self._refresh_kungfu_list()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror('错误', f'读档失败: {e}')
            self.status_var.set('读档失败')

    def _refresh_char_list(self):
        self.char_listbox.delete(0, tk.END)
        keyword = self.search_var.get().strip()
        count = 0
        for c in self.characters:
            display = c.name
            if not keyword or keyword in c.name or keyword in (c.nickname or '') or keyword in display:
                self.char_listbox.insert(tk.END, f'{c.seq:>4} {display}')
                count += 1
        self.char_count_var.set(f'共({count})')

    def _filter_chars(self):
        self._refresh_char_list()

    def _save_current_state(self):
        """保存当前人物的模拟状态"""
        if self._current_char_name and self.sim.current_char:
            self.char_states[self._current_char_name] = {
                'learned': list(self.sim.learned),
                'washed': list(self.sim.washed),
                'special_books': list(self.sim.special_books),
                'level_bonus': self.sim.level_bonus,
                'assigned': dict(self.sim.assigned),
                'save_remaining': self.sim.save_remaining_points,
                'original_inner': self.sim.original_inner_type,
            }

    def _restore_char_state(self, char_name):
        """恢复某人物的模拟状态"""
        state = self.char_states.get(char_name)
        if state:
            self.sim.learned = list(state['learned'])
            self.sim.washed = list(state['washed'])
            self.sim.special_books = list(state.get('special_books', []))
            self.sim.level_bonus = state['level_bonus']
            self.sim.assigned = dict(state['assigned'])
            self.sim.save_remaining_points = state.get('save_remaining', 0)
            self.sim.original_inner_type = state.get('original_inner', None)
            return True
        return False

    def _on_char_select(self, event):
        sel = self.char_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        keyword = self.search_var.get().strip()
        filtered = [c for c in self.characters if not keyword or keyword in c.name or keyword in c.nickname]
        if idx < len(filtered):
            char = filtered[idx]
            # 保存上一个人物的状态
            self._save_current_state()
            # 加载新人物
            self.sim.kfid_to_name = self.kfid_to_name
            self.sim.load_character(char)
            self._current_char_name = char.name
            # 恢复该人物的模拟状态(如果有)
            restored = self._restore_char_state(char.name)
            display_name = char.name
            self.name_var.set(display_name)
            self.nick_var.set(char.nickname or '-')
            self._refresh_all()
            # 更新顶部显示(含当前角色明玉丹数量)
            if hasattr(self, 'save_meta') and self.save_meta:
                m = self.save_meta
                week = m['week']
                attr_cap = 999 + (week - 1) * 40
                wf_base = 20 + (week - 1) * 2
                ts = 15
                lvl_cap = 25 + (week - 2) * 5 + min(ts,5)*5 + max(0,min(ts-5,5))*3 + max(0,ts-10)*1
                my = self.sim.mingyu_total
                self.meta_var.set(f'{m["week_name"]} | {m["difficulty_name"]} | 属性上限{attr_cap} | 武功格{wf_base}+明玉丹{my} | 等级上限{lvl_cap}')
            if restored:
                self.status_var.set(f'已恢复 {display_name} 的模拟规划')
            else:
                self.status_var.set(f'已切换到 {display_name}')

    def _on_assign_entry(self, key):
        """输入框回车/失焦: 保存属性分配点数"""
        if not self.sim.current_char:
            return
        # key到属性名的映射(攻防轻用英文key, 系数用中文key)
        key_to_attr = {
            'attack': '攻击', 'defense': '防御', 'dodge': '轻功',
            '拳掌': '拳掌', '御剑': '御剑', '兵器': '兵器',
            '指腿': '指腿', '暗毒': '暗毒',
        }
        attr_name = key_to_attr.get(key, key)
        try:
            target = int(self.assign_vars[key].get())
        except ValueError:
            self.assign_vars[key].set(str(self.sim.assigned.get(attr_name, 0)))
            return
        ok, msg = self.sim.set_assign(attr_name, target)
        if not ok:
            self.status_var.set(msg)
            self.assign_vars[key].set(str(self.sim.assigned.get(attr_name, 0)))
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _on_level_to(self):
        """升级到指定等级"""
        try:
            target = int(self.level_to_var.get())
        except ValueError:
            self.level_to_var.set(str(self.sim.current_char.level + self.sim.level_bonus))
            return
        c = self.sim.current_char
        if c is None:
            return
        delta = target - c.level
        if delta < 0:
            delta = 0
        self.sim.level_bonus = delta
        self.sim._clamp_assigned()
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _all_kungfu_to_10(self):
        """所有已学武功升到10级"""
        new_learned = []
        for kf, lv in self.sim.learned:
            new_learned.append((kf, 10))
        self.sim.learned = new_learned
        self._refresh_attrs()
        self._refresh_kungfu_list()
        self._refresh_learn_lists()
        self.status_var.set('所有武功已升到10级')

    def _reset_level(self):
        self.sim.reset_level()
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _reset_assigned(self):
        """单独重置自由属性加点，不影响等级"""
        self.sim.assigned = {k: 0 for k in self.sim.assigned}
        for key, var in self.assign_vars.items():
            var.set('0')
        self._refresh_attrs()
        self.status_var.set('已重置加点')

    def _level_to_cap(self):
        """升级至当前周目等级上限"""
        c = self.sim.current_char
        if c is None:
            return
        cap = self.sim.level_cap
        delta = cap - c.level
        if delta < 0:
            delta = 0
        self.sim.level_bonus = delta
        self.sim._clamp_assigned()
        self.level_to_var.set(str(c.level + delta))
        self._refresh_attrs()
        self._refresh_kungfu_list()
        self.status_var.set(f'已升至{cap}级(上限)')

    def _refresh_all(self):
        self._refresh_attrs()
        self._refresh_kungfu_list()
        self._refresh_learn_lists()
        self._refresh_special_books()

    def _refresh_attrs(self):
        if not self.sim.current_char:
            return
        attrs = self.sim.get_current_attrs()
        c = self.sim.current_char

        # 左列: 基础属性(只读) - 医毒武常包含武功加成
        self.base_labels['gender'].config(text=c.gender)
        self.base_labels['level'].config(text=str(c.level + self.sim.level_bonus))
        self.base_labels['medical'].config(text=str(attrs.get('医疗', c.medical)))
        self.base_labels['use_poison'].config(text=str(attrs.get('用毒', c.use_poison)))
        self.base_labels['detox'].config(text=str(attrs.get('解毒', c.detox)))
        self.base_labels['anti_poison'].config(text=str(attrs.get('抗毒', c.anti_poison)))
        self.base_labels['wuchang'].config(text=str(attrs.get('武常', c.wuchang)))
        self.base_labels['hp_max'].config(text=str(c.hp_max))
        self.base_labels['mp_max'].config(text=str(c.mp_max))
        self.base_labels['qualification'].config(text=str(c.qualification))
        self.base_labels['body'].config(text=str(c.body))
        self.base_labels['left_right'].config(text='是' if c.left_right else '否')
        self.base_labels['inner_type'].config(text=c.inner_type)
        self.base_labels['family_name'].config(text=c.family_name or '无')
        self.base_labels['sect_name'].config(text=c.sect_name or '无')

        # 右列: 可加点属性(原始值 + 根骨输入框)
        assign_map = {
            'attack': '攻击', 'defense': '防御', 'dodge': '轻功',
            '拳掌': '拳掌', '御剑': '御剑', '兵器': '兵器',
            '指腿': '指腿', '暗毒': '暗毒',
        }
        focused = self.root.focus_get()
        for key, attr_name in assign_map.items():
            # 原始值 = 最终属性 - 自由分配(包含基础+等级+武功加成)
            final_val = attrs.get(attr_name, 0)
            assigned_val = self.sim.assigned.get(attr_name, 0)
            base_val = final_val - assigned_val
            self.assign_labels[key].config(text=str(base_val))
            # 跳过有焦点的输入框, 避免打断输入
            if focused != self.assign_entries.get(key):
                self.assign_vars[key].set(str(assigned_val))
            # 最终值
            self.final_labels[key].config(text=f'= {final_val}')

        # 剩余根骨点(存档剩余 + 模拟器升级获得 - 已分配)
        free = self.sim.get_free_level_points()
        if free < 0:
            self.sim._clamp_assigned()
            free = self.sim.get_free_level_points()
        self.root_points_var.set(str(max(0, free)))

        # 升级到输入框
        self.level_to_var.set(str(c.level + self.sim.level_bonus))

        # 加成汇总
        bonuses = self.sim.get_bonus_summary()
        parts = []
        for k, v in bonuses.items():
            if isinstance(v, int) and v != 0:
                sign = '+' if v > 0 else ''
                parts.append(f'{k}{sign}{v}')
            elif isinstance(v, str):
                parts.append(v)
        self.bonus_var.set('  '.join(parts) if parts else '暂无加成')

    def _select_category(self, cat):
        self.current_category = cat
        self._refresh_kungfu_list()

    def _format_qual(self, q):
        if q is None:
            return ''
        if q > 0:
            return f'资≥{q}'
        else:
            return f'资≤{abs(q) + 1}'

    def _refresh_kungfu_list(self):
        self.kungfu_tree.delete(*self.kungfu_tree.get_children())
        available = self.sim.get_available_kungfus(self.current_category)
        for kf, ok, reason in available:
            tag = 'ok' if ok else 'no'
            # 内功/轻功显示等级(1级-5级/防功), 五系显示+品阶
            if kf.category in ('内功', '轻功') and getattr(kf, 'level_str', ''):
                tier_display = kf.level_str
            else:
                tier_display = f'+{kf.tier}' if kf.tier else '-'
            self.kungfu_tree.insert('', tk.END,
                values=(tier_display, kf.name, kf.skill_name),
                tags=(tag,))
        self.kungfu_tree.tag_configure('no', foreground='gray')
        self.kungfu_tree.tag_configure('ok', foreground='black')

    def _on_kungfu_select(self, event):
        item = self.kungfu_tree.focus()
        if not item:
            return
        vals = self.kungfu_tree.item(item, 'values')
        if not vals:
            return
        book_name = vals[1]
        kf = self.sim.db_by_name.get(book_name)
        if not kf:
            self.req_var.set('未找到秘籍数据')
            return
        # 需求
        reqs = []
        if kf.qualification:
            reqs.append(self._format_qual(kf.qualification))
        if kf.gender:
            reqs.append(f'性别{kf.gender}')
        if kf.inner_type and kf.inner_type != '调和':
            reqs.append(f'{kf.inner_type}内')
        if kf.limit_person is not None or kf.limit_person2 is not None:
            from save_reader import get_seq_to_name
            name_map = get_seq_to_name()
            names = []
            for s in [kf.limit_person, kf.limit_person2]:
                if s is not None:
                    n = name_map.get(s, f'#{s}')
                    if s == 0: n = '主角'
                    names.append(n)
            reqs.append('限' + '或'.join(names))
        if kf.need_family is not None:
            from save_reader import FAMILY_MAP
            reqs.append(FAMILY_MAP.get(kf.need_family, f'家族#{kf.need_family}'))
        if kf.need_school is not None:
            from save_reader import SECT_MAP
            reqs.append(SECT_MAP.get(kf.need_school, f'门派#{kf.need_school}'))
        if kf.need_inner:
            reqs.append(f'内力≥{kf.need_inner}')
        if kf.need_attack:
            reqs.append(f'攻击≥{kf.need_attack}')
        if kf.need_dodge:
            reqs.append(f'轻功≥{kf.need_dodge}')
        for skill, need in kf.need_skills.items():
            reqs.append(f'{skill}≥{need}')
        # 效果
        effects = []
        for skill, bonus in kf.bonuses.items():
            if bonus != 0:
                effects.append(f'{skill}+{bonus}')
        req_str = '需求: ' + ('、'.join(reqs) if reqs else '无')
        eff_str = '效果: ' + ('、'.join(effects) if effects else '无')
        self.req_var.set(req_str + '\n' + eff_str)

    def _on_kungfu_double(self, event, washed=False):
        item = self.kungfu_tree.identify_row(event.y)
        if not item:
            return
        vals = self.kungfu_tree.item(item, 'values')
        if not vals:
            return
        book_name = vals[1]
        kf = self.sim.db_by_name.get(book_name)
        if not kf:
            return
        # 检查是否已学过(不可重复学习)
        for learned_kf, _ in self.sim.learned:
            if learned_kf.item_id == kf.item_id:
                messagebox.showinfo('提示', f'已学会《{kf.skill_name}》，不可重复学习')
                return
        for washed_kf, _ in self.sim.washed:
            if washed_kf.item_id == kf.item_id:
                messagebox.showinfo('提示', f'已洗过《{kf.skill_name}》，不可重复学习')
                return
        for special_kf, _ in self.sim.special_books:
            if special_kf.item_id == kf.item_id:
                messagebox.showinfo('提示', f'已学过《{kf.name}》，不可重复学习')
                return
        # 洗武功升9级, 学习升10级
        level = 9 if washed else 10
        ok, reason = self.sim.add_kungfu(kf, level, washed)
        if not ok:
            messagebox.showwarning('无法添加', reason)
            return
        self._refresh_learn_lists()
        self._refresh_special_books()
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _remove_kungfu(self, washed=False):
        tree = self.wash_tree if washed else self.learn_tree
        sel = tree.selection()
        if not sel:
            return
        # 初始武功(含天赋特技)不可删除
        if not washed:
            tags = tree.item(sel[0], 'tags')
            if 'initial' in tags:
                messagebox.showinfo('提示', '初始武功/天赋特技不可删除')
                return
        idx = tree.index(sel[0])
        # 修炼武功列表中要减去特技数量
        if not washed and hasattr(self.sim, 'special_count'):
            idx = idx - self.sim.special_count
            if idx < 0:
                return
        self.sim.remove_kungfu(idx, washed)
        self._refresh_learn_lists()
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _remove_special_book(self, event):
        """双击删除已学特殊书籍(医毒书/宝典)"""
        sel = self.special_tree.selection()
        if not sel:
            return
        idx = self.special_tree.index(sel[0])
        self.sim.remove_special_book(idx)
        self._refresh_special_books()
        self._refresh_attrs()
        self._refresh_kungfu_list()

    def _refresh_special_books(self):
        """刷新已学特殊书籍列表"""
        self.special_tree.delete(*self.special_tree.get_children())
        for kf, level in self.sim.special_books:
            bonus_str = kf.get_bonus_str()
            if kf.change_inner:
                bonus_str += f' 内属→{kf.change_inner}'
            self.special_tree.insert('', tk.END, values=(kf.name, bonus_str))

    def _refresh_learn_lists(self):
        self.learn_tree.delete(*self.learn_tree.get_children())
        # 特技(天赋): 也是初始武功的一种, 蓝色, 占格子, 不可删除
        special_count = 0
        if hasattr(self.sim, 'special_kungfu_names'):
            for name in self.sim.special_kungfu_names:
                special_count += 1
                self.learn_tree.insert('', tk.END, values=(special_count, name, 10), tags=('initial',))
        self.sim.special_count = special_count
        # 修炼武功: 初始武功(蓝) / 周目内武功(黑) / 明玉丹格子武功(橙)
        week_slots = 20 + (self.sim.week - 1) * 2
        learned_initial = getattr(self.sim, 'initial_count', 0)
        # 总初始武功数 = 特技 + 初始修炼武功
        total_initial = special_count + learned_initial
        for i, (kf, level) in enumerate(self.sim.learned):
            idx = special_count + i + 1
            # 格子位置: 特技占了special_count格, 所以从special_count开始算
            slot_pos = special_count + i
            if slot_pos < total_initial:
                tag = 'initial'  # 初始武功
            elif slot_pos < week_slots:
                tag = 'normal'   # 周目内武功
            else:
                tag = 'mingyu'   # 明玉丹格子
            self.learn_tree.insert('', tk.END, values=(idx, kf.skill_name, level), tags=(tag,))
        self.learn_tree.tag_configure('initial', foreground='blue')
        self.learn_tree.tag_configure('normal', foreground='black')
        self.learn_tree.tag_configure('mingyu', foreground='darkorange')

        self.wash_tree.delete(*self.wash_tree.get_children())
        for idx, (kf, level) in enumerate(self.sim.washed, 1):
            self.wash_tree.insert('', tk.END, values=(idx, kf.skill_name, level))

    def reset_current_char(self):
        """重置当前人物的模拟状态"""
        if not self.sim.current_char:
            messagebox.showwarning('提示', '请先选择角色')
            return
        if messagebox.askyesno('确认', f'重置 {self.sim.current_char.name} 的所有修炼/洗武功/等级/根骨?'):
            self.sim.reset()
            if self._current_char_name:
                self.char_states.pop(self._current_char_name, None)
            self._refresh_all()
            self.status_var.set(f'已重置 {self.sim.current_char.name}')

    def reset_sim(self):
        if messagebox.askyesno('确认', '重置所有修炼/洗武功/等级?'):
            self.sim.reset()
            self._refresh_all()

    def export_sim(self):
        """导出模拟为JSON文件"""
        if not self.sim.current_char:
            messagebox.showwarning('提示', '请先选择角色')
            return
        path = filedialog.asksaveasfilename(
            title='导出模拟', defaultextension='.json',
            filetypes=[('模拟文件', '*.json')]
        )
        if not path:
            return
        import json
        c = self.sim.current_char
        data = {
            'char_name': c.name,
            'char_nick': c.nickname,
            'level_bonus': self.sim.level_bonus,
            'assigned': dict(self.sim.assigned),
            'inner_type': c.inner_type,
            'learned': [{'item_id': kf.item_id, 'level': lv} for kf, lv in self.sim.learned],
            'washed': [{'item_id': kf.item_id, 'level': lv} for kf, lv in self.sim.washed],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status_var.set(f'已导出到 {path}')

    def import_sim(self):
        """从JSON文件导入模拟"""
        if not self.sim.current_char:
            messagebox.showwarning('提示', '请先选择角色')
            return
        path = filedialog.askopenfilename(
            title='导入模拟', filetypes=[('模拟文件', '*.json')]
        )
        if not path:
            return
        import json
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror('错误', f'读取文件失败: {e}')
            return
        # 清空当前状态
        self.sim.learned = []
        self.sim.washed = []
        self.sim.level_bonus = 0
        self.sim.assigned = {k: 0 for k in self.sim.assigned}
        # 恢复等级和加点
        self.sim.level_bonus = data.get('level_bonus', 0)
        for k, v in data.get('assigned', {}).items():
            if k in self.sim.assigned:
                self.sim.assigned[k] = v
        # 恢复内属
        if 'inner_type' in data:
            self.sim.current_char.inner_type = data['inner_type']
        # 恢复已学武功
        missing = []
        for item in data.get('learned', []):
            kf = self.sim.db_by_id.get(item['item_id'])
            if kf:
                self.sim.learned.append((kf, item.get('level', 10)))
            else:
                missing.append(f"秘籍#{item['item_id']}")
        for item in data.get('washed', []):
            kf = self.sim.db_by_id.get(item['item_id'])
            if kf:
                self.sim.washed.append((kf, item.get('level', 9)))
            else:
                missing.append(f"秘籍#{item['item_id']}")
        self._refresh_all()
        msg = f'已导入 {data.get("char_name", "?")} 的模拟'
        if missing:
            msg += f'\n以下秘籍未找到: {", ".join(missing)}'
        self.status_var.set(msg)

    def _load_template_file(self, tpl_path, append=False):
        """加载一个洗武功模版文件"""
        import json
        with open(tpl_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not append:
            self.sim.washed = []
        missing = []
        for item in data.get('washed', []):
            kf = self.sim.db_by_id.get(item['item_id'])
            if kf:
                self.sim.washed.append((kf, item.get('level', 9)))
            else:
                missing.append(item.get('name', f"#{item['item_id']}"))
        return len(data.get('washed', [])), missing

    def load_char_template(self):
        """加载当前角色的洗武功模板"""
        if not self.sim.current_char:
            messagebox.showwarning('提示', '请先选择角色')
            return
        import os, re
        from kungfu_db import resource_path
        char = self.sim.current_char
        char_name = char.name
        tpl_dir = resource_path('templates')
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', char_name)
        tpl_path = os.path.join(tpl_dir, f'{safe_name}.json')

        # 主角(复制人)可选择载入复制人本身或原始主角模版
        is_main = getattr(char, 'is_main', False) or char.seq == 0
        main_tpl_path = os.path.join(tpl_dir, '谢破军.json')

        if is_main and os.path.exists(main_tpl_path):
            # 弹出选择框: 是=复制人模版, 否=原始主角模版, 取消=取消操作
            choice = messagebox.askyesnocancel(
                '选择模版',
                f'当前是主角({char_name})\n\n'
                f'是 = 载入复制人模版({char_name})\n'
                f'否 = 载入原始主角模版(谢破军)\n'
                f'取消 = 取消操作'
            )
            if choice is None:
                return  # 取消
            elif choice:
                if not os.path.exists(tpl_path):
                    messagebox.showinfo('提示', f'暂无{char_name}的洗武功模板')
                    return
                target_path = tpl_path
                target_name = char_name
            else:
                target_path = main_tpl_path
                target_name = '谢破军(原始主角)'
        else:
            if not os.path.exists(tpl_path):
                messagebox.showinfo('提示', f'暂无{char_name}的洗武功模板')
                return
            target_path = tpl_path
            target_name = char_name

        if not messagebox.askyesno('确认', f'加载{target_name}的洗武功模板?\n将追加到当前洗武功(不清空, 可分多次载入)。'):
            return
        n, missing = self._load_template_file(target_path, append=True)
        self._refresh_all()
        msg = f'已追加{target_name}洗武功模板({n}格)'
        if missing:
            msg += f'\n以下秘籍未找到: {", ".join(missing)}'
        self.status_var.set(msg)

# 字体优先级列表，Tkinter自动选择第一个可用的
FONT_FAMILY = ('vivo Sans SC VF', 'Microsoft YaHei UI', 'Microsoft YaHei', 'SimHei', 'TkDefaultFont')

def main():
    root = tk.Tk()
    root.option_add('*Font', (FONT_FAMILY, 12))
    root.option_add('*Listbox*Font', (FONT_FAMILY, 12))
    root.option_add('*Entry*Font', (FONT_FAMILY, 12))
    style = ttk.Style()
    style.configure('TLabel', font=(FONT_FAMILY, 12))
    style.configure('TButton', font=(FONT_FAMILY, 12))
    style.configure('TEntry', font=(FONT_FAMILY, 12))
    style.configure('Treeview', font=(FONT_FAMILY, 12), rowheight=28)
    style.configure('Treeview.Heading', font=(FONT_FAMILY, 12, 'bold'))
    root.minsize(1320, 700)
    app = KungfuSimulatorGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()

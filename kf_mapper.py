"""武功编号->名称/秘籍映射工具(从JSON读取)"""
import json
import os
from kungfu_db import resource_path

_kfid_to_name_cache = None
_bookname_to_itemid_cache = None

def load_kfid_name_map(json_path=None):
    """从kungfu_list.json加载 武功编号->名称 映射"""
    global _kfid_to_name_cache
    if _kfid_to_name_cache is not None:
        return _kfid_to_name_cache
    if json_path is None:
        json_path = resource_path('kungfu_list.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    _kfid_to_name_cache = {int(k): v['name'] for k, v in data.items()}
    return _kfid_to_name_cache

def build_map_from_books(json_path=None, books=None):
    """结合武功列表和秘籍数据, 构建 武功编号->物品编号 映射"""
    if json_path is None:
        json_path = resource_path('kungfu_list.json')
    kfid_to_name = load_kfid_name_map(json_path)
    # 秘籍名->物品编号
    bookname_to_itemid = {}
    if books:
        for b in books:
            bookname_to_itemid[b.name] = b.item_id
    # 武功编号->物品编号
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    kfid_to_itemid = {}
    for seq_str, info in data.items():
        book_name = info.get('book', '')
        if book_name and book_name in bookname_to_itemid:
            kfid_to_itemid[int(seq_str)] = bookname_to_itemid[book_name]
    return kfid_to_itemid, kfid_to_name

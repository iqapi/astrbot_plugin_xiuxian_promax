# core/shop_manager.py

import random
import time
import json
from typing import List, Dict, Optional, Tuple

from astrbot.api import AstrBotConfig, logger
from ..config_manager import ConfigManager
from ..models import Item

class ShopManager:
    """商店管理器，负责商店物品生成、刷新和购买"""

    def __init__(self, config: AstrBotConfig, config_manager: ConfigManager):
        self.config = config
        self.config_manager = config_manager

    def _format_required_level(self, level_index: int) -> str:
        """同时展示灵修/体修的需求境界名称"""
        names = []
        if 0 <= level_index < len(self.config_manager.level_data):
            name = self.config_manager.level_data[level_index].get("level_name", "")
            if name:
                names.append(name)
        if 0 <= level_index < len(self.config_manager.body_level_data):
            name = self.config_manager.body_level_data[level_index].get("level_name", "")
            if name and name not in names:
                names.append(name)
        if not names:
            return "未知境界"
        return " / ".join(names)

    def _get_all_shop_items(self) -> List[Dict]:
        """获取所有可以在商店出售的物品"""
        all_items = []

        # 添加武器
        for weapon in self.config_manager.weapons_data.values():
            if weapon.get('shop_weight', 0) > 0 and weapon.get('price', 0) > 0:
                all_items.append({
                    'id': weapon['id'],
                    'name': weapon['name'],
                    'type': 'weapon',
                    'price': weapon['price'],
                    'weight': weapon['shop_weight'],
                    'rank': weapon.get('rank', '凡品'),
                    'data': weapon
                })

        # 添加物品（防具、心法、功法）
        for item in self.config_manager.items_data.values():
            if item.get('shop_weight', 0) > 0 and item.get('price', 0) > 0:
                all_items.append({
                    'id': item.get('id', item['name']),
                    'name': item['name'],
                    'type': item['type'],
                    'price': item['price'],
                    'weight': item['shop_weight'],
                    'rank': item.get('rank', '凡品'),
                    'data': item
                })

        # 添加破境丹
        for pill in self.config_manager.pills_data.values():
            if pill.get('shop_weight', 0) > 0 and pill.get('price', 0) > 0:
                all_items.append({
                    'id': pill['id'],
                    'name': pill['name'],
                    'type': 'pill',
                    'price': pill['price'],
                    'weight': pill['shop_weight'],
                    'rank': pill.get('rank', '凡品'),
                    'data': pill
                })

        # 添加修为丹
        for pill in self.config_manager.exp_pills_data.values():
            if pill.get('shop_weight', 0) > 0 and pill.get('price', 0) > 0:
                all_items.append({
                    'id': pill['id'],
                    'name': pill['name'],
                    'type': 'exp_pill',
                    'price': pill['price'],
                    'weight': pill['shop_weight'],
                    'rank': pill.get('rank', '凡品'),
                    'data': pill
                })

        # 添加功能丹
        for pill in self.config_manager.utility_pills_data.values():
            if pill.get('shop_weight', 0) > 0 and pill.get('price', 0) > 0:
                all_items.append({
                    'id': pill['id'],
                    'name': pill['name'],
                    'type': 'utility_pill',
                    'price': pill['price'],
                    'weight': pill['shop_weight'],
                    'rank': pill.get('rank', '凡品'),
                    'data': pill
                })

        return all_items

    def _weighted_random_choice(self, items: List[Dict], count: int) -> List[Dict]:
        """基于权重的随机选择（不重复）"""
        if len(items) <= count:
            return items.copy()

        selected = []
        available_items = items.copy()

        for _ in range(count):
            if not available_items:
                break

            # 计算总权重
            total_weight = sum(item['weight'] for item in available_items)
            if total_weight == 0:
                # 如果所有权重都是0，则随机选择
                choice = random.choice(available_items)
            else:
                # 基于权重选择
                rand = random.uniform(0, total_weight)
                cumulative = 0
                choice = available_items[0]
                for item in available_items:
                    cumulative += item['weight']
                    if rand <= cumulative:
                        choice = item
                        break

            selected.append(choice)
            available_items.remove(choice)

        return selected

    def _calculate_stock(self, weight: int) -> int:
        """根据权重计算库存数量

        权重越高，物品越常见，库存越多
        权重越低，物品越稀有，库存越少（最少为1）

        Args:
            weight: 物品的商店权重

        Returns:
            库存数量（最小为1）
        """
        # 获取库存计算基数，默认100
        stock_divisor = self._cfg("SHOP_STOCK_DIVISOR", 100)

        # 库存 = 权重 / 基数，向上取整，最小为1
        stock = max(1, (weight + stock_divisor - 1) // stock_divisor)

        return stock

    def _cfg(self, key: str, default):
        """读取 VALUES 分组下的配置（schema 中 SHOP_* 嵌套在 VALUES 下），兼容顶层旧写法"""
        return self.config.get("VALUES", {}).get(key, self.config.get(key, default))

    def ensure_items_have_stock(self, shop_items: List[Dict]) -> bool:
        """确保已有商店物品列表包含库存字段（用于兼容旧数据）

        Args:
            shop_items: 商店物品列表

        Returns:
            是否发生了修改
        """
        updated = False
        for item in shop_items:
            stock = item.get('stock')
            if stock is None:
                data = item.get('data', {})
                weight = 0
                if isinstance(data, dict):
                    weight = data.get('shop_weight') or data.get('weight') or 0
                item['stock'] = self._calculate_stock(weight)
                updated = True
            elif stock < 0:
                item['stock'] = 0
                updated = True
        return updated

    def generate_shop_items(self, count: int) -> List[Dict]:
        """生成商店物品列表

        Args:
            count: 要生成的物品数量

        Returns:
            商店物品列表，每个物品包含 id, name, type, price, discount, final_price, stock
        """
        all_items = self._get_all_shop_items()
        if not all_items:
            logger.warning("没有可用的商店物品")
            return []

        # 随机选择物品
        selected_items = self._weighted_random_choice(all_items, count)

        # 获取折扣配置
        discount_min = self._cfg("SHOP_DISCOUNT_MIN", 0.8)
        discount_max = self._cfg("SHOP_DISCOUNT_MAX", 1.2)

        # 生成商店物品
        shop_items = []
        for item in selected_items:
            # 随机折扣
            discount = random.uniform(discount_min, discount_max)
            final_price = int(item['price'] * discount)

            # 计算库存（基于权重）
            stock = self._calculate_stock(item['weight'])

            shop_items.append({
                'id': item['id'],
                'name': item['name'],
                'type': item['type'],
                'rank': item['rank'],
                'original_price': item['price'],
                'discount': discount,
                'price': final_price,
                'stock': stock,
                'data': item['data']
            })

        return shop_items

    def should_refresh_shop(self, last_refresh_time: int, refresh_hours: int = None) -> bool:
        """检查是否需要刷新"""
        if refresh_hours is None:
            refresh_hours = self.config.get("SHOP_REFRESH_HOURS", 6)
        if refresh_hours <= 0:
            return False
        return (int(time.time()) - last_refresh_time) >= (refresh_hours * 3600)

    def generate_pavilion_items(self, item_getter, count: int) -> List[Dict]:
        """生成阁楼物品列表（带库存和折扣）"""
        base_items = item_getter(count * 2)  # 获取更多以便随机选择
        selected = self._weighted_random_choice(
            [{'weight': i.get('data', {}).get('shop_weight', 100), **i} for i in base_items], count
        )
        discount_min = self._cfg("SHOP_DISCOUNT_MIN", 0.8)
        discount_max = self._cfg("SHOP_DISCOUNT_MAX", 1.2)
        result = []
        for item in selected:
            discount = random.uniform(discount_min, discount_max)
            stock = self._calculate_stock(item.get('weight', 100))
            result.append({
                'name': item['name'], 'type': item['type'], 'rank': item['rank'],
                'original_price': item['price'], 'discount': discount,
                'price': int(item['price'] * discount), 'stock': stock, 'data': item.get('data', {})
            })
        return result

    def get_pills_for_display(self, count: int) -> List[Dict]:
        """获取丹药列表用于丹阁展示"""
        all_pills = []
        for pill in self.config_manager.pills_data.values():
            if pill.get('price', 0) > 0:
                all_pills.append({'name': pill['name'], 'type': 'pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        for pill in self.config_manager.exp_pills_data.values():
            if pill.get('price', 0) > 0:
                all_pills.append({'name': pill['name'], 'type': 'exp_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        for pill in self.config_manager.utility_pills_data.values():
            if pill.get('price', 0) > 0:
                all_pills.append({'name': pill['name'], 'type': 'utility_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        return all_pills

    def get_weapons_for_display(self, count: int) -> List[Dict]:
        """获取武器列表用于器阁展示"""
        all_weapons = []
        for weapon in self.config_manager.weapons_data.values():
            if weapon.get('price', 0) > 0:
                all_weapons.append({'name': weapon['name'], 'type': 'weapon', 'price': weapon['price'], 'rank': weapon.get('rank', '凡品'), 'data': weapon})
        return all_weapons

    def get_all_items_for_display(self, count: int) -> List[Dict]:
        """获取所有物品用于百宝阁展示"""
        all_items = []
        for weapon in self.config_manager.weapons_data.values():
            if weapon.get('price', 0) > 0:
                all_items.append({'name': weapon['name'], 'type': 'weapon', 'price': weapon['price'], 'rank': weapon.get('rank', '凡品'), 'data': weapon})
        for item in self.config_manager.items_data.values():
            if item.get('price', 0) > 0:
                # 映射旧格式类型到新格式
                item_type = self._map_legacy_item_type(item)
                all_items.append({'name': item['name'], 'type': item_type, 'price': item['price'], 'rank': item.get('rank', '凡品'), 'data': item})
        for pill in self.config_manager.pills_data.values():
            if pill.get('price', 0) > 0:
                all_items.append({'name': pill['name'], 'type': 'pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        for pill in self.config_manager.exp_pills_data.values():
            if pill.get('price', 0) > 0:
                all_items.append({'name': pill['name'], 'type': 'exp_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        for pill in self.config_manager.utility_pills_data.values():
            if pill.get('price', 0) > 0:
                all_items.append({'name': pill['name'], 'type': 'utility_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill})
        return all_items

    def _map_legacy_item_type(self, item: dict) -> str:
        """将旧格式物品类型映射到新格式

        Args:
            item: 物品配置字典

        Returns:
            映射后的类型字符串
        """
        original_type = item.get('type', '')
        subtype = item.get('subtype', '')

        # 法器类型映射
        if original_type == '法器':
            if subtype == '武器':
                return 'weapon'
            elif subtype == '防具':
                return 'armor'
            elif subtype == '饰品':
                return 'accessory'
            else:
                return 'weapon'  # 默认为武器

        # 功法类型映射
        if original_type == '功法':
            return 'technique'

        # 丹药类型映射（旧系统丹药）
        if original_type == '丹药':
            return 'legacy_pill'

        # 材料类型映射
        if original_type == '材料':
            return 'material'

        # 其他类型保持不变
        return original_type

    def find_item_by_name(self, name: str) -> Optional[Dict]:
        """根据名称查找物品"""
        for weapon in self.config_manager.weapons_data.values():
            if weapon['name'] == name and weapon.get('price', 0) > 0:
                return {'name': weapon['name'], 'type': 'weapon', 'price': weapon['price'], 'rank': weapon.get('rank', '凡品'), 'data': weapon}
        for item in self.config_manager.items_data.values():
            if item['name'] == name and item.get('price', 0) > 0:
                # 映射旧格式类型到新格式
                item_type = self._map_legacy_item_type(item)
                return {'name': item['name'], 'type': item_type, 'price': item['price'], 'rank': item.get('rank', '凡品'), 'data': item}
        for pill in self.config_manager.pills_data.values():
            if pill['name'] == name and pill.get('price', 0) > 0:
                return {'name': pill['name'], 'type': 'pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill}
        for pill in self.config_manager.exp_pills_data.values():
            if pill['name'] == name and pill.get('price', 0) > 0:
                return {'name': pill['name'], 'type': 'exp_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill}
        for pill in self.config_manager.utility_pills_data.values():
            if pill['name'] == name and pill.get('price', 0) > 0:
                return {'name': pill['name'], 'type': 'utility_pill', 'price': pill['price'], 'rank': pill.get('rank', '凡品'), 'data': pill}
        return None

    def format_pavilion_display(self, pavilion_name: str, items: List[Dict], refresh_hours: int = 6, last_refresh: int = 0) -> str:
        """格式化阁楼展示信息"""
        if not items:
            return f"{pavilion_name}暂无物品出售"

        type_label_map = {
            'weapon': '武器', 'armor': '防具', 'main_technique': '心法', 'technique': '功法',
            'pill': '破境丹', 'exp_pill': '修为丹', 'utility_pill': '功能丹',
            'legacy_pill': '丹药', 'material': '材料', 'accessory': '饰品'
        }

        lines = [f"=== {pavilion_name} ===\n"]
        display_index = 0
        for item in items:
            stock = item.get('stock', 0)
            if stock <= 0:
                continue
            display_index += 1
            type_label = type_label_map.get(item['type'], '物品')
            discount_text = ""
            if item.get('discount', 1.0) < 1.0:
                discount_text = f" [{round(item['discount'] * 10, 1)}折]"
            elif item.get('discount', 1.0) > 1.0:
                discount_text = f" [+{int((item['discount'] - 1.0) * 100)}%]"
            stock_text = f"库存紧张:{stock}" if stock <= 3 else f"库存:{stock}"

            # 获取物品效果描述
            effect_desc = self._get_item_effect_short(item)
            effect_line = f"\n   效果: {effect_desc}" if effect_desc else ""

            lines.append(f"{display_index}. [{item['rank']}] {item['name']} ({type_label}){discount_text}\n   价格: {item['price']} 灵石 {stock_text}{effect_line}\n")

        if refresh_hours > 0 and last_refresh:
            remaining = (last_refresh + refresh_hours * 3600) - int(time.time())
            if remaining > 0:
                lines.append(f"\n下次刷新: {remaining // 3600}小时{(remaining % 3600) // 60}分钟后")
        lines.append(f"\n提示: 使用 '购买 [物品名]' 购买物品")
        return "".join(lines)

    # v3.24.2：功法/饰品通用 effects 词条表（键 → 中文标签）
    _EFFECT_LABELS = {
        "crit_rate": ("会心+", "%"),
        "crit_damage": ("会心伤害", "x"),
        "combo_rate": ("连击+", "%"),
        "lifesteal": ("吸血+", "%"),
        "counter_damage": ("反伤+", "%"),
    }

    @classmethod
    def _effects_dict_text(cls, effect_data: Dict, limit: int = 2) -> List[str]:
        """把 effects 字典转成简短中文词条"""
        out = []
        if not isinstance(effect_data, dict):
            return out
        for key, label in cls._EFFECT_LABELS.items():
            val = effect_data.get(key, 0)
            if not val:
                continue
            name = label[0]
            if label[1] == "%":
                out.append(f"{name}{val}%")
            elif label[1] == "x":
                out.append(f"{name}{val:.1f}倍")
            else:
                out.append(f"{name}+{val}")
        return out[:limit]

    def _get_item_effect_short(self, item: Dict) -> str:
        """获取物品效果的简短描述（v3.24.2 增强：补修为丹/功法词条/五行/容量/境界门槛）"""
        data = item.get('data', {})
        item_type = item.get('type', '')
        effects = []

        # 五行属性（武器/功法名带金木水火土即有克制关系，值得展示）
        element = data.get('element')
        if not element and self.config_manager:
            _elem_fn = getattr(self.config_manager, 'get_element_from_name', None)
            if callable(_elem_fn):
                element = _elem_fn(item.get('name', ''))
        if element:
            effects.append(f"[{element}]")

        # 境界门槛
        req_lv = data.get('required_level_index', 0)
        if req_lv:
            effects.append(f"需境界{req_lv}")

        # 武器/装备属性
        if item_type in ['weapon', 'armor', 'accessory']:
            if data.get('physical_damage', 0) > 0:
                effects.append(f"物伤+{data['physical_damage']}")
            if data.get('magic_damage', 0) > 0:
                effects.append(f"法伤+{data['magic_damage']}")
            if data.get('physical_defense', 0) > 0:
                effects.append(f"物防+{data['physical_defense']}")
            if data.get('magic_defense', 0) > 0:
                effects.append(f"法防+{data['magic_defense']}")
            if data.get('mental_power', 0) > 0:
                effects.append(f"精神力+{data['mental_power']}")

        # 储物戒
        elif item_type == 'storage_ring':
            cap = data.get('capacity', 0)
            if cap:
                effects.append(f"容量{cap}")

        # 功法属性（v3.24.2：补 effects 词条）
        elif item_type in ['main_technique', 'technique', '功法']:
            if data.get('exp_multiplier', 0) > 0:
                effects.append(f"修炼效率+{int(data['exp_multiplier']*100)}%")
            if data.get('physical_damage', 0) > 0:
                effects.append(f"物伤+{data['physical_damage']}")
            if data.get('magic_damage', 0) > 0:
                effects.append(f"法伤+{data['magic_damage']}")
            effects.extend(self._effects_dict_text(data.get('effects'), 2))

        # 丹药效果
        elif item_type in ['pill', 'exp_pill', 'utility_pill', 'legacy_pill']:
            # 尝试从 effect 字段获取
            effect_data = data.get('effect', {})
            if isinstance(effect_data, dict):
                if effect_data.get('add_experience', 0) > 0:
                    effects.append(f"修为+{effect_data['add_experience']}")
                if effect_data.get('add_hp', 0) > 0:
                    effects.append(f"气血+{effect_data['add_hp']}")
                if effect_data.get('add_max_hp', 0) > 0:
                    effects.append(f"气血上限+{effect_data['add_max_hp']}")
                if effect_data.get('add_attack', 0) > 0:
                    effects.append(f"攻击+{effect_data['add_attack']}")
                if effect_data.get('add_defense', 0) > 0:
                    effects.append(f"防御+{effect_data['add_defense']}")
                effects.extend(self._effects_dict_text(effect_data, 1))

            # 破境丹特殊处理
            if data.get('subtype') == 'breakthrough':
                bonus = data.get('breakthrough_bonus', 0)
                if bonus > 0:
                    effects.append(f"突破成功率+{int(bonus*100)}%")

            # 修为丹（v3.24.2：补 exp_gain 字段——exp_pills.json 用的是这个键，此前被漏掉）
            if data.get('exp_boost', 0) > 0:
                effects.append(f"修为+{data['exp_boost']}")
            if data.get('exp_gain', 0) > 0:
                effects.append(f"修为+{data['exp_gain']}")
        
        # 材料
        elif item_type == 'material':
            if data.get('description'):
                return data['description'][:20]
        
        # 如果有描述字段，优先使用
        if not effects and data.get('description'):
            desc = data['description']
            return desc[:25] + "..." if len(desc) > 25 else desc

        return ", ".join(effects[:4]) if effects else ""

    def describe_item_by_name(self, item_name: str) -> str:
        """v3.24.2 按名查配置并生成功效简述（供坊市等只有物品名的场景使用）
        注意：items_data 以 id 为键，统一遍历 values() 按名称匹配"""
        try:
            cm = self.config_manager
            if not cm:
                return ""

            def _scan(source, itype):
                # v3.24.2：兼容 list 与 dict 两种配置装载形态
                vals = source.values() if isinstance(source, dict) else source
                for data in vals:
                    if isinstance(data, dict) and data.get('name') == item_name:
                        return (itype, data)
                return None

            found = (
                _scan(cm.weapons_data, 'weapon')
                or _scan(cm.pills_data, 'pill')
                or _scan(cm.exp_pills_data, 'exp_pill')
                or _scan(cm.utility_pills_data, 'utility_pill')
                or _scan(cm.techniques_data, 'technique')
                or _scan(cm.storage_rings_data, 'storage_ring')
                or _scan(cm.items_data, None)
            )
            if not found:
                return ""
            itype, data = found
            if itype is None:
                raw_type = str(data.get('type', ''))
                if raw_type in ('武器', '法器') or data.get('physical_damage'):
                    itype = 'weapon'
                elif raw_type == '防具' or data.get('physical_defense') or data.get('magic_defense'):
                    itype = 'armor'
                elif raw_type == '材料':
                    itype = 'material'
                else:
                    itype = 'accessory'
            return self._get_item_effect_short({'type': itype, 'name': item_name, 'data': data})
        except Exception:
            return ""

    def get_item_details(self, item_data: Dict) -> str:
        """获取物品详细信息

        Args:
            item_data: 物品数据字典

        Returns:
            物品详细描述
        """
        item_type = item_data.get('type', '')
        data = item_data.get('data', {})

        details = [f"名称: {item_data['name']}"]
        details.append(f"品级: {item_data['rank']}")
        details.append(f"价格: {item_data['price']} 灵石")

        description = data.get('description')
        if description:
            details.append(f"描述: {description}")

        # 武器/防具/饰品属性
        if item_type in ['weapon', 'armor', 'accessory']:
            attrs = []
            if data.get('magic_damage', 0) > 0:
                attrs.append(f"法伤+{data['magic_damage']}")
            if data.get('physical_damage', 0) > 0:
                attrs.append(f"物伤+{data['physical_damage']}")
            if data.get('magic_defense', 0) > 0:
                attrs.append(f"法防+{data['magic_defense']}")
            if data.get('physical_defense', 0) > 0:
                attrs.append(f"物防+{data['physical_defense']}")
            if data.get('mental_power', 0) > 0:
                attrs.append(f"精神力+{data['mental_power']}")
            if attrs:
                details.append(f"属性: {', '.join(attrs)}")
            if 'required_level_index' in data:
                level_name = self._format_required_level(data['required_level_index'])
                details.append(f"需求境界: {level_name}")

        # 心法/功法
        elif item_type in ['main_technique', 'technique']:
            attrs = []
            if data.get('exp_multiplier', 0) > 0:
                attrs.append(f"修炼效率+{data['exp_multiplier']:.1%}")
            if data.get('spiritual_qi', 0) > 0:
                attrs.append(f"灵气+{data['spiritual_qi']}")
            if data.get('magic_damage', 0) > 0:
                attrs.append(f"法伤+{data['magic_damage']}")
            if data.get('physical_damage', 0) > 0:
                attrs.append(f"物伤+{data['physical_damage']}")
            if data.get('magic_defense', 0) > 0:
                attrs.append(f"法防+{data['magic_defense']}")
            if data.get('physical_defense', 0) > 0:
                attrs.append(f"物防+{data['physical_defense']}")
            if data.get('mental_power', 0) > 0:
                attrs.append(f"精神力+{data['mental_power']}")
            if attrs:
                details.append(f"效果: {', '.join(attrs)}")
            if 'required_level_index' in data:
                level_name = self._format_required_level(data['required_level_index'])
                details.append(f"需求境界: {level_name}")

        # 丹药类
        elif item_type in ['pill', 'exp_pill', 'utility_pill', 'legacy_pill']:
            if 'required_level_index' in data and data['required_level_index'] > 0:
                level_name = self._format_required_level(data['required_level_index'])
                details.append(f"需求境界: {level_name}")

            subtype = data.get('subtype', '')
            effect_desc = []

            if item_type == 'pill' and subtype == 'breakthrough':
                bonus = data.get('breakthrough_bonus', 0)
                max_rate = data.get('max_success_rate', 1.0)
                target = data.get('target_level_index')
                if target is not None:
                    level_name = self._format_required_level(target)
                    effect_desc.append(f"目标境界: {level_name}")
                effect_desc.append(f"突破成功率+{int(bonus * 100)}%，最高可达 {int(max_rate * 100)}%")

            elif item_type == 'exp_pill':
                exp_gain = data.get('exp_gain', 0)
                effect_desc.append(f"立即获得修为：+{exp_gain}")

            elif item_type == 'utility_pill':
                effect_type = data.get('effect_type', '')
                if subtype == 'resurrection':
                    effect_desc.append("死亡时自动复活（属性减半）")
                elif effect_type == 'temporary':
                    duration = data.get('duration_minutes', 0)
                    mult = data.get('cultivation_multiplier', 0)
                    if mult > 0:
                        effect_desc.append(f"修炼速度+{int(mult * 100)}% 持续 {duration} 分钟")
                    if data.get('physical_damage_multiplier'):
                        effect_desc.append(f"物伤倍率+{data['physical_damage_multiplier']:.0%}")
                elif effect_type == 'permanent':
                    gains = []
                    for attr_key, label in [
                        ('physical_damage_gain', '物伤'),
                        ('magic_damage_gain', '法伤'),
                        ('physical_defense_gain', '物防'),
                        ('magic_defense_gain', '法防'),
                        ('mental_power_gain', '精神力')
                    ]:
                        value = data.get(attr_key)
                        if value:
                            sign = "+" if value > 0 else ""
                            gains.append(f"{label}{sign}{value}")
                    if gains:
                        effect_desc.append("永久增益：" + "，".join(gains))
                if data.get('resets_permanent_pills'):
                    refund_ratio = data.get('reset_refund_ratio', 0)
                    hint = "重置所有永久丹药增益"
                    if refund_ratio:
                        hint += f"，返还售价的{int(refund_ratio*100)}%"
                    effect_desc.append(hint)
                if data.get('blocks_next_debuff'):
                    effect_desc.append("获得定魂护盾，抵消下一次负面状态")

            elif item_type == 'legacy_pill':
                effect_data = data.get('effect', {})
                for key, label in [
                    ('add_hp', '恢复气血'),
                    ('add_experience', '增加修为'),
                    ('add_max_hp', '提升上限'),
                    ('add_attack', '物伤变化'),
                    ('add_defense', '物防变化'),
                    ('add_spiritual_power', '法伤变化'),
                    ('add_mental_power', '精神力变化'),
                    ('add_gold', '灵石变化'),
                ]:
                    value = effect_data.get(key)
                    if value:
                        sign = "+" if value > 0 else ""
                        effect_desc.append(f"{label}{sign}{value}")
                if effect_data.get('add_breakthrough_bonus'):
                    effect_desc.append(f"突破成功率+{int(effect_data['add_breakthrough_bonus']*100)}%（1小时）")

            if effect_desc:
                details.append("效果: " + "；".join(effect_desc))

        return "\n".join(details)

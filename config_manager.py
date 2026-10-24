import json
from pathlib import Path
from typing import List, Dict, Any

from astrbot.api import logger
from .data.default_configs import SECT_CONFIG, BOSS_CONFIG, RIFT_CONFIG, ALCHEMY_CONFIG

class ConfigManager:
    """配置管理器，加载境界、物品、武器和丹药配置"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self.level_data: List[dict] = []  
        self.body_level_data: List[dict] = []  
        self.items_data: Dict[str, dict] = {}  
        self.weapons_data: Dict[str, dict] = {}  
        self.pills_data: Dict[str, dict] = {}  
        self.exp_pills_data: Dict[str, dict] = {}  
        self.utility_pills_data: Dict[str, dict] = {}  
        self.storage_rings_data: Dict[str, dict] = {}  
        self.techniques_data: Dict[str, dict] = {} # 新增：功法数据
        
        self.sect_config: Dict[str, Any] = {}
        self.boss_config: Dict[str, Any] = {}
        self.rift_config: Dict[str, Any] = {}
        self.alchemy_config: Dict[str, Any] = {}
        
        self._load_all()

    def get_level_data(self, cultivation_type: str = "灵修") -> List[dict]:
        if cultivation_type == "体修":
            return self.body_level_data
        return self.level_data

    def _load_json_data(self, file_path: Path) -> List[dict]:
        if not file_path.exists():
            return []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 {file_path} 失败: {e}")
            return []
            
    def _load_config_with_default(self, file_path: Path, default_config: Dict) -> Dict:
        if not file_path.exists():
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                return default_config
            except Exception as e:
                return default_config
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return default_config

    def _load_items_data(self, file_path: Path) -> Dict[str, dict]:
        if not file_path.exists():
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {item.get("name", ""): item for item in data if isinstance(item, dict) and item.get("name")}
                elif isinstance(data, dict):
                    items_dict = {}
                    for item_id, item_data in data.items():
                        if isinstance(item_data, dict) and item_data.get("name"):
                            if "id" not in item_data: item_data["id"] = item_id
                            items_dict[item_data["name"]] = item_data
                    return items_dict
                return {}
        except Exception as e:
            logger.error(f"加载物品数据失败: {e}")
            return {}

    def _load_all(self):
        config_dir = self._base_dir / "config"
        
        self.level_data = self._load_json_data(config_dir / "level_config.json")
        self.body_level_data = self._load_json_data(config_dir / "body_level_config.json")
        self.items_data = self._load_items_data(config_dir / "items.json")
        self.weapons_data = self._load_items_data(config_dir / "weapons.json")
        self.pills_data = self._load_items_data(config_dir / "pills.json")
        self.exp_pills_data = self._load_items_data(config_dir / "exp_pills.json")
        self.utility_pills_data = self._load_items_data(config_dir / "utility_pills.json")
        self.storage_rings_data = self._load_items_data(config_dir / "storage_rings.json")
        
        # 加载功法
        self.techniques_data = self._load_items_data(config_dir / "techniques.json")
        
        self.sect_config = self._load_config_with_default(config_dir / "sect_config.json", SECT_CONFIG)
        self.boss_config = self._load_config_with_default(config_dir / "boss_config.json", BOSS_CONFIG)
        self.rift_config = self._load_config_with_default(config_dir / "rift_config.json", RIFT_CONFIG)
        self.alchemy_config = self._load_config_with_default(config_dir / "alchemy_config.json", ALCHEMY_CONFIG)
        self.alchemy_recipes = self._load_items_data(config_dir / "alchemy_recipes.json")
        self.game_config = self._load_config_with_default(config_dir / "game_config.json", {})
        
        self._pill_names_cache = None
        self._annotate_elements()
        logger.info("配置管理器初始化完成")

    # ===== 五行属性标注 =====
    # 名称关键词 → 五行（含变体属性映射：雷属木、风属木、冰属水、光属火、暗属水）
    ELEMENT_KEYWORDS = [
        ("金", "金"), ("庚", "金"), ("锐", "金"), ("锋", "金"),
        ("木", "木"), ("青", "木"), ("雷", "木"), ("风", "木"), ("闪", "木"), ("生生", "木"),
        ("水", "水"), ("冰", "水"), ("寒", "水"), ("暗", "水"), ("幽", "水"), ("壬", "水"),
        ("火", "火"), ("炎", "火"), ("焰", "火"), ("光", "火"), ("阳", "火"), ("丙", "火"),
        ("土", "土"), ("山", "土"), ("岩", "土"), ("厚", "土"), ("戊", "土"),
    ]

    def _infer_element(self, name: str) -> str:
        for keyword, element in self.ELEMENT_KEYWORDS:
            if keyword in name:
                return element
        return ""

    def _annotate_elements(self):
        """加载配置后按名称关键词为武器/防具/功法/心法标注五行属性（仅运行时，不写回文件）。
        配置里显式写了 element 字段的优先保留。"""
        self._element_index = {}
        annotated = 0
        for data in (self.weapons_data, self.items_data, self.techniques_data):
            for name, cfg in data.items():
                if not isinstance(cfg, dict):
                    continue
                element = cfg.get("element") or self._infer_element(name)
                if element:
                    cfg["element"] = element
                    self._element_index[name] = element
                    annotated += 1
        logger.info(f"五行属性标注完成：{annotated} 件物品/功法获得属性")

    def get_item_element(self, item_name: str) -> str:
        """获取物品/功法的五行属性（未标注返回空串）"""
        return self._element_index.get(item_name, "")

    def is_pill(self, item_name: str) -> bool:
        if item_name in self.pills_data or item_name in self.exp_pills_data or item_name in self.utility_pills_data:
            return True
        item_config = self.items_data.get(item_name)
        if item_config and item_config.get("type") == "丹药":
            return True
        return False
    
    def get_all_pill_names(self) -> set:
        if self._pill_names_cache is not None:
            return self._pill_names_cache
        pill_names = set()
        pill_names.update(self.pills_data.keys())
        pill_names.update(self.exp_pills_data.keys())
        pill_names.update(self.utility_pills_data.keys())
        for name, item in self.items_data.items():
            if isinstance(item, dict) and item.get("type") == "丹药":
                pill_names.add(name)
        self._pill_names_cache = pill_names
        return pill_names
    
    def invalidate_cache(self):
        self._pill_names_cache = None
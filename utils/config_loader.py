# utils/config_loader.py
import json
import os
from typing import Dict, Any

class ConfigLoader:
    """通用配置加载器"""
    
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

    def load_config(self, filename: str, default_config: Dict[str, Any]) -> Dict[str, Any]:
        """加载配置，所谓文件不存在则创建默认配置"""
        file_path = os.path.join(self.config_dir, filename)
        
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return default_config
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config {filename}: {e}")
            return default_config

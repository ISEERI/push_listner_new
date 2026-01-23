import json
import os
from typing import Dict

CONFIG_FILE = "config.json"


class ConfigManager:
    """Управление конфигурацией приложения."""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file

    def load(self) -> Dict[str, str]:
        """Загружает конфигурацию из файла."""
        default_config = {
            "save_data_dir": ".",
            "load_data_dir": "."
        }

        if not os.path.exists(self.config_file):
            return default_config

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Валидация типов
                if isinstance(config.get("save_data_dir"), str):
                    default_config["save_data_dir"] = config["save_data_dir"]
                if isinstance(config.get("load_data_dir"), str):
                    default_config["load_data_dir"] = config["load_data_dir"]
                return default_config
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load config: {e}")
            return default_config

    def save(self, config: Dict[str, str]) -> None:
        """Сохраняет конфигурацию в файл."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"Warning: Could not save config: {e}")

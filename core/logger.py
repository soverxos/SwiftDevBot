import logging.config
import yaml
from pathlib import Path

def setup_logging():
    """Настройка системы логирования"""
    config_path = Path("config.yml")
    
    if not config_path.exists():
        raise FileNotFoundError("Configuration file not found")
        
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": config["logging"]["format"]
            }
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": f"{config['logging']['path']}/bot.log",
                "formatter": "standard"
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard"
            }
        },
        "loggers": {
            "": {
                "handlers": ["console", "file"],
                "level": config["logging"]["level"]
            }
        }
    }
    
    logging.config.dictConfig(logging_config)
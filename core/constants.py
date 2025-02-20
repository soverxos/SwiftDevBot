#constants.py
from enum import Enum
from typing import Dict, Any

# Системные константы
class SystemStatus(Enum):
    STOPPED = 0
    STARTING = 1
    RUNNING = 2
    STOPPING = 3
    ERROR = 4
    MAINTENANCE = "maintenance"

class ModuleStatus(Enum):
    UNLOADED = 0
    LOADING = 1
    LOADED = 2
    ERROR = 3
    ACTIVE = "active"
    DISABLED = "disabled"

class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3
    LOWEST = 0
    MONITOR = 5
    HIGHEST = 4

# Настройки по умолчанию
DEFAULT_CONFIG: Dict[str, Any] = {
    # Основные настройки
    "BOT_NAME": "SwiftDevBot",
    "VERSION": "1.0.0",
    "DESCRIPTION": "Modular Telegram Bot Framework",

    # Пути
    "MODULES_DIR": "modules",
    "SYSTEM_MODULES_DIR": "modules/system",
    "CONFIG_DIR": "config",
    "LOGS_DIR": "logs",
    "TEMP_DIR": "temp",

    # Логирование
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "LOG_DATE_FORMAT": "%Y-%m-%d %H:%M:%S",
    "LOG_MAX_SIZE": 10485760,  # 10MB
    "LOG_BACKUP_COUNT": 5,

    # Безопасность
    "MAX_MESSAGE_LENGTH": 4096,
    "RATE_LIMIT_MESSAGES": 30,
    "RATE_LIMIT_PERIOD": 60,  # секунды
    "MAX_CONNECTIONS": 100,

    # Таймауты
    "COMMAND_TIMEOUT": 60,  # секунды
    "MODULE_LOAD_TIMEOUT": 30,  # секунды
    "API_TIMEOUT": 30,  # секунды

    # Кэширование
    "CACHE_ENABLED": True,
    "CACHE_TTL": 3600,  # секунды
    "CACHE_MAX_SIZE": 1000,

    # События
    "MAX_EVENT_HISTORY": 1000,
    "EVENT_TIMEOUT": 10,  # секунды

    # Модули
    "AUTO_LOAD_MODULES": True,
    "REQUIRED_MODULES": [
        "system.database",
        "system.admin",
        "system.security"
    ],

    # Права доступа
    "DEFAULT_ROLES": ["guest", "user", "admin", "system"],
    "ADMIN_COMMANDS": [
        "module.load",
        "module.unload",
        "module.reload",
        "system.status",
        "system.restart"
    ]
}

# Системные события
class SystemEvents:
    # Жизненный цикл
    STARTING = "system.starting"
    STARTED = "system.started"
    STOPPING = "system.stopping"
    STOPPED = "system.stopped"

    # Модули
    MODULE_LOADING = "module.loading"
    MODULE_LOADED = "module.loaded"
    MODULE_UNLOADING = "module.unloading"
    MODULE_UNLOADED = "module.unloaded"
    MODULE_ERROR = "module.error"

    # Команды
    COMMAND_BEFORE = "command.before"
    COMMAND_AFTER = "command.after"
    COMMAND_ERROR = "command.error"

    # Ошибки
    ERROR = "system.error"
    CRITICAL_ERROR = "system.critical_error"

# Коды ошибок
class ErrorCodes:
    # Общие ошибки
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_ARGUMENT = 2
    TIMEOUT = 3

    # Модули
    MODULE_NOT_FOUND = 100
    MODULE_LOAD_ERROR = 101
    MODULE_ALREADY_LOADED = 102
    MODULE_DEPENDENCY_ERROR = 103

    # Команды
    COMMAND_NOT_FOUND = 200
    COMMAND_ERROR = 201
    COMMAND_TIMEOUT = 202

    # Безопасность
    UNAUTHORIZED = 300
    FORBIDDEN = 301
    RATE_LIMIT_EXCEEDED = 302

    # База данных
    DATABASE_ERROR = 400
    DATABASE_CONNECTION_ERROR = 401

    # API
    API_ERROR = 500
    API_TIMEOUT = 501

# Метаданные
METADATA_SCHEMA = {
    "name": str,
    "version": str,
    "description": str,
    "author": str,
    "dependencies": list,
    "permissions": list,
    "commands": dict,
    "settings": dict
}

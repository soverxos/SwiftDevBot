class BotError(Exception):
    """Базовое исключение бота"""
    pass

class ModuleError(BotError):
    """Ошибка модуля"""
    pass

class ConfigError(BotError):
    """Ошибка конфигурации"""
    pass

class HandlerError(BotError):
    """Ошибка обработчика"""
    pass
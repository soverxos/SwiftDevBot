from typing import Any, Optional, Dict, List, Callable, Coroutine
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass

@dataclass
class ModuleMetadata:
    """Метаданные модуля"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    dependencies: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

class ModuleInterface(ABC):
    """Базовый интерфейс для всех модулей"""
    
    @abstractmethod
    async def setup(self, kernel: Any) -> Any:
        """Инициализация модуля"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Очистка ресурсов модуля"""
        pass

    async def register_handlers(self, bot: Any) -> None:
        """Регистрация обработчиков команд"""
        pass

    async def get_commands(self) -> List[dict]:
        """Получение списка команд модуля"""
        return []

class ModuleAPI:
    """API для взаимодействия модулей с ядром"""

    def __init__(self, kernel: Any):
        self._kernel = kernel
        self._module_data: Dict[str, Dict] = {}

    async def register_command(self, module_name: str, command: str, handler: Callable) -> bool:
        """Регистрация команды от модуля"""
        if not self._kernel.is_running:
            return False

        registry = self._kernel.get_service('registry')
        return await registry.register_command(module_name, command, handler)

    async def register_handler(self, module_name: str, event_type: str, handler: Callable) -> bool:
        """Регистрация обработчика событий"""
        if not self._kernel.is_running:
            return False

        registry = self._kernel.get_service('registry')
        return await registry.register_handler(module_name, event_type, handler)

    async def get_module_data(self, module_name: str) -> Dict:
        """Получение данных модуля"""
        return self._module_data.get(module_name, {})

    async def set_module_data(self, module_name: str, data: Dict) -> None:
        """Установка данных модуля"""
        self._module_data[module_name] = data

    async def get_service(self, service_name: str) -> Optional[Any]:
        """Получение доступа к сервису"""
        return self._kernel.get_service(service_name)

    async def emit_event(self, event_name: str, data: Any = None) -> None:
        """Отправка события в систему"""
        await self._kernel.emit_event(event_name, data)

    async def register_service(self, name: str, service: Any) -> bool:
        """Регистрация нового сервиса"""
        if name not in self._kernel.services:
            self._kernel.register_service(name, service)
            return True
        return False

    async def get_module(self, module_name: str) -> Optional[Any]:
        """Получение экземпляра другого модуля"""
        return self._kernel.get_module(module_name)

    async def reload_module(self, module_name: str) -> bool:
        """Перезагрузка модуля"""
        return await self._kernel.reload_module(module_name)

    @property
    def is_running(self) -> bool:
        """Проверка, запущено ли ядро"""
        return self._kernel.is_running

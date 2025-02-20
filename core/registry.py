from typing import Dict, List, Any, Callable, Optional
from collections import defaultdict
import asyncio
import logging
from datetime import datetime

class Registry:
    """Центральный реестр для управления сервисами и командами"""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._commands: Dict[str, Dict] = {}
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._modules: Dict[str, Dict] = {}
        self._logger = logging.getLogger('registry')
        self._locks: Dict[str, asyncio.Lock] = {}

    async def register_service(self, name: str, service: Any, metadata: Dict = None) -> bool:
        """Регистрация сервиса"""
        if name in self._services:
            return False

        lock = self._get_lock(f"service_{name}")
        async with lock:
            self._services[name] = {
                'instance': service,
                'metadata': metadata or {},
                'registered_at': datetime.now()
            }
            self._logger.info(f"Service registered: {name}")
            return True

    async def unregister_service(self, name: str) -> bool:
        """Удаление сервиса из реестра"""
        lock = self._get_lock(f"service_{name}")
        async with lock:
            if name in self._services:
                service = self._services[name]['instance']
                if hasattr(service, 'cleanup'):
                    await service.cleanup()
                del self._services[name]
                self._logger.info(f"Service unregistered: {name}")
                return True
            return False

    async def register_command(self, module_name: str, command: str, handler: Callable, metadata: Dict = None) -> bool:
        """Регистрация команды"""
        lock = self._get_lock(f"command_{command}")
        async with lock:
            if command in self._commands:
                return False

            self._commands[command] = {
                'module': module_name,
                'handler': handler,
                'metadata': metadata or {},
                'registered_at': datetime.now()
            }
            self._logger.info(f"Command registered: {command} by {module_name}")
            return True

    async def register_handler(self, module_name: str, event_type: str, handler: Callable) -> bool:
        """Регистрация обработчика событий"""
        lock = self._get_lock(f"handler_{event_type}")
        async with lock:
            handler_info = {
                'module': module_name,
                'handler': handler,
                'registered_at': datetime.now()
            }
            if handler_info not in self._handlers[event_type]:
                self._handlers[event_type].append(handler_info)
                self._logger.info(f"Handler registered for {event_type} by {module_name}")
                return True
            return False

    async def register_module(self, name: str, module: Any, metadata: Dict = None) -> bool:
        """Регистрация модуля"""
        lock = self._get_lock(f"module_{name}")
        async with lock:
            if name in self._modules:
                return False

            self._modules[name] = {
                'instance': module,
                'metadata': metadata or {},
                'registered_at': datetime.now(),
                'status': 'active'
            }
            self._logger.info(f"Module registered: {name}")
            return True

    def get_service(self, name: str) -> Optional[Any]:
        """Получение сервиса"""
        return self._services.get(name, {}).get('instance')

    def get_command_handler(self, command: str) -> Optional[Callable]:
        """Получение обработчика команды"""
        return self._commands.get(command, {}).get('handler')

    def get_handlers(self, event_type: str) -> List[Callable]:
        """Получение обработчиков события"""
        return [h['handler'] for h in self._handlers.get(event_type, [])]

    def get_module(self, name: str) -> Optional[Any]:
        """Получение модуля"""
        return self._modules.get(name, {}).get('instance')

    def list_services(self) -> Dict[str, Dict]:
        """Список всех сервисов"""
        return {name: {**info, 'instance': str(info['instance'])}
                for name, info in self._services.items()}

    def list_commands(self) -> Dict[str, Dict]:
        """Список всех команд"""
        return {name: {**info, 'handler': str(info['handler'])}
                for name, info in self._commands.items()}

    def list_modules(self) -> Dict[str, Dict]:
        """Список всех модулей"""
        return {name: {**info, 'instance': str(info['instance'])}
                for name, info in self._modules.items()}

    def _get_lock(self, name: str) -> asyncio.Lock:
        """Получение блокировки по имени"""
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    async def cleanup(self):
        """Очистка всех ресурсов"""
        for name in list(self._services.keys()):
            await self.unregister_service(name)
        self._commands.clear()
        self._handlers.clear()
        self._modules.clear()
        self._locks.clear()

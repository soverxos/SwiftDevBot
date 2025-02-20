import asyncio
import importlib
import os
import logging
import yaml  # Добавляем импорт yaml
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path
from core.module_api import ModuleInterface  # Добавляем импорт ModuleInterface
from core.events import EventManager
    
class Kernel:
    # Определяем порядок загрузки системных модулей
    CORE_MODULES = [
        "system.database",  # База данных должна загружаться первой
        "system.logger",    # Логгер следующий
        "system.security",  # Безопасность зависит от БД
        "system.api",       # API может зависеть от безопасности
        "system.notifications",
        "system.scheduler",
        "system.stats",
        "system.admin",
        "system.module_manager",
        "system.backup",
        "system.base"
    ]

    def __init__(self):
        self.logger = logging.getLogger('kernel')
        self._modules: Dict[str, ModuleInterface] = {}
        self._services: Dict[str, Any] = {}  # Добавляем инициализацию сервисов
        self._running: bool = False
        self._token: Optional[str] = None
        self._modules_path = Path(__file__).parent.parent / 'modules'
        self._event_manager = EventManager()

    async def init(self, token: str, modules_path: str = "modules"):
        """Инициализация ядра"""
        self._modules_path = Path(modules_path)
        self._token = token

        # Инициализация базового функционала
        await self._init_events()
        await self._init_registry()

        # Инициализация телеграм-бота до загрузки модулей
        from telegram.ext import Application
        self._bot = Application.builder().token(self._token).build()
        await self._bot.initialize()
        
        # Теперь загружаем модули
        await self._load_modules()

    async def _init_events(self):
        """Инициализация системы событий"""
        from .events import EventManager
        self._event_manager = EventManager()
        self._services['events'] = self._event_manager

    async def _init_registry(self):
        """Инициализация реестра сервисов"""
        from .registry import Registry
        self._registry = Registry()
        self._services['registry'] = self._registry

    async def _load_modules(self):
        """Загрузка модулей в правильном порядке"""
        self.logger.info("Starting modules auto-loading...")
        
        # Сначала загружаем core модули в определенном порядке
        for module_name in self.CORE_MODULES:
            try:
                await self._load_module(module_name)
                self.logger.info(f"✅ Loaded core module: {module_name}")
            except Exception as e:
                self.logger.error(f"❌ Failed to load core module {module_name}: {e}")
                if module_name in ["system.database", "system.security"]:
                    raise  # Критические модули, без них нельзя продолжать

        # Затем загружаем пользовательские модули
        user_path = self._modules_path / "user"
        if user_path.exists():
            for module_dir in user_path.iterdir():
                if not module_dir.is_dir() or not (module_dir / "main.py").exists():
                    continue
                    
                module_name = f"user.{module_dir.name}"
                try:
                    await self._load_module(module_name)
                    self.logger.info(f"✅ Loaded user module: {module_name}")
                except Exception as e:
                    self.logger.error(f"❌ Failed to load user module {module_name}: {e}")

        self.logger.info(f"✨ Auto-loaded {len(self._modules)} modules")

    async def _check_dependencies(self):
        """Проверка зависимостей модулей"""
        for module_name, module in self._modules.items():
            if not hasattr(module, 'metadata'):
                continue
                
            if not hasattr(module.metadata, 'dependencies'):
                continue
                
            for dependency in module.metadata.dependencies:
                if dependency not in self._modules:
                    self.logger.warning(f"⚠️ Module {module_name} depends on {dependency} which is not loaded")

    async def _load_module(self, module_name: str):
        """Загрузка отдельного модуля"""
        try:
            # Формируем путь к модулю
            module_parts = module_name.split('.')
            module_path = self._modules_path.joinpath(*module_parts)
            main_file = module_path / "main.py"
            config_file = module_path / "config.yml"

            if not main_file.exists():
                raise FileNotFoundError(f"Module file not found: {main_file}")

            # Загружаем конфигурацию
            module_config = {}
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    module_config = yaml.safe_load(f)

            # Импортируем модуль
            spec = importlib.util.spec_from_file_location(module_name, str(main_file))
            if spec is None:
                raise ImportError(f"Cannot create spec for module: {module_name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            if spec.loader is None:
                raise ImportError(f"Cannot load module: {module_name}")

            spec.loader.exec_module(module)

            # Ищем класс модуля
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, ModuleInterface) and attr != ModuleInterface:
                    instance = attr()
                    instance.config = module_config
                    await instance.setup(self)
                    self._modules[module_name] = instance
                    self.logger.info(f"✅ Loaded module: {module_name}")
                    return

            raise ValueError(f"No module class found in {module_name}")

        except Exception as e:
            self.logger.error(f"❌ Failed to load module {module_name}: {str(e)}")
            raise

    async def start(self):
        """Запуск бота"""
        if self._running:
            raise RuntimeError("Bot is already running")
            
        if not self._token:
            raise ValueError("Bot token is not set")
            
        self._running = True
        try:
            await self._event_manager.emit('before_start')

            # Инициализация телеграм-бота
            from telegram.ext import Application
            self._bot = Application.builder().token(self._token).build()
            
            # Инициализация бота
            await self._bot.initialize()

            # Регистрация обработчиков от модулей
            for module_name, module in self._modules.items():
                if hasattr(module, 'register_handlers'):
                    try:
                        await module.register_handlers(self._bot)
                        self.logger.info(f"📡 Registered handlers for module: {module_name}")
                    except Exception as e:
                        self.logger.error(f"❌ Failed to register handlers for {module_name}: {e}")

            await self._event_manager.emit('after_start')
            
            # Запуск бота
            await self._bot.start()
            await self._bot.updater.start_polling()
                
        except Exception as e:
            self._running = False
            self.logger.error(f"❌ Failed to start bot: {e}")
            raise

    async def stop(self):
        """Остановка бота"""
        if not self._running:
            return
            
        self._running = False
        try:
            await self._event_manager.emit('before_stop')

            # Сначала останавливаем все модули
            for module_name in reversed(list(self._modules.keys())):
                module = self._modules[module_name]
                try:
                    if hasattr(module, 'cleanup'):
                        await module.cleanup()
                        self.logger.info(f"🧹 Cleaned up module: {module_name}")
                except Exception as e:
                    self.logger.error(f"❌ Error cleaning up {module_name}: {e}")

            # Потом останавливаем бота
            if hasattr(self, '_bot'):
                try:
                    if self._bot.updater and self._bot.updater.running:
                        await self._bot.updater.stop()
                    await self._bot.stop()
                    await self._bot.shutdown()
                    self.logger.info("🤖 Bot stopped successfully")
                except Exception as e:
                    self.logger.error(f"❌ Error stopping bot: {e}")

            await self._event_manager.emit('after_stop')
            
        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")
        finally:
            # Очистка ресурсов в любом случае
            self._modules.clear()
            self._services.clear()

    def get_module(self, name: str) -> Optional[Any]:
        """Получение модуля по имени"""
        return self._modules.get(name)

    def get_service(self, name: str) -> Optional[Any]:
        """Получение сервиса по имени"""
        return self._services.get(name)

    async def reload_module(self, module_name: str) -> bool:
        """Перезагрузка модуля"""
        if not module_name in self._modules:
            await self._event_manager.emit('module_reload_error', {
                'name': module_name,
                'error': 'Module not found'
            })
            return False

        try:
            # Выгрузка старого модуля
            if hasattr(self._modules[module_name], 'cleanup'):
                await self._modules[module_name].cleanup()
            del self._modules[module_name]

            # Загрузка нового
            await self._load_module(module_name)
            await self._event_manager.emit('module_reloaded', {'name': module_name})
            return True
        except Exception as e:
            await self._event_manager.emit('module_reload_error', {
                'name': module_name,
                'error': str(e)
            })
            return False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def modules(self) -> Dict[str, Any]:
        return self._modules.copy()

    @property
    def services(self) -> Dict[str, Any]:
        return self._services.copy()

    def register_service(self, name: str, service: Any):
        """Регистрация нового сервиса"""
        self._services[name] = service

    async def emit_event(self, event_name: str, data: Any = None):
        """Отправка события"""
        await self._event_manager.emit(event_name, data)

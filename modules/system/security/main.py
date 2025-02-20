# modules/system/security/main.py
import logging
import yaml
import json
from collections import defaultdict
from core.module_api import ModuleInterface, ModuleMetadata
from core.database import DatabaseService
from telegram.ext import MessageHandler, filters
from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
from typing import Optional, List, Dict

class SecurityService(DatabaseService):
    def __init__(self, kernel):
        super().__init__(kernel)
        self.logger = logging.getLogger('security')
        self.rate_limits = defaultdict(list)
        self.user_roles_cache = {}
        self.config = self._load_config()

    async def setup(self):
        await self._create_tables()

    def _load_config(self) -> dict:
        try:
            with open("config/security.yml", 'r') as f:
                config = yaml.safe_load(f)
                self.logger.info("Security config loaded successfully")
                return config or {}
        except FileNotFoundError:
            self.logger.warning("Security config not found, using defaults")
            return {}
        except Exception as e:
            self.logger.error(f"Error loading security config: {e}")
            return {}

    async def _create_tables(self):
        """Создание необходимых таблиц"""
        try:
            queries = [
                """
                CREATE TABLE IF NOT EXISTS roles (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    permissions TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id INTEGER,
                    role_id INTEGER,
                    assigned_by INTEGER,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, role_id),
                    FOREIGN KEY (role_id) REFERENCES roles(id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS security_logs (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            ]

            for query in queries:
                await self.execute(query)
                
            await self.db.commit()
            self.logger.info("Security tables created successfully")

        except Exception as e:
            self.logger.error(f"Error creating security tables: {e}")
            raise

        # Добавляем базовые роли
        roles = [
            ("guest", '{"can_read": true}'),
            ("user", '{"can_read": true, "can_write": true}'),
            ("moderator", '{"can_read": true, "can_write": true, "can_moderate": true}'),
            ("admin", '{"can_read": true, "can_write": true, "can_moderate": true, "can_manage": true}')
        ]
        
        for role, perms in roles:
            await self.execute(
                "INSERT OR IGNORE INTO roles (name, permissions) VALUES (?, ?)",
                (role, perms)
            )
        await self.db.commit()

    async def check_rate_limit(self, user_id: int) -> bool:
        """Проверка ограничения частоты запросов"""
        now = datetime.now()
        user_requests = self.rate_limits[user_id]

        # Удаляем старые запросы
        user_requests = [req for req in user_requests
                        if now - req < timedelta(seconds=self.config.get('rate_period', 60))]

        # Проверяем лимит
        if len(user_requests) >= self.config.get('rate_limit', 30):
            return False

        user_requests.append(now)
        self.rate_limits[user_id] = user_requests
        return True

    async def get_user_roles(self, user_id: int) -> List[str]:
        """Получение ролей пользователя"""
        # Проверяем кэш
        if user_id in self.user_roles_cache:
            return self.user_roles_cache[user_id]

        query = """
        SELECT r.name FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        """
        roles = await self.db.fetch_all(query, (user_id,))
        role_names = [role['name'] for role in roles]

        # Кэшируем результат
        self.user_roles_cache[user_id] = role_names
        return role_names

    async def add_role(self, name: str, permissions: List[str]) -> bool:
        """Добавление новой роли"""
        try:
            query = "INSERT INTO roles (name, permissions) VALUES (?, ?)"
            await self.db.execute(query, (name, json.dumps(permissions)))
            return True
        except Exception as e:
            self.logger.error(f"Error adding role {name}: {e}")
            return False

    async def assign_role(self, user_id: int, role_name: str, assigned_by: int) -> bool:
        """Назначение роли пользователю"""
        try:
            # Получаем ID роли
            query = "SELECT id FROM roles WHERE name = ?"
            role = await self.db.fetch_one(query, (role_name,))
            if not role:
                return False

            # Назначаем роль
            query = "INSERT INTO user_roles (user_id, role_id, assigned_by) VALUES (?, ?, ?)"
            await self.db.execute(query, (user_id, role['id'], assigned_by))

            # Очищаем кэш
            self.user_roles_cache.pop(user_id, None)
            return True
        except Exception as e:
            self.logger.error(f"Error assigning role {role_name} to user {user_id}: {e}")
            return False

    async def check_permission(self, user_id: int, permission: str) -> bool:
        """Проверка прав доступа"""
        roles = await self.get_user_roles(user_id)

        # Проверяем каждую роль
        for role_name in roles:
            query = "SELECT permissions FROM roles WHERE name = ?"
            role = await self.db.fetch_one(query, (role_name,))
            if role:
                permissions = json.loads(role['permissions'])
                if permission in permissions or '*' in permissions:
                    return True
        return False

    async def log_security_event(self, user_id: int, action: str, details: Dict, ip: str = None):
        """Логирование событий безопасности"""
        query = """
        INSERT INTO security_logs (user_id, action, details, ip_address)
        VALUES (?, ?, ?, ?)
        """
        await self.db.execute(query, (user_id, action, json.dumps(details), ip))

class SecurityModule(ModuleInterface):
    async def setup(self, kernel):
        """Инициализация модуля безопасности"""
        self.kernel = kernel
        self.logger = logging.getLogger('security.module')
        
        self.metadata = ModuleMetadata(
            name="system.security",
            version="1.0.0",
            description="Модуль безопасности",
            dependencies=["system.database"]
        )

        try:
            # Получаем сервис БД
            self.db = kernel.get_service("database")
            if not self.db or not hasattr(self.db, 'execute'):
                raise RuntimeError("Database service not properly initialized")
            
            # Создаем сервис безопасности
            self.service = SecurityService(kernel)
            
            # Создаем таблицы
            await self._create_security_tables()
            
            # Регистрируем сервис
            kernel.register_service("security", self.service)
            
            self.logger.info("Security module initialized successfully")
            return self
            
        except Exception as e:
            self.logger.error(f"Failed to initialize security module: {e}")
            raise

    async def _create_security_tables(self):
        """Создание таблиц безопасности"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                permissions TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER,
                role_id INTEGER,
                assigned_by INTEGER,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (role_id) REFERENCES roles(id)
            )
            """
        ]

        for query in queries:
            await self.db.execute(query)
            
        await self.db.connection.commit()

    async def cleanup(self):
        """Очистка ресурсов модуля"""
        try:
            # Очищаем кэши
            if hasattr(self, 'service'):
                self.service.user_roles_cache.clear()
                self.service.rate_limits.clear()
            self.logger.info("Security module cleaned up")
        except Exception as e:
            self.logger.error(f"Error during security cleanup: {e}")

    async def register_handlers(self, bot):
        """Регистрация обработчиков сообщений"""
        bot.add_handler(MessageHandler(
            filters.ALL & ~filters.COMMAND, 
            self.message_handler
        ))
        self.logger.info("Security handlers registered")

    async def message_handler(self, update, context):
        """Обработчик всех сообщений для проверки безопасности"""
        try:
            user_id = update.effective_user.id
            
            # Проверяем ограничения
            if not await self.service.check_rate_limit(user_id):
                await update.message.reply_text(
                    "⚠️ Превышен лимит сообщений. Пожалуйста, подождите."
                )
                return
                
            # Проверяем права доступа
            if not await self.service.check_permission(user_id, "can_write"):
                await update.message.reply_text(
                    "🚫 У вас нет прав для отправки сообщений."
                )
                return
                
        except Exception as e:
            self.logger.error(f"Error in security message handler: {e}")
            
        # Логируем событие
        await self.service.log_security_event(
            user_id,
            'message',
            {
                'chat_id': update.effective_chat.id,
                'message_id': update.message.message_id,
                'text_length': len(update.message.text or '')
            }
        )

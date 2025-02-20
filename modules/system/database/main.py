# modules/system/database/main.py
from core.module_api import ModuleInterface, ModuleMetadata
import aiosqlite
import asyncpg
import logging
from pathlib import Path
import yaml
from typing import Any, List, Dict, Optional

class DatabaseService:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger('database')
        self._connection = None

    async def connect(self):
        """Установка соединения с БД"""
        db_type = self.config['type']

        if db_type == 'sqlite':
            db_path = Path(self.config['path'])
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = await aiosqlite.connect(db_path)

        elif db_type == 'postgresql':
            self._connection = await asyncpg.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['name']
            )

        self.logger.info(f"Connected to {db_type} database")

    async def disconnect(self):
        """Закрытие соединения"""
        if self._connection:
            await self._connection.close()
            self.logger.info("Database connection closed")

    async def execute(self, query: str, params: tuple = None) -> Any:
        """Выполнение SQL запроса"""
        try:
            if self.config['type'] == 'sqlite':
                async with self._connection.execute(query, params or ()) as cursor:
                    await self._connection.commit()
                    return cursor.rowcount
            else:
                return await self._connection.execute(query, *params if params else ())
        except Exception as e:
            self.logger.error(f"Query execution error: {e}")
            raise

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Получение всех строк"""
        try:
            if self.config['type'] == 'sqlite':
                async with self._connection.execute(query, params or ()) as cursor:
                    rows = await cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
            else:
                rows = await self._connection.fetch(query, *params if params else ())
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Query fetch error: {e}")
            raise

    async def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Получение одной строки"""
        try:
            if self.config['type'] == 'sqlite':
                async with self._connection.execute(query, params or ()) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        columns = [description[0] for description in cursor.description]
                        return dict(zip(columns, row))
                    return None
            else:
                row = await self._connection.fetchrow(query, *params if params else ())
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Query fetch error: {e}")
            raise

    async def create_tables(self):
        """Создание базовых таблиц"""
        queries = [
            # Таблица пользователей
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language_code TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Таблица настроек
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Таблица статистики
            """
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]

        for query in queries:
            await self.execute(query)

        self.logger.info("Base tables created")

class DatabaseModule(ModuleInterface):
    async def setup(self, kernel):
        """Инициализация модуля базы данных"""
        self.kernel = kernel
        self.logger = logging.getLogger('database')
        
        self.metadata = ModuleMetadata(
            name="system.database",
            version="1.0.0",
            description="Модуль базы данных"
        )

        try:
            # Создаем директорию для БД если её нет
            db_dir = Path("data/db")
            db_dir.mkdir(parents=True, exist_ok=True)
            
            # Путь к файлу БД
            db_path = db_dir / "database.db"
            
            # Создаем соединение
            self.connection = await aiosqlite.connect(db_path)
            await self.connection.execute("PRAGMA foreign_keys = ON")
            await self.connection.execute("PRAGMA journal_mode = WAL")  # Улучшаем производительность
            
            # Базовые таблицы
            await self._create_base_tables()
            
            # Регистрируем сервис
            self.kernel.register_service("database", self)
            
            self.logger.info(f"Database initialized at {db_path}")
            return self
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Получение всех результатов запроса"""
        try:
            async with self.connection.execute(query, params or ()) as cursor:
                # Получаем имена колонок
                columns = [description[0] for description in cursor.description]
                # Получаем все строки
                rows = await cursor.fetchall()
                # Преобразуем в словари
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Error in fetch_all: {e}")
            return []

    async def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Получение одной записи"""
        try:
            async with self.connection.execute(query, params or ()) as cursor:
                row = await cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            self.logger.error(f"Error in fetch_one: {e}")
            return None

    async def execute(self, query: str, params: tuple = None) -> Optional[aiosqlite.Cursor]:
        """Выполнение запроса"""
        try:
            if params:
                return await self.connection.execute(query, params)
            return await self.connection.execute(query)
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            return None

    async def execute_many(self, query: str, params_list: List[tuple]) -> bool:
        """Выполнение множества запросов"""
        try:
            await self.connection.executemany(query, params_list)
            await self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error in execute_many: {e}")
            return False

    async def _create_base_tables(self):
        """Создание базовых таблиц"""
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                version TEXT NOT NULL,
                enabled BOOLEAN DEFAULT TRUE
            )
        """)
        await self.connection.commit()
        self.logger.info("Base tables created")

    async def cleanup(self):
        """Очистка ресурсов"""
        if hasattr(self, 'connection'):
            await self.connection.close()
            self.logger.info("Database connection closed")

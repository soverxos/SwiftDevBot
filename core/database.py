from typing import Dict, List, Optional, Any
import aiosqlite
import logging

class DatabaseService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('database')
        self._connection: Optional[aiosqlite.Connection] = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if not self._connection:
            raise RuntimeError("Database not initialized")
        return self._connection

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Получение всех результатов запроса"""
        try:
            async with self.connection.execute(query, params or ()) as cursor:
                columns = [description[0] for description in cursor.description]
                rows = await cursor.fetchall()
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

    async def init_db(self, connection: aiosqlite.Connection):
        self._connection = connection
        await self._create_tables()

    async def _create_tables(self):
        """Переопределите этот метод в дочерних классах"""
        pass
# modules/system/logger/main.py
from core.module_api import ModuleInterface, ModuleMetadata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import logging
import logging.handlers
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import aiofiles
import os
import yaml

class LoggerService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.base_logger = logging.getLogger('system')
        self.db = kernel.get_service('database')
        self.config = self._load_config()

        # Настройка логгера
        self._setup_logging()

        # Очередь для асинхронной записи логов
        self.log_queue = asyncio.Queue()
        self._running = False
        self._process_task = None
        self.logger = logging.getLogger('logger')

    async def start(self):
        self._running = True
        self._process_task = asyncio.create_task(self._process_log_queue())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._process_task:
            try:
                # Ждем завершения всех задач в очереди
                if not self.log_queue.empty():
                    await self.log_queue.join()
                self._process_task.cancel()
                await asyncio.shield(self._process_task)
            except asyncio.CancelledError:
                pass

    def _load_config(self) -> dict:
        """Загрузка конфигурации логгера"""
        with open("config.yml", 'r') as f:
            config = yaml.safe_load(f)
        return config.get('logging', {})

    def _setup_logging(self):
        """Настройка системы логирования"""
        log_dir = Path(self.config.get('path', 'logs'))
        log_dir.mkdir(parents=True, exist_ok=True)

        # Основной файл лога
        main_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'main.log',
            maxBytes=self.config.get('max_size', 10_000_000),
            backupCount=self.config.get('backup_count', 5),
            encoding='utf-8'
        )

        # Файл для ошибок
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'error.log',
            maxBytes=self.config.get('max_size', 10_000_000),
            backupCount=self.config.get('backup_count', 5),
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)

        # Форматтер для логов
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        main_handler.setFormatter(formatter)
        error_handler.setFormatter(formatter)

        # Добавляем обработчики
        self.base_logger.addHandler(main_handler)
        self.base_logger.addHandler(error_handler)

        # Устанавливаем уровень логирования
        self.base_logger.setLevel(
            getattr(logging, self.config.get('level', 'INFO'))
        )

    async def _create_tables(self):
        """Создание таблиц для логов"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT NOT NULL,
                module TEXT,
                message TEXT NOT NULL,
                details TEXT,
                user_id INTEGER,
                chat_id INTEGER
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp
            ON system_logs(timestamp)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_logs_level
            ON system_logs(level)
            """
        ]

        for query in queries:
            await self.db.execute(query)

    async def _process_log_queue(self):
        """Обработка очереди логов"""
        while self._running:
            try:
                log_entry = await self.log_queue.get()
                await self._save_log_to_db(log_entry)
                self.log_queue.task_done()
            except asyncio.CancelledError:
                # При отмене задачи, завершаем обработку текущих логов
                while not self.log_queue.empty():
                    try:
                        log_entry = self.log_queue.get_nowait()
                        await self._save_log_to_db(log_entry)
                        self.log_queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                break
            except Exception as e:
                self.logger.error(f"Error processing log: {e}")
            await asyncio.sleep(0.1)

    async def _save_log_to_db(self, log_entry: Dict):
        """Сохранение лога в БД"""
        query = """
        INSERT INTO system_logs
        (timestamp, level, module, message, details, user_id, chat_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            (
                log_entry['timestamp'],
                log_entry['level'],
                log_entry['module'],
                log_entry['message'],
                json.dumps(log_entry.get('details')),
                log_entry.get('user_id'),
                log_entry.get('chat_id')
            )
        )

    async def log(self, level: str, message: str, module: str = None,
                  details: Dict = None, user_id: int = None,
                  chat_id: int = None):
        """Асинхронное логирование"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level.upper(),
            'module': module,
            'message': message,
            'details': details,
            'user_id': user_id,
            'chat_id': chat_id
        }

        # Добавляем в очередь
        await self.log_queue.put(log_entry)

        # Логируем через стандартный логгер
        logger = logging.getLogger(module if module else 'system')
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(message)

    async def get_logs(self, level: str = None, module: str = None,
                      start_date: datetime = None,
                      end_date: datetime = None,
                      limit: int = 100) -> List[Dict]:
        """Получение логов из БД"""
        conditions = []
        params = []

        query = "SELECT * FROM system_logs"

        if level:
            conditions.append("level = ?")
            params.append(level.upper())

        if module:
            conditions.append("module = ?")
            params.append(module)

        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        return await self.db.fetch_all(query, tuple(params))

    async def clear_old_logs(self, days: int = 30):
        """Очистка старых логов"""
        cutoff_date = datetime.now() - timedelta(days=days)

        # Очистка БД
        query = "DELETE FROM system_logs WHERE timestamp < ?"
        await self.db.execute(query, (cutoff_date.isoformat(),))

        # Очистка файлов логов
        log_dir = Path(self.config.get('path', 'logs'))
        for log_file in log_dir.glob("*.log.*"):
            if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                try:
                    os.remove(log_file)
                except Exception as e:
                    self.base_logger.error(f"Error removing old log file {log_file}: {e}")

class LoggerModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('logger.module')
        
        self.metadata = ModuleMetadata(
            name="system.logger",
            version="1.0.0",
            description="Модуль логирования",
            dependencies=["system.database"]
        )

        try:
            # Получаем сервис БД
            self.db = kernel.get_service("database")
            if not self.db or not hasattr(self.db, 'execute'):
                raise RuntimeError("Database service not properly initialized")
            
            # Создаем таблицу логов
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await self.db.connection.commit()
            
            self.logger.info("Logger module initialized")
            return self
            
        except Exception as e:
            self.logger.error(f"Failed to initialize logger module: {e}")
            raise

    async def cleanup(self):
        """Очистка ресурсов"""
        if hasattr(self, 'cleanup_task'):
            self.cleanup_task.cancel()
        self.logger.info("Logger module cleaned up")

    async def _periodic_cleanup(self):
        """Периодическая очистка старых логов"""
        while True:
            try:
                await asyncio.sleep(86400)  # раз в сутки
                await self.log_service.clear_old_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic cleanup: {e}")

    async def logs_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню просмотра логов"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для просмотра логов")
            return

        keyboard = [
            [
                InlineKeyboardButton("📋 Все логи", callback_data="log_all"),
                InlineKeyboardButton("❌ Ошибки", callback_data="log_error")
            ],
            [
                InlineKeyboardButton("⚠️ Предупреждения", callback_data="log_warning"),
                InlineKeyboardButton("ℹ️ Информация", callback_data="log_info")
            ],
            [
                InlineKeyboardButton("🗑 Очистить старые", callback_data="log_clear")
            ]
        ]

        await update.message.reply_text(
            "📊 *Система логирования*\\n\\n"
            "Выберите тип логов для просмотра:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def clear_logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда очистки логов"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для очистки логов")
            return

        try:
            days = int(context.args[0]) if context.args else 30
            await self.log_service.clear_old_logs(days)
            await update.message.reply_text(f"✅ Логи старше {days} дней очищены")
        except ValueError:
            await update.message.reply_text("❌ Использование: /clearlogs [дней]")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()

        if not await self.kernel.get_service('security').check_permission(
            query.from_user.id, 'admin'
        ):
            return

        action = query.data.split('_')[1]

        if action == "clear":
            await self.log_service.clear_old_logs()
            await query.message.reply_text("✅ Старые логи очищены")
            return

        # Получаем логи
        level = action.upper() if action != "all" else None
        logs = await self.log_service.get_logs(level=level, limit=10)

        if not logs:
            await query.message.reply_text("📝 Логи отсутствуют")
            return

        text = "📋 *Последние логи:*\\n\\n"
        for log in logs:
            text += (f"*{log['level']}* - {log['timestamp']}\\n"
                    f"Module: {log['module']}\\n"
                    f"Message: {log['message']}\\n\\n")

        await query.message.reply_text(
            text[:4096],  # Telegram limit
            parse_mode='Markdown'
        )

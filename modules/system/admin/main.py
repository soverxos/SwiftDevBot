from core.module_api import ModuleInterface, ModuleMetadata
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import yaml
import logging
from datetime import datetime
from pathlib import Path

class AdminService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('admin')
        self.db = kernel.get_service('database')

    async def _create_tables(self):
        """Создание необходимых таблиц"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                added_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES admins(user_id)
            )
            """
        ]
        
        for query in queries:
            await self.db.execute(query)

    async def is_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        query = "SELECT 1 FROM admins WHERE user_id = ?"
        result = await self.db.fetch_one(query, (user_id,))
        return result is not None

    async def add_admin(self, user_id: int, added_by: int = None) -> bool:
        """Добавление администратора"""
        try:
            query = """
            INSERT INTO admins (user_id, added_by, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """
            await self.db.execute(query, (user_id, added_by))
            return True
        except Exception as e:
            self.logger.error(f"Error adding admin {user_id}: {e}")
            return False

    async def remove_admin(self, user_id: int) -> bool:
        """Удаление администратора"""
        try:
            query = "DELETE FROM admins WHERE user_id = ?"
            await self.db.execute(query, (user_id,))
            return True
        except Exception as e:
            self.logger.error(f"Error removing admin {user_id}: {e}")
            return False

    async def get_admins(self) -> list:
        """Получение списка администраторов"""
        query = """
        SELECT user_id, username, first_name, last_name, created_at 
        FROM admins
        """
        return await self.db.fetch_all(query)

    async def get_commands(self) -> dict:
        """Получение списка команд"""
        registry = self.kernel.get_service('registry')
        return registry._commands

class AdminModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.logger = kernel.get_logger('admin')
        
        self.metadata = ModuleMetadata(
            name="system.admin",
            version="1.0.0",
            description="Модуль администрирования",
            dependencies=["system.database"]
        )

        try:
            # Создаем сервис
            self.service = AdminService(kernel)
            
            # Получаем БД
            self.db = kernel.get_service("database")
            if not self.db:
                raise RuntimeError("Database service not available")
                
            # Создаем таблицы
            await self.service._create_tables()
            
            # Регистрируем сервис
            kernel.register_service("admin", self.service)
            
            # Загружаем конфигурацию
            config_path = Path(__file__).parent / "config.yml"
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
            
            self.logger.info("Admin module initialized")
            return self
            
        except Exception as e:
            self.logger.error(f"Failed to initialize admin module: {e}")
            raise

    async def cleanup(self):
        """Реализация абстрактного метода cleanup"""
        pass

    async def register_handlers(self, bot):
        """Регистрация обработчиков команд"""
        # Базовые команды
        bot.add_handler(CommandHandler("admin", self.cmd_admin))
        bot.add_handler(CommandHandler("addadmin", self.cmd_add_admin))
        bot.add_handler(CommandHandler("rmadmin", self.cmd_remove_admin))
        bot.add_handler(CommandHandler("admins", self.cmd_list_admins))
        bot.add_handler(CommandHandler("commands", self.cmd_list_commands))

    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню администратора"""
        if not await self._is_admin(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        keyboard = [
            [InlineKeyboardButton("👥 Управление админами", callback_data='admin_manage')],
            [InlineKeyboardButton("📝 Список команд", callback_data='admin_commands')],
            [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛠 Меню администратора\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )

    async def cmd_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавить администратора"""
        if not await self._is_admin(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        if not context.args:
            await update.message.reply_text("❌ Укажите ID пользователя")
            return

        try:
            user_id = int(context.args[0])
            # Добавление в базу данных
            await self.db.execute(
                "INSERT INTO admins (user_id) VALUES (?)",
                (user_id,)
            )
            await update.message.reply_text(f"✅ Пользователь {user_id} добавлен как администратор")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удалить администратора"""
        if not await self._is_admin(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        if not context.args:
            await update.message.reply_text("❌ Укажите ID пользователя")
            return

        try:
            user_id = int(context.args[0])
            # Удаление из базы данных
            await self.db.execute(
                "DELETE FROM admins WHERE user_id = ?",
                (user_id,)
            )
            await update.message.reply_text(f"✅ Пользователь {user_id} удален из администраторов")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список администраторов"""
        if not await self._is_admin(update.effective_user.id):
            await update.message.reply_text("❌ У вас нет прав администратора")
            return

        try:
            admins = await self.db.fetchall("SELECT user_id FROM admins")
            if not admins:
                await update.message.reply_text("📝 Список администраторов пуст")
                return

            text = "👥 Список администраторов:\n\n"
            for admin in admins:
                text += f"• {admin['user_id']}\n"
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_list_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список команд"""
        commands_text = "📝 Доступные команды:\n\n"
        for cmd, desc in self.config['commands'].items():
            commands_text += f"/{cmd} - {desc}\n"
        await update.message.reply_text(commands_text)

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка прав администратора"""
        try:
            admin = await self.db.fetchone(
                "SELECT 1 FROM admins WHERE user_id = ?",
                (user_id,)
            )
            return admin is not None
        except Exception:
            return False

# modules/system/scheduler/main.py
from core.module_api import ModuleInterface, ModuleMetadata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import aiocron
import logging
from datetime import datetime, timedelta
import json
import yaml
from typing import Dict, List, Callable, Any, Optional

class Task:
    def __init__(self, id: int, name: str, cron: str, handler: str,
                 args: List = None, kwargs: Dict = None, enabled: bool = True):
        self.id = id
        self.name = name
        self.cron = cron
        self.handler = handler
        self.args = args or []
        self.kwargs = kwargs or {}
        self.enabled = enabled
        self.last_run = None
        self.next_run = None
        self.job = None

class SchedulerService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('scheduler')
        self.db = kernel.get_service('database')
        self.tasks: Dict[int, Task] = {}
        self.handlers: Dict[str, Callable] = {}

    async def _create_tables(self):
        """Создание таблиц для задач"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cron TEXT NOT NULL,
                handler TEXT NOT NULL,
                args TEXT,
                kwargs TEXT,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run TIMESTAMP,
                next_run TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                status TEXT,
                result TEXT,
                error TEXT,
                duration FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
            )
            """
        ]

        for query in queries:
            await self.db.execute(query)

    async def load_tasks(self):
        """Загрузка задач из БД"""
        query = "SELECT * FROM scheduled_tasks"
        tasks = await self.db.fetch_all(query)

        for task_data in tasks:
            task = Task(
                id=task_data['id'],
                name=task_data['name'],
                cron=task_data['cron'],
                handler=task_data['handler'],
                args=json.loads(task_data['args'] or '[]'),
                kwargs=json.loads(task_data['kwargs'] or '{}'),
                enabled=task_data['enabled']
            )
            await self.add_task(task)

    async def add_task(self, task: Task) -> bool:
        """Добавление новой задачи"""
        try:
            if task.id is None:
                # Новая задача
                query = """
                INSERT INTO scheduled_tasks (name, cron, handler, args, kwargs, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
                """
                result = await self.db.execute(
                    query,
                    (task.name, task.cron, task.handler,
                     json.dumps(task.args), json.dumps(task.kwargs),
                     task.enabled)
                )
                task.id = result.lastrowid

            if task.enabled:
                # Создаём cron-задачу
                task.job = aiocron.crontab(
                    task.cron,
                    func=self._execute_task,
                    args=(task,),
                    start=True
                )

            self.tasks[task.id] = task
            return True

        except Exception as e:
            self.logger.error(f"Error adding task {task.name}: {e}")
            return False

    async def remove_task(self, task_id: int) -> bool:
        """Удаление задачи"""
        try:
            task = self.tasks.get(task_id)
            if task and task.job:
                task.job.stop()

            query = "DELETE FROM scheduled_tasks WHERE id = ?"
            await self.db.execute(query, (task_id,))

            self.tasks.pop(task_id, None)
            return True

        except Exception as e:
            self.logger.error(f"Error removing task {task_id}: {e}")
            return False

    async def enable_task(self, task_id: int) -> bool:
        """Включение задачи"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        try:
            task.enabled = True
            task.job = aiocron.crontab(
                task.cron,
                func=self._execute_task,
                args=(task,),
                start=True
            )

            query = "UPDATE scheduled_tasks SET enabled = TRUE WHERE id = ?"
            await self.db.execute(query, (task_id,))
            return True

        except Exception as e:
            self.logger.error(f"Error enabling task {task_id}: {e}")
            return False

    async def disable_task(self, task_id: int) -> bool:
        """Отключение задачи"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        try:
            task.enabled = False
            if task.job:
                task.job.stop()
                task.job = None

            query = "UPDATE scheduled_tasks SET enabled = FALSE WHERE id = ?"
            await self.db.execute(query, (task_id,))
            return True

        except Exception as e:
            self.logger.error(f"Error disabling task {task_id}: {e}")
            return False

    async def _execute_task(self, task: Task):
        """Выполнение задачи"""
        start_time = datetime.now()
        status = "success"
        error = None
        result = None

        try:
            handler = self.handlers.get(task.handler)
            if not handler:
                raise ValueError(f"Handler {task.handler} not found")

            result = await handler(*task.args, **task.kwargs)

            # Обновляем время выполнения
            task.last_run = start_time
            task.next_run = task.job.next() if task.job else None

            query = """
            UPDATE scheduled_tasks
            SET last_run = ?, next_run = ?
            WHERE id = ?
            """
            await self.db.execute(query, (task.last_run, task.next_run, task.id))

        except Exception as e:
            status = "error"
            error = str(e)
            self.logger.error(f"Task {task.name} failed: {e}")

        finally:
            # Логируем выполнение
            duration = (datetime.now() - start_time).total_seconds()
            query = """
            INSERT INTO task_logs (task_id, status, result, error, duration)
            VALUES (?, ?, ?, ?, ?)
            """
            await self.db.execute(
                query,
                (task.id, status, json.dumps(result) if result else None, error, duration)
            )

    def register_handler(self, name: str, handler: Callable):
        """Регистрация обработчика задач"""
        self.handlers[name] = handler

class Module(ModuleInterface):
    async def setup(self, kernel):
        """Инициализация модуля"""
        self.kernel = kernel
        self.logger = logging.getLogger('system.scheduler')

        # Создаём сервис планировщика
        self.scheduler = SchedulerService(kernel)
        await self.scheduler._create_tables()

        # Регистрируем сервис
        await kernel.get_service('registry').register_service(
            'scheduler',
            self.scheduler
        )

        # Регистрируем команды
        commands = [
            ('tasks', self.tasks_menu, 'Управление задачами'),
            ('addtask', self.add_task_command, 'Добавить задачу'),
            ('rmtask', self.remove_task_command, 'Удалить задачу'),
        ]

        for cmd, handler, desc in commands:
            self.kernel._bot.add_handler(CommandHandler(cmd, handler))

        # Регистрируем обработчик callback
        self.kernel._bot.add_handler(
            CallbackQueryHandler(self.button_callback, pattern='^task_')
        )

        # Загружаем существующие задачи
        await self.scheduler.load_tasks()

        self.logger.info("Scheduler module initialized")

    async def cleanup(self):
        """Очистка ресурсов"""
        # Останавливаем все задачи
        for task in self.scheduler.tasks.values():
            if task.job:
                task.job.stop()
        self.logger.info("Scheduler module cleaned up")

    async def tasks_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню управления задачами"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для управления задачами")
            return

        keyboard = []
        for task in self.scheduler.tasks.values():
            status = "✅" if task.enabled else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {task.name}",
                    callback_data=f"task_toggle_{task.id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("➕ Добавить задачу", callback_data="task_add")
        ])

        await update.message.reply_text(
            "⏰ *Управление задачами*\\n\\n"
            "Выберите задачу для управления:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def add_task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление новой задачи"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для управления задачами")
            return

        try:
            # /addtask name cron handler
            name, cron, handler = context.args[:3]

            task = Task(
                id=None,
                name=name,
                cron=cron,
                handler=handler
            )

            if await self.scheduler.add_task(task):
                await update.message.reply_text(f"✅ Задача {name} добавлена")
            else:
                await update.message.reply_text("❌ Ошибка при добавлении задачи")

        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Использование: /addtask <name> <cron> <handler>"
            )

    async def remove_task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаление задачи"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для управления задачами")
            return

        try:
            task_id = int(context.args[0])
            if await self.scheduler.remove_task(task_id):
                await update.message.reply_text(f"✅ Задача удалена")
            else:
                await update.message.reply_text("❌ Ошибка при удалении задачи")

        except (ValueError, IndexError):
            await update.message.reply_text("❌ Использование: /rmtask <task_id>")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()

        if not await self.kernel.get_service('security').check_permission(
            query.from_user.id, 'admin'
        ):
            return

        action = query.data.split('_')[1]

        if action == "toggle":
            task_id = int(query.data.split('_')[2])
            task = self.scheduler.tasks.get(task_id)

            if task:
                if task.enabled:
                    await self.scheduler.disable_task(task_id)
                else:
                    await self.scheduler.enable_task(task_id)

                # Обновляем меню
                await self.tasks_menu(update, context)

# modules/system/notifications/main.py
from core.module_api import ModuleInterface
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Union
import asyncio
import yaml
from jinja2 import Template

class Notification:
    def __init__(self, id: int, type: str, user_id: int,
                 message: str, status: str = 'pending',
                 scheduled_at: datetime = None,
                 metadata: Dict = None):
        self.id = id
        self.type = type
        self.user_id = user_id
        self.message = message
        self.status = status
        self.scheduled_at = scheduled_at
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.sent_at = None

class NotificationService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('notifications')
        self.db = kernel.get_service('database')
        self.config = self._load_config()

        # Очередь уведомлений
        self.queue = asyncio.Queue()
        self._running = False
        self._process_task = None

        # Кэш шаблонов
        self.templates = {}

    def _load_config(self) -> dict:
        with open("config.yml", 'r') as f:
            config = yaml.safe_load(f)
        return config.get('notifications', {})

    async def _create_tables(self):
        """Создание таблиц для уведомлений"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                scheduled_at TIMESTAMP,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notification_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                template TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                types TEXT,
                quiet_hours TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]

        for query in queries:
            await self.db.execute(query)

    async def load_templates(self):
        """Загрузка шаблонов из БД"""
        query = "SELECT name, template FROM notification_templates"
        templates = await self.db.fetch_all(query)

        for template in templates:
            self.templates[template['name']] = Template(template['template'])

    async def send(self, user_id: int, message: str,
                  type: str = 'info',
                  scheduled_at: datetime = None,
                  metadata: Dict = None) -> int:
        """Отправка уведомления"""
        # Проверяем настройки пользователя
        if not await self._check_user_preferences(user_id, type):
            return None

        # Создаем уведомление
        notification = Notification(
            id=None,
            type=type,
            user_id=user_id,
            message=message,
            scheduled_at=scheduled_at,
            metadata=metadata
        )

        # Сохраняем в БД
        query = """
        INSERT INTO notifications
        (type, user_id, message, status, scheduled_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        result = await self.db.execute(
            query,
            (
                notification.type,
                notification.user_id,
                notification.message,
                notification.status,
                notification.scheduled_at.isoformat() if notification.scheduled_at else None,
                json.dumps(notification.metadata) if notification.metadata else None
            )
        )
        notification.id = result.lastrowid

        # Добавляем в очередь
        await self.queue.put(notification)
        return notification.id

    async def send_template(self, template_name: str, user_id: int,
                          context: Dict = None, **kwargs) -> int:
        """Отправка уведомления по шаблону"""
        template = self.templates.get(template_name)
        if not template:
            # Пробуем загрузить из БД
            query = "SELECT template FROM notification_templates WHERE name = ?"
            result = await self.db.fetch_one(query, (template_name,))

            if not result:
                raise ValueError(f"Template {template_name} not found")

            template = Template(result['template'])
            self.templates[template_name] = template

        # Рендерим шаблон
        message = template.render(**(context or {}))
        return await self.send(user_id, message, **kwargs)

    async def broadcast(self, message: str, type: str = 'broadcast',
                       filter_func: callable = None) -> List[int]:
        """Массовая рассылка"""
        # Получаем список пользователей
        query = "SELECT id FROM users"
        users = await self.db.fetch_all(query)

        notification_ids = []
        for user in users:
            if filter_func and not await filter_func(user['id']):
                continue

            if notification_id := await self.send(
                user['id'],
                message,
                type=type
            ):
                notification_ids.append(notification_id)

        return notification_ids

    async def _process_queue(self):
        while self._running:
            try:
                notification = await self.queue.get()
                if notification:
                    await self._send_notification(notification)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing notification: {e}")
            await asyncio.sleep(0.1)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._process_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._process_task:
            await self.queue.join()
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

    async def _check_user_preferences(self, user_id: int, type: str) -> bool:
        """Проверка настроек пользователя"""
        query = "SELECT * FROM user_preferences WHERE user_id = ?"
        prefs = await self.db.fetch_one(query, (user_id,))

        if not prefs:
            return True

        if not prefs['enabled']:
            return False

        if prefs['types']:
            allowed_types = json.loads(prefs['types'])
            if type not in allowed_types:
                return False

        return True

    async def _is_quiet_hours(self, user_id: int) -> bool:
        """Проверка тихого часа"""
        query = "SELECT quiet_hours FROM user_preferences WHERE user_id = ?"
        prefs = await self.db.fetch_one(query, (user_id,))

        if not prefs or not prefs['quiet_hours']:
            return False

        quiet_hours = json.loads(prefs['quiet_hours'])
        now = datetime.now().time()

        start = datetime.strptime(quiet_hours['start'], '%H:%M').time()
        end = datetime.strptime(quiet_hours['end'], '%H:%M').time()

        if start <= end:
            return start <= now <= end
        else:
            return now >= start or now <= end

    async def _get_next_active_time(self, user_id: int) -> datetime:
        """Получение следующего активного времени"""
        query = "SELECT quiet_hours FROM user_preferences WHERE user_id = ?"
        prefs = await self.db.fetch_one(query, (user_id,))

        if not prefs or not prefs['quiet_hours']:
            return datetime.now()

        quiet_hours = json.loads(prefs['quiet_hours'])
        end = datetime.strptime(quiet_hours['end'], '%H:%M').time()

        next_time = datetime.combine(datetime.now().date(), end)
        if next_time < datetime.now():
            next_time += timedelta(days=1)

        return next_time

    async def _update_status(self, notification_id: int,
                           status: str, sent_at: datetime = None):
        """Обновление статуса уведомления"""
        query = """
        UPDATE notifications
        SET status = ?, sent_at = ?
        WHERE id = ?
        """
        await self.db.execute(
            query,
            (status, sent_at.isoformat() if sent_at else None, notification_id)
        )

class Module(ModuleInterface):
    async def setup(self, kernel):
        """Инициализация модуля"""
        self.kernel = kernel
        self.logger = logging.getLogger('system.notifications')

        # Создаём сервис уведомлений
        self.notifications = NotificationService(kernel)
        await self.notifications._create_tables()
        await self.notifications.load_templates()

        # Регистрируем сервис
        await kernel.get_service('registry').register_service(
            'notifications',
            self.notifications
        )

        # Регистрируем команды
        commands = [
            ('notifications', self.notifications_menu, 'Настройки уведомлений'),
        ]

        for cmd, handler, desc in commands:
            self.kernel._bot.add_handler(CommandHandler(cmd, handler))

        # Регистрируем обработчик callback
        self.kernel._bot.add_handler(
            CallbackQueryHandler(self.button_callback, pattern='^notif_')
        )

        self.logger.info("Notifications module initialized")

    async def cleanup(self):
        """Очистка ресурсов"""
        if hasattr(self.notifications, 'worker_task'):
            self.notifications.worker_task.cancel()
        self.logger.info("Notifications module cleaned up")

    async def notifications_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню настроек уведомлений"""
        user_id = update.effective_user.id

        # Получаем текущие настройки
        query = "SELECT * FROM user_preferences WHERE user_id = ?"
        prefs = await self.kernel.get_service('database').fetch_one(
            query,
            (user_id,)
        )

        enabled = "🔔" if not prefs or prefs['enabled'] else "🔕"

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{enabled} Уведомления",
                    callback_data="notif_toggle"
                )
            ],
            [
                InlineKeyboardButton(
                    "⚙️ Типы уведомлений",
                    callback_data="notif_types"
                )
            ],
            [
                InlineKeyboardButton(
                    "🌙 Тихий час",
                    callback_data="notif_quiet"
                )
            ]
        ]

        await update.message.reply_text(
            "🔔 *Настройки уведомлений*\\n\\n"
            "Управляйте своими уведомлениями:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()

        action = query.data.split('_')[1]
        user_id = query.from_user.id

        if action == "toggle":
            # Переключение уведомлений
            prefs = await self.kernel.get_service('database').fetch_one(
                "SELECT enabled FROM user_preferences WHERE user_id = ?",
                (user_id,)
            )

            enabled = not (prefs and prefs['enabled'])

            await self.kernel.get_service('database').execute(
                """
                INSERT INTO user_preferences (user_id, enabled)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET enabled = ?
                """,
                (user_id, enabled, enabled)
            )

            await self.notifications_menu(update, context)

        elif action == "types":
            # Настройка типов уведомлений
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📢 Системные",
                        callback_data="notif_type_system"
                    ),
                    InlineKeyboardButton(
                        "ℹ️ Информационные",
                        callback_data="notif_type_info"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⚡️ Важные",
                        callback_data="notif_type_important"
                    ),
                    InlineKeyboardButton(
                        "📝 Напоминания",
                        callback_data="notif_type_reminder"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "◀️ Назад",
                        callback_data="notif_back"
                    )
                ]
            ]

            await query.message.edit_text(
                "📝 *Типы уведомлений*\\n\\n"
                "Выберите типы уведомлений:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif action == "quiet":
            # Настройка тихого часа
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🌙 22:00 - 08:00",
                        callback_data="notif_quiet_night"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🕐 Свое время",
                        callback_data="notif_quiet_custom"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Отключить",
                        callback_data="notif_quiet_off"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "◀️ Назад",
                        callback_data="notif_back"
                    )
                ]
            ]

            await query.message.edit_text(
                "🌙 *Тихий час*\\n\\n"
                "Выберите время тихого часа:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        elif action == "back":
            await self.notifications_menu(update, context)

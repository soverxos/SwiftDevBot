# modules/system/stats/main.py
from core.module_api import ModuleInterface, ModuleMetadata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import logging
import yaml
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional
import asyncio
from collections import defaultdict
import matplotlib.pyplot as plt
import io
import pandas as pd

class StatsService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('stats')
        self.db = kernel.get_service('database')

        # Кэш для агрегированных данных
        self.cache = {}
        self.cache_ttl = 300  # 5 минут

        # Счетчики в памяти
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)

        # Запуск периодического сохранения
        asyncio.create_task(self._periodic_save())

    async def _create_tables(self):
        """Создание таблиц для статистики"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS stats_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                tags TEXT,
                period TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS stats_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                chat_id INTEGER,
                details TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
            ON stats_metrics(timestamp)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_metrics_metric
            ON stats_metrics(metric)
            """
        ]

        for query in queries:
            await self.db.execute(query)

    async def increment(self, metric: str, value: float = 1, tags: Dict = None):
        """Увеличение счетчика"""
        self.counters[metric] += value
        await self._save_metric(metric, value, tags, 'counter')

    async def gauge(self, metric: str, value: float, tags: Dict = None):
        """Установка значения метрики"""
        self.gauges[metric] = value
        await self._save_metric(metric, value, tags, 'gauge')

    async def event(self, event_type: str, user_id: int = None,
                   chat_id: int = None, details: Dict = None):
        """Регистрация события"""
        query = """
        INSERT INTO stats_events
        (event_type, user_id, chat_id, details)
        VALUES (?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            (event_type, user_id, chat_id, json.dumps(details) if details else None)
        )

    async def _save_metric(self, metric: str, value: float,
                          tags: Dict = None, period: str = None):
        """Сохранение метрики в БД"""
        query = """
        INSERT INTO stats_metrics (metric, value, tags, period)
        VALUES (?, ?, ?, ?)
        """
        await self.db.execute(
            query,
            (metric, value, json.dumps(tags) if tags else None, period)
        )

    async def _periodic_save(self):
        """Периодическое сохранение счетчиков"""
        while True:
            try:
                await asyncio.sleep(60)  # каждую минуту

                # Сохраняем счетчики
                for metric, value in self.counters.items():
                    await self._save_metric(
                        metric, value, None, 'minute'
                    )

                # Сохраняем gauge метрики
                for metric, value in self.gauges.items():
                    await self._save_metric(
                        metric, value, None, 'minute'
                    )

                # Очищаем счетчики
                self.counters.clear()

            except Exception as e:
                self.logger.error(f"Error in periodic save: {e}")

    async def get_metric_stats(self, metric: str,
                             period: str = 'day',
                             from_date: datetime = None,
                             to_date: datetime = None) -> List[Dict]:
        """Получение статистики по метрике"""
        if not from_date:
            from_date = datetime.now() - timedelta(days=1)
        if not to_date:
            to_date = datetime.now()

        cache_key = f"{metric}:{period}:{from_date}:{to_date}"

        # Проверяем кэш
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if datetime.now().timestamp() - cache_time < self.cache_ttl:
                return data

        query = """
        SELECT timestamp, SUM(value) as value
        FROM stats_metrics
        WHERE metric = ? AND timestamp BETWEEN ? AND ?
        GROUP BY strftime(?, timestamp)
        ORDER BY timestamp
        """

        # Формат группировки в зависимости от периода
        group_format = {
            'hour': '%Y-%m-%d %H',
            'day': '%Y-%m-%d',
            'week': '%Y-%W',
            'month': '%Y-%m'
        }.get(period, '%Y-%m-%d')

        results = await self.db.fetch_all(
            query,
            (metric, from_date.isoformat(), to_date.isoformat(), group_format)
        )

        # Кэшируем результат
        self.cache[cache_key] = (datetime.now().timestamp(), results)
        return results

    async def get_event_stats(self, event_type: str = None,
                            from_date: datetime = None,
                            to_date: datetime = None) -> List[Dict]:
        """Получение статистики по событиям"""
        conditions = []
        params = []

        query = "SELECT * FROM stats_events"

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if from_date:
            conditions.append("timestamp >= ?")
            params.append(from_date.isoformat())

        if to_date:
            conditions.append("timestamp <= ?")
            params.append(to_date.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC"

        return await self.db.fetch_all(query, tuple(params))

    async def generate_chart(self, metric: str, period: str = 'day') -> bytes:
        """Генерация графика для метрики"""
        data = await self.get_metric_stats(metric, period)

        if not data:
            return None

        # Создаем DataFrame
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Создаем график
        plt.figure(figsize=(10, 6))
        plt.plot(df['timestamp'], df['value'])
        plt.title(f'Statistics for {metric}')
        plt.xlabel('Time')
        plt.ylabel('Value')
        plt.grid(True)

        # Поворачиваем метки времени
        plt.xticks(rotation=45)

        # Сохраняем в буфер
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()

        return buf.getvalue()

class Module(ModuleInterface):
    async def setup(self, kernel):
        """Инициализация модуля"""
        self.kernel = kernel
        self.logger = logging.getLogger('system.stats')

        # Создаём сервис статистики
        self.stats = StatsService(kernel)
        await self.stats._create_tables()

        # Регистрируем сервис
        await kernel.get_service('registry').register_service(
            'stats',
            self.stats
        )

        # Регистрируем команды
        commands = [
            ('stats', self.stats_menu, 'Просмотр статистики'),
        ]

        for cmd, handler, desc in commands:
            self.kernel._bot.add_handler(CommandHandler(cmd, handler))

        # Регистрируем обработчик callback
        self.kernel._bot.add_handler(
            CallbackQueryHandler(self.button_callback, pattern='^stats_')
        )

        self.logger.info("Stats module initialized")

    async def cleanup(self):
        """Очистка ресурсов"""
        self.logger.info("Stats module cleaned up")

    async def stats_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню статистики"""
        if not await self.kernel.get_service('security').check_permission(
            update.effective_user.id, 'admin'
        ):
            await update.message.reply_text("⛔️ У вас нет прав для просмотра статистики")
            return

        keyboard = [
            [
                InlineKeyboardButton("📊 Пользователи", callback_data="stats_users"),
                InlineKeyboardButton("💬 Сообщения", callback_data="stats_messages")
            ],
            [
                InlineKeyboardButton("⚡️ Команды", callback_data="stats_commands"),
                InlineKeyboardButton("📈 Нагрузка", callback_data="stats_load")
            ],
            [
                InlineKeyboardButton("📋 Отчёт", callback_data="stats_report")
            ]
        ]

        await update.message.reply_text(
            "📊 *Статистика системы*\\n\\n"
            "Выберите тип статистики:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()

        if not await self.kernel.get_service('security').check_permission(
            query.from_user.id, 'admin'
        ):
            return

        action = query.data.split('_')[1]

        if action == "users":
            # Статистика пользователей
            data = await self.stats.get_metric_stats('users.active')
            chart = await self.stats.generate_chart('users.active')

            if chart:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=chart,
                    caption="📊 Активные пользователи за последние 24 часа"
                )
            else:
                await query.message.reply_text("📊 Данные отсутствуют")

        elif action == "messages":
            # Статистика сообщений
            data = await self.stats.get_metric_stats('messages.count')
            chart = await self.stats.generate_chart('messages.count')

            if chart:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=chart,
                    caption="💬 Количество сообщений за последние 24 часа"
                )
            else:
                await query.message.reply_text("📊 Данные отсутствуют")

        elif action == "commands":
            # Статистика команд
            events = await self.stats.get_event_stats('command')

            if events:
                commands = defaultdict(int)
                for event in events:
                    if details := json.loads(event['details'] or '{}'):
                        cmd = details.get('command')
                        if cmd:
                            commands[cmd] += 1

                text = "⚡️ *Популярные команды:*\\n\\n"
                for cmd, count in sorted(
                    commands.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]:
                    text += f"/{cmd}: {count} раз\\n"

                await query.message.reply_text(text, parse_mode='Markdown')
            else:
                await query.message.reply_text("📊 Данные отсутствуют")

        elif action == "load":
            # Статистика нагрузки
            data = await self.stats.get_metric_stats('system.cpu')
            chart = await self.stats.generate_chart('system.cpu')

            if chart:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=chart,
                    caption="📈 Загрузка CPU за последние 24 часа"
                )
            else:
                await query.message.reply_text("📊 Данные отсутствуют")

        elif action == "report":
            # Генерация отчета
            report = "📋 *Системный отчет*\\n\\n"

            # Пользователи
            users = await self.kernel.get_service('database').fetch_one(
                "SELECT COUNT(*) as count FROM users"
            )
            report += f"👥 Всего пользователей: {users['count']}\\n"

            # Сообщения за сутки
            messages = await self.stats.get_metric_stats('messages.count', period='day')
            total_messages = sum(m['value'] for m in messages)
            report += f"💬 Сообщений за 24ч: {total_messages}\\n"

            # Команды за сутки
            commands = await self.stats.get_event_stats(
                'command',
                from_date=datetime.now() - timedelta(days=1)
            )
            report += f"⚡️ Команд за 24ч: {len(commands)}\\n"

            # Ошибки за сутки
            errors = await self.kernel.get_service('logger').get_logs(
                level='ERROR',
                start_date=datetime.now() - timedelta(days=1)
            )
            report += f"❌ Ошибок за 24ч: {len(errors)}\\n"

            await query.message.reply_text(report, parse_mode='Markdown')

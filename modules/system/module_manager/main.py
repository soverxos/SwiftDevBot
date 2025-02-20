# modules/system/module_manager/main.py
from core.module_api import ModuleInterface
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
import yaml
from pathlib import Path
import logging

class Module(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('module_manager')

        # Регистрируем команду
        await kernel.get_service('registry').register_command(
            'system.module_manager',
            'modules',
            self.modules_command
        )

        # Регистрируем обработчик callback
        self.kernel._bot.add_handler(
            CallbackQueryHandler(self.button_callback, pattern='^module_')
        )

    async def cleanup(self):
        pass

    async def modules_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню управления модулями"""
        if not await self._check_admin(update.effective_user.id):
            await update.message.reply_text("У вас нет прав для управления модулями!")
            return

        keyboard = await self._get_modules_keyboard()
        await update.message.reply_text(
            "📱 Управление модулями\\n\\n"
            "Здесь вы можете включать и отключать модули бота.\\n"
            "⚠️ Внимание: Изменение состояния системных модулей может нарушить работу бота!",
            reply_markup=keyboard
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        await query.answer()

        if not await self._check_admin(query.from_user.id):
            return

        data = query.data.split('_')
        action = data[1]
        module_name = '_'.join(data[2:])

        if action == 'toggle':
            success = await self._toggle_module(module_name)
            if success:
                # Обновляем клавиатуру
                keyboard = await self._get_modules_keyboard()
                await query.message.edit_reply_markup(reply_markup=keyboard)

                status = "включен ✅" if await self._is_module_enabled(module_name) else "отключен ❌"
                await query.message.reply_text(f"Модуль {module_name} {status}")
            else:
                await query.message.reply_text("❌ Ошибка при изменении состояния модуля")

    async def _get_modules_keyboard(self) -> InlineKeyboardMarkup:
        """Создание клавиатуры с модулями"""
        keyboard = []
        modules_path = Path("modules")
        config = await self._load_config()

        # Получаем список всех модулей
        for module_dir in modules_path.glob("**/main.py"):
            module_name = str(module_dir.parent.relative_to(modules_path))
            if module_name.startswith('__'): continue

            # Проверяем, является ли модуль системным
            is_system = module_name.startswith('system')
            enabled = await self._is_module_enabled(module_name)

            status = "✅" if enabled else "❌"
            system_mark = "🔒" if is_system else ""

            keyboard.append([InlineKeyboardButton(
                f"{system_mark}{module_name} {status}",
                callback_data=f"module_toggle_{module_name}"
            )])

        return InlineKeyboardMarkup(keyboard)

    async def _toggle_module(self, module_name: str) -> bool:
        """Включение/отключение модуля"""
        try:
            config = await self._load_config()

            # Проверяем, является ли модуль системным
            if module_name.startswith('system'):
                required_modules = config['modules'].get('required', [])
                if module_name in required_modules:
                    return False

            disabled_modules = config['modules'].get('disabled', [])

            if module_name in disabled_modules:
                disabled_modules.remove(module_name)
            else:
                disabled_modules.append(module_name)

            config['modules']['disabled'] = disabled_modules

            # Сохраняем конфигурацию
            await self._save_config(config)

            # Перезагружаем модуль если он был включен
            if module_name not in disabled_modules:
                await self.kernel.reload_module(module_name)

            return True

        except Exception as e:
            self.logger.error(f"Error toggling module {module_name}: {e}")
            return False

    async def _is_module_enabled(self, module_name: str) -> bool:
        """Проверка, включен ли модуль"""
        config = await self._load_config()
        return module_name not in config['modules'].get('disabled', [])

    async def _check_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        config = await self._load_config()
        return user_id in config['bot']['admins']

    async def _load_config(self) -> dict:
        """Загрузка конфигурации"""
        with open("config.yml", 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    async def _save_config(self, config: dict):
        """Сохранение конфигурации"""
        with open("config.yml", 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)

from core.module_api import ModuleInterface, ModuleMetadata
from telegram.ext import CommandHandler
from telegram import Update
from telegram.ext import ContextTypes

class BaseModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.metadata = ModuleMetadata(
            name="system.base",
            version="1.0.0",
            description="Базовые команды бота"
        )
        return self

    async def cleanup(self):
        pass

    async def register_handlers(self, bot):
        bot.add_handler(CommandHandler("start", self.cmd_start))
        bot.add_handler(CommandHandler("help", self.cmd_help))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Привет! Я SwiftDevBot\n\n"
            "🔹 Используйте /help для списка команд"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 Доступные команды:\n\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать это сообщение"
        )
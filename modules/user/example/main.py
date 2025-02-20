from core.module_api import ModuleInterface, ModuleMetadata
from telegram.ext import CommandHandler

class ExampleModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.metadata = ModuleMetadata(
            name="example",
            version="1.0.0",
            description="Example module"
        )
        return self

    async def cleanup(self):
        pass

    async def register_handlers(self, bot):
        bot.add_handler(CommandHandler("example", self.example_command))

    async def example_command(self, update, context):
        await update.message.reply_text("This is an example command!")
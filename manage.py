#!/usr/bin/env python3
import click
import asyncio
import yaml
import sys
from pathlib import Path
from core.kernel import Kernel

@click.group()
def cli():
    """Утилита управления SwiftDevBot"""
    pass

@cli.command()
def run():
    """Запуск бота"""
    from bot import BotManager
    bot = BotManager()
    asyncio.run(bot.run())

@cli.command()
def createmodule():
    """Создать новый модуль"""
    name = click.prompt("Введите имя модуля")
    category = click.prompt("Категория модуля", type=click.Choice(['system', 'user']))
    
    module_path = Path(f"modules/{category}/{name}")
    module_path.mkdir(parents=True, exist_ok=True)

    # Создаем структуру модуля
    (module_path / "__init__.py").touch()
    
    # Конфигурация модуля
    config = {
        "enabled": True,
        "version": "1.0.0",
        "dependencies": []
    }
    
    with open(module_path / "config.yml", "w") as f:
        yaml.dump(config, f)

    # Шаблон main.py
    main_template = """
from core.module_api import ModuleInterface, ModuleMetadata

class {class_name}(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.metadata = ModuleMetadata(
            name="{module_name}",
            version="1.0.0",
            description="{description}"
        )
        return self

    async def cleanup(self):
        pass

    async def register_handlers(self, bot):
        pass
""".format(
        class_name=name.title() + "Module",
        module_name=name,
        description=f"{name.title()} module"
    )

    with open(module_path / "main.py", "w") as f:
        f.write(main_template)

    click.echo(f"Модуль {name} успешно создан в {module_path}")

@cli.command()
def list_modules():
    """Список всех модулей"""
    modules_path = Path("modules")
    for module in modules_path.glob("**/main.py"):
        module_name = module.parent.relative_to(modules_path)
        click.echo(f"- {module_name}")

@cli.command()
@click.argument('module_name')
def enable_module(module_name):
    """Включить модуль"""
    config_path = Path("config.yml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    if module_name in config['modules'].get('disabled', []):
        config['modules']['disabled'].remove(module_name)
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        click.echo(f"Module '{module_name}' enabled!")
    else:
        click.echo(f"Module '{module_name}' is already enabled!")

@cli.command()
@click.argument('module_name')
def disable_module(module_name):
    """Отключить модуль"""
    config_path = Path("config.yml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    if module_name not in config['modules'].get('disabled', []):
        if 'disabled' not in config['modules']:
            config['modules']['disabled'] = []
        config['modules']['disabled'].append(module_name)
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        click.echo(f"Module '{module_name}' disabled!")
    else:
        click.echo(f"Module '{module_name}' is already disabled!")

if __name__ == '__main__':
    cli()

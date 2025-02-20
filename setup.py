from setuptools import setup, find_packages

setup(
    name="swiftdevbot",
    version="1.0.0",
    description="Модульный Telegram бот для разработки на Python",
    author="SoverX",
    author_email="soverx.online@gmail.com",
    url="https://github.com/soverxos/SwiftDevBot",
    packages=find_packages(),
    install_requires=[
        # Основные зависимости
        "python-telegram-bot>=20.0",
        "aiosqlite>=0.19.0",
        "PyYAML>=6.0",
        "aiohttp>=3.9.1",
        "aiocron>=1.8",

        # Безопасность
        "PyJWT>=2.8.0",
        "cryptography>=41.0.0",
        "passlib>=1.7.4",

        # API и Web
        "fastapi>=0.104.1",
        "uvicorn>=0.24.0",
        "python-multipart>=0.0.6",
        "starlette>=0.27.0",
        "python-dotenv>=0.19.0",

        # База данных и ORM
        "asyncpg>=0.29.0",
        "aioredis>=2.0.1",
        "alembic>=1.13.0",
        "SQLAlchemy>=1.4.0",

        # Статистика и визуализация
        "matplotlib>=3.8.2",
        "pandas>=2.1.3",
        "seaborn>=0.13.0",
        "plotly>=5.18.0",

        # Шаблоны и форматирование
        "Jinja2>=3.1.2",

        # Утилиты
        "python-dateutil>=2.8.2",
        "pytz>=2023.3",
        "aiofiles>=23.2.1",
        "aiologger>=0.7.0",
        "asyncio-throttle>=1.0.2",
        "boto3>=1.28.44",
    ],
    extras_require={
        'dev': [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-cov>=4.1.0",
            "black>=23.11.0",
            "flake8>=6.1.0",
            "mypy>=1.7.1",
        ],
        'docs': [
            "Sphinx>=7.2.6",
            "sphinx-rtd-theme>=1.3.0",
        ],
    },
    entry_points={
        'console_scripts': [
            'swiftdevbot=main:main',
            'swiftdevbot-manage=manage:cli',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Framework :: AsyncIO",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Communications :: Chat",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.9",
    include_package_data=True,
    package_data={
        'swiftdevbot': [
            'modules/*/config.yml',
            'config.yml',
        ],
    },
    zip_safe=False,
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
)
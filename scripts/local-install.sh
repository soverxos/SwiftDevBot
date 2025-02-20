#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "❌ Использование: $0 path/to/swiftdevbot_X.Y.Z.tar.gz"
    exit 1
fi

ARCHIVE=$1
INSTALL_DIR="swiftdevbot"

echo "🚀 Локальная установка SwiftDevBot..."

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден!"
    exit 1
fi

# Создание директории
mkdir -p "${INSTALL_DIR}"
tar xzf "${ARCHIVE}" -C "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

# Создание виртуального окружения
echo "🐍 Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo "📚 Установка зависимостей..."
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# Проверка конфигурации
if [ ! -f config.yml ]; then
    cp config.example.yml config.yml
    echo "⚠️ Создан файл конфигурации config.yml"
fi

# Создание структуры
mkdir -p data/{db,backups,temp,cache}
mkdir -p logs

# Настройка прав
chmod +x scripts/*.sh
chmod 755 data logs
chmod 700 config.yml

echo "
✅ Локальная установка завершена!

📝 Следующие шаги:
1. Отредактируйте config.yml и добавьте токен бота
2. Активируйте виртуальное окружение:
   source venv/bin/activate
3. Запустите бота:
   python main.py

💡 Для установки как системный сервис используйте:
   sudo ./scripts/install-service.sh
"
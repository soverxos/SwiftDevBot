#!/bin/bash

# Определяем корневую директорию проекта
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

# Создаем директорию для релизов
RELEASES_DIR="releases"
mkdir -p "${RELEASES_DIR}"

echo "📦 Создание релиза SwiftDevBot..."

# Проверка версии из setup.py
if [ -f "setup.py" ]; then
    VERSION=$(python3 -c "exec(open('setup.py').read()); print(setup_args['version'])" 2>/dev/null || echo "1.0.0")
    if [ -z "$VERSION" ]; then
        echo "⚠️ Ошибка чтения версии, используем версию по умолчанию"
        VERSION="1.0.0"
    fi
else
    echo "⚠️ Файл setup.py не найден, используем версию по умолчанию"
    VERSION="1.0.0"
fi

ARCHIVE_NAME="${RELEASES_DIR}/swiftdevbot_${VERSION}.tar.gz"
echo "📝 Версия: ${VERSION}"

# Очистка временных файлов
echo "🧹 Очистка временных файлов..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.py[cod]" -delete
find . -type f -name "*~" -delete
find . -type f -name ".DS_Store" -delete

# Создание временной директории
TEMP_DIR=$(mktemp -d)
echo "📁 Подготовка файлов..."

# Список файлов для включения в релиз
FILES_TO_INCLUDE=(
    "core"
    "modules"
    "scripts"
    "config"
    "config.example.yml"
    "main.py"
    "setup.py"
    "requirements.txt"
    "README.md"
    "alembic.ini"
    "alembic"
    "manage.py"
)

# Копирование только нужных файлов
for item in "${FILES_TO_INCLUDE[@]}"; do
    if [ -e "$item" ]; then
        echo "  📄 Копирование: ${item}"
        cp -r "$item" "${TEMP_DIR}/"
    else
        echo "  ⚠️ Пропущен: ${item} (не найден)"
    fi
done

# Создание структуры каталогов
echo "📁 Создание структуры каталогов..."
mkdir -p "${TEMP_DIR}"/{data/{db,backups,temp,cache},logs}
touch "${TEMP_DIR}"/data/{db,backups,temp,cache}/.gitkeep
touch "${TEMP_DIR}/logs/.gitkeep"

# Создание архива
echo "📚 Создание архива..."
cd "${TEMP_DIR}"
tar czf "${PROJECT_ROOT}/${ARCHIVE_NAME}" ./*
cd - > /dev/null

# Очистка
rm -rf "${TEMP_DIR}"

if [ -f "${ARCHIVE_NAME}" ]; then
    echo "✅ Релиз успешно создан:"
    echo "📂 Расположение: $(realpath ${ARCHIVE_NAME})"
    echo "📦 Размер: $(du -h ${ARCHIVE_NAME} | cut -f1)"
else
    echo "❌ Ошибка при создании релиза!"
    exit 1
fi
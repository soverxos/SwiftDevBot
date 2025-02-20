#!/bin/bash

# Проверка что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Запустите скрипт от root (sudo ./install.sh)"
    exit 1
fi

echo "🚀 Начинаем установку SwiftDevBot..."

# Создание системного пользователя swiftdevbot без домашней директории и без возможности входа в систему
echo "👤 Создание системного пользователя..."
useradd -r -s /bin/false swiftdevbot

# Определение директории установки
INSTALL_DIR="/opt/swiftdevbot"
echo "📁 Установка в директорию: ${INSTALL_DIR}"

# Создание директории установки
mkdir -p "$INSTALL_DIR"

# Копирование всех файлов бота в директорию установки
echo "📋 Копирование файлов..."
cp -r ../* "$INSTALL_DIR/"

# Создание структуры директорий для данных
echo "📁 Создание структуры директорий..."
mkdir -p "${INSTALL_DIR}/data"/{db,backups,temp,cache}
mkdir -p "${INSTALL_DIR}/logs"

# Создание .gitkeep файлов чтобы git сохранял пустые директории
touch "${INSTALL_DIR}/data/"{db,backups,temp,cache}/.gitkeep
touch "${INSTALL_DIR}/logs/.gitkeep"

# Настройка прав доступа
echo "🔒 Настройка прав доступа..."
chown -R swiftdevbot:swiftdevbot "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 700 "${INSTALL_DIR}/config.yml"  # Особые права для конфига с токеном

# Создание виртуального окружения
echo "🐍 Создание виртуального окружения Python..."
python3 -m venv "${INSTALL_DIR}/venv"
source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip wheel setuptools
pip install -r "${INSTALL_DIR}/requirements.txt"

# Создание и настройка systemd сервиса
echo "⚙️ Настройка systemd сервиса..."
cat > /etc/systemd/system/swiftdevbot.service << EOF
[Unit]
Description=SwiftDevBot Telegram Bot
After=network.target

[Service]
Type=simple
User=swiftdevbot
Group=swiftdevbot
WorkingDirectory=/opt/swiftdevbot
Environment=PATH=/opt/swiftdevbot/venv/bin:$PATH
ExecStart=/opt/swiftdevbot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка конфигурации systemd
echo "🔄 Перезагрузка конфигурации systemd..."
systemctl daemon-reload

# Включение и запуск сервиса
echo "▶️ Включение и запуск сервиса..."
systemctl enable swiftdevbot
systemctl start swiftdevbot

# Проверка статуса
echo "📊 Проверка статуса..."
systemctl status swiftdevbot

echo "
✅ Установка SwiftDevBot завершена!

📝 Следующие шаги:
1. Отредактируйте конфигурацию:
   sudo nano ${INSTALL_DIR}/config.yml

2. Перезапустите бота:
   sudo systemctl restart swiftdevbot

3. Проверьте статус:
   sudo systemctl status swiftdevbot

4. Просмотр логов:
   sudo journalctl -u swiftdevbot -f

🔧 Основные команды управления:
- Запуск:    sudo systemctl start swiftdevbot
- Остановка: sudo systemctl stop swiftdevbot
- Статус:    sudo systemctl status swiftdevbot
- Логи:      sudo journalctl -u swiftdevbot
"
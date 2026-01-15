# Деплой на VPS

## Быстрый старт (копируй и вставляй)

### 1. Подключись к VPS
```bash
ssh root@198.12.73.168
# Пароль: S5M50Xb9Os2a8GvgUs
```

### 2. Установи зависимости
```bash
apt update && apt install -y python3.11 python3.11-venv python3-pip git
```

### 3. Клонируй репозиторий
```bash
cd /root
git clone https://github.com/Fedor-K/calorie-tracker-bot.git
cd calorie-tracker-bot
```

### 4. Создай виртуальное окружение
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Создай .env файл
```bash
nano .env
```
Вставь содержимое из локального .env файла.

### 6. Проверь запуск
```bash
python bot.py
```
Если работает - переходи к systemd.

### 7. Создай systemd сервис
```bash
cat > /etc/systemd/system/calorie-bot.service << 'EOF'
[Unit]
Description=Calorie Tracker Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/calorie-tracker-bot
Environment=PATH=/root/calorie-tracker-bot/venv/bin
ExecStart=/root/calorie-tracker-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 8. Запусти бота
```bash
systemctl daemon-reload
systemctl enable calorie-bot
systemctl start calorie-bot
```

### 9. Проверь статус
```bash
systemctl status calorie-bot
journalctl -u calorie-bot -f
```

## Полезные команды

```bash
# Перезапустить бота
systemctl restart calorie-bot

# Остановить
systemctl stop calorie-bot

# Логи в реальном времени
journalctl -u calorie-bot -f

# Обновить код
cd /root/calorie-tracker-bot
git pull
systemctl restart calorie-bot
```

## Если что-то не работает

1. Проверь логи: `journalctl -u calorie-bot -n 50`
2. Проверь .env файл: `cat .env`
3. Попробуй запустить вручную: `python bot.py`

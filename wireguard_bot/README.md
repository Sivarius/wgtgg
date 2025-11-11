# Простой Telegram-бот для управления WireGuard

Бот на базе aiogram для администрирования пиров WireGuard: добавление, отключение, продление, выдача клиентских конфигов и автообслуживание через планировщик.

Возможности
- Команды Telegram для администрирования: /add, /list, /remove, /edit, /info, /reload
- Генерация клиентских конфигов из шаблона config/template.conf
- Хранение состояния в JSON (config/*.json)
- Ежедневные задачи: уведомления об истечении и автоотключение истёкших
- Интеграция с wg (Linux/Debian): применение/удаление пиров через wg set

Требования
- Debian/Ubuntu (Linux) с установленным WireGuard
- Python 3.8+

Установка (Debian) — через скрипт
1) Склонируйте репозиторий и запустите инсталлятор:
```bash
cd /path/to/wireguard_bot
bash deploy/install.sh
```
Скрипт:
- установит python3-venv, python3-pip, wireguard
- создаст виртуальное окружение и установит зависимости
- создаст /etc/wireguard-bot.env (если его нет) — отредактируйте его, чтобы указать токен и параметры WG
- сконфигурирует WireGuard сервер (wg0): создаст /etc/wireguard/wg0.conf, включит форвардинг и NAT, поднимет wg-quick@wg0
- сгенерирует systemd unit /etc/systemd/system/wireguard-bot.service с WorkingDirectory на текущий каталог
- инициализирует недостающие файлы в config/

2) Отредактируйте /etc/wireguard-bot.env:
- BOT_TOKEN — Telegram токен бота
- WG_INTERFACE — интерфейс WG (по умолчанию wg0)
- WG_SERVER_PUBLIC_KEY — публичный ключ сервера WG (если пусто — будет вычислен из server_private.key)
- WG_SERVER_ENDPOINT — endpoint сервера (host:port)
- WG_DNS — DNS в клиентском шаблоне (опционально)
- WG_SERVER_ADDRESS — адрес WG-сети на сервере (например 10.8.0.1/24)
- WG_LISTEN_PORT — порт WireGuard (по умолчанию 51820)
- WG_NAT_INTERFACE — внешний интерфейс для NAT (если пусто — определяется автоматически)

3) При необходимости отредактируйте config/template.conf (если не задано в env — в шаблон будут подставлены заглушки).

4) Включите интерфейс WG на сервере (если ещё не включён):
```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
```

5) Запустите сервис бота:
```bash
sudo systemctl daemon-reload
sudo systemctl enable wireguard-bot
sudo systemctl start wireguard-bot
sudo systemctl status wireguard-bot --no-pager
```

Ручной запуск (для проверки без systemd)
```bash
export BOT_TOKEN="<ваш токен>"
python3 bot.py
```

Команды бота
- /add name, dd.mm.yyyy — добавить пользователя, сгенерировать конфиг, присвоить новый IP
- /list — список активных пользователей
- /remove idN — отключить пользователя и перенести в архив
- /edit idN dd.mm.yyyy — изменить срок, при необходимости восстановить из архива
- /info idN — подробная информация о пользователе
- /reload — применить актуальные пиры и перенести просроченных в архив

Хранилище и файлы
- config/admins.json — список Telegram user_id админов
- config/peers.json — активные пользователи (словарь idN -> объект)
- config/archive.json — архив (словарь idN -> объект)
- config/last_ip.json — последний выданный IP
- config/template.conf — шаблон клиентского конфига (используются плейсхолдеры %AD%, %PrK%, %PhK%)
- wg/clients/*.conf — сгенерированные клиентские конфиги

Примечания
- Операции wg выполняются только на Linux; на Debian всё работает полноценно.
- По умолчанию используется интерфейс wg0. При другом интерфейсе измените WG_INTERFACE в /etc/wireguard-bot.env.
- Шаблон template.conf должен содержать реальные PublicKey/Endpoint сервера.

Быстрый старт (TL;DR)
```bash
bash deploy/install.sh
sudo nano /etc/wireguard-bot.env   # укажите BOT_TOKEN и WG_SERVER_ENDPOINT (при необходимости WG_NAT_INTERFACE)
sudo systemctl restart wg-quick@wg0
sudo systemctl restart wireguard-bot
```

Управление сервисом
```bash
# бот
sudo systemctl status wireguard-bot --no-pager
sudo systemctl restart wireguard-bot
sudo journalctl -u wireguard-bot -n 200 --no-pager

# wireguard интерфейс
sudo systemctl status wg-quick@wg0 --no-pager
sudo systemctl restart wg-quick@wg0
```

Добавление админов
- Впишите Telegram user_id в config/admins.json, поле admins: []
- Узнать свой user_id можно, например, через @userinfobot

Траблшутинг
- Нет интернета у клиентов: проверьте WG_NAT_INTERFACE и PostUp/PostDown в /etc/wireguard/wg0.conf
- Порт недоступен снаружи: откройте порт WG_LISTEN_PORT (UDP) на фаерволе/в провайдере
- Бот не стартует: проверьте BOT_TOKEN в /etc/wireguard-bot.env, логи через journalctl
- Пиры не применяются: убедитесь, что интерфейс wg0 поднят и переменная WG_INTERFACE совпадает

Безопасность
- /etc/wireguard-bot.env создаётся с правами 600; храните там только необходимые секреты
- Резервно сохраните /etc/wireguard/server_private.key; потеря файла приведёт к смене ключей сервера

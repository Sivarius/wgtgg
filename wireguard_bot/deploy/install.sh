# WireGuard Bot — установочный скрипт (Debian)
#
# Запуск:
#   bash deploy/install.sh
#
# Действия:
# - Устанавливает пакеты: python3-venv, python3-pip, wireguard
# - Создаёт venv и ставит зависимости
# - Создаёт /etc/wireguard-bot.env из примера (если нет)
# - Порождает systemd unit /etc/systemd/system/wireguard-bot.service
# - Инициализирует недостающие файлы в config/

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "[!] Требуются права root. Перезапуск через sudo..."
  exec sudo -E bash "$0" "$@"
fi

HERE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${HERE_DIR}/.." && pwd)"
PY_BIN="${REPO_DIR}/.venv/bin/python"
# Поиск requirements.txt: сперва внутри проекта, затем в родителе
REQS_FILE_PRIMARY="${REPO_DIR}/requirements.txt"
REQS_FILE_ALT="$(cd "${REPO_DIR}/.." && pwd)/requirements.txt"
if [[ -f "${REQS_FILE_PRIMARY}" ]]; then
  REQS_FILE="${REQS_FILE_PRIMARY}"
elif [[ -f "${REQS_FILE_ALT}" ]]; then
  REQS_FILE="${REQS_FILE_ALT}"
else
  REQS_FILE=""
fi
ENV_FILE="/etc/wireguard-bot.env"
UNIT_FILE="/etc/systemd/system/wireguard-bot.service"

echo "[*] Установка системных пакетов..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip wireguard

echo "[*] Создание виртуального окружения и установка зависимостей..."
python3 -m venv "${REPO_DIR}/.venv"
"${REPO_DIR}/.venv/bin/pip" install --upgrade pip
if [[ -n "${REQS_FILE}" && -f "${REQS_FILE}" ]]; then
  echo "[*] Установка зависимостей из ${REQS_FILE}"
  "${REPO_DIR}/.venv/bin/pip" install -r "${REQS_FILE}"
else
  echo "[!] requirements.txt не найден ни в ${REPO_DIR}, ни в родителе; установка aiogram и APScheduler по умолчанию"
  "${REPO_DIR}/.venv/bin/pip" install aiogram \
    'APScheduler>=3,<4'
fi

mkdir -p "${REPO_DIR}/config" "${REPO_DIR}/logs" "${REPO_DIR}/wg/clients"

# Инициализация JSON-файлов
[[ -f "${REPO_DIR}/config/peers.json" ]] || echo '{}' > "${REPO_DIR}/config/peers.json"
[[ -f "${REPO_DIR}/config/archive.json" ]] || echo '{}' > "${REPO_DIR}/config/archive.json"
[[ -f "${REPO_DIR}/config/admins.json" ]] || echo '{"admins": []}' > "${REPO_DIR}/config/admins.json"

# ENV-файл
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[*] Создание ${ENV_FILE} из примера"
  install -m 600 /dev/null "${ENV_FILE}"
cat >"${ENV_FILE}" <<'EOF'
# Обязательные настройки
BOT_TOKEN=

# Настройки WireGuard (клиентский шаблон)
WG_INTERFACE=wg0
WG_SERVER_PUBLIC_KEY=
WG_SERVER_ENDPOINT=example.com:51820
WG_DNS=8.8.8.8

# Настройки сервера WireGuard (wg0)
WG_SERVER_ADDRESS=10.8.0.1/24
WG_LISTEN_PORT=51820
# Сетевой интерфейс, через который интернет уходит в мир (для NAT)
# Если не указать — будет определён автоматически по default route
WG_NAT_INTERFACE=
EOF
  echo "[!] Отредактируйте ${ENV_FILE} (минимум BOT_TOKEN, WG_SERVER_PUBLIC_KEY, WG_SERVER_ENDPOINT)"
fi

# Подгрузим переменные окружения, если заданы
set +u
. "${ENV_FILE}" 2>/dev/null || true
set -u

# Автоконфигурация WireGuard (wg0)
mkdir -p /etc/wireguard
umask 077
# Определение интерфейса для NAT по маршруту по умолчанию
DEFAULT_IF=$(ip route | awk '/default/ {print $5; exit}')
: "${WG_NAT_INTERFACE:=${DEFAULT_IF:-eth0}}"
: "${WG_SERVER_ADDRESS:=10.8.0.1/24}"
: "${WG_LISTEN_PORT:=51820}"

# Генерация серверного ключа, если отсутствует
if [[ ! -f /etc/wireguard/server_private.key ]]; then
  echo "[*] Генерация ключа сервера WireGuard"
  wg genkey | tee /etc/wireguard/server_private.key > /etc/wireguard/server_public.key
  chmod 600 /etc/wireguard/server_private.key
fi
SERVER_PUB_COMPUTED=$(wg pubkey < /etc/wireguard/server_private.key 2>/dev/null || true)

# Включение IPv4 forwarding
SYSCTL_FILE=/etc/sysctl.d/99-wireguard-forwarding.conf
cat >"${SYSCTL_FILE}" <<EOF
net.ipv4.ip_forward=1
EOF
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
sysctl -p "${SYSCTL_FILE}" >/dev/null 2>&1 || true

# Создание wg0.conf при отсутствии
WG_CONF=/etc/wireguard/wg0.conf
if [[ ! -f "${WG_CONF}" ]]; then
  echo "[*] Создание ${WG_CONF}"
  cat >"${WG_CONF}" <<EOF
[Interface]
Address = ${WG_SERVER_ADDRESS}
ListenPort = ${WG_LISTEN_PORT}
PrivateKey = $(cat /etc/wireguard/server_private.key)
SaveConfig = true
PostUp = iptables -t nat -A POSTROUTING -o ${WG_NAT_INTERFACE} -j MASQUERADE; iptables -A FORWARD -i ${WG_NAT_INTERFACE} -o %i -m state --state RELATED,ESTABLISHED -j ACCEPT; iptables -A FORWARD -i %i -o ${WG_NAT_INTERFACE} -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o ${WG_NAT_INTERFACE} -j MASQUERADE; iptables -D FORWARD -i ${WG_NAT_INTERFACE} -o %i -m state --state RELATED,ESTABLISHED -j ACCEPT; iptables -D FORWARD -i %i -o ${WG_NAT_INTERFACE} -j ACCEPT
EOF
  chmod 600 "${WG_CONF}"
fi

# Включение и запуск wg-quick для интерфейса
systemctl enable "wg-quick@${WG_INTERFACE:-wg0}" || true
systemctl restart "wg-quick@${WG_INTERFACE:-wg0}" || true

# Шаблон клиента
if [[ ! -f "${REPO_DIR}/config/template.conf" ]]; then
  echo "[*] Генерация config/template.conf из переменных окружения"
  : "${WG_DNS:=8.8.8.8}"
  # если публичный ключ сервера не задан, используем вычисленный
  : "${WG_SERVER_PUBLIC_KEY:=${SERVER_PUB_COMPUTED:-CHANGE_ME_PUBLIC_KEY}}"
  : "${WG_SERVER_ENDPOINT:=endpoint:51820}"
  cat >"${REPO_DIR}/config/template.conf" <<EOF
[Interface]
Address = %AD%
PrivateKey = %PrK%
DNS = ${WG_DNS}

[Peer]
PublicKey = ${WG_SERVER_PUBLIC_KEY}
PresharedKey = %PhK%
AllowedIPs = 0.0.0.0/0
Endpoint = ${WG_SERVER_ENDPOINT}
PersistentKeepalive = 25
EOF
fi

# Unit-файл
echo "[*] Установка systemd unit в ${UNIT_FILE}"
cat >"${UNIT_FILE}" <<EOF
[Unit]
Description=WireGuard Telegram Bot
After=network-online.target wg-quick@${WG_INTERFACE:-wg0}.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${PY_BIN} bot.py
User=root
Group=root
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wireguard-bot

if [[ -n "${BOT_TOKEN:-}" ]]; then
  echo "[*] Запуск сервиса wireguard-bот"
  systemctl restart wireguard-bot || true
  systemctl status wireguard-bot --no-pager || true
else
  echo "[!] BOT_TOKEN не задан в ${ENV_FILE}. Установите значение и выполните:"
  echo "    sudo systemctl restart wireguard-bot"
fi

echo "[✓] Готово. WireGuard (wg0) сконфигурирован, бот установлен. Проверьте ${ENV_FILE} и config/template.conf при необходимости."

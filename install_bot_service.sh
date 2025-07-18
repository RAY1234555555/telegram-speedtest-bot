#!/bin/bash
# Installs and configures the Telegram Speedtest Bot service on Debian.

# --- Configuration ---
GITHUB_REPO_URL="https://github.com/RAY1234555555/telegram-speedtest-bot.git"
BOT_INSTALL_DIR="/opt/telegram-speedtest-bot"
BOT_SERVICE_NAME="telegram-speedtest-bot.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${BOT_SERVICE_NAME}"
SECRETS_FILE="${BOT_INSTALL_DIR}/secrets.enc"
DECRYPT_SCRIPT="${BOT_INSTALL_DIR}/decrypt_secrets.sh"
RUNNER_SCRIPT="${BOT_INSTALL_DIR}/secure_runner.sh"
BOT_MAIN_SCRIPT="${BOT_INSTALL_DIR}/bot.py"
BOT_VENV_PATH="${BOT_INSTALL_DIR}/venv/bin/activate"

# --- Helper Functions ---
log_info() { echo "[INFO] $1"; }
log_error() { echo "[ERROR] $1" >&2; }
log_warning() { echo "[WARNING] $1" >&2; }
log_success() { echo -e "\033[32m[SUCCESS] $1\033[0m"; }

sudo_if_needed() {
    if [ "$(id -u)" -ne 0 ]; then
        sudo "$@"
    else
        "$@"
    fi
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

safe_read() {
    local prompt="$1"
    local var_name="$2"
    local encrypted_input="$3"
    local input_str=""
    if [ "$encrypted_input" = true ]; then
        read -sp "$prompt: " input_str
    else
        read -p "$prompt: " input_str
    fi
    eval "$var_name='$input_str'"
    echo
}

# --- Pre-checks ---
log_info "🔍 检查系统环境..."
for cmd in git python3 pip3 openssl systemctl curl; do
    if ! command_exists $cmd; then
        log_error "'$cmd' 未安装。请先安装: sudo apt update && sudo apt install $cmd"
        exit 1
    fi
done
log_success "系统环境检查通过"

# --- Gather Information ---
log_info "📝 收集配置信息..."
safe_read "请输入 Telegram Bot Token (从 @BotFather 获取)" BOT_TOKEN false
safe_read "请输入授权用户ID (多个用逗号分隔，如: 123456789,987654321)" ALLOWED_USER_IDS false
safe_read "请输入主密码 (用于加密存储敏感信息)" MASTER_PASSWORD true

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "所有信息都是必填的，安装中止"
    exit 1
fi

# --- Setup Directories ---
log_info "📁 创建目录结构..."
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR"
cd "$BOT_INSTALL_DIR" || exit 1

# --- Clone/Update Repository ---
if [ -d ".git" ]; then
    log_info "🔄 更新现有代码库..."
    git pull origin main || log_warning "代码更新失败，继续使用现有代码"
else
    log_info "📥 克隆代码库..."
    git clone "$GITHUB_REPO_URL" . || {
        log_error "代码库克隆失败"
        exit 1
    }
fi

# --- Setup Python Environment ---
log_info "🐍 设置 Python 环境..."
python3 -m venv venv || {
    log_error "虚拟环境创建失败"
    exit 1
}

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || {
    log_error "Python 依赖安装失败"
    deactivate
    exit 1
}
deactivate
log_success "Python 环境设置完成"

# --- Encrypt Secrets ---
log_info "🔐 加密敏感信息..."
cat > temp_secrets_data.txt << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
ALLOWED_USER_IDS=$ALLOWED_USER_IDS
EOF

echo "$MASTER_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -in temp_secrets_data.txt -out "$SECRETS_FILE" -pass stdin || {
    log_error "信息加密失败"
    rm -f temp_secrets_data.txt
    exit 1
}

sudo_if_needed chmod 600 "$SECRETS_FILE"
rm -f temp_secrets_data.txt
log_success "敏感信息加密完成"

# --- Create Scripts ---
log_info "📜 生成运行脚本..."

# Decrypt script
cat > "$DECRYPT_SCRIPT" << 'EOF'
#!/bin/bash
MASTER_PASSWORD="$1"
SECRET_FILE="/opt/telegram-speedtest-bot/secrets.enc"

if [[ -z "$MASTER_PASSWORD" || ! -f "$SECRET_FILE" ]]; then
    echo "Error: Missing password or secrets file" >&2
    exit 1
fi

DECRYPTED_DATA=$(echo "$MASTER_PASSWORD" | openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -salt -pass stdin -in "$SECRET_FILE" 2>/dev/null)

if [[ $? -ne 0 || -z "$DECRYPTED_DATA" ]]; then
    echo "Error: Decryption failed" >&2
    exit 1
fi

echo "$DECRYPTED_DATA"
EOF

chmod 700 "$DECRYPT_SCRIPT"

# Runner script
cat > "$RUNNER_SCRIPT" << EOF
#!/bin/bash
MASTER_PASSWORD="$MASTER_PASSWORD"
SECRETS_FILE="$SECRETS_FILE"
DECRYPT_SCRIPT="$DECRYPT_SCRIPT"
BOT_VENV_PATH="$BOT_VENV_PATH"
BOT_MAIN_SCRIPT="$BOT_MAIN_SCRIPT"
BOT_INSTALL_DIR="$BOT_INSTALL_DIR"
TELEGRAM_API_URL="https://tg.993474.xyz"

if [[ ! -f "\$SECRETS_FILE" || ! -f "\$DECRYPT_SCRIPT" ]]; then
    echo "Error: Required files not found" >&2
    exit 1
fi

DECRYPTED_DATA=\$(bash "\$DECRYPT_SCRIPT" "\$MASTER_PASSWORD" 2>/dev/null)
if [[ \$? -ne 0 || -z "\$DECRYPTED_DATA" ]]; then
    echo "Error: Failed to decrypt secrets" >&2
    exit 1
fi

BOT_TOKEN=\$(echo "\$DECRYPTED_DATA" | grep "^TELEGRAM_BOT_TOKEN=" | cut -d'=' -f2-)
USER_IDS=\$(echo "\$DECRYPTED_DATA" | grep "^ALLOWED_USER_IDS=" | cut -d'=' -f2-)

if [[ -z "\$BOT_TOKEN" || -z "\$USER_IDS" ]]; then
    echo "Error: Could not parse credentials" >&2
    exit 1
fi

echo "🚀 启动 Telegram 测速机器人..."
export TELEGRAM_BOT_TOKEN="\$BOT_TOKEN"
export ALLOWED_USER_IDS="\$USER_IDS"
export TELEGRAM_API_URL="\$TELEGRAM_API_URL"

cd "\$BOT_INSTALL_DIR" && source "\$BOT_VENV_PATH" && python "\$BOT_MAIN_SCRIPT"
EOF

chmod 700 "$RUNNER_SCRIPT"

# --- Create Systemd Service ---
log_info "⚙️ 配置系统服务..."
cat > "$SYSTEMD_SERVICE_PATH" << EOF
[Unit]
Description=Telegram Speed Test Bot v2.0
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$BOT_INSTALL_DIR
ExecStart=$RUNNER_SCRIPT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo_if_needed chmod 644 "$SYSTEMD_SERVICE_PATH"

# --- Start Service ---
log_info "🔄 启动服务..."
sudo_if_needed systemctl daemon-reload
sudo_if_needed systemctl enable "$BOT_SERVICE_NAME"
sudo_if_needed systemctl start "$BOT_SERVICE_NAME"

# --- Wait and Check Status ---
sleep 3
if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_success "✅ 机器人服务启动成功！"
else
    log_error "❌ 服务启动失败"
    sudo journalctl -u "$BOT_SERVICE_NAME" --no-pager -n 10
    exit 1
fi

# --- Final Instructions ---
echo ""
echo "🎉 =================================="
echo "   Telegram 测速机器人安装完成！"
echo "=================================="
echo ""
echo "📊 服务状态: $(sudo systemctl is-active $BOT_SERVICE_NAME)"
echo "🤖 机器人已自动发送测试消息给授权用户"
echo ""
echo "🔧 管理命令:"
echo "   查看日志: sudo journalctl -u $BOT_SERVICE_NAME -f"
echo "   重启服务: sudo systemctl restart $BOT_SERVICE_NAME"
echo "   停止服务: sudo systemctl stop $BOT_SERVICE_NAME"
echo "   更新代码: cd $BOT_INSTALL_DIR && git pull && sudo systemctl restart $BOT_SERVICE_NAME"
echo ""
echo "🚀 现在可以向机器人发送节点链接进行测速了！"
echo ""

# --- Send Test Message ---
log_info "📤 机器人将自动发送测试消息..."

exit 0

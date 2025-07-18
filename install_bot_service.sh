#!/bin/bash
# Fixed installation script with better network handling for China servers

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
log_info() { echo -e "\033[34m[INFO]\033[0m $1"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $1" >&2; }
log_warning() { echo -e "\033[33m[WARNING]\033[0m $1" >&2; }
log_success() { echo -e "\033[32m[SUCCESS]\033[0m $1"; }

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

test_telegram_api() {
    local bot_token="$1"
    local api_url="$2"
    
    log_info "🔍 测试 Telegram API 连接..."
    
    # Test with proxy
    local test_url="${api_url}/bot${bot_token}/getMe"
    local response=$(curl -s -w "%{http_code}" -o /tmp/tg_test_response.json --connect-timeout 10 --max-time 30 "$test_url")
    local http_code="${response: -3}"
    
    if [ "$http_code" = "200" ]; then
        log_success "✅ Telegram API 连接成功"
        local bot_info=$(cat /tmp/tg_test_response.json | grep -o '"first_name":"[^"]*"' | cut -d'"' -f4)
        log_info "🤖 机器人名称: $bot_info"
        rm -f /tmp/tg_test_response.json
        return 0
    else
        log_error "❌ Telegram API 连接失败 (HTTP: $http_code)"
        if [ -f /tmp/tg_test_response.json ]; then
            log_error "响应内容: $(cat /tmp/tg_test_response.json)"
            rm -f /tmp/tg_test_response.json
        fi
        return 1
    fi
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

# --- Stop existing service ---
if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_info "🛑 停止现有服务..."
    sudo_if_needed systemctl stop "$BOT_SERVICE_NAME"
fi

# --- Gather Information ---
log_info "📝 收集配置信息..."
safe_read "请输入 Telegram Bot Token (从 @BotFather 获取)" BOT_TOKEN false
safe_read "请输入授权用户ID (多个用逗号分隔，如: 123456789,987654321)" ALLOWED_USER_IDS false
safe_read "请输入 Telegram API 反代地址 (默认: https://tg.993474.xyz)" TELEGRAM_API_URL false
safe_read "请输入主密码 (用于加密存储敏感信息)" MASTER_PASSWORD true

# Set default API URL if empty
if [[ -z "$TELEGRAM_API_URL" ]]; then
    TELEGRAM_API_URL="https://tg.993474.xyz"
fi

# Remove trailing slash and /bot if present
TELEGRAM_API_URL=$(echo "$TELEGRAM_API_URL" | sed 's|/$||' | sed 's|/bot$||')

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "所有信息都是必填的，安装中止"
    exit 1
fi

# --- Test Telegram API Connection ---
if ! test_telegram_api "$BOT_TOKEN" "$TELEGRAM_API_URL"; then
    log_error "Telegram API 连接测试失败，请检查："
    log_error "1. Bot Token 是否正确"
    log_error "2. 反代地址是否可用: $TELEGRAM_API_URL"
    log_error "3. 服务器网络连接是否正常"
    exit 1
fi

# --- Setup Directories ---
log_info "📁 创建目录结构..."
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR"
cd "$BOT_INSTALL_DIR" || exit 1

# --- Force update repository ---
log_info "📥 更新代码库..."
if [ -d ".git" ]; then
    # Backup important files
    [ -f "secrets.enc" ] && cp secrets.enc /tmp/secrets.enc.backup
    [ -f "secure_runner.sh" ] && cp secure_runner.sh /tmp/secure_runner.sh.backup
    
    # Force reset and pull
    git stash push -m "Auto-stash before update"
    git reset --hard origin/main
    git pull origin main || {
        log_warning "Git pull 失败，尝试重新克隆..."
        cd ..
        sudo_if_needed rm -rf "$BOT_INSTALL_DIR"
        git clone "$GITHUB_REPO_URL" "$BOT_INSTALL_DIR"
        cd "$BOT_INSTALL_DIR" || exit 1
        sudo_if_needed chown -R "${CURRENT_USER}:${CURRENT_GROUP}" .
    }
else
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

# Runner script with better error handling
cat > "$RUNNER_SCRIPT" << EOF
#!/bin/bash
set -e

MASTER_PASSWORD="$MASTER_PASSWORD"
SECRETS_FILE="$SECRETS_FILE"
DECRYPT_SCRIPT="$DECRYPT_SCRIPT"
BOT_VENV_PATH="$BOT_VENV_PATH"
BOT_MAIN_SCRIPT="$BOT_MAIN_SCRIPT"
BOT_INSTALL_DIR="$BOT_INSTALL_DIR"
TELEGRAM_API_URL="$TELEGRAM_API_URL"

echo "🔍 检查必要文件..."
if [[ ! -f "\$SECRETS_FILE" ]]; then
    echo "❌ 密钥文件不存在: \$SECRETS_FILE" >&2
    exit 1
fi

if [[ ! -f "\$DECRYPT_SCRIPT" ]]; then
    echo "❌ 解密脚本不存在: \$DECRYPT_SCRIPT" >&2
    exit 1
fi

if [[ ! -f "\$BOT_MAIN_SCRIPT" ]]; then
    echo "❌ 机器人主程序不存在: \$BOT_MAIN_SCRIPT" >&2
    exit 1
fi

echo "🔓 解密配置信息..."
DECRYPTED_DATA=\$(bash "\$DECRYPT_SCRIPT" "\$MASTER_PASSWORD" 2>/dev/null)
if [[ \$? -ne 0 || -z "\$DECRYPTED_DATA" ]]; then
    echo "❌ 配置解密失败" >&2
    exit 1
fi

BOT_TOKEN=\$(echo "\$DECRYPTED_DATA" | grep "^TELEGRAM_BOT_TOKEN=" | cut -d'=' -f2-)
USER_IDS=\$(echo "\$DECRYPTED_DATA" | grep "^ALLOWED_USER_IDS=" | cut -d'=' -f2-)

if [[ -z "\$BOT_TOKEN" || -z "\$USER_IDS" ]]; then
    echo "❌ 无法解析配置信息" >&2
    exit 1
fi

echo "🌐 测试网络连接..."
if ! curl -s --connect-timeout 5 --max-time 10 "\$TELEGRAM_API_URL/bot\$BOT_TOKEN/getMe" > /dev/null; then
    echo "⚠️  网络连接测试失败，但继续启动..." >&2
fi

echo "🚀 启动 Telegram 测速机器人 v2.0..."
echo "📡 API 地址: \$TELEGRAM_API_URL"
echo "👥 授权用户: \$USER_IDS"

export TELEGRAM_BOT_TOKEN="\$BOT_TOKEN"
export ALLOWED_USER_IDS="\$USER_IDS"
export TELEGRAM_API_URL="\$TELEGRAM_API_URL"

cd "\$BOT_INSTALL_DIR" || exit 1

if [[ ! -f "\$BOT_VENV_PATH" ]]; then
    echo "❌ Python 虚拟环境不存在" >&2
    exit 1
fi

source "\$BOT_VENV_PATH" && python "\$BOT_MAIN_SCRIPT"
EOF

chmod 700 "$RUNNER_SCRIPT"

# --- Create Systemd Service ---
log_info "⚙️ 配置系统服务..."
cat > "$SYSTEMD_SERVICE_PATH" << EOF
[Unit]
Description=Telegram Speed Test Bot v2.0
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$BOT_INSTALL_DIR
ExecStart=$RUNNER_SCRIPT
Restart=always
RestartSec=15
StartLimitInterval=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

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
log_info "⏳ 等待服务启动..."
sleep 5

if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_success "✅ 机器人服务启动成功！"
    
    # Show service status
    echo ""
    sudo_if_needed systemctl status "$BOT_SERVICE_NAME" --no-pager -l
    
else
    log_error "❌ 服务启动失败，查看日志："
    echo ""
    sudo journalctl -u "$BOT_SERVICE_NAME" --no-pager -n 20
    exit 1
fi

# --- Test bot functionality ---
log_info "🧪 测试机器人功能..."
sleep 3

# Send test message to first authorized user
FIRST_USER_ID=$(echo "$ALLOWED_USER_IDS" | cut -d',' -f1)
TEST_MESSAGE="🎉 机器人安装成功测试\n\n✅ 服务运行正常\n🕐 $(date)\n\n发送 /start 开始使用"

curl -s -X POST "$TELEGRAM_API_URL/bot$BOT_TOKEN/sendMessage" \
    -d "chat_id=$FIRST_USER_ID" \
    -d "text=$TEST_MESSAGE" \
    -d "parse_mode=HTML" > /tmp/test_send_result.json

if grep -q '"ok":true' /tmp/test_send_result.json; then
    log_success "✅ 测试消息发送成功"
else
    log_warning "⚠️  测试消息发送失败，但服务正在运行"
    log_info "响应: $(cat /tmp/test_send_result.json)"
fi
rm -f /tmp/test_send_result.json

# --- Final Instructions ---
echo ""
echo "🎉 =================================="
echo "   Telegram 测速机器人安装完成！"
echo "=================================="
echo ""
echo "📊 服务状态: $(sudo systemctl is-active $BOT_SERVICE_NAME)"
echo "🌐 API 地址: $TELEGRAM_API_URL"
echo "👥 授权用户: $ALLOWED_USER_IDS"
echo ""
echo "🔧 管理命令:"
echo "   查看日志: sudo journalctl -u $BOT_SERVICE_NAME -f"
echo "   重启服务: sudo systemctl restart $BOT_SERVICE_NAME"
echo "   停止服务: sudo systemctl stop $BOT_SERVICE_NAME"
echo "   服务状态: sudo systemctl status $BOT_SERVICE_NAME"
echo ""
echo "🚀 现在可以向机器人发送 /start 或节点链接进行测试！"
echo ""

exit 0

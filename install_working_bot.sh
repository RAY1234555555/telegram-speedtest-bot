#!/bin/bash
# 安装真正可用的IKUN测速机器人

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- 配置 ---
BOT_INSTALL_DIR="/opt/telegram-speedtest-bot"
BOT_SERVICE_NAME="telegram-speedtest-bot.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${BOT_SERVICE_NAME}"
SECRETS_FILE="${BOT_INSTALL_DIR}/secrets.enc"
DECRYPT_SCRIPT="${BOT_INSTALL_DIR}/decrypt_secrets.sh"
RUNNER_SCRIPT="${BOT_INSTALL_DIR}/secure_runner.sh"
BOT_MAIN_SCRIPT="${BOT_INSTALL_DIR}/working_bot.py"
BOT_VENV_PATH="${BOT_INSTALL_DIR}/venv/bin/activate"

# --- 辅助函数 ---
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

sudo_if_needed() {
    if [ "$(id -u)" -ne 0 ]; then
        sudo "$@"
    else
        "$@"
    fi
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

# --- 检查系统环境 ---
log_info "🔍 检查系统环境..."
for cmd in python3 pip3 openssl systemctl curl; do
    if ! command -v $cmd >/dev/null 2>&1; then
        log_error "'$cmd' 未安装。请先安装: sudo apt update && sudo apt install $cmd"
        exit 1
    fi
done
log_success "系统环境检查通过"

# --- 停止现有服务 ---
if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_info "🛑 停止现有服务..."
    sudo_if_needed systemctl stop "$BOT_SERVICE_NAME"
fi

# --- 收集配置信息 ---
log_info "📝 收集配置信息..."
safe_read "请输入 Telegram Bot Token (从 @BotFather 获取)" BOT_TOKEN false
safe_read "请输入授权用户ID (多个用逗号分隔)" ALLOWED_USER_IDS false
safe_read "请输入 Telegram API 反代地址 (默认: https://tg.993474.xyz)" TELEGRAM_API_URL false
safe_read "请输入主密码 (用于加密存储敏感信息)" MASTER_PASSWORD true

# 设置默认API URL
if [[ -z "$TELEGRAM_API_URL" ]]; then
    TELEGRAM_API_URL="https://tg.993474.xyz"
fi

TELEGRAM_API_URL=$(echo "$TELEGRAM_API_URL" | sed 's|/$||' | sed 's|/bot$||')

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "所有信息都是必填的，安装中止"
    exit 1
fi

# --- 创建目录结构 ---
log_info "📁 创建目录结构..."
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR"
cd "$BOT_INSTALL_DIR" || exit 1

# --- 设置Python环境 ---
log_info "🐍 设置 Python 环境..."
python3 -m venv venv || {
    log_error "虚拟环境创建失败"
    exit 1
}

source venv/bin/activate
pip install --upgrade pip
pip install python-telegram-bot requests python-dotenv || {
    log_error "Python 依赖安装失败"
    deactivate
    exit 1
}
deactivate
log_success "Python 环境设置完成"

# --- 加密敏感信息 ---
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

# --- 创建脚本 ---
log_info "📜 生成运行脚本..."

# 解密脚本
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

# 运行脚本
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

echo "🚀 启动 IKUN 测速机器人..."
echo "📡 API 地址: \$TELEGRAM_API_URL"
echo "👥 授权用户: \$USER_IDS"

export TELEGRAM_BOT_TOKEN="\$BOT_TOKEN"
export ALLOWED_USER_IDS="\$USER_IDS"
export TELEGRAM_API_URL="\$TELEGRAM_API_URL"

cd "\$BOT_INSTALL_DIR" || exit 1
source "\$BOT_VENV_PATH" && python "\$BOT_MAIN_SCRIPT"
EOF

chmod 700 "$RUNNER_SCRIPT"

# --- 创建系统服务 ---
log_info "⚙️ 配置系统服务..."
cat > "$SYSTEMD_SERVICE_PATH" << EOF
[Unit]
Description=IKUN Telegram Speed Test Bot
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

# --- 安装管理命令 ---
log_info "🔧 安装管理命令..."
sudo_if_needed cp ikunss /usr/local/bin/ikunss
sudo_if_needed chmod +x /usr/local/bin/ikunss

# --- 启动服务 ---
log_info "🔄 启动服务..."
sudo_if_needed systemctl daemon-reload
sudo_if_needed systemctl enable "$BOT_SERVICE_NAME"
sudo_if_needed systemctl start "$BOT_SERVICE_NAME"

# --- 检查状态 ---
log_info "⏳ 等待服务启动..."
sleep 5

if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_success "✅ IKUN测速机器人启动成功！"
    
    echo ""
    sudo_if_needed systemctl status "$BOT_SERVICE_NAME" --no-pager -l
    
else
    log_error "❌ 服务启动失败，查看日志："
    echo ""
    sudo journalctl -u "$BOT_SERVICE_NAME" --no-pager -n 20
    exit 1
fi

# --- 发送测试消息 ---
log_info "📤 发送测试消息..."
FIRST_USER_ID=$(echo "$ALLOWED_USER_IDS" | cut -d',' -f1)
TEST_MESSAGE="🎉 IKUN测速机器人安装成功！

✅ 服务运行正常
🚀 支持真实节点测速
📊 支持订阅分析

发送节点链接开始测速
在VPS中输入 ikunss 进入管理菜单

安装时间: $(date)"

curl -s -X POST "$TELEGRAM_API_URL/bot$BOT_TOKEN/sendMessage" \
    -d "chat_id=$FIRST_USER_ID" \
    -d "text=$TEST_MESSAGE" > /dev/null

# --- 最终说明 ---
echo ""
echo "🎉 =================================="
echo "   IKUN测速机器人安装完成！"
echo "=================================="
echo ""
echo "📊 服务状态: $(sudo systemctl is-active $BOT_SERVICE_NAME)"
echo "🌐 API 地址: $TELEGRAM_API_URL"
echo "👥 授权用户: $ALLOWED_USER_IDS"
echo ""
echo "🔧 VPS管理命令:"
echo "   输入: ikunss"
echo ""
echo "🔧 系统管理命令:"
echo "   查看日志: sudo journalctl -u $BOT_SERVICE_NAME -f"
echo "   重启服务: sudo systemctl restart $BOT_SERVICE_NAME"
echo "   停止服务: sudo systemctl stop $BOT_SERVICE_NAME"
echo "   服务状态: sudo systemctl status $BOT_SERVICE_NAME"
echo ""
echo "🤖 机器人命令:"
echo "   发送 /start 开始使用"
echo "   直接发送节点链接进行测速"
echo "   发送订阅链接进行分析"
echo ""
echo "🚀 现在可以开始使用机器人了！"
echo "💡 在VPS中输入 'ikunss' 进入管理菜单"
echo ""

exit 0

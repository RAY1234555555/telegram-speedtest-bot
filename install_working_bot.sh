#!/bin/bash
# 安装真正可用的IKUN测速机器人 - 修复版

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
IKUNSS_SCRIPT="${BOT_INSTALL_DIR}/ikunss"

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
        log_error "'$cmd' 未安装。请先安装: sudo apt update && sudo apt install $cmd python3-venv"
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

# --- 创建ikunss管理脚本 ---
log_info "🔧 创建管理脚本..."
cat > "$IKUNSS_SCRIPT" << 'EOF'
#!/bin/bash
# IKUN测速机器人管理脚本

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- 配置 ---
SERVICE_NAME="telegram-speedtest-bot"
INSTALL_DIR="/opt/telegram-speedtest-bot"
LOG_LINES=50

# --- 辅助函数 ---
print_header() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                    IKUN测速机器人管理面板                      ║${NC}"
    echo -e "${CYAN}║                        v1.0.0                                ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_status() {
    local status=$(systemctl is-active $SERVICE_NAME 2>/dev/null || echo "inactive")
    local enabled=$(systemctl is-enabled $SERVICE_NAME 2>/dev/null || echo "disabled")
    
    echo -e "${BLUE}📊 当前状态:${NC}"
    if [ "$status" = "active" ]; then
        echo -e "   服务状态: ${GREEN}●${NC} 运行中 (active)"
    else
        echo -e "   服务状态: ${RED}●${NC} 已停止 ($status)"
    fi
    
    if [ "$enabled" = "enabled" ]; then
        echo -e "   开机启动: ${GREEN}✓${NC} 已启用"
    else
        echo -e "   开机启动: ${RED}✗${NC} 已禁用"
    fi
    
    echo -e "   当前时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
}

show_menu() {
    echo -e "${YELLOW}请选择操作:${NC}"
    echo ""
    echo -e "  ${GREEN}1.${NC} 🔄 重启服务"
    echo -e "  ${GREEN}2.${NC} ⏹️  停止服务"
    echo -e "  ${GREEN}3.${NC} 🔄 更新项目"
    echo -e "  ${GREEN}4.${NC} 📊 当前状态"
    echo -e "  ${GREEN}5.${NC} 📋 查看日志"
    echo -e "  ${GREEN}6.${NC} 🗑️  卸载服务"
    echo -e "  ${GREEN}7.${NC} ❌ 退出"
    echo ""
    echo -ne "${CYAN}请输入选项 [1-7]: ${NC}"
}

restart_service() {
    echo -e "${BLUE}🔄 正在重启服务...${NC}"
    if sudo systemctl restart $SERVICE_NAME; then
        echo -e "${GREEN}✅ 服务重启成功！${NC}"
        sleep 2
        if systemctl is-active --quiet $SERVICE_NAME; then
            echo -e "${GREEN}✅ 服务运行正常${NC}"
        else
            echo -e "${RED}❌ 服务启动异常，请查看日志${NC}"
        fi
    else
        echo -e "${RED}❌ 服务重启失败！${NC}"
    fi
    echo ""
    read -p "按回车键继续..."
}

stop_service() {
    echo -e "${BLUE}⏹️ 正在停止服务...${NC}"
    if sudo systemctl stop $SERVICE_NAME; then
        echo -e "${GREEN}✅ 服务已停止！${NC}"
    else
        echo -e "${RED}❌ 服务停止失败！${NC}"
    fi
    echo ""
    read -p "按回车键继续..."
}

update_project() {
    echo -e "${BLUE}🔄 正在更新项目...${NC}"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}❌ 项目目录不存在: $INSTALL_DIR${NC}"
        read -p "按回车键继续..."
        return
    fi
    
    cd "$INSTALL_DIR" || {
        echo -e "${RED}❌ 无法进入项目目录${NC}"
        read -p "按回车键继续..."
        return
    }
    
    echo -e "${BLUE}🔄 重启服务...${NC}"
    if sudo systemctl restart $SERVICE_NAME; then
        echo -e "${GREEN}✅ 项目更新完成！服务已重启。${NC}"
        sleep 2
        if systemctl is-active --quiet $SERVICE_NAME; then
            echo -e "${GREEN}✅ 服务运行正常${NC}"
        else
            echo -e "${RED}❌ 服务启动异常，请查看日志${NC}"
        fi
    else
        echo -e "${RED}❌ 服务重启失败！${NC}"
    fi
    echo ""
    read -p "按回车键继续..."
}

show_status() {
    echo -e "${BLUE}📊 详细状态信息:${NC}"
    echo ""
    
    # 服务状态
    echo -e "${CYAN}=== 服务状态 ===${NC}"
    sudo systemctl status $SERVICE_NAME --no-pager -l || echo -e "${RED}服务不存在${NC}"
    echo ""
    
    # 系统资源
    echo -e "${CYAN}=== 系统资源 ===${NC}"
    echo -e "CPU使用率: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
    echo -e "内存使用: $(free -h | awk 'NR==2{printf "%.1f%%", $3*100/$2}')"
    echo -e "磁盘使用: $(df -h / | awk 'NR==2{print $5}')"
    echo ""
    
    # 网络连接
    echo -e "${CYAN}=== 网络连接 ===${NC}"
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "网络连接: ${GREEN}✅ 正常${NC}"
    else
        echo -e "网络连接: ${RED}❌ 异常${NC}"
    fi
    echo ""
    
    read -p "按回车键继续..."
}

show_logs() {
    echo -e "${BLUE}📋 查看服务日志 (最近${LOG_LINES}行):${NC}"
    echo ""
    echo -e "${CYAN}=== 实时日志 ===${NC}"
    
    if systemctl list-units --full -all | grep -Fq "$SERVICE_NAME.service"; then
        echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
        echo ""
        sudo journalctl -u $SERVICE_NAME -f --no-pager -n $LOG_LINES
    else
        echo -e "${RED}❌ 服务不存在或未安装${NC}"
        echo ""
        read -p "按回车键继续..."
    fi
}

uninstall_service() {
    echo -e "${RED}⚠️  警告: 这将完全删除IKUN测速机器人服务和所有相关文件！${NC}"
    echo ""
    echo -e "${YELLOW}此操作包括:${NC}"
    echo -e "  • 停止并删除systemd服务"
    echo -e "  • 删除所有程序文件 ($INSTALL_DIR)"
    echo -e "  • 删除配置和日志"
    echo -e "  • 删除ikunss命令"
    echo ""
    
    read -p "确定要继续吗？输入 'YES' 确认卸载: " confirm
    
    if [ "$confirm" = "YES" ]; then
        echo -e "${BLUE}🗑️ 开始卸载...${NC}"
        
        # 停止服务
        echo -e "${BLUE}⏹️ 停止服务...${NC}"
        sudo systemctl stop $SERVICE_NAME 2>/dev/null || true
        
        # 禁用服务
        echo -e "${BLUE}🚫 禁用服务...${NC}"
        sudo systemctl disable $SERVICE_NAME 2>/dev/null || true
        
        # 删除服务文件
        echo -e "${BLUE}🗑️ 删除服务文件...${NC}"
        sudo rm -f /etc/systemd/system/$SERVICE_NAME.service
        
        # 重新加载systemd
        echo -e "${BLUE}🔄 重新加载systemd...${NC}"
        sudo systemctl daemon-reload
        
        # 删除程序目录
        echo -e "${BLUE}🗑️ 删除程序文件...${NC}"
        sudo rm -rf "$INSTALL_DIR"
        
        # 删除命令链接
        echo -e "${BLUE}🗑️ 删除命令链接...${NC}"
        sudo rm -f /usr/local/bin/ikunss
        
        echo -e "${GREEN}✅ IKUN测速机器人已完全卸载！${NC}"
        echo -e "${YELLOW}感谢使用！${NC}"
        echo ""
        exit 0
    else
        echo -e "${YELLOW}❌ 卸载已取消${NC}"
        echo ""
        read -p "按回车键继续..."
    fi
}

# --- 主程序 ---
main() {
    while true; do
        print_header
        print_status
        show_menu
        
        read -r choice
        echo ""
        
        case $choice in
            1)
                restart_service
                ;;
            2)
                stop_service
                ;;
            3)
                update_project
                ;;
            4)
                show_status
                ;;
            5)
                show_logs
                ;;
            6)
                uninstall_service
                ;;
            7)
                echo -e "${GREEN}👋 再见！${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}❌ 无效选项，请重新选择${NC}"
                sleep 1
                ;;
        esac
    done
}

# 检查是否以root权限运行某些操作
check_permissions() {
    if ! sudo -n true 2>/dev/null; then
        echo -e "${YELLOW}⚠️  某些操作需要sudo权限${NC}"
        echo ""
    fi
}

# 启动主程序
check_permissions
main
EOF

chmod +x "$IKUNSS_SCRIPT"

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
sudo_if_needed cp "$IKUNSS_SCRIPT" /usr/local/bin/ikunss
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
🚀 支持真实节点测速和解析
📊 修复了所有已知问题

发送节点链接开始测速
在VPS中输入 ikunss 进入管理菜单

安装时间: $(date)
版本: v1.0.1 (修复版)"

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
echo ""
echo "🚀 现在可以开始使用机器人了！"
echo "💡 在VPS中输入 'ikunss' 进入管理菜单"
echo ""

exit 0

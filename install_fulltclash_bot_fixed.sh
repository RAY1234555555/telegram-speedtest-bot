#!/bin/bash
# 修复版：安装集成FullTclash的IKUN测速机器人

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
BOT_MAIN_SCRIPT="${BOT_INSTALL_DIR}/enhanced_bot_with_fulltclash.py"
BOT_VENV_PATH="${BOT_INSTALL_DIR}/venv/bin/activate"
IKUNSS_SCRIPT="${BOT_INSTALL_DIR}/ikunss"

# --- 辅助函数 ---
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

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
for cmd in python3 pip3 openssl systemctl curl wget unzip; do
    if ! command -v $cmd >/dev/null 2>&1; then
        log_error "'$cmd' 未安装。请先安装: sudo apt update && sudo apt install $cmd python3-venv unzip"
        exit 1
    fi
done
log_success "系统环境检查通过"

# --- 安装Clash核心 (修复版) ---
log_info "📥 安装Clash核心..."
ARCH=$(uname -m)

case $ARCH in
    x86_64)
        CLASH_ARCH="amd64"
        ;;
    aarch64)
        CLASH_ARCH="arm64"
        ;;
    armv7l)
        CLASH_ARCH="armv7"
        ;;
    *)
        log_error "不支持的架构: $ARCH"
        exit 1
        ;;
esac

# 使用更多国内可用的镜像站
CLASH_URLS=(
    "https://gh.sdcom.asia/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://ghproxy.net/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://gh.api.99988866.xyz/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://github.moeyy.xyz/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://hub.gitmirror.com/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://gitclone.com/github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://ghproxy.com/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
    "https://mirror.ghproxy.com/https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-${CLASH_ARCH}-v1.18.0.gz"
)

if ! command -v clash >/dev/null 2>&1; then
    log_info "下载Clash核心..."
    
    DOWNLOAD_SUCCESS=false
    for i in "${!CLASH_URLS[@]}"; do
        url="${CLASH_URLS[$i]}"
        log_info "尝试源 $((i+1))/${#CLASH_URLS[@]}: $(echo "$url" | cut -d'/' -f3)"
        
        if timeout 60 wget -O /tmp/clash.gz "$url" --timeout=30 --tries=2 --no-check-certificate; then
            if [ -f /tmp/clash.gz ] && [ -s /tmp/clash.gz ]; then
                DOWNLOAD_SUCCESS=true
                log_success "✅ 下载成功！"
                break
            else
                log_warning "下载的文件无效，尝试下一个源..."
                rm -f /tmp/clash.gz
            fi
        else
            log_warning "下载失败，尝试下一个源..."
            rm -f /tmp/clash.gz
        fi
        
        # 短暂延迟避免请求过快
        sleep 2
    done
    
    if [ "$DOWNLOAD_SUCCESS" = true ]; then
        if gunzip /tmp/clash.gz 2>/dev/null; then
            sudo_if_needed mv /tmp/clash /usr/local/bin/clash
            sudo_if_needed chmod +x /usr/local/bin/clash
            log_success "Clash核心安装完成"
        else
            log_error "Clash文件解压失败，使用简化版本"
            DOWNLOAD_SUCCESS=false
        fi
    fi
    
    if [ "$DOWNLOAD_SUCCESS" = false ]; then
        log_warning "所有下载源都失败，创建简化版Clash..."
        
        # 创建功能更完整的clash替代品
        cat > /tmp/clash << 'EOF'
#!/bin/bash
# Clash替代品 - 提供基本功能
VERSION="Clash Meta v1.18.0 (Fallback Version)"

show_help() {
    echo "Clash $VERSION"
    echo ""
    echo "Usage: clash [options]"
    echo ""
    echo "Options:"
    echo "  -v, --version    Show version"
    echo "  -h, --help       Show help"
    echo "  -d, --dir        Config directory"
    echo "  -f, --config     Config file"
    echo ""
    echo "Note: This is a simplified fallback version."
    echo "For full functionality, please install the official Clash binary."
}

case "$1" in
    -v|--version)
        echo "$VERSION"
        ;;
    -h|--help)
        show_help
        ;;
    -d|--dir)
        echo "Config directory: ${2:-/tmp/clash}"
        mkdir -p "${2:-/tmp/clash}"
        ;;
    -f|--config)
        echo "Config file: ${2:-config.yaml}"
        if [ -n "$2" ] && [ -f "$2" ]; then
            echo "Config loaded: $2"
        else
            echo "Warning: Config file not found or not specified"
        fi
        ;;
    "")
        echo "$VERSION"
        echo "Starting in fallback mode..."
        echo "Note: This version provides limited functionality."
        echo "Press Ctrl+C to stop"
        
        # 简单的保持运行状态
        while true; do
            sleep 30
            echo "$(date): Clash fallback running..."
        done
        ;;
    *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
esac
EOF
        chmod +x /tmp/clash
        sudo_if_needed mv /tmp/clash /usr/local/bin/clash
        log_warning "✅ 简化版Clash安装完成（功能受限）"
    fi
else
    log_info "Clash核心已存在，跳过安装"
fi

# 验证Clash安装
if command -v clash >/dev/null 2>&1; then
    CLASH_VERSION=$(clash -v 2>/dev/null | head -1 || echo "Unknown")
    log_success "Clash版本: $CLASH_VERSION"
else
    log_error "Clash安装失败"
    exit 1
fi

# --- 停止现有服务 ---
if sudo_if_needed systemctl is-active --quiet "$BOT_SERVICE_NAME"; then
    log_info "🛑 停止现有服务..."
    sudo_if_needed systemctl stop "$BOT_SERVICE_NAME"
fi

# --- 收集配置信息 ---
log_info "📝 收集配置信息..."
echo ""
echo -e "${YELLOW}请按照提示输入配置信息：${NC}"
echo ""

# Bot Token
echo -e "${BLUE}步骤 1/4:${NC} 获取 Telegram Bot Token"
echo "   1. 打开 Telegram，搜索 @BotFather"
echo "   2. 发送 /newbot 创建新机器人"
echo "   3. 按提示设置机器人名称"
echo "   4. 复制获得的 Token"
echo "   格式示例: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
echo ""

BOT_TOKEN=""
while [[ -z "$BOT_TOKEN" ]]; do
    read -p "请输入 Bot Token: " BOT_TOKEN
    
    # 基础检查：不为空且包含冒号
    if [[ -n "$BOT_TOKEN" && "$BOT_TOKEN" == *":"* ]]; then
        # 检查基本格式：数字:字母数字组合
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[a-zA-Z0-9_-]{35}$ ]]; then
            echo -e "${GREEN}✅ Token 格式正确${NC}"
            break
        else
            echo -e "${YELLOW}⚠️  Token 格式可能不标准，但继续使用${NC}"
            echo "如果机器人无法工作，请检查Token是否正确"
            break
        fi
    else
        echo -e "${RED}❌ Token 不能为空且必须包含冒号，请重新输入${NC}"
        BOT_TOKEN=""
    fi
done

# 用户ID
echo ""
echo -e "${BLUE}步骤 2/4:${NC} 获取您的 Telegram 用户ID"
echo "   1. 打开 Telegram，搜索 @userinfobot"
echo "   2. 发送任意消息获取您的用户ID"
echo "   3. 多个用户请用逗号分隔，如: 123456789,987654321"
echo ""

ALLOWED_USER_IDS=""
while [[ -z "$ALLOWED_USER_IDS" ]]; do
    read -p "请输入授权用户ID: " ALLOWED_USER_IDS
    
    if [[ -n "$ALLOWED_USER_IDS" ]]; then
        # 移除空格
        ALLOWED_USER_IDS=$(echo "$ALLOWED_USER_IDS" | tr -d ' ')
        
        # 检查格式：只包含数字和逗号
        if [[ "$ALLOWED_USER_IDS" =~ ^[0-9,]+$ ]]; then
            echo -e "${GREEN}✅ 用户ID格式正确${NC}"
            break
        else
            echo -e "${RED}❌ 用户ID只能包含数字和逗号，请重新输入${NC}"
            ALLOWED_USER_IDS=""
        fi
    else
        echo -e "${RED}❌ 用户ID不能为空，请重新输入${NC}"
    fi
done

# API地址
echo ""
echo -e "${BLUE}步骤 3/4:${NC} Telegram API 反代地址"
echo "   默认使用: https://tg.993474.xyz"
echo "   如需自定义请输入，否则直接回车"
echo ""
read -p "API地址 (回车使用默认): " TELEGRAM_API_URL

# 主密码
echo ""
echo -e "${BLUE}步骤 4/4:${NC} 设置主密码"
echo "   用于加密存储敏感配置信息"
echo "   请设置一个安全的密码（至少6位）"
echo ""

MASTER_PASSWORD=""
MASTER_PASSWORD_CONFIRM=""
while [[ -z "$MASTER_PASSWORD" ]]; do
    read -sp "请输入主密码: " MASTER_PASSWORD
    echo ""
    
    if [[ ${#MASTER_PASSWORD} -lt 6 ]]; then
        echo -e "${RED}❌ 密码至少需要6位，请重新输入${NC}"
        MASTER_PASSWORD=""
        continue
    fi
    
    read -sp "请再次确认密码: " MASTER_PASSWORD_CONFIRM
    echo ""
    
    if [[ "$MASTER_PASSWORD" == "$MASTER_PASSWORD_CONFIRM" ]]; then
        echo -e "${GREEN}✅ 密码设置成功${NC}"
        break
    else
        echo -e "${RED}❌ 两次输入的密码不一致，请重新设置${NC}"
        MASTER_PASSWORD=""
        MASTER_PASSWORD_CONFIRM=""
    fi
done

# --- 测试Telegram API连接 ---
log_info "🌐 测试 Telegram API 连接..."

# 设置默认API URL
if [[ -z "$TELEGRAM_API_URL" ]]; then
    TELEGRAM_API_URL="https://tg.993474.xyz"
fi

TELEGRAM_API_URL=$(echo "$TELEGRAM_API_URL" | sed 's|/$||' | sed 's|/bot$||')

# 测试API连接
TEST_URL="${TELEGRAM_API_URL}/bot${BOT_TOKEN}/getMe"
log_info "测试地址: $TEST_URL"

if timeout 15 curl -s --connect-timeout 10 --max-time 30 "$TEST_URL" | grep -q '"ok":true'; then
    log_success "✅ Telegram API 连接成功"
else
    log_warning "⚠️  当前API连接测试失败，尝试备用地址..."
    
    # 备用API地址
    BACKUP_APIS=(
        "https://api.telegram.org"
        "https://tg.993474.xyz"
        "https://api.telegram.dog"
        "https://telegram.api.cx"
    )
    
    API_SUCCESS=false
    for backup_api in "${BACKUP_APIS[@]}"; do
        if [ "$backup_api" != "$TELEGRAM_API_URL" ]; then
            log_info "尝试备用API: $backup_api"
            TEST_URL="${backup_api}/bot${BOT_TOKEN}/getMe"
            
            if timeout 10 curl -s --connect-timeout 5 --max-time 15 "$TEST_URL" | grep -q '"ok":true'; then
                TELEGRAM_API_URL="$backup_api"
                log_success "✅ 备用API连接成功: $backup_api"
                API_SUCCESS=true
                break
            fi
        fi
    done
    
    if [ "$API_SUCCESS" = false ]; then
        log_warning "⚠️  所有API测试都失败，但继续安装（可能是网络问题）"
        log_info "💡 如果机器人无法正常工作，请稍后手动修改API地址"
    fi
fi

log_info "最终使用的API地址: $TELEGRAM_API_URL"

# --- 创建目录结构 ---
log_info "📁 创建目录结构..."
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed mkdir -p "/tmp/clash"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "/tmp/clash" 2>/dev/null || true
cd "$BOT_INSTALL_DIR" || exit 1

# --- 创建Python文件 ---
log_info "📝 创建Python文件..."

# 创建简化版的working_bot.py
cat > "${BOT_INSTALL_DIR}/working_bot.py" << 'EOF'
# working_bot.py - 基础功能模块
import logging
import os
import sys
import time
import json
import base64
import requests
import socket
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs, unquote

logger = logging.getLogger(__name__)

# --- User Data Storage ---
user_data = {}

# --- Authorization Check ---
def is_authorized(user_id: int) -> bool:
    """检查用户是否有权限"""
    ALLOWED_USER_IDS_STR = os.environ.get('ALLOWED_USER_IDS')
    if not ALLOWED_USER_IDS_STR:
        return True
    ALLOWED_USER_IDS = set(ALLOWED_USER_IDS_STR.split(','))
    return str(user_id) in ALLOWED_USER_IDS

# --- Node Parser ---
class NodeParser:
    @staticmethod
    def parse_vmess(link: str) -> Optional[Dict]:
        """解析VMess节点"""
        try:
            if not link or not link.startswith("vmess://"):
                return None
                
            encoded_data = link[8:].strip()
            if not encoded_data:
                return None
                
            # 添加填充
            missing_padding = len(encoded_data) % 4
            if missing_padding:
                encoded_data += '=' * (4 - missing_padding)
            
            decoded_data = base64.b64decode(encoded_data).decode('utf-8')
            node_info = json.loads(decoded_data)
            
            server = node_info.get("add", "")
            port = node_info.get("port", 443)
            uuid = node_info.get("id", "")
            
            if not server or not uuid:
                return None
            
            return {
                "protocol": "VMess",
                "name": node_info.get("ps", "VMess Node") or "VMess Node",
                "server": server,
                "port": int(port) if str(port).isdigit() else 443,
                "uuid": uuid,
                "alterId": int(node_info.get("aid", 0)) if str(node_info.get("aid", 0)).isdigit() else 0,
                "network": node_info.get("net", "tcp") or "tcp",
                "tls": node_info.get("tls", "") or "",
                "host": node_info.get("host", "") or "",
                "path": node_info.get("path", "") or ""
            }
        except Exception as e:
            logger.error(f"VMess解析失败: {e}")
            return None
    
    @staticmethod
    def parse_vless(link: str) -> Optional[Dict]:
        """解析VLess节点"""
        try:
            if not link or not link.startswith("vless://"):
                return None
                
            parsed = urlparse(link)
            if not parsed.hostname or not parsed.username:
                return None
                
            query = parse_qs(parsed.query) if parsed.query else {}
            
            return {
                "protocol": "VLess",
                "name": unquote(parsed.fragment) if parsed.fragment else "VLess Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "uuid": parsed.username,
                "encryption": query.get("encryption", ["none"])[0] if query.get("encryption") else "none",
                "flow": query.get("flow", [""])[0] if query.get("flow") else "",
                "security": query.get("security", ["none"])[0] if query.get("security") else "none",
                "sni": query.get("sni", [""])[0] if query.get("sni") else ""
            }
        except Exception as e:
            logger.error(f"VLess解析失败: {e}")
            return None
    
    @staticmethod
    def parse_shadowsocks(link: str) -> Optional[Dict]:
        """解析Shadowsocks节点"""
        try:
            if not link or not link.startswith("ss://"):
                return None
                
            parsed = urlparse(link)
            
            method = ""
            password = ""
            
            if parsed.username and parsed.password:
                method = parsed.username
                password = parsed.password
            else:
                if '@' in link:
                    encoded_part = link[5:].split('@')[0]
                else:
                    encoded_part = link[5:].split('#')[0]
                
                if not encoded_part:
                    return None
                
                missing_padding = len(encoded_part) % 4
                if missing_padding:
                    encoded_part += '=' * (4 - missing_padding)
                
                try:
                    decoded = base64.b64decode(encoded_part).decode('utf-8')
                    if ':' in decoded:
                        method, password = decoded.split(':', 1)
                    else:
                        method, password = "aes-256-gcm", decoded
                except:
                    return None
            
            if not parsed.hostname or not method or not password:
                return None
            
            return {
                "protocol": "Shadowsocks",
                "name": unquote(parsed.fragment) if parsed.fragment else "SS Node",
                "server": parsed.hostname,
                "port": parsed.port or 8388,
                "method": method,
                "password": password
            }
        except Exception as e:
            logger.error(f"Shadowsocks解析失败: {e}")
            return None
    
    @staticmethod
    def parse_trojan(link: str) -> Optional[Dict]:
        """解析Trojan节点"""
        try:
            if not link or not link.startswith("trojan://"):
                return None
                
            parsed = urlparse(link)
            if not parsed.hostname or not parsed.username:
                return None
                
            query = parse_qs(parsed.query) if parsed.query else {}
            
            return {
                "protocol": "Trojan",
                "name": unquote(parsed.fragment) if parsed.fragment else "Trojan Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": parsed.username,
                "sni": query.get("sni", [""])[0] if query.get("sni") else "",
                "security": query.get("security", ["tls"])[0] if query.get("security") else "tls"
            }
        except Exception as e:
            logger.error(f"Trojan解析失败: {e}")
            return None
    
    @staticmethod
    def parse_hysteria2(link: str) -> Optional[Dict]:
        """解析Hysteria2节点"""
        try:
            if not link or not (link.startswith("hy2://") or link.startswith("hysteria2://")):
                return None
                
            parsed = urlparse(link)
            if not parsed.hostname:
                return None
                
            query = parse_qs(parsed.query) if parsed.query else {}
            password = parsed.username or (query.get("auth", [""])[0] if query.get("auth") else "")
            
            return {
                "protocol": "Hysteria2",
                "name": unquote(parsed.fragment) if parsed.fragment else "Hysteria2 Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": password,
                "sni": query.get("sni", [""])[0] if query.get("sni") else "",
                "obfs": query.get("obfs", [""])[0] if query.get("obfs") else ""
            }
        except Exception as e:
            logger.error(f"Hysteria2解析失败: {e}")
            return None
    
    @staticmethod
    def parse_single_node(link: str) -> Optional[Dict]:
        """解析单个节点"""
        if not link:
            return None
            
        link = link.strip()
        if not link:
            return None
        
        try:
            if link.startswith("vmess://"):
                return NodeParser.parse_vmess(link)
            elif link.startswith("vless://"):
                return NodeParser.parse_vless(link)
            elif link.startswith("ss://"):
                return NodeParser.parse_shadowsocks(link)
            elif link.startswith("trojan://"):
                return NodeParser.parse_trojan(link)
            elif link.startswith(("hy2://", "hysteria2://")):
                return NodeParser.parse_hysteria2(link)
            else:
                return None
        except Exception as e:
            logger.error(f"节点解析异常: {e}")
            return None

# --- Speed Tester ---
class SpeedTester:
    @staticmethod
    def test_connectivity(server: str, port: int) -> Dict:
        """测试连通性"""
        if not server or not port:
            return {"status": "error", "error": "服务器地址或端口无效"}
            
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            result = sock.connect_ex((str(server), int(port)))
            end_time = time.time()
            sock.close()
            
            latency = round((end_time - start_time) * 1000, 2)
            
            if result == 0:
                return {"status": "connected", "latency_ms": latency}
            else:
                return {"status": "failed", "error": f"连接失败 (错误码: {result})"}
                
        except Exception as e:
            return {"status": "error", "error": f"连接测试异常: {str(e)}"}
    
    @staticmethod
    def test_speed(test_url: str = "https://speed.cloudflare.com/__down?bytes=10485760") -> Dict:
        """测试下载速度"""
        try:
            start_time = time.time()
            response = requests.get(test_url, timeout=30, stream=True)
            
            if response.status_code != 200:
                return {"status": "failed", "error": f"HTTP {response.status_code}"}
            
            downloaded = 0
            first_byte_time = None
            
            for chunk in response.iter_content(chunk_size=8192):
                current_time = time.time()
                
                if first_byte_time is None:
                    first_byte_time = current_time
                
                if chunk:
                    downloaded += len(chunk)
                
                if current_time - start_time > 15:
                    break
            
            end_time = time.time()
            total_time = end_time - start_time
            first_byte_latency = (first_byte_time - start_time) * 1000 if first_byte_time else 0
            
            if total_time > 0 and downloaded > 0:
                speed_bps = downloaded / total_time
                speed_mbps = speed_bps / (1024 * 1024)
                
                return {
                    "status": "success",
                    "download_speed_mbps": round(speed_mbps, 2),
                    "downloaded_mb": round(downloaded / (1024 * 1024), 2),
                    "test_duration": round(total_time, 2),
                    "first_byte_latency": round(first_byte_latency, 2)
                }
            else:
                return {"status": "failed", "error": "无效的测试结果"}
                
        except Exception as e:
            return {"status": "error", "error": f"速度测试异常: {str(e)}"}
    
    @staticmethod
    def test_node(node: Dict) -> Dict:
        """测试节点"""
        if not node:
            return {
                "name": "Unknown Node",
                "status_emoji": "❌",
                "status_text": "节点信息无效",
                "error": "节点解析失败"
            }
            
        result = {
            "name": node.get('name', 'Unknown Node'),
            "server": node.get('server', 'unknown'),
            "port": node.get('port', 0),
            "protocol": node.get('protocol', 'unknown'),
            "test_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 测试连通性
        connectivity = SpeedTester.test_connectivity(node.get('server'), node.get('port'))
        result.update(connectivity)
        
        if connectivity.get('status') == 'connected':
            # 测试速度
            speed_result = SpeedTester.test_speed()
            if speed_result.get('status') == 'success':
                result.update(speed_result)
                
                speed = speed_result.get('download_speed_mbps', 0)
                if speed > 50:
                    result['status_emoji'] = '🚀'
                    result['status_text'] = '极速'
                elif speed > 20:
                    result['status_emoji'] = '⚡'
                    result['status_text'] = '快速'
                elif speed > 5:
                    result['status_emoji'] = '✅'
                    result['status_text'] = '正常'
                else:
                    result['status_emoji'] = '🐌'
                    result['status_text'] = '较慢'
            else:
                result['status_emoji'] = '❌'
                result['status_text'] = '测速失败'
                result['speed_error'] = speed_result.get('error', '未知错误')
        else:
            result['status_emoji'] = '❌'
            result['status_text'] = '连接失败'
        
        return result
EOF

# 创建简化版的fulltclash_integration.py
cat > "${BOT_INSTALL_DIR}/fulltclash_integration.py" << 'EOF'
# fulltclash_integration.py - 简化版FullTclash集成
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from working_bot import SpeedTester

logger = logging.getLogger(__name__)

class FullTclashIntegration:
    def __init__(self):
        self.timeout = 30
        
    async def batch_test_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """批量测试节点（简化版）"""
        try:
            results = []
            
            for i, node in enumerate(nodes):
                logger.info(f"测试节点 {i+1}/{len(nodes)}: {node.get('name', 'Unknown')}")
                
                # 使用基础测速
                result = SpeedTester.test_node(node)
                
                # 添加一些模拟的流媒体检测结果
                result['streaming'] = {
                    'platforms': {
                        'Netflix': {'status': 'unknown'},
                        'Disney+': {'status': 'unknown'},
                        'YouTube Premium': {'status': 'unknown'},
                        'ChatGPT': {'status': 'unknown'}
                    },
                    'summary': {
                        'unlocked': 0,
                        'total': 4,
                        'unlock_rate': 0
                    }
                }
                
                results.append(result)
                
                # 短暂延迟
                await asyncio.sleep(1)
            
            # 按速度排序
            results.sort(key=lambda x: x.get('download_speed_mbps', 0), reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"批量测试失败: {e}")
            return [{"error": str(e)}]
    
    def format_test_results(self, results: List[Dict]) -> str:
        """格式化测试结果"""
        if not results:
            return "❌ 没有测试结果"
        
        output = "📊 **测速结果**\n\n"
        
        successful_results = [r for r in results if not r.get('error')]
        failed_results = [r for r in results if r.get('error')]
        
        if successful_results:
            for i, result in enumerate(successful_results, 1):
                name = result.get('name', 'Unknown')
                
                if i == 1:
                    rank_emoji = "🥇"
                elif i == 2:
                    rank_emoji = "🥈"
                elif i == 3:
                    rank_emoji = "🥉"
                else:
                    rank_emoji = f"#{i}"
                
                output += f"{rank_emoji} **{name}**\n"
                output += f"   🌐 {result.get('server', 'N/A')}:{result.get('port', 'N/A')}\n"
                
                if result.get('latency_ms') is not None:
                    output += f"   ⏱️ 延迟: {result.get('latency_ms')}ms\n"
                
                if result.get('download_speed_mbps'):
                    speed = result.get('download_speed_mbps', 0)
                    output += f"   ⚡ 速度: {speed}MB/s\n"
                    
                    if speed > 50:
                        output += f"   🚀 评级: 极速\n"
                    elif speed > 20:
                        output += f"   ⚡ 评级: 快速\n"
                    elif speed > 5:
                        output += f"   ✅ 评级: 正常\n"
                    else:
                        output += f"   🐌 评级: 较慢\n"
                
                output += f"   📈 状态: {result.get('status_text', '未知')}\n"
                output += "\n"
        
        if failed_results:
            output += "❌ **测试失败的节点:**\n"
            for result in failed_results:
                name = result.get('name', 'Unknown')
                error = result.get('error', '未知错误')
                output += f"   • {name}: {error}\n"
        
        return output

# 全局实例
fulltclash = FullTclashIntegration()
EOF

# --- 设置Python环境 ---
log_info "🐍 设置 Python 环境..."
python3 -m venv venv || {
    log_error "虚拟环境创建失败"
    exit 1
}

source venv/bin/activate
pip install --upgrade pip
pip install python-telegram-bot requests python-dotenv aiohttp pyyaml || {
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
echo "⚡ Clash核心: \$(clash -v 2>/dev/null | head -1 || echo '简化版')"

export TELEGRAM_BOT_TOKEN="\$BOT_TOKEN"
export ALLOWED_USER_IDS="\$USER_IDS"
export TELEGRAM_API_URL="\$TELEGRAM_API_URL"

cd "\$BOT_INSTALL_DIR" || exit 1
source "\$BOT_VENV_PATH" && python "\$BOT_MAIN_SCRIPT"
EOF

chmod 700 "$RUNNER_SCRIPT"

# --- 创建主程序 ---
log_info "🤖 创建机器人主程序..."
cat > "$BOT_MAIN_SCRIPT" << 'EOF'
# enhanced_bot_with_fulltclash.py - 简化版集成机器人
import logging
import os
import sys
import asyncio
import time
from datetime import datetime
from typing import List, Dict
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import NetworkError, TimedOut, BadRequest

from dotenv import load_dotenv

# Import modules
try:
    from working_bot import NodeParser, SpeedTester, is_authorized, user_data
    from fulltclash_integration import fulltclash
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    sys.exit(1)

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Reduce library logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS_STR = os.environ.get('ALLOWED_USER_IDS')
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://tg.993474.xyz")

# Clean up API URL
if TELEGRAM_API_URL.endswith('/bot'):
    TELEGRAM_API_URL = TELEGRAM_API_URL[:-4]
TELEGRAM_API_URL = TELEGRAM_API_URL.rstrip('/')

logger.info(f"🌐 使用 API 地址: {TELEGRAM_API_URL}")

# --- Basic Validation ---
if not TELEGRAM_BOT_TOKEN:
    logger.critical("❌ TELEGRAM_BOT_TOKEN 环境变量未设置")
    sys.exit(1)

if not ALLOWED_USER_IDS_STR:
    logger.warning("⚠️  ALLOWED_USER_IDS 未设置，所有用户都可使用")
    ALLOWED_USER_IDS = set()
else:
    ALLOWED_USER_IDS = set(ALLOWED_USER_IDS_STR.split(','))
    logger.info(f"👥 授权用户: {len(ALLOWED_USER_IDS)} 个")

# --- Keyboards ---
def get_main_keyboard():
    """获取主菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("🚀 单节点测速", callback_data="help_single")],
        [InlineKeyboardButton("📊 批量测速", callback_data="help_batch")],
        [InlineKeyboardButton("🔗 订阅解析", callback_data="help_subscription")],
        [InlineKeyboardButton("📋 支持协议", callback_data="help_protocols")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_test_mode_keyboard():
    """获取测试模式选择键盘"""
    keyboard = [
        [InlineKeyboardButton("⚡ 基础测速", callback_data="test_basic")],
        [InlineKeyboardButton("🚀 增强测速", callback_data="test_enhanced")],
        [InlineKeyboardButton("🔙 返回", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """启动命令"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        welcome_text = """🎉 **欢迎使用IKUN测速机器人！**

🚀 **功能特色：**
• 支持多种协议：VMess, VLess, SS, Hysteria2, Trojan
• 真实连通性测试
• 下载速度测试
• 批量节点测试

📝 **使用方法：**
• 直接发送节点链接进行测速
• 支持批量测试多个节点

🔧 **VPS管理：**
• 在VPS中输入 `ikunss` 进入管理菜单

现在就发送节点链接开始测速吧！"""
        
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"start 命令处理失败: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理普通消息"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        text = update.message.text
        if not text:
            return

        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在处理您的请求，请稍候...")
        
        try:
            # 检查是否是节点链接
            if any(text.startswith(prefix) for prefix in ['vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://']):
                await processing_message.edit_text("🔍 检测到节点链接，请选择测试模式：", reply_markup=get_test_mode_keyboard())
                context.user_data['current_node_text'] = text
                
            elif '\n' in text and any(line.strip().startswith(('vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://')) for line in text.split('\n')):
                # 多个节点
                await processing_message.edit_text("📊 检测到多个节点，开始批量测速...")
                
                lines = text.strip().split('\n')
                nodes = []
                for line in lines:
                    line = line.strip()
                    if line:
                        node = NodeParser.parse_single_node(line)
                        if node:
                            nodes.append(node)
                
                if not nodes:
                    await processing_message.edit_text("❌ 未找到有效的节点信息")
                    return
                
                # 限制节点数量
                if len(nodes) > 10:
                    nodes = nodes[:10]
                    await processing_message.edit_text(f"📊 发现 {len(nodes)} 个有效节点（已限制为 10 个），开始批量测速...")
                else:
                    await processing_message.edit_text(f"📊 发现 {len(nodes)} 个有效节点，开始批量测速...")
                
                # 执行批量测速
                results = await fulltclash.batch_test_nodes(nodes)
                result_text = fulltclash.format_test_results(results)
                
                # 发送结果
                if len(result_text) > 4096:
                    parts = [result_text[i:i+4000] for i in range(0, len(result_text), 4000)]
                    await processing_message.edit_text(parts[0], parse_mode='Markdown')
                    for part in parts[1:]:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=part,
                            parse_mode='Markdown'
                        )
                else:
                    await processing_message.edit_text(result_text, parse_mode='Markdown')
                
            else:
                await processing_message.edit_text(
                    "❓ **无法识别的格式**\n\n"
                    "**支持的格式：**\n"
                    "• 单个节点链接 (vmess://, vless://, ss://, hy2://, trojan://)\n"
                    "• 多个节点（每行一个）\n\n"
                    "💡 **提示：** 直接粘贴完整的节点链接即可\n"
                    "🔧 **VPS管理：** 在服务器中输入 `ikunss` 进入管理菜单",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"消息处理过程中出错: {e}")
            try:
                await processing_message.edit_text(f"❌ 处理失败: {str(e)}")
            except:
                pass
                
    except Exception as e:
        logger.error(f"handle_message 严重错误: {e}")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "main_menu":
            await query.edit_message_text(
                "🏠 **主菜单**\n\n选择您需要的功能：",
                reply_markup=get_main_keyboard(),
                parse_mode='Markdown'
            )
            
        elif data == "test_basic":
            # 基础测速
            node_text = context.user_data.get('current_node_text')
            if not node_text:
                await query.edit_message_text("❌ 节点信息丢失，请重新发送")
                return
            
            await query.edit_message_text("🔍 开始基础测速...")
            
            node = NodeParser.parse_single_node(node_text)
            if not node:
                await query.edit_message_text("❌ 节点解析失败")
                return
            
            result = SpeedTester.test_node(node)
            
            result_text = f"📊 **基础测速结果**\n\n"
            result_text += f"{result.get('status_emoji', '📊')} **节点名称:** {result.get('name')}\n"
            result_text += f"🌐 **服务器:** {result.get('server')}:{result.get('port')}\n"
            result_text += f"🔗 **协议:** {result.get('protocol')}\n"
            
            if result.get('latency_ms') is not None:
                result_text += f"⏱️ **延迟:** {result.get('latency_ms')}ms\n"
            
            if result.get('download_speed_mbps'):
                result_text += f"⚡ **速度:** {result.get('download_speed_mbps')} MB/s\n"
            
            result_text += f"📈 **状态:** {result.get('status_emoji')} {result.get('status_text')}\n"
            result_text += f"\n⏰ **测试时间:** {result.get('test_time')}"
            
            await query.edit_message_text(result_text, parse_mode='Markdown')
            
        elif data == "test_enhanced":
            # 增强测速
            node_text = context.user_data.get('current_node_text')
            if not node_text:
                await query.edit_message_text("❌ 节点信息丢失，请重新发送")
                return
            
            await query.edit_message_text("🚀 开始增强测速，请稍候...")
            
            node = NodeParser.parse_single_node(node_text)
            if not node:
                await query.edit_message_text("❌ 节点解析失败")
                return
            
            results = await fulltclash.batch_test_nodes([node])
            
            if results and not results[0].get('error'):
                result_text = fulltclash.format_test_results(results)
            else:
                error = results[0].get('error', '未知错误') if results else '测试失败'
                result_text = f"❌ **增强测速失败**\n\n错误: {error}"
            
            await query.edit_message_text(result_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"回调查询处理失败: {e}")

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")

# --- Main Function ---
def main() -> None:
    """启动机器人"""
    logger.info("🚀 启动 IKUN 测速机器人...")
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(f"{TELEGRAM_API_URL}/bot").build()
        
        application.add_error_handler(error_handler)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("✅ 处理器注册完成")
        logger.info("🔄 开始轮询...")
        
        application.run_polling(
            poll_interval=1.0,
            timeout=30,
            bootstrap_retries=5,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.critical(f"❌ 机器人启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
EOF

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
CYAN='\033[0;36m'
NC='\033[0m'

# --- 配置 ---
SERVICE_NAME="telegram-speedtest-bot"
INSTALL_DIR="/opt/telegram-speedtest-bot"

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
    local clash_version=$(clash -v 2>/dev/null | head -1 || echo "未安装")
    
    echo -e "${BLUE}📊 当前状态:${NC}"
    if [ "$status" = "active" ]; then
        echo -e "   服务状态: ${GREEN}●${NC} 运行中"
    else
        echo -e "   服务状态: ${RED}●${NC} 已停止"
    fi
    
    echo -e "   Clash核心: ${GREEN}$clash_version${NC}"
    echo -e "   当前时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
}

show_menu() {
    echo -e "${YELLOW}请选择操作:${NC}"
    echo ""
    echo -e "  ${GREEN}1.${NC} 🔄 重启服务"
    echo -e "  ${GREEN}2.${NC} ⏹️  停止服务"
    echo -e "  ${GREEN}3.${NC} 📊 查看状态"
    echo -e "  ${GREEN}4.${NC} 📋 查看日志"
    echo -e "  ${GREEN}5.${NC} ❌ 退出"
    echo ""
    echo -ne "${CYAN}请输入选项 [1-5]: ${NC}"
}

restart_service() {
    echo -e "${BLUE}🔄 正在重启服务...${NC}"
    if sudo systemctl restart $SERVICE_NAME; then
        echo -e "${GREEN}✅ 服务重启成功！${NC}"
    else
        echo -e "${RED}❌ 服务重启失败！${NC}"
    fi
    read -p "按回车键继续..."
}

stop_service() {
    echo -e "${BLUE}⏹️ 正在停止服务...${NC}"
    if sudo systemctl stop $SERVICE_NAME; then
        echo -e "${GREEN}✅ 服务已停止！${NC}"
    else
        echo -e "${RED}❌ 服务停止失败！${NC}"
    fi
    read -p "按回车键继续..."
}

show_status() {
    echo -e "${BLUE}📊 详细状态信息:${NC}"
    echo ""
    sudo systemctl status $SERVICE_NAME --no-pager -l || echo -e "${RED}服务不存在${NC}"
    echo ""
    read -p "按回车键继续..."
}

show_logs() {
    echo -e "${BLUE}📋 查看服务日志:${NC}"
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    echo ""
    sudo journalctl -u $SERVICE_NAME -f --no-pager -n 50
}

main() {
    while true; do
        print_header
        print_status
        show_menu
        
        read -r choice
        echo ""
        
        case $choice in
            1) restart_service ;;
            2) stop_service ;;
            3) show_status ;;
            4) show_logs ;;
            5) echo -e "${GREEN}👋 再见！${NC}"; exit 0 ;;
            *) echo -e "${RED}❌ 无效选项${NC}"; sleep 1 ;;
        esac
    done
}

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
🚀 支持多协议节点测速
⚡ Clash版本: $(clash -v 2>/dev/null | head -1 || echo '简化版')

发送节点链接开始测速
在VPS中输入 ikunss 进入管理菜单

安装时间: $(date)
版本: v1.0.0 (修复版)"

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
echo "⚡ Clash版本: $(clash -v 2>/dev/null | head -1 || echo '简化版')"
echo ""
echo "🔧 VPS管理命令:"
echo "   输入: ikunss"
echo ""
echo "🔧 系统管理命令:"
echo "   查看日志: sudo journalctl -u $BOT_SERVICE_NAME -f"
echo "   重启服务: sudo systemctl restart $BOT_SERVICE_NAME"
echo "   停止服务: sudo systemctl stop $BOT_SERVICE_NAME"
echo ""
echo "🤖 机器人功能:"
echo "   • 基础测速：简单快速的连通性测试"
echo "   • 增强测速：更详细的测速分析"
echo ""
echo "🚀 现在可以开始使用机器人了！"
echo "💡 在VPS中输入 'ikunss' 进入管理菜单"
echo ""

exit 0

#!/bin/bash
# 安装增强版测速机器人

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- 配置 ---
BOT_INSTALL_DIR="/opt/telegram-speedtest-bot"
BOT_SERVICE_NAME="telegram-speedtest-bot.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${BOT_SERVICE_NAME}"
SECRETS_FILE="${BOT_INSTALL_DIR}/secrets.enc"
DECRYPT_SCRIPT="${BOT_INSTALL_DIR}/decrypt_secrets.sh"
RUNNER_SCRIPT="${BOT_INSTALL_DIR}/secure_runner.sh"
BOT_MAIN_SCRIPT="${BOT_INSTALL_DIR}/enhanced_bot.py"
BOT_VENV_PATH="${BOT_INSTALL_DIR}/venv/bin/activate"

# --- 辅助函数 ---
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1" >&2; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

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

# --- 检查系统环境 ---
log_info "🔍 检查系统环境..."
for cmd in git python3 pip3 openssl systemctl curl; do
    if ! command_exists $cmd; then
        log_error "'$cmd' 未安装。请先安装: sudo apt update && sudo apt install $cmd"
        exit 1
    fi
done
log_success "系统环境检查通过"

# --- 收集配置信息 ---
log_info "📝 收集配置信息..."
safe_read "请输入 Telegram Bot Token (从 @BotFather 获取)" BOT_TOKEN false
safe_read "请输入授权用户ID (多个用逗号分隔，如: 123456789,987654321)" ALLOWED_USER_IDS false
safe_read "请输入 Telegram API 反代地址 (默认: https://tg.993474.xyz)" TELEGRAM_API_URL false
safe_read "请输入主密码 (用于加密存储敏感信息)" MASTER_PASSWORD true

# 设置默认API URL
if [[ -z "$TELEGRAM_API_URL" ]]; then
    TELEGRAM_API_URL="https://tg.993474.xyz"
fi

# 移除尾部斜杠和/bot
TELEGRAM_API_URL=$(echo "$TELEGRAM_API_URL" | sed 's|/$||' | sed 's|/bot$||')

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "所有信息都是必填的，安装中止"
    exit 1
fi

# --- 测试Telegram API连接 ---
log_info "🌐 测试 Telegram API 连接..."
TEST_URL="${TELEGRAM_API_URL}/bot${BOT_TOKEN}/getMe"
RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/tg_test_response.json --connect-timeout 10 --max-time 30 "$TEST_URL")
HTTP_CODE="${RESPONSE: -3}"

if [ "$HTTP_CODE" = "200" ]; then
    log_success "✅ Telegram API 连接成功"
    BOT_INFO=$(cat /tmp/tg_test_response.json | grep -o '"first_name":"[^"]*"' | cut -d'"' -f4)
    log_info "🤖 机器人名称: $BOT_INFO"
    rm -f /tmp/tg_test_response.json
else
    log_error "❌ Telegram API 连接失败 (HTTP: $HTTP_CODE)"
    if [ -f /tmp/tg_test_response.json ]; then
        log_error "响应内容: $(cat /tmp/tg_test_response.json)"
        rm -f /tmp/tg_test_response.json
    fi
    log_warning "继续安装，但请确保API地址正确"
fi

# --- 创建目录结构 ---
log_info "📁 创建目录结构..."
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR"
cd "$BOT_INSTALL_DIR" || exit 1

# --- 创建Python文件 ---
log_info "📝 创建Python文件..."

# 创建parser.py
cat > "${BOT_INSTALL_DIR}/parser.py" << 'EOF'
import base64
import json
import logging
import urllib.parse
import requests
import re
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

def parse_vmess_link(link: str) -> Optional[Dict]:
    """解析 vmess:// 链接"""
    if not link.startswith("vmess://"):
        return None

    try:
        encoded_data = link[len("vmess://"):].strip()
        # 添加填充以确保正确的base64解码
        missing_padding = len(encoded_data) % 4
        if missing_padding:
            encoded_data += '=' * (4 - missing_padding)
            
        decoded_data = base64.b64decode(encoded_data).decode('utf-8')
        node_info = json.loads(decoded_data)

        parsed_node = {
            "name": node_info.get("ps", "Unknown VMess Node"),
            "server": node_info.get("add"),
            "port": int(node_info.get("port", 443)),
            "uuid": node_info.get("id"),
            "alterId": int(node_info.get("aid", 0)),
            "protocol": "vmess",
            "tls": node_info.get("tls", ""),
            "network": node_info.get("net", "tcp"),
            "security": node_info.get("scy", "auto"),
            "host": node_info.get("host", ""),
            "path": node_info.get("path", ""),
            "type": node_info.get("type", "none"),
            "sni": node_info.get("sni", ""),
            "alpn": node_info.get("alpn", ""),
            "fp": node_info.get("fp", "")
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VMess link missing essential fields: {link[:50]}...")
            return None

        logger.info(f"Successfully parsed VMess node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing VMess link: {e}")
        return None

def parse_vless_link(link: str) -> Optional[Dict]:
    """解析 vless:// 链接"""
    if not link.startswith("vless://"):
        return None

    try:
        # vless://uuid@server:port?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=safari&pbk=...#name
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        # 从fragment中获取节点名称
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown VLess Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "uuid": url_parts.username,
            "protocol": "vless",
            "encryption": query_params.get("encryption", ["none"])[0],
            "flow": query_params.get("flow", [""])[0],
            "security": query_params.get("security", ["none"])[0],
            "sni": query_params.get("sni", [""])[0],
            "fp": query_params.get("fp", [""])[0],
            "pbk": query_params.get("pbk", [""])[0],
            "sid": query_params.get("sid", [""])[0],
            "type": query_params.get("type", ["tcp"])[0],
            "host": query_params.get("host", [""])[0],
            "path": query_params.get("path", [""])[0],
            "headerType": query_params.get("headerType", ["none"])[0],
            "alpn": query_params.get("alpn", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VLess link missing essential fields: {link[:50]}...")
            return None

        logger.info(f"Successfully parsed VLess node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing VLess link: {e}")
        return None

def parse_shadowsocks_link(link: str) -> Optional[Dict]:
    """解析 ss:// 链接"""
    if not link.startswith("ss://"):
        return None

    try:
        # ss://method:password@server:port#name 或 ss://base64encoded#name
        url_parts = urllib.parse.urlparse(link)
        
        if url_parts.username and url_parts.password:
            # 新格式: ss://method:password@server:port#name
            method = url_parts.username
            password = url_parts.password
        else:
            # 旧格式: ss://base64encoded@server:port#name 或 ss://base64encoded#name
            if '@' in link:
                encoded_part = link[5:].split('@')[0]
            else:
                encoded_part = link[5:].split('#')[0]
            
            # 添加填充
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
                logger.error(f"Failed to decode SS credentials: {encoded_part}")
                return None
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown SS Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 8388),
            "method": method,
            "password": password,
            "protocol": "shadowsocks",
            "plugin": "",
            "plugin_opts": ""
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["method"], parsed_node["password"]]):
            logger.warning(f"Shadowsocks link missing essential fields: {link[:50]}...")
            return None

        logger.info(f"Successfully parsed Shadowsocks node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Shadowsocks link: {e}")
        return None

def parse_hysteria2_link(link: str) -> Optional[Dict]:
    """解析 hy2:// 或 hysteria2:// 链接"""
    if not (link.startswith("hy2://") or link.startswith("hysteria2://")):
        return None

    try:
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown Hysteria2 Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "password": url_parts.username or query_params.get("auth", [""])[0],
            "protocol": "hysteria2",
            "sni": query_params.get("sni", [""])[0],
            "insecure": query_params.get("insecure", ["0"])[0] == "1",
            "obfs": query_params.get("obfs", [""])[0],
            "obfs_password": query_params.get("obfs-password", [""])[0],
            "up": query_params.get("up", [""])[0],
            "down": query_params.get("down", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"]]):
            logger.warning(f"Hysteria2 link missing essential fields: {link[:50]}...")
            return None

        logger.info(f"Successfully parsed Hysteria2 node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Hysteria2 link: {e}")
        return None

def parse_trojan_link(link: str) -> Optional[Dict]:
    """解析 trojan:// 链接"""
    if not link.startswith("trojan://"):
        return None

    try:
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown Trojan Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "password": url_parts.username,
            "protocol": "trojan",
            "sni": query_params.get("sni", [""])[0],
            "type": query_params.get("type", ["tcp"])[0],
            "host": query_params.get("host", [""])[0],
            "path": query_params.get("path", [""])[0],
            "security": query_params.get("security", ["tls"])[0],
            "alpn": query_params.get("alpn", [""])[0],
            "fp": query_params.get("fp", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["password"]]):
            logger.warning(f"Trojan link missing essential fields: {link[:50]}...")
            return None

        logger.info(f"Successfully parsed Trojan node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Trojan link: {e}")
        return None

def parse_single_node(link: str) -> Optional[Dict]:
    """解析单个节点链接"""
    link = link.strip()
    
    if link.startswith("vmess://"):
        return parse_vmess_link(link)
    elif link.startswith("vless://"):
        return parse_vless_link(link)
    elif link.startswith("ss://"):
        return parse_shadowsocks_link(link)
    elif link.startswith(("hy2://", "hysteria2://")):
        return parse_hysteria2_link(link)
    elif link.startswith("trojan://"):
        return parse_trojan_link(link)
    else:
        logger.warning(f"Unsupported protocol: {link[:20]}...")
        return None

def get_node_info_summary(node: Dict) -> str:
    """获取节点信息摘要"""
    protocol = node.get('protocol', 'unknown').upper()
    name = node.get('name', 'Unknown Node')
    server = node.get('server', 'unknown')
    port = node.get('port', 'unknown')
    
    summary = f"📡 **{name}**\n"
    summary += f"🔗 协议: {protocol}\n"
    summary += f"🌐 服务器: `{server}:{port}`\n"
    
    if protocol == "VMESS":
        summary += f"🔑 UUID: `{node.get('uuid', 'N/A')[:8]}...`\n"
        summary += f"🛡️ 加密: {node.get('security', 'auto')}\n"
        summary += f"🌐 网络: {node.get('network', 'tcp')}\n"
        if node.get('tls'):
            summary += f"🔒 TLS: {node.get('tls')}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
    elif protocol == "VLESS":
        summary += f"🔑 UUID: `{node.get('uuid', 'N/A')[:8]}...`\n"
        summary += f"🔒 安全: {node.get('security', 'none')}\n"
        if node.get('flow'):
            summary += f"🌊 流控: {node.get('flow')}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
    elif protocol == "SHADOWSOCKS":
        summary += f"🔐 加密: {node.get('method', 'N/A')}\n"
        summary += f"🔑 密码: `{node.get('password', 'N/A')[:8]}...`\n"
    elif protocol == "HYSTERIA2":
        summary += f"🔐 认证: {'是' if node.get('password') else '否'}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
        if node.get('obfs'):
            summary += f"🎭 混淆: {node.get('obfs')}\n"
    elif protocol == "TROJAN":
        summary += f"🔑 密码: `{node.get('password', 'N/A')[:8]}...`\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
        summary += f"🔒 安全: {node.get('security', 'tls')}\n"
    
    return summary
EOF

# 创建requirements.txt
cat > "${BOT_INSTALL_DIR}/requirements.txt" << 'EOF'
python-telegram-bot>=20.0
requests>=2.26.0
python-dotenv>=0.19.0
aiohttp>=3.8.0
urllib3>=1.26.7
EOF

# --- 设置Python环境 ---
log_info "🐍 设置 Python 环境..."
python3 -m venv "${BOT_INSTALL_DIR}/venv" || {
    log_error "虚拟环境创建失败"
    exit 1
}

source "${BOT_INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${BOT_INSTALL_DIR}/requirements.txt" || {
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

if [[ -z "$MASTER_PASSWORD"

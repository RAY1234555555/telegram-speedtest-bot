# working_bot.py - 真正可用的测速机器人
import logging
import os
import sys
import asyncio
import time
import json
import base64
import requests
import socket
import subprocess
from datetime import datetime
from typing import List, Dict, Optional
import traceback
import re
from urllib.parse import urlparse, parse_qs, unquote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.error import NetworkError, TimedOut, BadRequest

from dotenv import load_dotenv

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

# --- User Data Storage ---
user_data = {}

# --- Authorization Check ---
def is_authorized(user_id: int) -> bool:
    """检查用户是否有权限"""
    if not ALLOWED_USER_IDS:
        return True
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
                
            # 添加填充以确保正确的base64解码
            missing_padding = len(encoded_data) % 4
            if missing_padding:
                encoded_data += '=' * (4 - missing_padding)
            
            decoded_data = base64.b64decode(encoded_data).decode('utf-8')
            node_info = json.loads(decoded_data)
            
            # 安全获取字段，避免None错误
            server = node_info.get("add", "")
            port = node_info.get("port", 443)
            uuid = node_info.get("id", "")
            
            if not server or not uuid:
                logger.warning("VMess节点缺少必要字段")
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
                # 新格式: ss://method:password@server:port#name
                method = parsed.username
                password = parsed.password
            else:
                # 旧格式: ss://base64encoded@server:port#name 或 ss://base64encoded#name
                if '@' in link:
                    encoded_part = link[5:].split('@')[0]
                else:
                    encoded_part = link[5:].split('#')[0]
                
                if not encoded_part:
                    return None
                
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
                    logger.error(f"SS解码失败: {encoded_part}")
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
            
            # 获取密码，可能在username或auth参数中
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
                logger.warning(f"不支持的协议: {link[:20]}...")
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
            return {
                "status": "error",
                "error": "服务器地址或端口无效"
            }
            
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            result = sock.connect_ex((str(server), int(port)))
            end_time = time.time()
            sock.close()
            
            latency = round((end_time - start_time) * 1000, 2)
            
            if result == 0:
                return {
                    "status": "connected",
                    "latency_ms": latency
                }
            else:
                return {
                    "status": "failed",
                    "error": f"连接失败 (错误码: {result})"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"连接测试异常: {str(e)}"
            }
    
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
                
                # 限制测试时间
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
                
                # 根据速度评分
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
• 节点信息解析

📝 **使用方法：**
• 直接发送节点链接进行测速
• 支持的格式：vmess://, vless://, ss://, hy2://, hysteria2://

🔧 **VPS管理：**
• 在VPS中输入 `ikunss` 进入管理菜单

现在就发送节点链接开始测速吧！"""
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
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
            await update.message.reply_text("❌ 请发送有效的文本消息")
            return

        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在处理您的请求，请稍候...")
        
        try:
            # 检查是否是节点链接
            if any(text.startswith(prefix) for prefix in ['vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://']):
                await processing_message.edit_text("🔍 检测到节点链接，开始解析...")
                
                # 解析节点
                node = NodeParser.parse_single_node(text)
                if not node:
                    await processing_message.edit_text(
                        "❌ **节点解析失败**\n\n"
                        "可能的原因：\n"
                        "• 节点链接格式不正确\n"
                        "• 缺少必要的参数\n"
                        "• 编码问题\n\n"
                        "请检查节点链接是否完整和正确"
                    )
                    return
                
                await processing_message.edit_text("✅ 节点解析成功，开始测速...")
                
                # 执行测速
                result = SpeedTester.test_node(node)
                
                # 格式化结果
                result_text = f"📊 **测速结果**\n\n"
                result_text += f"{result.get('status_emoji', '📊')} **节点名称:** {result.get('name')}\n"
                result_text += f"🌐 **服务器:** {result.get('server')}:{result.get('port')}\n"
                result_text += f"🔗 **协议:** {result.get('protocol')}\n"
                
                if result.get('latency_ms') is not None:
                    result_text += f"⏱️ **延迟:** {result.get('latency_ms')}ms\n"
                
                if result.get('download_speed_mbps'):
                    result_text += f"⚡ **速度:** {result.get('download_speed_mbps')} MB/s\n"
                    result_text += f"📊 **测试时长:** {result.get('test_duration', 0)}s\n"
                    result_text += f"💾 **下载量:** {result.get('downloaded_mb', 0)}MB\n"
                
                result_text += f"📈 **状态:** {result.get('status_emoji')} {result.get('status_text')}\n"
                
                if result.get('error'):
                    result_text += f"❌ **错误:** {result.get('error')}\n"
                
                result_text += f"\n⏰ **测试时间:** {result.get('test_time')}"
                
                await processing_message.edit_text(result_text, parse_mode='Markdown')
                
            else:
                await processing_message.edit_text(
                    "❓ **无法识别的格式**\n\n"
                    "**支持的格式：**\n"
                    "• VMess: `vmess://...`\n"
                    "• VLess: `vless://...`\n"
                    "• Shadowsocks: `ss://...`\n"
                    "• Hysteria2: `hy2://...` 或 `hysteria2://...`\n"
                    "• Trojan: `trojan://...`\n\n"
                    "💡 **提示：** 直接粘贴完整的节点链接即可\n"
                    "🔧 **VPS管理：** 在服务器中输入 `ikunss` 进入管理菜单",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"消息处理过程中出错: {e}")
            error_msg = f"❌ **处理过程中出现错误**\n\n错误信息: {str(e)}\n\n请检查输入格式或稍后重试"
            try:
                await processing_message.edit_text(error_msg, parse_mode='Markdown')
            except:
                await processing_message.edit_text("❌ 处理失败，请稍后重试")
                
    except Exception as e:
        logger.error(f"handle_message 严重错误: {e}")
        try:
            await update.message.reply_text("❌ 系统错误，请稍后重试")
        except:
            pass

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")
    logger.error(f"Traceback: {traceback.format_exc()}")

# --- Main Function ---
def main() -> None:
    """启动机器人"""
    logger.info("🚀 启动 IKUN 测速机器人...")
    
    try:
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(f"{TELEGRAM_API_URL}/bot").build()
        
        # 注册错误处理器
        application.add_error_handler(error_handler)
        
        # 注册命令处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("✅ 处理器注册完成")

        # 启动机器人
        logger.info("🔄 开始轮询...")
        application.run_polling(
            poll_interval=1.0,
            timeout=30,
            bootstrap_retries=5,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.critical(f"❌ 机器人启动失败: {e}")
        logger.critical(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main()

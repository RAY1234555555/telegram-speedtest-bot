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
            encoded_data = link[8:].strip()
            missing_padding = len(encoded_data) % 4
            if missing_padding:
                encoded_data += '=' * (4 - missing_padding)
            
            decoded_data = base64.b64decode(encoded_data).decode('utf-8')
            node_info = json.loads(decoded_data)
            
            return {
                "protocol": "VMess",
                "name": node_info.get("ps", "VMess Node"),
                "server": node_info.get("add"),
                "port": int(node_info.get("port", 443)),
                "uuid": node_info.get("id"),
                "alterId": int(node_info.get("aid", 0)),
                "network": node_info.get("net", "tcp"),
                "tls": node_info.get("tls", ""),
                "host": node_info.get("host", ""),
                "path": node_info.get("path", "")
            }
        except Exception as e:
            logger.error(f"VMess解析失败: {e}")
            return None
    
    @staticmethod
    def parse_vless(link: str) -> Optional[Dict]:
        """解析VLess节点"""
        try:
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "VLess",
                "name": unquote(parsed.fragment) if parsed.fragment else "VLess Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "uuid": parsed.username,
                "encryption": query.get("encryption", ["none"])[0],
                "flow": query.get("flow", [""])[0],
                "security": query.get("security", ["none"])[0],
                "sni": query.get("sni", [""])[0]
            }
        except Exception as e:
            logger.error(f"VLess解析失败: {e}")
            return None
    
    @staticmethod
    def parse_shadowsocks(link: str) -> Optional[Dict]:
        """解析Shadowsocks节点"""
        try:
            parsed = urlparse(link)
            
            if parsed.username and parsed.password:
                method = parsed.username
                password = parsed.password
            else:
                # 处理旧格式
                encoded_part = link[5:].split('@')[0] if '@' in link else link[5:].split('#')[0]
                missing_padding = len(encoded_part) % 4
                if missing_padding:
                    encoded_part += '=' * (4 - missing_padding)
                
                decoded = base64.b64decode(encoded_part).decode('utf-8')
                if ':' in decoded:
                    method, password = decoded.split(':', 1)
                else:
                    method, password = "aes-256-gcm", decoded
            
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
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "Trojan",
                "name": unquote(parsed.fragment) if parsed.fragment else "Trojan Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": parsed.username,
                "sni": query.get("sni", [""])[0],
                "security": query.get("security", ["tls"])[0]
            }
        except Exception as e:
            logger.error(f"Trojan解析失败: {e}")
            return None
    
    @staticmethod
    def parse_hysteria2(link: str) -> Optional[Dict]:
        """解析Hysteria2节点"""
        try:
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "Hysteria2",
                "name": unquote(parsed.fragment) if parsed.fragment else "Hysteria2 Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": parsed.username or query.get("auth", [""])[0],
                "sni": query.get("sni", [""])[0],
                "obfs": query.get("obfs", [""])[0]
            }
        except Exception as e:
            logger.error(f"Hysteria2解析失败: {e}")
            return None
    
    @staticmethod
    def parse_single_node(link: str) -> Optional[Dict]:
        """解析单个节点"""
        link = link.strip()
        
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

# --- Subscription Parser ---
class SubscriptionParser:
    @staticmethod
    def fetch_subscription(url: str) -> Optional[str]:
        """获取订阅内容"""
        try:
            headers = {
                'User-Agent': 'clash-verge/v1.3.1',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            }
            
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            
            if response.status_code == 403:
                return None
            
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            logger.error(f"获取订阅失败: {e}")
            return None
    
    @staticmethod
    def parse_subscription_info(response) -> Dict:
        """解析订阅信息"""
        info = {}
        
        # 从响应头获取流量信息
        headers = response.headers if hasattr(response, 'headers') else {}
        
        if 'subscription-userinfo' in headers:
            userinfo = headers['subscription-userinfo']
            parts = userinfo.split(';')
            for part in parts:
                if '=' in part:
                    key, value = part.strip().split('=', 1)
                    try:
                        info[key] = int(value)
                    except ValueError:
                        info[key] = value
            
            # 计算流量信息
            if 'upload' in info and 'download' in info:
                info['used_traffic'] = info['upload'] + info['download']
                info['used_traffic_gb'] = round(info['used_traffic'] / (1024**3), 2)
            
            if 'total' in info:
                info['total_traffic_gb'] = round(info['total'] / (1024**3), 2)
                if 'used_traffic' in info:
                    info['remaining_traffic'] = info['total'] - info['used_traffic']
                    info['remaining_traffic_gb'] = round(info['remaining_traffic'] / (1024**3), 2)
                    info['usage_percentage'] = round((info['used_traffic'] / info['total']) * 100, 1)
            
            if 'expire' in info:
                try:
                    expire_time = datetime.fromtimestamp(info['expire'])
                    info['expire_date'] = expire_time.strftime('%Y/%m/%d %H:%M:%S')
                    remaining_days = (expire_time - datetime.now()).days
                    info['remaining_days'] = max(0, remaining_days)
                except:
                    pass
        
        return info
    
    @staticmethod
    def parse_subscription_content(content: str) -> List[Dict]:
        """解析订阅内容中的节点"""
        nodes = []
        
        try:
            # 尝试base64解码
            try:
                decoded_content = base64.b64decode(content).decode('utf-8')
                content = decoded_content
            except:
                pass
            
            # 按行分割处理
            lines = content.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                node = NodeParser.parse_single_node(line)
                if node:
                    nodes.append(node)
        
        except Exception as e:
            logger.error(f"解析订阅内容失败: {e}")
        
        return nodes
    
    @staticmethod
    def analyze_subscription(url: str) -> Dict:
        """分析订阅"""
        try:
            # 获取订阅内容
            response = requests.get(url, headers={
                'User-Agent': 'clash-verge/v1.3.1'
            }, timeout=30, verify=False)
            
            if response.status_code == 403:
                return {
                    "status": "error",
                    "error": "订阅链接被WAF拦截，请检查链接或稍后重试"
                }
            
            response.raise_for_status()
            
            # 解析订阅信息
            sub_info = SubscriptionParser.parse_subscription_info(response)
            
            # 解析节点
            nodes = SubscriptionParser.parse_subscription_content(response.text)
            
            # 统计信息
            protocols = {}
            regions = {}
            
            for node in nodes:
                protocol = node.get('protocol', 'Unknown')
                protocols[protocol] = protocols.get(protocol, 0) + 1
                
                # 简单的地区检测
                name = node.get('name', '').lower()
                server = node.get('server', '').lower()
                text = f"{name} {server}"
                
                region = "🌍 其他"
                if any(keyword in text for keyword in ['hk', 'hong kong', '香港']):
                    region = "🇭🇰 香港"
                elif any(keyword in text for keyword in ['tw', 'taiwan', '台湾']):
                    region = "🇹🇼 台湾"
                elif any(keyword in text for keyword in ['jp', 'japan', '日本']):
                    region = "🇯🇵 日本"
                elif any(keyword in text for keyword in ['sg', 'singapore', '新加坡']):
                    region = "🇸🇬 新加坡"
                elif any(keyword in text for keyword in ['us', 'usa', '美国']):
                    region = "🇺🇸 美国"
                elif any(keyword in text for keyword in ['uk', 'britain', '英国']):
                    region = "🇬🇧 英国"
                
                regions[region] = regions.get(region, 0) + 1
            
            return {
                "status": "success",
                "subscription_info": sub_info,
                "nodes": nodes,
                "statistics": {
                    "total_nodes": len(nodes),
                    "protocols": protocols,
                    "regions": regions
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

# --- Speed Tester ---
class SpeedTester:
    @staticmethod
    def test_connectivity(server: str, port: int) -> Dict:
        """测试连通性"""
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            result = sock.connect_ex((server, port))
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
                "error": str(e)
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
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    def test_node(node: Dict) -> Dict:
        """测试节点"""
        result = {
            "name": node.get('name', 'Unknown Node'),
            "server": node.get('server'),
            "port": node.get('port'),
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
        else:
            result['status_emoji'] = '❌'
            result['status_text'] = '连接失败'
        
        return result

# --- Management Commands ---
class BotManager:
    @staticmethod
    def get_service_status() -> str:
        """获取服务状态"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'telegram-speedtest-bot'], 
                                  capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "unknown"
    
    @staticmethod
    def restart_service() -> bool:
        """重启服务"""
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'telegram-speedtest-bot'], 
                          check=True)
            return True
        except:
            return False
    
    @staticmethod
    def stop_service() -> bool:
        """停止服务"""
        try:
            subprocess.run(['sudo', 'systemctl', 'stop', 'telegram-speedtest-bot'], 
                          check=True)
            return True
        except:
            return False
    
    @staticmethod
    def get_logs() -> str:
        """获取日志"""
        try:
            result = subprocess.run(['sudo', 'journalctl', '-u', 'telegram-speedtest-bot', 
                                   '--no-pager', '-n', '20'], 
                                  capture_output=True, text=True)
            return result.stdout
        except:
            return "无法获取日志"
    
    @staticmethod
    def update_project() -> bool:
        """更新项目"""
        try:
            os.chdir('/opt/telegram-speedtest-bot')
            subprocess.run(['git', 'pull'], check=True)
            subprocess.run(['sudo', 'systemctl', 'restart', 'telegram-speedtest-bot'], 
                          check=True)
            return True
        except:
            return False

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
• 订阅链接解析与流量分析
• 真实速度测试
• 节点连通性检测

📝 **使用方法：**
• 直接发送节点链接进行测速
• 发送订阅链接获取分析
• 发送多个节点进行批量测试

🔧 **管理命令：**
• 发送 `ikunss` 进入管理菜单

现在就发送节点链接开始测速吧！"""
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"start 命令处理失败: {e}")

async def ikunss_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """管理命令"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        keyboard = [
            [InlineKeyboardButton("🔄 重启服务", callback_data="mgmt_restart")],
            [InlineKeyboardButton("⏹️ 停止服务", callback_data="mgmt_stop")],
            [InlineKeyboardButton("🔄 更新项目", callback_data="mgmt_update")],
            [InlineKeyboardButton("📊 当前状态", callback_data="mgmt_status")],
            [InlineKeyboardButton("📋 查看日志", callback_data="mgmt_logs")],
            [InlineKeyboardButton("🗑️ 卸载服务", callback_data="mgmt_uninstall")],
            [InlineKeyboardButton("❌ 退出", callback_data="mgmt_exit")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛠️ **IKUN测速机器人管理面板**\n\n请选择要执行的操作：",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"ikunss 命令处理失败: {e}")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("mgmt_"):
            if data == "mgmt_restart":
                await query.edit_message_text("🔄 正在重启服务...")
                success = BotManager.restart_service()
                if success:
                    await query.edit_message_text("✅ 服务重启成功！")
                else:
                    await query.edit_message_text("❌ 服务重启失败！")
            
            elif data == "mgmt_stop":
                await query.edit_message_text("⏹️ 正在停止服务...")
                success = BotManager.stop_service()
                if success:
                    await query.edit_message_text("✅ 服务已停止！")
                else:
                    await query.edit_message_text("❌ 服务停止失败！")
            
            elif data == "mgmt_update":
                await query.edit_message_text("🔄 正在更新项目...")
                success = BotManager.update_project()
                if success:
                    await query.edit_message_text("✅ 项目更新成功！服务已重启。")
                else:
                    await query.edit_message_text("❌ 项目更新失败！")
            
            elif data == "mgmt_status":
                status = BotManager.get_service_status()
                status_text = f"📊 **服务状态**\n\n"
                status_text += f"状态: {status}\n"
                status_text += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                await query.edit_message_text(status_text, parse_mode='Markdown')
            
            elif data == "mgmt_logs":
                await query.edit_message_text("📋 正在获取日志...")
                logs = BotManager.get_logs()
                if len(logs) > 4000:
                    logs = logs[-4000:]
                await query.edit_message_text(f"📋 **最近日志**\n\n```\n{logs}\n```", parse_mode='Markdown')
            
            elif data == "mgmt_uninstall":
                await query.edit_message_text(
                    "⚠️ **确认卸载**\n\n这将完全删除服务和所有文件！\n\n确定要继续吗？",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ 确认卸载", callback_data="mgmt_uninstall_confirm")],
                        [InlineKeyboardButton("❌ 取消", callback_data="mgmt_exit")]
                    ]),
                    parse_mode='Markdown'
                )
            
            elif data == "mgmt_uninstall_confirm":
                await query.edit_message_text("🗑️ 正在卸载服务...")
                try:
                    subprocess.run(['sudo', 'systemctl', 'stop', 'telegram-speedtest-bot'], check=True)
                    subprocess.run(['sudo', 'systemctl', 'disable', 'telegram-speedtest-bot'], check=True)
                    subprocess.run(['sudo', 'rm', '/etc/systemd/system/telegram-speedtest-bot.service'], check=True)
                    subprocess.run(['sudo', 'rm', '-rf', '/opt/telegram-speedtest-bot'], check=True)
                    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
                    await query.edit_message_text("✅ 服务已完全卸载！")
                except:
                    await query.edit_message_text("❌ 卸载过程中出现错误！")
            
            elif data == "mgmt_exit":
                await query.edit_message_text("👋 已退出管理面板")
                
    except Exception as e:
        logger.error(f"回调查询处理失败: {e}")

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

        # 处理管理命令
        if text.lower() == 'ikunss':
            await ikunss_command(update, context)
            return

        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在处理您的请求，请稍候...")
        
        try:
            # 检查是否是单个节点链接
            if any(text.startswith(prefix) for prefix in ['vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://']):
                await processing_message.edit_text("🔍 检测到节点链接，开始解析和测速...")
                
                # 解析节点
                node = NodeParser.parse_single_node(text)
                if not node:
                    await processing_message.edit_text("❌ 节点链接解析失败，请检查格式是否正确")
                    return
                
                # 执行测速
                result = SpeedTester.test_node(node)
                
                # 格式化结果
                result_text = f"📊 **测速结果**\n\n"
                result_text += f"{result.get('status_emoji', '📊')} **节点名称:** {result.get('name')}\n"
                result_text += f"🌐 **服务器:** {result.get('server')}:{result.get('port')}\n"
                result_text += f"🔗 **协议:** {result.get('protocol')}\n"
                
                if result.get('latency_ms'):
                    result_text += f"⏱️ **延迟:** {result.get('latency_ms')}ms\n"
                
                if result.get('download_speed_mbps'):
                    result_text += f"⚡ **速度:** {result.get('download_speed_mbps')} MB/s\n"
                    result_text += f"📊 **状态:** {result.get('status_emoji')} {result.get('status_text')}\n"
                    if result.get('downloaded_mb'):
                        result_text += f"💾 **剩余流量:** 500GB\n"
                else:
                    result_text += f"📊 **状态:** {result.get('status_emoji')} {result.get('status_text')}\n"
                
                result_text += f"\n注意: 这是演示结果，实际功能正在开发中"
                
                await processing_message.edit_text(result_text, parse_mode='Markdown')
                
            elif text.startswith(('http://', 'https://')):
                await processing_message.edit_text("🔗 检测到订阅链接，正在分析...")
                
                # 分析订阅
                sub_result = SubscriptionParser.analyze_subscription(text)
                
                if sub_result.get("status") == "success":
                    sub_info = sub_result.get("subscription_info", {})
                    stats = sub_result.get("statistics", {})
                    
                    result_text = "📊 **订阅分析结果**\n\n"
                    
                    # 流量信息
                    if sub_info.get('total_traffic_gb'):
                        used = sub_info.get('used_traffic_gb', 0)
                        total = sub_info.get('total_traffic_gb', 0)
                        remaining = sub_info.get('remaining_traffic_gb', 0)
                        percentage = sub_info.get('usage_percentage', 0)
                        
                        result_text += f"📈 **流量详情:** {used} GB / {total} GB\n"
                        result_text += f"📊 **使用进度:** {percentage}%\n"
                        result_text += f"💾 **剩余可用:** {remaining} GB\n"
                    
                    # 过期时间
                    if sub_info.get('expire_date'):
                        remaining_days = sub_info.get('remaining_days', 0)
                        result_text += f"⏰ **过期时间:** {sub_info['expire_date']} (剩余{remaining_days}天)\n"
                    
                    result_text += "\n"
                    
                    # 节点统计
                    total_nodes = stats.get('total_nodes', 0)
                    protocols = stats.get('protocols', {})
                    regions = stats.get('regions', {})
                    
                    result_text += f"🌐 **节点总数:** {total_nodes}\n"
                    
                    if protocols:
                        protocol_list = ', '.join(protocols.keys())
                        result_text += f"🔐 **协议类型:** {protocol_list}\n"
                    
                    if regions:
                        region_list = list(regions.keys())[:5]  # 显示前5个地区
                        regions_text = ', '.join([r.split(' ', 1)[1] if ' ' in r else r for r in region_list])
                        result_text += f"🗺️ **覆盖范围:** {regions_text}\n"
                    
                    await processing_message.edit_text(result_text, parse_mode='Markdown')
                    
                    # 如果有节点，询问是否测速
                    nodes = sub_result.get("nodes", [])
                    if nodes and len(nodes) > 0:
                        test_keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🚀 测试前5个节点", callback_data="test_nodes_5")],
                            [InlineKeyboardButton("📊 测试全部节点", callback_data="test_nodes_all")]
                        ])
                        
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"发现 {len(nodes)} 个节点，是否需要测速？",
                            reply_markup=test_keyboard
                        )
                else:
                    await processing_message.edit_text(
                        f"❌ **订阅分析失败**\n\n错误: {sub_result.get('error', '未知错误')}",
                        parse_mode='Markdown'
                    )
                
            else:
                await processing_message.edit_text(
                    "❓ **无法识别的格式**\n\n"
                    "**支持的格式：**\n"
                    "• 单个节点链接 (vmess://, vless://, ss://, hy2://, trojan://)\n"
                    "• 订阅链接 (http/https)\n"
                    "• 发送 `ikunss` 进入管理菜单\n\n"
                    "💡 **提示：** 直接粘贴节点链接或订阅地址即可",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"消息处理过程中出错: {e}")
            await processing_message.edit_text(f"❌ 处理过程中出现错误: {str(e)}")
                
    except Exception as e:
        logger.error(f"handle_message 严重错误: {e}")

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")

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
        application.add_handler(CommandHandler("ikunss", ikunss_command))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
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
        sys.exit(1)

if __name__ == '__main__':
    main()

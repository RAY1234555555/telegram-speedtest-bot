# bot.py - Fixed version with better error handling and network connectivity
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

# Import our custom modules
try:
    from parser import parse_single_node, parse_subscription_link, get_node_info_summary
    from speedtester import test_node_speed, test_multiple_nodes_speed, format_test_result
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    print("请确保所有必要的文件都存在")
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

# Reduce telegram library logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

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

# --- Main Keyboard ---
def get_main_keyboard():
    """获取主菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("🚀 单节点测速", callback_data="help_single")],
        [InlineKeyboardButton("📊 批量测速", callback_data="help_batch")],
        [InlineKeyboardButton("🔗 订阅测速", callback_data="help_subscription")],
        [InlineKeyboardButton("📋 支持协议", callback_data="help_protocols")],
        [InlineKeyboardButton("⚙️ 设置选项", callback_data="settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # 获取详细错误信息
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    logger.error(f"Traceback: {tb_string}")
    
    # 如果是网络错误，记录但不发送消息给用户
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("网络连接问题，稍后重试")
        return
    
    # 尝试通知用户
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ 系统出现错误，请稍后重试"
            )
        except Exception as e:
            logger.error(f"无法发送错误消息: {e}")

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """启动命令处理"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        logger.info(f"👤 用户 {username} ({user_id}) 发送了 /start 命令")
        
        if not is_authorized(user_id):
            logger.warning(f"🚫 未授权用户尝试访问: {user_id}")
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        welcome_text = """🎉 **欢迎使用全能测速机器人 v2.0！**

🚀 **功能特色：**
• 支持多种协议：VMess, VLess, SS, Hysteria2, Trojan
• 订阅链接批量测速
• 实时速度和延迟检测
• 节点信息详细展示
• 流量使用情况查询

📝 **快速开始：**
直接发送节点链接或订阅地址即可开始测速！

点击下方按钮了解更多功能 👇"""
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ 成功回复用户 {username}")
        
    except Exception as e:
        logger.error(f"start 命令处理失败: {e}")
        try:
            await update.message.reply_text("❌ 启动失败，请稍后重试")
        except:
            pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """帮助命令处理"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        help_text = """📖 **使用说明**

🔸 **单节点测速**
直接发送节点链接：
`vmess://...`
`vless://...`
`ss://...`
`hy2://...`
`trojan://...`

🔸 **批量测速**
发送多个节点（每行一个）

🔸 **订阅测速**
发送订阅链接：
`https://your-subscription-url`

🔸 **快捷命令**
/start - 开始使用
/help - 查看帮助
/status - 查看状态
/ping - 测试连接

💡 **提示：** 测速过程可能需要几秒钟，请耐心等待！"""
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"help 命令处理失败: {e}")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ping 命令 - 测试机器人响应"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        start_time = time.time()
        message = await update.message.reply_text("🏓 Pong!")
        end_time = time.time()
        
        response_time = round((end_time - start_time) * 1000, 2)
        
        await message.edit_text(f"🏓 Pong!\n⏱️ 响应时间: {response_time}ms")
        
        logger.info(f"✅ Ping 命令成功，响应时间: {response_time}ms")
        
    except Exception as e:
        logger.error(f"ping 命令处理失败: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """状态命令"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        status_text = f"""📊 **机器人状态**

🤖 状态: 运行中 ✅
⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🌐 API 地址: {TELEGRAM_API_URL}
👥 授权用户: {len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else '无限制'}
🔧 版本: v2.0.0

🌐 **支持协议:**
• VMess ✅
• VLess ✅  
• Shadowsocks ✅
• Hysteria2 ✅
• Trojan ✅

📈 **使用统计:**
• 测速次数: {user_data.get(user_id, {}).get('test_count', 0)}
• 节点数量: {user_data.get(user_id, {}).get('node_count', 0)}"""
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"status 命令处理失败: {e}")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "main_menu":
            await query.edit_message_text(
                "🏠 主菜单\n\n选择您需要的功能：",
                reply_markup=get_main_keyboard()
            )
        elif data == "help_single":
            help_text = """🚀 **单节点测速**

支持的格式：
• `vmess://base64encoded`
• `vless://uuid@server:port?params#name`
• `ss://method:password@server:port#name`
• `hy2://auth@server:port?params#name`
• `trojan://password@server:port?params#name`

直接发送节点链接即可开始测速！"""
            await query.edit_message_text(help_text, parse_mode='Markdown')
        elif data == "help_protocols":
            protocols_text = """📋 **支持的协议**

✅ **VMess**
- 支持 TCP/WS/gRPC
- 支持 TLS/Reality

✅ **VLess** 
- 支持 XTLS-Vision
- 支持 Reality

✅ **Shadowsocks**
- 支持各种加密方式
- 支持 SIP003 插件

✅ **Hysteria2**
- 基于 QUIC 协议
- 高速传输

✅ **Trojan**
- TLS 伪装
- 高安全性

🔄 更多协议持续添加中..."""
            await query.edit_message_text(protocols_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"回调查询处理失败: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理普通消息"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        if not is_authorized(user_id):
            logger.warning(f"🚫 未授权用户 {username} ({user_id}) 尝试发送消息")
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        text = update.message.text
        if not text:
            return

        logger.info(f"📨 收到用户 {username} 的消息: {text[:50]}...")

        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在处理您的请求，请稍候...")
        
        try:
            # 简单的测试响应
            if text.lower() in ['test', '测试', 'hello', '你好']:
                await processing_message.edit_text(
                    "✅ 机器人运行正常！\n\n"
                    "🚀 发送节点链接开始测速\n"
                    "📋 发送 /help 查看使用说明\n"
                    "📊 发送 /status 查看状态"
                )
                return
            
            # 检查是否是节点链接
            if any(text.startswith(prefix) for prefix in ['vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://']):
                await processing_message.edit_text("🔍 检测到节点链接，正在解析...")
                
                # 这里可以添加实际的节点解析和测速逻辑
                # 目前先返回一个模拟结果
                await asyncio.sleep(2)  # 模拟处理时间
                
                result_text = """📊 **测速结果**

📡 节点名称: 测试节点
🌐 服务器: example.com:443
🔗 协议: VMess
📍 地区: 🇺🇸 美国
⚡ 速度: 25.6 MB/s
⏱️ 延迟: 120 ms
📊 状态: ✅ 正常
💾 剩余流量: 500GB

*注意: 这是演示结果，实际功能正在开发中*"""
                
                await processing_message.edit_text(result_text, parse_mode='Markdown')
                
            elif text.startswith(('http://', 'https://')):
                await processing_message.edit_text("🔗 检测到订阅链接，正在获取...")
                await asyncio.sleep(1)
                await processing_message.edit_text("📊 订阅解析功能正在开发中，敬请期待！")
                
            else:
                await processing_message.edit_text(
                    "❓ 无法识别的格式\n\n"
                    "支持的格式：\n"
                    "• 节点链接 (vmess://, vless://, ss://, 等)\n"
                    "• 订阅链接 (http/https)\n"
                    "• 发送 'test' 测试机器人\n"
                    "• 发送 /help 查看帮助"
                )
            
            # 更新用户统计
            if user_id not in user_data:
                user_data[user_id] = {'test_count': 0, 'node_count': 0}
            user_data[user_id]['test_count'] += 1
            
        except Exception as e:
            logger.error(f"消息处理过程中出错: {e}")
            try:
                await processing_message.edit_text("❌ 处理过程中出现错误，请稍后重试")
            except:
                pass
                
    except Exception as e:
        logger.error(f"handle_message 严重错误: {e}")
        try:
            await update.message.reply_text("❌ 系统错误，请稍后重试")
        except:
            pass

# --- Main Function ---
def main() -> None:
    """启动机器人"""
    logger.info("🚀 启动 Telegram 测速机器人 v2.0...")
    logger.info(f"🌐 API 地址: {TELEGRAM_API_URL}")
    logger.info(f"👥 授权用户数: {len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else '无限制'}")
    
    try:
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(f"{TELEGRAM_API_URL}/bot").build()
        
        # 注册错误处理器
        application.add_error_handler(error_handler)
        
        # 注册命令处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("ping", ping_command))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("✅ 处理器注册完成")

        # 启动机器人
        logger.info("🔄 开始轮询...")
        application.run_polling(
            timeout=30,
            bootstrap_retries=5,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )

    except Exception as e:
        logger.critical(f"❌ 机器人启动失败: {e}")
        logger.critical(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main()

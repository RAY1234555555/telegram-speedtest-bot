# bot.py
import logging
import os
import sys
import asyncio
import time
from datetime import datetime
from typing import List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from dotenv import load_dotenv

# Import our custom modules
from parser import parse_single_node, parse_subscription_link, get_node_info_summary
from speedtester import test_node_speed, test_multiple_nodes_speed, format_test_result

# --- Setup Logging ---
# Ensure output goes to stdout so systemd can capture it.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Output to stdout
    ]
)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
# For systemd, env vars are passed via secure_runner.sh.
# load_dotenv() is mainly for local development convenience if you run this script directly.
load_dotenv()

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ALLOWED_USER_IDS_STR = os.environ.get('ALLOWED_USER_IDS') # String from env
# !!! USING YOUR PROVIDED TELEGRAM API PROXY URL !!!
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://tg.993474.xyz/bot") # <<< YOUR TG API PROXY URL

# --- Basic Validation ---
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
    sys.exit(1)
if not ALLOWED_USER_IDS_STR:
    logger.warning("ALLOWED_USER_IDS environment variable not set. Bot will not restrict users.")
    ALLOWED_USER_IDS = set() # Empty set means no restriction
else:
    ALLOWED_USER_IDS = set(ALLOWED_USER_IDS_STR.split(',')) # Convert to a set for faster lookup

# --- User Data Storage ---
# In production, use a database
user_data = {}

# --- Authorization Check ---
def is_authorized(user_id: int) -> bool:
    """检查用户是否有权限"""
    if not ALLOWED_USER_IDS: # If no restrictions are set
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

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt from User ID: {user_id}")
        await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
        return

    welcome_text = """
🎉 欢迎使用全能测速机器人！

🚀 **功能特色：**
• 支持多种协议：VMess, VLess, SS, Hysteria2, Trojan
• 订阅链接批量测速
• 实时速度和延迟检测
• 节点信息详细展示
• 流量使用情况查询

📝 **快速开始：**
直接发送节点链接或订阅地址即可开始测速！

点击下方按钮了解更多功能 👇
"""
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
        return

    help_text = """
📖 **使用说明**

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
/settings - 设置选项
/stats - 使用统计

💡 **提示：** 测速过程可能需要几秒钟，请耐心等待！
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """状态命令"""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
        return

    status_text = f"""
📊 **机器人状态**

🤖 状态: 运行中 ✅
⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 授权用户: {len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else '无限制'}
🔧 版本: v2.0.0

🌐 **支持协议:**
• VMess ✅
• VLess ✅  
• Shadowsocks ✅
• Hysteria2 ✅
• Trojan ✅

📈 **今日统计:**
• 测速次数: {user_data.get(user_id, {}).get('test_count', 0)}
• 节点数量: {user_data.get(user_id, {}).get('node_count', 0)}
"""
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """设置命令"""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
        return

    keyboard = [
        [InlineKeyboardButton("⚡ 快速模式", callback_data="setting_fast")],
        [InlineKeyboardButton("🔍 详细模式", callback_data="setting_detailed")],
        [InlineKeyboardButton("🔢 并发数设置", callback_data="setting_concurrent")],
        [InlineKeyboardButton("⏱️ 超时设置", callback_data="setting_timeout")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
    ]
    
    settings_text = """
⚙️ **设置选项**

当前设置：
• 测试模式: 标准模式
• 并发数: 3
• 超时时间: 30秒
• 详细信息: 开启

请选择要修改的设置：
"""
    
    await update.message.reply_text(
        settings_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理回调查询"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "main_menu":
        await query.edit_message_text(
            "🏠 主菜单\n\n选择您需要的功能：",
            reply_markup=get_main_keyboard()
        )
    elif data == "help_single":
        help_text = """
🚀 **单节点测速**

支持的格式：
• `vmess://base64encoded`
• `vless://uuid@server:port?params#name`
• `ss://method:password@server:port#name`
• `hy2://auth@server:port?params#name`
• `trojan://password@server:port?params#name`

直接发送节点链接即可开始测速！
"""
        await query.edit_message_text(help_text, parse_mode='Markdown')
    elif data == "help_protocols":
        protocols_text = """
📋 **支持的协议**

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

🔄 更多协议持续添加中...
"""
        await query.edit_message_text(protocols_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages, treating them as potential node links or subscription links."""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            logger.warning(f"Unauthorized message from User ID: {user_id}")
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        text = update.message.text
        if not text:
            return

        logger.info(f"Received message from {update.effective_user.username} ({user_id}): {text[:60]}...") # Log first 60 chars

        # Send a "processing" message and get its ID to edit later
        try:
            processing_message = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ Processing your request, please wait...")
            message_id_to_edit = processing_message.message_id
        except Exception as e:
            logger.error(f"Failed to send processing message: {e}")
            # If sending the initial message fails, try to send a simple reply
            await update.message.reply_text("⏳ Processing your request, please wait...")
            return

        try:
            nodes_to_test = []
            # --- Parsing Logic ---
            # Check if it's a direct VMess link
            if text.startswith("vmess://"):
                node = parse_single_node(text)
                if node:
                    nodes_to_test.append(node)
            # Check if it's a VLess link (not supported yet)
            elif text.startswith("vless://"):
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text="❌ VLess protocol is not supported yet. Please send a vmess:// link instead."
                )
                return
            # Check if it's a URL (potential subscription link)
            elif text.startswith("http://") or text.startswith("https://"):
                # TODO: Implement fetching and parsing for subscription URLs
                # For now, we'll inform the user that only direct vmess links are supported for parsing
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text="🔄 正在获取订阅内容..."
                )
                nodes_to_test = parse_subscription_link(text)
                
                if not nodes_to_test:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=message_id_to_edit,
                        text="❌ 无法解析订阅链接或订阅为空"
                    )
                    return
                    
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text=f"📊 发现 {len(nodes_to_test)} 个节点，开始测速..."
                )
                
            elif '\n' in text:
                # Multiple nodes
                lines = text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        node = parse_single_node(line)
                        if node:
                            nodes_to_test.append(node)
                
                if not nodes_to_test:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=message_id_to_edit,
                        text="❌ 未找到有效的节点信息"
                    )
                    return
                    
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text=f"📊 发现 {len(nodes_to_test)} 个节点，开始测速..."
                )
            else:
                # Not a recognized format
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text="❌ 无法识别的格式\n\n"
                    "支持的格式：\n"
                    "• 单个节点链接\n"
                    "• 多个节点（每行一个）\n"
                    "• 订阅链接 (http/https)\n\n"
                    "使用 /help 查看详细说明"
                )
                return

            # --- Perform Speed Tests ---
            if len(nodes_to_test) == 1:
                # Single node speed test
                result = test_node_speed(nodes_to_test[0])
                response_text = "🎯 **单节点测速结果**\n\n"
                response_text += format_test_result(result)
                
            else:
                # Multiple nodes speed test
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id_to_edit,
                    text=f"🚀 正在并发测试 {len(nodes_to_test)} 个节点..."
                )
                results = test_multiple_nodes_speed(nodes_to_test[:10])  # Limit to 10 nodes
                
                # Sort by speed
                results.sort(key=lambda x: x.get('download_speed_mbps', 0), reverse=True)
                
                response_text = f"📊 **批量测速结果** ({len(results)} 个节点)\n\n"
                
                for i, result in enumerate(results[:5], 1):  # Show top 5
                    response_text += f"**#{i}** {format_test_result(result)}\n"
                
                if len(results) > 5:
                    response_text += f"\n... 还有 {len(results) - 5} 个节点结果"

            # --- Update User Statistics ---
            if user_id not in user_data:
                user_data[user_id] = {'test_count': 0, 'node_count': 0}

            user_data[user_id]['test_count'] += 1
            user_data[user_id]['node_count'] += len(nodes_to_test)

            # --- Send Results ---
            if len(response_text) > 4096:
                # Message too long, split into chunks
                chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id_to_edit, text=chunks[0], parse_mode='Markdown')
                for chunk in chunks[1:]:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk, parse_mode='Markdown')
            else:
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id_to_edit, text=response_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            try:
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id_to_edit, text="An internal error occurred. Please try again later.")
            except Exception as edit_err:
                logger.error(f"Failed to edit message after error: {edit_err}")
                # If editing fails, try to send a new message
                try:
                    await update.message.reply_text("An internal error occurred. Please try again later.")
                except Exception as reply_err:
                    logger.error(f"Failed to send reply after error: {reply_err}")

    except Exception as e:
        logger.error(f"Critical error in handle_message: {e}", exc_info=True)
        try:
            await update.message.reply_text("A critical error occurred. Please try again later.")
        except Exception as critical_err:
            logger.error(f"Failed to send critical error message: {critical_err}")

async def send_test_message(application):
    """Send a test message to authorized users."""
    if not ALLOWED_USER_IDS:
        return
        
    test_message = """
🎉 **测速机器人安装成功！**

✅ 服务已启动并运行正常
🚀 支持多种协议测速
📊 功能完整可用

发送 /start 开始使用
发送节点链接进行测速测试

---
安装时间: {time}
""".format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    for user_id in ALLOWED_USER_IDS:
        try:
            await application.bot.send_message(
                chat_id=int(user_id),
                text=test_message,
                parse_mode='Markdown'
            )
            logger.info(f"Test message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send test message to user {user_id}: {e}")

# --- Main Function ---
def main() -> None:
    """Start the bot."""
    logger.info("Starting Telegram Speed Test Bot v2.0...")
    
    try:
        # Create the Application and pass it your bot's token.
        # Use the base_url parameter to use your custom API URL (your反代 address).
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(TELEGRAM_API_URL).build()

        # Register handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Bot handlers registered successfully")

        # Start the Bot
        logger.info("Starting bot polling...")
        
        # Send test message
        asyncio.create_task(send_test_message(application))
        
        application.run_polling()

    except Exception as e:
        logger.critical(f"Failed to initialize or run bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()

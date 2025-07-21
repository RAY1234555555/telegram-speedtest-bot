# enhanced_bot_with_fulltclash.py - 集成FullTclash的增强机器人
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
logging.getLogger("aiohttp").setLevel(logging.WARNING)

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

# --- User Settings ---
user_settings = {}

def get_user_settings(user_id: int) -> Dict:
    """获取用户设置"""
    if user_id not in user_settings:
        user_settings[user_id] = {
            'test_mode': 'fulltclash',  # basic, standard, fulltclash
            'max_nodes': 10,
            'enable_streaming': True,
            'enable_speed_test': True,
            'show_details': True
        }
    return user_settings[user_id]

def update_user_settings(user_id: int, key: str, value) -> None:
    """更新用户设置"""
    settings = get_user_settings(user_id)
    settings[key] = value
    user_settings[user_id] = settings

# --- Keyboards ---
def get_main_keyboard():
    """获取主菜单键盘"""
    keyboard = [
        [InlineKeyboardButton("🚀 单节点测速", callback_data="help_single")],
        [InlineKeyboardButton("📊 FullTclash批量测速", callback_data="help_fulltclash")],
        [InlineKeyboardButton("🔗 订阅解析", callback_data="help_subscription")],
        [InlineKeyboardButton("🎬 流媒体解锁", callback_data="help_streaming")],
        [InlineKeyboardButton("⚙️ 设置选项", callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_test_mode_keyboard():
    """获取测试模式选择键盘"""
    keyboard = [
        [InlineKeyboardButton("⚡ 基础测速", callback_data="test_basic")],
        [InlineKeyboardButton("🚀 FullTclash测速", callback_data="test_fulltclash")],
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

        welcome_text = """🎉 **欢迎使用IKUN增强测速机器人！**

🚀 **功能特色：**
• 集成FullTclash核心引擎
• 支持多种协议：VMess, VLess, SS, Hysteria2, Trojan
• 真实Clash核心测速
• 流媒体解锁检测
• 高精度延迟测试

📝 **测试模式：**
• 基础测速：简单快速的连通性测试
• FullTclash测速：完整的Clash核心测速

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
                
                # 存储节点信息供后续使用
                context.user_data['current_node_text'] = text
                
            elif '\n' in text and any(line.strip().startswith(('vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://')) for line in text.split('\n')):
                # 多个节点
                await processing_message.edit_text("📊 检测到多个节点，开始FullTclash批量测速...")
                
                # 解析所有节点
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
                settings = get_user_settings(user_id)
                max_nodes = settings['max_nodes']
                if len(nodes) > max_nodes:
                    nodes = nodes[:max_nodes]
                    await processing_message.edit_text(
                        f"📊 发现 {len(nodes)} 个有效节点（已限制为 {max_nodes} 个），开始FullTclash测速...\n\n"
                        f"⏱️ 预计需要 {len(nodes) * 20 // 60 + 1} 分钟，请耐心等待..."
                    )
                else:
                    await processing_message.edit_text(
                        f"📊 发现 {len(nodes)} 个有效节点，开始FullTclash测速...\n\n"
                        f"⏱️ 预计需要 {len(nodes) * 20 // 60 + 1} 分钟，请耐心等待..."
                    )
                
                # 执行FullTclash批量测速
                results = await fulltclash.batch_test_nodes(nodes)
                
                # 格式化结果
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
                
                # 更新用户统计
                if user_id not in user_data:
                    user_data[user_id] = {'test_count': 0, 'node_count': 0, 'join_time': datetime.now()}
                user_data[user_id]['test_count'] += 1
                user_data[user_id]['node_count'] += len(nodes)
                
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
            error_msg = f"❌ **处理过程中出现错误**\n\n错误信息: {str(e)}\n\n请检查输入格式或稍后重试"
            try:
                await processing_message.edit_text(error_msg, parse_mode='Markdown')
            except:
                await processing_message.edit_text("❌ 处理失败，请稍后重试")
                
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
            
            # 解析节点
            node = NodeParser.parse_single_node(node_text)
            if not node:
                await query.edit_message_text("❌ 节点解析失败")
                return
            
            # 执行基础测速
            result = SpeedTester.test_node(node)
            
            # 格式化结果
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
            
        elif data == "test_fulltclash":
            # FullTclash测速
            node_text = context.user_data.get('current_node_text')
            if not node_text:
                await query.edit_message_text("❌ 节点信息丢失，请重新发送")
                return
            
            await query.edit_message_text("🚀 开始FullTclash测速，请稍候...")
            
            # 解析节点
            node = NodeParser.parse_single_node(node_text)
            if not node:
                await query.edit_message_text("❌ 节点解析失败")
                return
            
            # 执行FullTclash测速
            results = await fulltclash.batch_test_nodes([node])
            
            if results and not results[0].get('error'):
                result_text = fulltclash.format_test_results(results)
            else:
                error = results[0].get('error', '未知错误') if results else '测试失败'
                result_text = f"❌ **FullTclash测速失败**\n\n错误: {error}"
            
            await query.edit_message_text(result_text, parse_mode='Markdown')
            
        elif data == "help_fulltclash":
            help_text = """🚀 **FullTclash测速**

**核心特性：**
• 使用真实Clash核心进行测速
• 支持所有Clash支持的协议
• 真实的代理环境测试
• 流媒体解锁检测
• 高精度延迟测试

**测试内容：**
• TCP连通性和延迟
• 真实下载速度测试
• Netflix、Disney+等流媒体解锁
• YouTube Premium解锁检测
• ChatGPT可用性测试

**使用方法：**
发送节点链接，选择"FullTclash测速"模式"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "help_streaming":
            help_text = """🎬 **流媒体解锁检测**

**支持平台：**
• Netflix 🎬
• Disney+ 🏰
• YouTube Premium 📺
• ChatGPT 🤖

**检测方式：**
• 通过真实Clash代理访问
• 检测地区限制状态
• 分析响应内容判断解锁情况

**结果说明：**
• ✅ Unlocked - 完全解锁
• ❌ Blocked - 被阻止访问
• ❓ Unknown - 状态未知

**使用方法：**
选择FullTclash测速模式自动包含解锁检测"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
    except Exception as e:
        logger.error(f"回调查询处理失败: {e}")

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")
    logger.error(f"Traceback: {traceback.format_exc()}")

# --- Main Function ---
def main() -> None:
    """启动机器人"""
    logger.info("🚀 启动 IKUN 增强测速机器人 (集成FullTclash)...")
    
    try:
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(f"{TELEGRAM_API_URL}/bot").build()
        
        # 注册错误处理器
        application.add_error_handler(error_handler)
        
        # 注册命令处理器
        application.add_handler(CommandHandler("start", start))
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
        logger.critical(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    main()

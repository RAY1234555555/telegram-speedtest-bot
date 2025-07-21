# enhanced_bot.py - 增强版机器人主程序
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

# Import enhanced modules
try:
    from parser import parse_single_node, get_node_info_summary
    from subscription_analyzer import subscription_analyzer
    from advanced_speedtester import advanced_speed_tester
    from platform_unlock_tester import platform_unlock_tester
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

# --- User Data Storage ---
user_data = {}
user_settings = {}

# --- Authorization Check ---
def is_authorized(user_id: int) -> bool:
    """检查用户是否有权限"""
    if not ALLOWED_USER_IDS:
        return True
    return str(user_id) in ALLOWED_USER_IDS

# --- User Settings ---
def get_user_settings(user_id: int) -> Dict:
    """获取用户设置"""
    if user_id not in user_settings:
        user_settings[user_id] = {
            'test_mode': 'advanced',  # basic, standard, advanced
            'max_nodes': 20,
            'timeout': 30,
            'show_details': True,
            'auto_sort': True,
            'enable_unlock_test': True,
            'enable_subscription_analysis': True
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
        [InlineKeyboardButton("📊 批量测速", callback_data="help_batch")],
        [InlineKeyboardButton("🔗 订阅分析", callback_data="help_subscription")],
        [InlineKeyboardButton("🔓 解锁检测", callback_data="help_unlock")],
        [InlineKeyboardButton("📋 支持协议", callback_data="help_protocols")],
        [InlineKeyboardButton("⚙️ 设置选项", callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard(user_id: int):
    """获取设置菜单键盘"""
    settings = get_user_settings(user_id)
    keyboard = [
        [InlineKeyboardButton(f"🎯 测试模式: {settings['test_mode']}", callback_data="setting_test_mode")],
        [InlineKeyboardButton(f"🔢 最大节点数: {settings['max_nodes']}", callback_data="setting_max_nodes")],
        [InlineKeyboardButton(f"⏱️ 超时时间: {settings['timeout']}s", callback_data="setting_timeout")],
        [InlineKeyboardButton(f"🔓 解锁测试: {'开' if settings['enable_unlock_test'] else '关'}", callback_data="setting_unlock_test")],
        [InlineKeyboardButton(f"📊 订阅分析: {'开' if settings['enable_subscription_analysis'] else '关'}", callback_data="setting_subscription_analysis")],
        [InlineKeyboardButton(f"📋 详细信息: {'开' if settings['show_details'] else '关'}", callback_data="setting_show_details")],
        [InlineKeyboardButton(f"🔄 自动排序: {'开' if settings['auto_sort'] else '关'}", callback_data="setting_auto_sort")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="main_menu")]
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

        # 初始化用户数据
        if user_id not in user_data:
            user_data[user_id] = {'test_count': 0, 'node_count': 0, 'join_time': datetime.now()}

        welcome_text = """🎉 **欢迎使用全能测速机器人 v3.0！**

🚀 **功能特色：**
• 支持多种协议：VMess, VLess, SS, Hysteria2, Trojan
• 订阅链接解析与流量分析
• 高级测速与节点评分系统
• 平台解锁检测 (Netflix, Disney+, ChatGPT等)
• 地理位置和ISP信息
• 节点稳定性与延迟测试

📝 **快速开始：**
• 发送单个节点链接进行详细测速
• 发送订阅链接获取完整分析
• 发送多个节点进行批量测试
• 使用 /unlock 命令检测平台解锁情况

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
• `vmess://...`
• `vless://...`
• `ss://...`
• `hy2://...` 或 `hysteria2://...`
• `trojan://...`

🔸 **批量测速**
发送多个节点（每行一个）

🔸 **订阅分析**
发送订阅链接：
• `https://your-subscription-url`
• 自动解析并分析订阅信息和节点

🔸 **平台解锁检测**
使用 /unlock 命令检测当前网络对各流媒体平台的解锁情况

🔸 **快捷命令**
• /start - 开始使用
• /help - 查看帮助
• /status - 查看状态
• /ping - 测试连接
• /stats - 使用统计
• /unlock - 解锁检测

🔸 **高级功能**
• 真实下载速度测试
• 节点延迟与稳定性分析
• IP地理位置与ISP检测
• 流媒体平台解锁检测
• 订阅流量与到期信息分析
• 智能节点质量评分

💡 **提示：** 
• 高级测速可能需要30-60秒
• 支持并发测试多个节点
• 结果按质量评分自动排序"""
        
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
        
        await message.edit_text(
            f"🏓 **Pong!**\n"
            f"⏱️ 响应时间: {response_time}ms\n"
            f"🤖 状态: 运行正常\n"
            f"🌐 API: {TELEGRAM_API_URL}",
            parse_mode='Markdown'
        )
        
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

        user_stats = user_data.get(user_id, {})
        settings = get_user_settings(user_id)
        
        status_text = f"""📊 **机器人状态**

🤖 状态: 运行中 ✅
⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🌐 API 地址: {TELEGRAM_API_URL}
👥 授权用户: {len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else '无限制'}
🔧 版本: v3.0.0

🌐 **支持协议:**
• VMess ✅ (完整支持)
• VLess ✅ (完整支持)
• Shadowsocks ✅ (完整支持)
• Hysteria2 ✅ (完整支持)
• Trojan ✅ (完整支持)

📈 **您的使用统计:**
• 测速次数: {user_stats.get('test_count', 0)}
• 节点数量: {user_stats.get('node_count', 0)}
• 加入时间: {user_stats.get('join_time', datetime.now()).strftime('%Y-%m-%d')}

⚙️ **当前设置:**
• 测试模式: {settings['test_mode']}
• 最大节点: {settings['max_nodes']}
• 超时时间: {settings['timeout']}s
• 解锁测试: {'开启' if settings['enable_unlock_test'] else '关闭'}
• 订阅分析: {'开启' if settings['enable_subscription_analysis'] else '关闭'}"""
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"status 命令处理失败: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """统计命令"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return

        # 计算全局统计
        total_users = len(user_data)
        total_tests = sum(data.get('test_count', 0) for data in user_data.values())
        total_nodes = sum(data.get('node_count', 0) for data in user_data.values())
        
        user_stats = user_data.get(user_id, {})
        
        stats_text = f"""📊 **使用统计**

👤 **您的统计:**
• 测速次数: {user_stats.get('test_count', 0)}
• 测试节点: {user_stats.get('node_count', 0)}
• 使用天数: {(datetime.now() - user_stats.get('join_time', datetime.now())).days + 1}

🌍 **全局统计:**
• 总用户数: {total_users}
• 总测速次数: {total_tests}
• 总测试节点: {total_nodes}
• 平均每用户: {round(total_tests/total_users, 1) if total_users > 0 else 0} 次测速

🏆 **功能使用率:**
• 高级速度测试: ✅
• 订阅流量分析: ✅
• 平台解锁检测: ✅
• 节点质量评分: ✅
• 批量并发测试: ✅"""
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"stats 命令处理失败: {e}")

async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """解锁检测命令"""
    try:
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text("❌ 抱歉，您没有使用此机器人的权限。")
            return
        
        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在检测各平台解锁情况，请稍候...")
        
        # 执行解锁测试
        unlock_results = await platform_unlock_tester.test_platform_unlock()
        
        # 格式化结果
        result_text = platform_unlock_tester.format_unlock_results(unlock_results)
        
        # 发送结果
        await processing_message.edit_text(result_text, parse_mode='Markdown')
        
        # 更新用户统计
        if user_id not in user_data:
            user_data[user_id] = {'test_count': 0, 'node_count': 0, 'join_time': datetime.now()}
        user_data[user_id]['test_count'] += 1
        
    except Exception as e:
        logger.error(f"unlock 命令处理失败: {e}")
        try:
            await update.message.reply_text(f"❌ 解锁检测失败: {str(e)}")
        except:
            pass

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
            
        elif data == "help_single":
            help_text = """🚀 **单节点测速**

支持的格式：
• `vmess://base64encoded`
• `vless://uuid@server:port?params#name`
• `ss://method:password@server:port#name`
• `hy2://auth@server:port?params#name`
• `trojan://password@server:port?params#name`

**测试内容：**
• TCP连通性和延迟
• 真实下载速度
• 节点稳定性分析
• IP地理位置和ISP
• 平台解锁检测
• 综合质量评分

直接发送节点链接即可开始测速！"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "help_batch":
            help_text = """📊 **批量测速**

**支持方式：**
• 多个节点链接（每行一个）
• 订阅链接自动解析

**功能特点：**
• 并发测试，速度更快
• 自动按质量评分排序
• 显示最优节点推荐
• 支持最多50个节点

**使用方法：**
直接发送多个节点链接或订阅地址"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "help_subscription":
            help_text = """🔗 **订阅分析**

**支持格式：**
• HTTP/HTTPS 订阅链接
• Base64编码的订阅内容
• 原始节点列表

**分析内容：**
• 订阅流量使用情况
• 剩余流量和到期时间
• 节点数量和地区分布
• 协议类型统计
• 自动解析所有节点

**使用方法：**
发送订阅链接，如：
`https://example.com/subscription`"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "help_unlock":
            help_text = """🔓 **平台解锁检测**

**支持平台：**
• Netflix
• Disney+
• YouTube Premium
• ChatGPT
• TikTok
• Spotify
• Instagram
• Twitter/X

**检测内容：**
• 平台可访问性
• 地区限制状态
• 响应时间
• 解锁比例统计

**使用方法：**
发送 /unlock 命令进行检测"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "help_protocols":
            protocols_text = """📋 **支持的协议**

✅ **VMess**
- 支持 TCP/WS/gRPC/HTTP2
- 支持 TLS/Reality/None
- 完整的配置解析

✅ **VLess** 
- 支持 XTLS-Vision/Reality
- 支持各种传输协议
- 完整的参数支持

✅ **Shadowsocks**
- 支持所有加密方式
- 支持 SIP003 插件
- 新旧格式兼容

✅ **Hysteria2**
- 基于 QUIC 协议
- 支持混淆和认证
- 高速传输优化

✅ **Trojan**
- TLS 伪装技术
- 支持多种传输
- 高安全性

🔄 **持续更新中...**"""
            
            back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="main_menu")]])
            await query.edit_message_text(protocols_text, parse_mode='Markdown', reply_markup=back_keyboard)
            
        elif data == "settings_menu":
            settings_text = """⚙️ **设置选项**

点击下方按钮修改设置："""
            await query.edit_message_text(
                settings_text,
                reply_markup=get_settings_keyboard(user_id),
                parse_mode='Markdown'
            )
            
        elif data.startswith("setting_"):
            await handle_setting_change(query, user_id, data)
            
    except Exception as e:
        logger.error(f"回调查询处理失败: {e}")

async def handle_setting_change(query, user_id: int, setting_type: str):
    """处理设置更改"""
    try:
        settings = get_user_settings(user_id)
        
        if setting_type == "setting_test_mode":
            modes = ['basic', 'standard', 'advanced']
            current_index = modes.index(settings['test_mode'])
            new_mode = modes[(current_index + 1) % len(modes)]
            update_user_settings(user_id, 'test_mode', new_mode)
            
        elif setting_type == "setting_max_nodes":
            limits = [5, 10, 20, 50]
            current_index = limits.index(settings['max_nodes']) if settings['max_nodes'] in limits else 1
            new_limit = limits[(current_index + 1) % len(limits)]
            update_user_settings(user_id, 'max_nodes', new_limit)
            
        elif setting_type == "setting_timeout":
            timeouts = [15, 30, 60, 120]
            current_index = timeouts.index(settings['timeout']) if settings['timeout'] in timeouts else 1
            new_timeout = timeouts[(current_index + 1) % len(timeouts)]
            update_user_settings(user_id, 'timeout', new_timeout)
            
        elif setting_type == "setting_show_details":
            update_user_settings(user_id, 'show_details', not settings['show_details'])
            
        elif setting_type == "setting_auto_sort":
            update_user_settings(user_id, 'auto_sort', not settings['auto_sort'])
            
        elif setting_type == "setting_unlock_test":
            update_user_settings(user_id, 'enable_unlock_test', not settings['enable_unlock_test'])
            
        elif setting_type == "setting_subscription_analysis":
            update_user_settings(user_id, 'enable_subscription_analysis', not settings['enable_subscription_analysis'])
        
        # 更新设置菜单
        settings_text = """⚙️ **设置选项**

点击下方按钮修改设置："""
        await query.edit_message_text(
            settings_text,
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"设置更改失败: {e}")

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

        logger.info(f"📨 收到用户 {username} 的消息: {text[:100]}...")

        # 获取用户设置
        settings = get_user_settings(user_id)

        # 发送处理中消息
        processing_message = await update.message.reply_text("⏳ 正在处理您的请求，请稍候...")
        
        try:
            # 简单的测试响应
            if text.lower() in ['test', '测试', 'hello', '你好', 'hi']:
                await processing_message.edit_text(
                    "✅ **机器人运行正常！**\n\n"
                    "🚀 发送节点链接开始测速\n"
                    "📋 发送 /help 查看使用说明\n"
                    "📊 发送 /status 查看状态\n"
                    "⚙️ 发送 /start 打开主菜单",
                    parse_mode='Markdown'
                )
                return
            
            # 检查是否是单个节点链接
            if any(text.startswith(prefix) for prefix in ['vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://']):
                await processing_message.edit_text("🔍 检测到节点链接，开始解析和测速...")
                
                # 解析节点
                node = parse_single_node(text)
                if not node:
                    await processing_message.edit_text("❌ 节点链接解析失败，请检查格式是否正确")
                    return
                
                # 显示节点信息
                node_info = get_node_info_summary(node)
                await processing_message.edit_text(
                    f"📡 **节点信息**\n\n{node_info}\n\n🔄 开始高级测速，请耐心等待...",
                    parse_mode='Markdown'
                )
                
                # 执行高级测速
                result = await advanced_speed_tester.comprehensive_test(node)
                
                # 格式化结果
                result_text = f"🎯 **节点测速结果**\n\n{advanced_speed_tester.format_advanced_result(result)}"
                
                # 如果启用了解锁测试，添加解锁结果
                if settings['enable_unlock_test'] and result.get('unlock_test'):
                    unlock_summary = result['unlock_test'].get('summary', {})
                    unlock_rate = unlock_summary.get('unlock_rate', 0)
                    unlocked = unlock_summary.get('unlocked_platforms', 0)
                    total = unlock_summary.get('total_platforms', 0)
                    
                    result_text += f"\n🔓 **解锁情况:** {unlocked}/{total} ({unlock_rate}%)\n"
                    
                    # 添加解锁平台详情
                    platforms = result['unlock_test'].get('platforms', {})
                    unlocked_platforms = [name for name, data in platforms.items() if data.get('unlocked')]
                    
                    if unlocked_platforms:
                        result_text += "✅ 已解锁: " + ", ".join(unlocked_platforms[:5])
                        if len(unlocked_platforms) > 5:
                            result_text += f" 等{len(unlocked_platforms)}个平台"
                
                if len(result_text) > 4096:
                    # 消息太长，分割发送
                    await processing_message.edit_text(result_text[:4000] + "...", parse_mode='Markdown')
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="..." + result_text[4000:],
                        parse_mode='Markdown'
                    )
                else:
                    await processing_message.edit_text(result_text, parse_mode='Markdown')
                
                # 更新用户统计
                if user_id not in user_data:
                    user_data[user_id] = {'test_count': 0, 'node_count': 0, 'join_time': datetime.now()}
                user_data[user_id]['test_count'] += 1
                user_data[user_id]['node_count'] += 1
                
            elif text.startswith(('http://', 'https://')) and settings['enable_subscription_analysis']:
                await processing_message.edit_text("🔗 检测到链接，正在分析...")
                
                # 分析订阅
                sub_result = subscription_analyzer.analyze_subscription(text)
                
                if sub_result.get("status") == "success":
                    # 格式化订阅信息
                    sub_info_text = subscription_analyzer.format_subscription_info(sub_result)
                    
                    # 发送订阅分析结果
                    await processing_message.edit_text(sub_info_text, parse_mode='Markdown')
                    
                    # 如果有节点，询问是否测速
                    nodes = sub_result.get("nodes", [])
                    if nodes:
                        # 限制节点数量
                        max_nodes = settings['max_nodes']
                        if len(nodes) > max_nodes:
                            nodes = nodes[:max_nodes]
                        
                        # 创建测速按钮
                        speed_test_keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🚀 测试全部节点", callback_data=f"speedtest_all_{len(nodes)}")],
                            [InlineKeyboardButton("📊 测试前10个节点", callback_data="speedtest_top10")]
                        ])
                        
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"📊 发现 {len(nodes)} 个节点，是否需要测速？",
                            reply_markup=speed_test_keyboard
                        )
                else:
                    await processing_message.edit_text(
                        f"❌ **订阅分析失败**\n\n错误: {sub_result.get('error', '未知错误')}",
                        parse_mode='Markdown'
                    )
                
                # 更新用户统计
                if user_id not in user_data:
                    user_data[user_id] = {'test_count': 0, 'node_count': 0, 'join_time': datetime.now()}
                user_data[user_id]['test_count'] += 1
                
            elif '\n' in text and any(line.strip().startswith(('vmess://', 'vless://', 'ss://', 'hy2://', 'hysteria2://', 'trojan://')) for line in text.split('\n')):
                # 多个节点
                await processing_message.edit_text("📊 检测到多个节点，开始解析...")
                
                lines = text.strip().split('\n')
                nodes = []
                for line in lines:
                    line = line.strip()
                    if line:
                        node = parse_single_node(line)
                        if node:
                            nodes.append(node)
                
                if not nodes:
                    await processing_message.edit_text("❌ 未找到有效的节点信息")
                    return
                
                # 限制节点数量
                max_nodes = settings['max_nodes']
                if len(nodes) > max_nodes:
                    nodes = nodes[:max_nodes]
                    await processing_message.edit_text(
                        f"📊 发现 {len(nodes)} 个有效节点（已限制为 {max_nodes} 个），开始批量测速...\n\n"
                        f"⏱️ 预计需要 {len(nodes) * 15 // 3} 秒，请耐心等待..."
                    )
                else:
                    await processing_message.edit_text(
                        f"📊 发现 {len(nodes)} 个有效节点，开始批量测速...\n\n"
                        f"⏱️ 预计需要 {len(nodes) * 15 // 3} 秒，请耐心等待..."
                    )
                
                # 执行批量测速
                results = []
                for node in nodes[:3]:  # 先测试前3个节点
                    try:
                        result = await advanced_speed_tester.comprehensive_test(node)
                        results.append(result)
                    except Exception as e:
                        logger.error(f"节点测试失败: {e}")
                        results.append({
                            "name": node.get('name', 'Unknown'),
                            "server": node.get('server', 'Unknown'),
                            "port": node.get('port', 0),
                            "protocol": node.get('protocol', 'unknown'),
                            "error": str(e),
                            "quality_score": 0,
                            "overall_status": "❌ 测试失败"
                        })
                
                # 按评分排序
                results.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
                
                # 格式化结果
                result_text = f"📊 **批量测速结果 ({len(results)}/{len(nodes)})**\n\n"
                
                for i, result in enumerate(results, 1):
                    result_text += f"**{i}. {result.get('name', 'Unknown')}**\n"
                    result_text += f"🌐 {result.get('server', 'N/A')}:{result.get('port', 'N/A')}\n"
                    result_text += f"📍 {result.get('region', '未知地区')}\n"
                    result_text += f"⚡ {result.get('download_speed_mbps', 0)}MB/s | ⏱️ {result.get('latency_ms', 0)}ms\n"
                    result_text += f"📈 {result.get('overall_status', '未知')} | 🏆 {result.get('quality_score', 0)}/100\n\n"
                
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
                
                # 如果节点较多，询问是否继续测试剩余节点
                if len(nodes) > 3:
                    continue_keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🚀 继续测试剩余节点", callback_data=f"continue_test_{len(nodes) - 3}")]
                    ])
                    
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"⚠️ 还有 {len(nodes) - 3} 个节点未测试，是否继续？",
                        reply_markup=continue_keyboard
                    )
                
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
                    "• 多个节点（每行一个）\n"
                    "• 订阅链接 (http/https)\n"
                    "• 发送 'test' 测试机器人\n"
                    "• 发送 /help 查看详细帮助\n\n"
                    "💡 **提示：** 直接粘贴节点链接或订阅地址即可",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"消息处理过程中出错: {e}")
            try:
                await processing_message.edit_text(
                    f"❌ **处理过程中出现错误**\n\n"
                    f"错误信息: {str(e)}\n\n"
                    f"请检查输入格式或稍后重试",
                    parse_mode='Markdown'
                )
            except:
                pass
                
    except Exception as e:
        logger.error(f"handle_message 严重错误: {e}")
        try:
            await update.message.reply_text("❌ 系统错误，请稍后重试")
        except:
            pass

async def send_test_message(application: Application) -> None:
    """发送测试消息给授权用户"""
    if not ALLOWED_USER_IDS:
        logger.info("没有设置授权用户，跳过测试消息发送")
        return
        
    test_message = f"""🎉 **测速机器人 v3.0 安装成功！**

✅ 服务已启动并运行正常
🚀 支持多种协议真实测速
📊 功能完整可用

**新功能：**
• 订阅流量分析
• 平台解锁检测
• 高级节点评分
• 多线程速度测试
• 节点稳定性分析

发送 /start 开始使用
发送节点链接进行真实测速

---
安装时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
版本: v3.0.0 (全功能增强版)"""

    for user_id in ALLOWED_USER_IDS:
        try:
            await application.bot.send_message(
                chat_id=int(user_id),
                text=test_message,
                parse_mode='Markdown'
            )
            logger.info(f"✅ 测试消息已发送给用户 {user_id}")
        except Exception as e:
            logger.error(f"❌ 发送测试消息给用户 {user_id} 失败: {e}")

async def post_init(application: Application) -> None:
    """应用初始化后的回调"""
    logger.info("🚀 机器人初始化完成，发送测试消息...")
    await send_test_message(application)

# --- Main Function ---
def main() -> None:
    """启动机器人"""
    logger.info("🚀 启动 Telegram 测速机器人 v3.0 (全功能增强版)...")
    logger.info(f"🌐 API 地址: {TELEGRAM_API_URL}")
    logger.info(f"👥 授权用户数: {len(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else '无限制'}")
    
    try:
        # 创建应用
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(f"{TELEGRAM_API_URL}/bot").post_init(post_init).build()
        
        # 注册错误处理器
        application.add_error_handler(error_handler)
        
        # 注册命令处理器
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("ping", ping_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("unlock", unlock_command))
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

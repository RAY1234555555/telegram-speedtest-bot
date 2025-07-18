# bot.py
import logging
import os
import sys
import subprocess # For update command (can be added later)
import base64

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from dotenv import load_dotenv # For local testing primarily

# Import our custom modules
from parser import parse_vmess_link, parse_subscription_link
from speedtester import test_node_speed

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
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://tg.993474.xyz") # <<< YOUR TG API PROXY URL

# --- Basic Validation ---
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
    sys.exit(1)
if not ALLOWED_USER_IDS_STR:
    logger.warning("ALLOWED_USER_IDS environment variable not set. Bot will not restrict users.")
    ALLOWED_USER_IDS = set() # Empty set means no restriction
else:
    ALLOWED_USER_IDS = set(ALLOWED_USER_IDS_STR.split(',')) # Convert to a set for faster lookup

# --- Authorization Check ---
def is_authorized(user_id: int) -> bool:
    """Checks if the user is authorized to use the bot."""
    if not ALLOWED_USER_IDS: # If no restrictions are set
        return True
    return str(user_id) in ALLOWED_USER_IDS

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt from User ID: {user_id}")
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    welcome_message = (
        "👋 Welcome to the Telegram Speedtest Bot!\n\n"
        "Send me a node link (like vmess://...) or a subscription link.\n"
        "I will test the node(s) and report the results.\n\n"
        "Supported formats: vmess:// (direct link).\n"
        "Use /help for more information."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt from User ID: {user_id}")
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    help_text = (
        "ℹ️ How to use the bot:\n\n"
        "1. Send a direct node link:\n"
        "   `vmess://eyJh...` (Base64 encoded VMess link)\n\n"
        "2. Send a subscription link (URL):\n"
        "   `https://your.subscription.link/path`\n"
        "   (Currently, only direct vmess:// links are fully supported for parsing).\n\n"
        "The bot will attempt to parse the provided link(s) and test the node speed.\n"
        "Please be patient as tests may take a moment."
    )
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages, treating them as potential node links or subscription links."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        logger.warning(f"Unauthorized message from User ID: {user_id}")
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
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
        # If sending the initial message fails, we can't edit it. Just log.
        return

    try:
        nodes_to_test = []
        # --- Parsing Logic ---
        # Check if it's a direct VMess link
        if text.startswith("vmess://"):
            node = parse_vmess_link(text)
            if node:
                nodes_to_test.append(node)
        # Check if it's a URL (potential subscription link)
        elif text.startswith("http://") or text.startswith("https://"):
            # TODO: Implement fetching and parsing for subscription URLs
            # For now, we'll inform the user that only direct vmess links are supported for parsing
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message_id_to_edit,
                text="❌ Currently, only direct vmess:// links are supported for parsing. Subscription URL fetching is not yet implemented."
            )
            return
        else:
            # Not a recognized format
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message_id_to_edit,
                text="❌ Could not parse the provided node information. Please check the format or send a vmess:// link."
            )
            return

        # --- Perform Speed Tests ---
        if not nodes_to_test:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message_id_to_edit,
                text="❌ No valid nodes were parsed from your input."
            )
            return

        results = []
        for node in nodes_to_test:
            test_result = test_node_speed(node)
            results.append(test_result)

        # --- Format and Send Results ---
        response_text = "✅ Test Results:\n\n"
        for result in results:
            if "error" in result:
                response_text += f"- {result.get('name', 'Unknown Node')}: Error - {result['error']}\n"
            else:
                status_emoji = "✅" if result.get("status") == "OK" else "❌"
                response_text += (
                    f"- {result.get('name', result.get('server'))}:\n"
                    f"  🚀 Speed: {result.get('download_speed_mbps', 0.0):.2f} MB/s\n"
                    f"  ⏱️ Latency: {result.get('latency_ms', 0.0):.2f} ms\n"
                    f"  🎫 Status: {status_emoji} {result.get('status')}\n"
                )
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id_to_edit, text=response_text)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        try:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=message_id_to_edit, text="An internal error occurred. Please try again later.")
        except Exception as edit_err:
            logger.error(f"Failed to edit message after error: {edit_err}")


# --- Main Function ---
def main() -> None:
    """Start the bot."""
    logger.info("Starting bot...")
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        sys.exit(1)

    # !!! USING YOUR PROVIDED TELEGRAM API PROXY URL !!!
    logger.info(f"Using Telegram API URL: {TELEGRAM_API_URL}")
    logger.info(f"Authorized User IDs: {ALLOWED_USER_IDS if ALLOWED_USER_IDS else 'None (all users allowed)'}")

    # Create the Application and pass it your bot's token.
    # Use the base_url parameter to use your custom API URL (your反代 address).
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).base_url(TELEGRAM_API_URL).build()

        # Register handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Start the Bot
        logger.info("Application initialized. Starting polling...")
        application.run_polling()

    except Exception as e:
        logger.critical(f"Failed to initialize or run bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()

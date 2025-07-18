#!/bin/bash
# This script runs locally on your machine to encrypt secrets before transferring.

# --- Configuration ---
SECRETS_DIR="$HOME/my_bot_secrets" # Local directory to store secrets
SECRETS_FILE="$SECRETS_DIR/secrets.enc"
ENCRYPTION_CMD="openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt" # Encryption command

# --- Helper Functions ---
log_info() { echo "[LOCAL INFO] $1"; }
log_error() { echo "[LOCAL ERROR] $1" >&2; }
safe_read() {
    local prompt="$1"
    local var_name="$2"
    local encrypted_input="$3" # If true, mask input
    local input_str=""
    if [ "$encrypted_input" = true ]; then
        read -sp "$prompt: " input_str
    else
        read -p "$prompt: " input_str
    fi
    eval "$var_name='$input_str'"
    echo
}

# --- Prompt for User Input ---
log_info "Gathering secrets for encryption..."
safe_read "Enter your Telegram Bot Token (from BotFather)" BOT_TOKEN false
safe_read "Enter allowed Telegram User IDs (comma-separated, e.g., 123456789,987654321)" ALLOWED_USER_IDS false
safe_read "Enter a Master Password for encrypting secrets" MASTER_PASSWORD true

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "Bot Token, User IDs, and Master Password are all required. Aborting."
    exit 1
fi

# --- Create secrets directory ---
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# --- Encrypt secrets ---
log_info "Encrypting secrets and saving to $SECRETS_FILE..."

# Create temporary file for data
echo -n "TELEGRAM_BOT_TOKEN=" > temp_secrets_data.txt
echo -n "$BOT_TOKEN" >> temp_secrets_data.txt
echo "" >> temp_secrets_data.txt
echo -n "ALLOWED_USER_IDS=" >> temp_secrets_data.txt
echo -n "$ALLOWED_USER_IDS" >> temp_secrets_data.txt
echo "" >> temp_secrets_data.txt

# Perform encryption
echo "$MASTER_PASSWORD" | $ENCRYPTION_CMD -out "$SECRETS_FILE" -pass stdin temp_secrets_data.txt
if [ $? -ne 0 ]; then
    log_error "openssl encryption failed. Ensure openssl is installed and Master Password is valid."
    rm -f temp_secrets_data.txt
    exit 1
fi

rm -f temp_secrets_data.txt
log_info "Secrets encrypted successfully. File: $SECRETS_FILE"
log_info "IMPORTANT: Keep your Master Password secure and remember it!"

exit 0

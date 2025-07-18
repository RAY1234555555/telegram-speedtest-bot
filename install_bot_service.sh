#!/bin/bash
# Installs and configures the Telegram Speedtest Bot service on Debian.

# --- Configuration ---
GITHUB_REPO_URL="https://github.com/RAY1234555555/telegram-speedtest-bot.git" # <<< YOUR GITHUB REPO URL
BOT_INSTALL_DIR="/opt/telegram-speedtest-bot"
BOT_SERVICE_NAME="telegram-speedtest-bot.service"
SYSTEMD_SERVICE_PATH="/etc/systemd/system/${BOT_SERVICE_NAME}"
SECRETS_FILE="${BOT_INSTALL_DIR}/secrets.enc"
DECRYPT_SCRIPT="${BOT_INSTALL_DIR}/decrypt_secrets.sh"
RUNNER_SCRIPT="${BOT_INSTALL_DIR}/secure_runner.sh"
BOT_MAIN_SCRIPT="${BOT_INSTALL_DIR}/bot.py"
BOT_VENV_PATH="${BOT_INSTALL_DIR}/venv/bin/activate"
ENCRYPT_SCRIPT_LOCAL="encrypt_secrets.sh" # Script to be run locally to generate secrets.enc
DECRYPT_SCRIPT_LOCAL="decrypt_secrets.sh" # Script to be placed on server for decryption
RUNNER_TEMPLATE="secure_runner.sh.template"
SERVICE_TEMPLATE="bot_service.service"
# README.md is also part of the repo but not directly used by installer

# --- Helper Functions ---
log_info() { echo "[INFO] $1"; }
log_error() { echo "[ERROR] $1" >&2; }
log_warning() { echo "[WARNING] $1"; } >&2

# Function to run commands with sudo if not root
sudo_if_needed() {
    if [ "$(id -u)" -ne 0 ]; then
        sudo "$@"
    else
        "$@"
    fi
}

# Function to ensure a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to safely read input (masked for passwords)
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
    echo # Newline after masked input
}

# --- Pre-checks ---
log_info "Checking system prerequisites on Debian server..."
if ! command_exists git; then log_error "'git' not installed. Please install it (e.g., sudo apt update && sudo apt install git)."; exit 1; fi
if ! command_exists python3; then log_error "'python3' not installed. Please install it (e.g., sudo apt update && sudo apt install python3)."; exit 1; fi
if ! command_exists pip3; then log_error "'pip3' not installed. Please install it (e.g., sudo apt update && sudo apt install python3-pip)."; exit 1; fi
if ! command_exists openssl; then log_error "'openssl' not installed. Please install it (e.g., sudo apt update && sudo apt install openssl)."; exit 1; fi
if ! command_exists systemctl; then log_error "'systemctl' command not found. This script is for systemd-based systems."; exit 1; fi
if ! command_exists curl; then log_error "'curl' not installed. Please install it (e.g., sudo apt update && sudo apt install curl)."; exit 1; fi

# --- Prompt for User Input ---
log_info "Gathering necessary information for the bot..."
safe_read "Enter your Telegram Bot Token (from BotFather)" BOT_TOKEN false
safe_read "Enter allowed Telegram User IDs (comma-separated, e.g., 123456789,987654321)" ALLOWED_USER_IDS false
safe_read "Enter a Master Password for encrypting secrets" MASTER_PASSWORD true

if [[ -z "$BOT_TOKEN" || -z "$ALLOWED_USER_IDS" || -z "$MASTER_PASSWORD" ]]; then
    log_error "Bot Token, User IDs, and Master Password are all required. Aborting."
    exit 1
fi

# --- Get current user/group for systemd service ---
CURRENT_USER=$(id -u -n)
CURRENT_GROUP=$(id -g -n)

# --- Create directories ---
log_info "Creating bot directories..."
sudo_if_needed mkdir -p "$BOT_INSTALL_DIR"
sudo_if_needed chown "${CURRENT_USER}:${CURRENT_GROUP}" "$BOT_INSTALL_DIR" # Set ownership for current user
sudo_if_needed mkdir -p "$(dirname "$DECRYPT_SCRIPT")" # For decrypt_secrets.sh
sudo_if_needed chmod 700 "$(dirname "$DECRYPT_SCRIPT")" # Ensure directory is secure
sudo_if_needed mkdir -p "$(dirname "$RUNNER_SCRIPT")"
sudo_if_needed chmod 700 "$(dirname "$RUNNER_SCRIPT")"

cd "$BOT_INSTALL_DIR" || { log_error "Failed to change directory to $BOT_INSTALL_DIR"; exit 1; }

# --- Clone or pull code from GitHub ---
if [ -d ".git" ]; then
    log_info "Updating existing bot repository in $BOT_INSTALL_DIR..."
    git pull origin main # Assuming 'main' is your default branch
    if [ $? -ne 0 ]; then
        log_warning "git pull failed. Attempting to proceed with existing code."
    fi
else
    log_info "Cloning repository $GITHUB_REPO_URL into $BOT_INSTALL_DIR..."
    git clone "$GITHUB_REPO_URL" "$BOT_INSTALL_DIR"
    if [ $? -ne 0 ]; then
        log_error "Failed to clone repository. Please check URL and network connection."
        exit 1
    fi
fi
cd "$BOT_INSTALL_DIR" || { log_error "Failed to change directory to $BOT_INSTALL_DIR"; exit 1; }

# --- Setup Python virtual environment ---
log_info "Setting up Python virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then log_error "Failed to create virtual environment."; exit 1; fi
source venv/bin/activate
pip install -r requirements.txt
if [ $? -ne 0 ]; then log_error "Failed to install Python dependencies."; deactivate; exit 1; fi
deactivate
log_info "Python environment setup complete."

# --- Encrypt Secrets ---
log_info "Encrypting secrets using Master Password..."
# Use openssl to encrypt. The Master Password is provided directly.
# We use a temporary file for data and export MASTER_PASSWORD as an environment variable for openssl.
# This helps handle special characters in the Master Password more robustly.
ENCRYPT_CMD="openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -salt -out \"$SECRETS_FILE\" -pass env:MASTER_PASSWORD_VAR"

# Prepare data for encryption
echo -n "TELEGRAM_BOT_TOKEN=" > temp_secrets_data.txt
echo -n "$BOT_TOKEN" >> temp_secrets_data.txt
echo "" >> temp_secrets_data.txt
echo -n "ALLOWED_USER_IDS=" >> temp_secrets_data.txt
echo -n "$ALLOWED_USER_IDS" >> temp_secrets_data.txt
echo "" >> temp_secrets_data.txt

# Execute encryption. Export MASTER_PASSWORD to an env var for openssl.
export MASTER_PASSWORD_VAR="$MASTER_PASSWORD"
eval $ENCRYPT_CMD temp_secrets_data.txt
if [ $? -ne 0 ]; then
    log_error "openssl encryption failed. Ensure openssl is installed and Master Password is valid."
    rm -f temp_secrets_data.txt
    exit 1
fi
sudo_if_needed chmod 600 "$SECRETS_FILE"
rm -f temp_secrets_data.txt
log_info "Secrets encrypted successfully to $SECRETS_FILE (permissions 600)."

# --- Create decrypt_secrets.sh ---
log_info "Generating decrypt_secrets.sh..."
DECRYPT_SCRIPT_CONTENT=$(cat <<EOF
#!/bin/bash
# Decrypts secrets.enc using a Master Password provided via stdin.
# CRITICAL: Master Password is provided via stdin from secure_runner.sh.
# Ensure this script has 700 permissions.

MASTER_PASSWORD_FROM_RUNNER="\$1" # Passed as the first argument from runner

SECRET_FILE="$SECRETS_FILE"

if [[ -z "\$MASTER_PASSWORD_FROM_RUNNER" || ! -f "\$SECRET_FILE" ]]; then
    echo "Error: Missing Master Password or secrets file. Exiting." >&2
    exit 1
fi

# Use openssl to decrypt. Pass password via stdin.
# Ensure encryption parameters match those used in encrypt_secrets.sh
DECRYPTED_DATA=\$(echo "\$MASTER_PASSWORD_FROM_RUNNER" | openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -salt -pass stdin -in "\$SECRET_FILE")

if [[ \$? -ne 0 || -z "\$DECRYPTED_DATA" ]]; then
    echo "Error: Failed to decrypt secrets. Incorrect Master Password or corrupted file. Exiting." >&2
    exit 1
fi

echo "\$DECRYPTED_DATA"
exit 0
EOF
)
echo "$DECRYPT_SCRIPT_CONTENT" > "$DECRYPT_SCRIPT"
sudo_if_needed chmod 700 "$DECRYPT_SCRIPT"
log_info "decrypt_secrets.sh created with 700 permissions."

# --- Create secure_runner.sh ---
log_info "Generating secure_runner.sh..."
RUNNER_SCRIPT_CONTENT=$(cat <<EOF
#!/bin/bash
# This script is executed by systemd to run the Telegram bot securely.

# --- Configuration ---
# !!! MASTER PASSWORD IS EMBEDDED HERE BY THE INSTALL SCRIPT !!!
# It should be a strong, randomly generated password.
MASTER_PASSWORD="$MASTER_PASSWORD" # <<< MASTER PASSWORD IS EMBEDDED HERE

BOT_TOKEN=""
USER_IDS=""

SECRETS_FILE="$SECRETS_FILE"
DECRYPT_SCRIPT="$DECRYPT_SCRIPT"
BOT_VENV_PATH="$BOT_VENV_PATH"
BOT_MAIN_SCRIPT="$BOT_MAIN_SCRIPT"
BOT_INSTALL_DIR="$BOT_INSTALL_DIR"
TELEGRAM_API_URL="$TELEGRAM_API_URL" # <<< YOUR TG API PROXY URL

# --- Decrypt secrets ---
# Check if secrets file and decrypt script exist
if [[ ! -f "\$SECRETS_FILE" || ! -f "\$DECRYPT_SCRIPT" ]]; then
  echo "Error: Secrets file or decrypt script not found. Exiting." >&2
  exit 1
fi

# Decrypt secrets.enc using the Master Password by piping it to the decrypt script.
# The decrypt script needs the Master Password as its first argument.
DECRYPTED_DATA=\$(bash "\$DECRYPT_SCRIPT" "\$MASTER_PASSWORD" 2>/dev/null)

if [[ \$? -ne 0 || -z "\$DECRYPTED_DATA" ]]; then
  echo "Error: Failed to decrypt secrets. Incorrect Master Password or corrupted file. Exiting." >&2
  exit 1
fi

# Parse the decrypted data
BOT_TOKEN=\$(echo "\$DECRYPTED_DATA" | grep "^TELEGRAM_BOT_TOKEN=" | cut -d'=' -f2-)
USER_IDS=\$(echo "\$DECRYPTED_DATA" | grep "^ALLOWED_USER_IDS=" | cut -d'=' -f2-)

if [[ -z "\$BOT_TOKEN" || -z "\$USER_IDS" ]]; then
  echo "Error: Could not parse Bot Token or User IDs from decrypted data. Exiting." >&2
  exit 1
fi

# --- Activate environment and run the bot ---
echo "Starting Telegram bot..."
export TELEGRAM_BOT_TOKEN="\$BOT_TOKEN"
export ALLOWED_USER_IDS="\$USER_IDS"
export TELEGRAM_API_URL="\$TELEGRAM_API_URL"

cd "\$BOT_INSTALL_DIR" && source "\$BOT_VENV_PATH" && python "\$BOT_MAIN_SCRIPT"
EOF
)
echo "$RUNNER_SCRIPT_CONTENT" > "$RUNNER_SCRIPT"
sudo_if_needed chmod 700 "$RUNNER_SCRIPT"
log_info "secure_runner.sh created with 700 permissions."

# --- Create systemd service file ---
log_info "Generating systemd service file..."
SERVICE_FILE_CONTENT=$(cat <<EOF
[Unit]
Description=Telegram Speedtest Bot
After=network.target

[Service]
User=${CURRENT_USER}
Group=${CURRENT_GROUP}
WorkingDirectory=${BOT_INSTALL_DIR}
ExecStart=${RUNNER_SCRIPT}

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
)
echo "$SERVICE_FILE_CONTENT" | sudo_if_needed tee "$SYSTEMD_SERVICE_PATH" > /dev/null
if [ $? -ne 0 ]; then log_error "Failed to create systemd service file."; exit 1; fi
sudo_if_needed chmod 644 "$SYSTEMD_SERVICE_PATH"
log_info "systemd service file created at ${SYSTEMD_SERVICE_PATH}."

# --- Reload systemd, enable and start the service ---
log_info "Reloading systemd, enabling and starting the service..."
sudo_if_needed systemctl daemon-reload
sudo_if_needed systemctl enable "${BOT_SERVICE_NAME}"
sudo_if_needed systemctl start "${BOT_SERVICE_NAME}"

# --- Final messages ---
log_info "--- Installation Complete ---"
log_info "Bot service '${BOT_SERVICE_NAME}' is configured and running."
log_info "You can view logs using: sudo journalctl -u ${BOT_SERVICE_NAME} -f"
log_info "To stop: sudo systemctl stop ${BOT_SERVICE_NAME}"
log_info "To restart: sudo systemctl restart ${BOT_SERVICE_NAME}"
log_info "To update: cd \"${BOT_INSTALL_DIR}\" && git pull && sudo systemctl restart ${BOT_SERVICE_NAME}"
log_info "IMPORTANT SECURITY NOTE: The Master Password is hardcoded in ${RUNNER_SCRIPT}. Ensure its permissions are 700 and restrict access to your user account."

exit 0

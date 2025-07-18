#!/bin/bash
# Decrypts secrets.enc using a Master Password provided via stdin.
# CRITICAL: Master Password is provided via stdin from secure_runner.sh.
# Ensure this script has 700 permissions.

# --- Configuration ---
# Master Password is provided as the first argument from the caller script (secure_runner.sh).
MASTER_PASSWORD="$1"
SECRET_FILE="/opt/telegram-speedtest-bot/secrets.enc"

# --- Validate Input ---
if [[ -z "$MASTER_PASSWORD" ]]; then
    echo "Error: Master Password is empty. Exiting." >&2
    exit 1
fi

if [[ ! -f "$SECRET_FILE" ]]; then
    echo "Error: Secrets file ($SECRET_FILE) not found. Exiting." >&2
    exit 1
fi

# --- Decrypt and output ---
# Use openssl to decrypt. Pass password via stdin.
# Ensure encryption parameters match those used in encrypt_secrets.sh
DECRYPTED_DATA=$(echo "$MASTER_PASSWORD" | openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -salt -pass stdin -in "$SECRET_FILE")

if [[ $? -ne 0 || -z "$DECRYPTED_DATA" ]]; then
    echo "Error: Failed to decrypt secrets. Incorrect Master Password or corrupted file. Exiting." >&2
    exit 1
fi

echo "$DECRYPTED_DATA"
exit 0

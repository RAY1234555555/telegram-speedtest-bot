# speedtester.py
import subprocess
import logging
import time

logger = logging.getLogger(__name__)

# --- Configuration ---
# You might want to fetch these from config or env variables later
# TELEGRAM_API_URL = "https://tg.993474.xyz" # Your Telegram API proxy
# For curl testing, we need a reliable download source.
# Using a Cloudflare worker for a consistent test file is a good idea.
# Example: https://speed.cloudflare.com/__down?bytes=1048576 (1MB download)
TEST_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=1048576" # 1MB file

def construct_curl_command(node: dict) -> list[str]:
    """
    Constructs the curl command based on node information.
    This is a simplified example and needs to be robust for various protocols.
    """
    cmd = ["curl", "-o", "/dev/null", "-w", "%{speed_download}\\n%{time_total}\\n%{http_code}", "--connect-timeout", "10", "-m", "30"]
    server = node.get("server")
    port = node.get("port")
    protocol = node.get("protocol")
    uuid = node.get("uuid")
    alterId = node.get("alterId")
    network = node.get("network", "tcp")
    tls = node.get("tls", "")
    host = node.get("host", "")
    path = node.get("path", "")

    proxy_address = server
    proxy_port = port

    if not all([server, port, uuid]):
        logger.error("Node missing essential info for curl command construction.")
        return []

    proxy_string = ""
    proxy_type = ""

    # Determine proxy type and build proxy string
    if protocol == "vmess":
        # For VMess, it's common to use a local V2Ray/Xray client as a SOCKS5 proxy.
        # For simplicity here, we'll assume direct SOCKS5 if available, or fail.
        # A real implementation might need to start a local V2Ray instance.
        proxy_type = "socks5h" # Use socks5h for DNS resolution over proxy
        proxy_string = f"{proxy_type}://{proxy_address}:{proxy_port}"
        # Note: VMess often requires additional headers for WS, gRPC etc.
        if network == "ws":
            cmd.extend(["--proxy-method", "POST"]) # Curl uses POST for WS proxy
            cmd.extend(["--proxy", proxy_string])
            cmd.extend(["--header", f"Host: {host}"])
            cmd.extend(["--header", f"Connection: Upgrade"])
            cmd.extend(["--header", f"Upgrade: websocket"])
            if path:
                cmd.extend(["--header", f"sec-websocket-protocol: {path}"]) # Assuming path is protocol for sec-ws
            if tls == "tls":
                cmd.extend(["--cacert", "/dev/null"]) # Ignore cert validation for simplicity
                cmd.extend(["--insecure"])
                cmd.extend(["--url", f"wss://{server}:{port}{path}"]) # Target URL for WS-TLS
            else:
                cmd.extend(["--url", f"ws://{server}:{port}{path}"]) # Target URL for WS
        else: # For direct TCP or other protocols
            cmd.extend(["--proxy-method", "POST"])
            cmd.extend(["--proxy", proxy_string])
            cmd.extend(["--url", f"tcp://{server}:{port}"]) # Simplified URL, might need adjustment
    elif protocol == "ss":
        # Shadowsocks requires specific 'ss://' prefix or separate command.
        # Curl doesn't directly support ss:// links for proxying without ss-local.
        # For simplicity, we'll skip direct SS support via curl for now, or assume ss-local is running.
        # A more robust way is to use a library or start ss-local.
        logger.warning("Direct Shadowsocks support via curl is complex. Consider ss-local.")
        return [] # Returning empty for now
    elif protocol == "http":
        proxy_type = "http"
        proxy_string = f"{proxy_type}://{proxy_address}:{proxy_port}"
        cmd.extend(["--proxy", proxy_string])
        cmd.append(proxy_type) # Indicate HTTP proxy

    # If no proxy is set, or if it's just a direct URL to test
    if not proxy_string:
         

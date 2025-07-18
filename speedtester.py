import subprocess
import logging
import time
import os
import json
import base64

logger = logging.getLogger(__name__)

# --- Configuration ---
# Use environment variable or default to your proxy URL
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://api.telegram.org/bot")
# A reliable source for testing download speed. Using Cloudflare's test file.
TEST_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=1048576" # 1MB file

def construct_curl_command(node: dict) -> list[str]:
    """
    Constructs the curl command based on node information.
    This is a simplified example and needs to be robust for various protocols.
    """
    cmd = ["curl", "-o", "/dev/null", "-w", "%{speed_download}\\n%{time_total}\\n%{http_code}", "--connect-timeout", "10", "-m", "30"]
    server = node.get("server")
    port = node.get("port")
    uuid = node.get("uuid")
    network = node.get("network", "tcp")
    tls = node.get("tls", "")
    host = node.get("host", "")
    path = node.get("path", "")
    protocol = node.get("protocol", "vmess") # Default to vmess if not specified

    if not all([server, port, uuid]):
        logger.error("Node missing essential info for curl command construction (server, port, uuid).")
        return []

    proxy_string = ""
    proxy_type = ""
    target_url = ""

    # Determine proxy type and build proxy string
    if protocol == "vmess":
        # For VMess, a local V2Ray/Xray client is often needed to act as a proxy.
        # Here, we assume the 'server' and 'port' are directly usable as a SOCKS5 proxy for simplicity.
        # In a real-world complex setup, you might need to manage a local proxy client.
        proxy_type = "socks5h" # Use socks5h for DNS resolution over proxy
        proxy_string = f"{proxy_type}://{server}:{port}"

        # VMess often uses WebSocket or gRPC over TLS.
        if network == "ws":
            target_url = f"{tls}://{server}:{port}{path if path else '/'}"
            cmd.extend(["--proxy-method", "POST"]) # Curl uses POST for WS proxy
            cmd.extend(["--proxy", proxy_string])
            cmd.extend(["--header", f"Host: {host if host else server}"])
            cmd.extend(["--header", "Connection: Upgrade"])
            cmd.extend(["--header", "Upgrade: websocket"])
            # Note: The 'sec-websocket-protocol' header is not directly supported by curl in this way
            # The path is often part of the URL for WS.
            if tls == "tls":
                cmd.extend(["--cacert", "/dev/null"]) # Ignore cert validation for simplicity
                cmd.extend(["--insecure"])
                # Target URL format for WS-TLS
                target_url = f"wss://{server}:{port}{path if path else '/'}"
            else:
                # Target URL format for WS
                target_url = f"ws://{server}:{port}{path if path else '/'}"
        else: # For direct TCP or other protocols (simplified)
            target_url = f"tcp://{server}:{port}" # Simplified. Might need adjustment for direct testing.
            cmd.extend(["--proxy-method", "POST"])
            cmd.extend(["--proxy", proxy_string])
    elif protocol == "ss":
        # Direct Shadowsocks support via curl is complex without ss-local.
        logger.warning("Direct Shadowsocks support via curl is complex. Consider using ss-local.")
        return [] # Returning empty for now, needs proper local proxy setup.
    elif protocol == "http":
        proxy_type = "http"
        proxy_string = f"{proxy_type}://{server}:{port}"
        cmd.extend(["--proxy", proxy_string])
        target_url = TEST_DOWNLOAD_URL # Test direct download for HTTP proxy
    else:
        logger.warning(f"Unsupported protocol for curl command: {protocol}")
        return []

    # If no proxy was explicitly set, or it's a direct connection test
    if not proxy_string:
        # If TLS is specified, use https; otherwise, http.
        # This assumes server address is directly reachable and can serve the test file.
        # This part is tricky without knowing the actual server setup.
        # For a generic test, we need to know the actual URL to fetch.
        # Assuming TEST_DOWNLOAD_URL is the target if no proxy is involved.
        if tls == "tls":
            target_url = f"https://{server}:{port}" # Simplified. Should use TEST_DOWNLOAD_URL for general speed test.
        else:
            target_url = f"http://{server}:{port}"

        # If it's a direct test, we'd ideally use the test URL, not the node's address directly.
        # For speed testing, we want to test against a known good speed test server.
        # So, if protocol is not specified or not supported for proxying, use TEST_DOWNLOAD_URL.
        if not target_url or target_url == f"tcp://{server}:{port}": # If target URL is node-specific and not a speed test server
            target_url = TEST_DOWNLOAD_URL


    # Ensure we have a target URL for the test file.
    if not target_url:
        logger.error("Could not determine a target URL for speed test.")
        return []

    cmd.append(target_url)
    logger.debug(f"Constructed curl command: {' '.join(cmd)}")
    return cmd


def test_node_speed(node: dict) -> dict:
    """
    Tests the speed of a single node.
    Returns a dictionary with test results.
    """
    if not node:
        return {"error": "No node information provided."}

    node_name = node.get('name', node.get('server', 'Unknown Node'))
    logger.info(f"Starting speed test for node: {node_name}")

    curl_command = construct_curl_command(node)

    if not curl_command:
        return {"error": "Failed to construct curl command for this node type or missing info."}

    try:
        start_time = time.time()
        # Execute the curl command
        # Capturing stdout which should contain speed_download, time_total, http_code
        # check=False prevents subprocess.run from raising an exception on non-zero exit codes
        process = subprocess.run(curl_command, capture_output=True, text=True, check=False)
        end_time = time.time()

        output_lines = process.stdout.strip().split('\n')
        speed_bps_str = output_lines[0] if output_lines else ""
        total_time_str = output_lines[1] if len(output_lines) > 1 else ""
        http_code_str = output_lines[2] if len(output_lines) > 2 else ""

        # Process results
        speed_mbps = 0.0
        # Check if speed_bps_str is a valid number before conversion
        if speed_bps_str and speed_bps_str.replace('.', '', 1).isdigit():
            speed_bps = float(speed_bps_str)
            speed_mbps = speed_bps / 1024 / 1024  # Convert bytes/sec to MB/s
        elif speed_bps_str:
            logger.warning(f"Invalid speed value received from curl: '{speed_bps_str}' for node {node_name}")

        latency = float(total_time_str) if total_time_str and total_time_str.replace('.', '', 1).isdigit() else 0.0
        http_code = int(http_code_str) if http_code_str.isdigit() else 0

        status = "OK" if (http_code >= 200 and http_code < 300) else "FAIL"

        # Adjust status if speed is very low and it's not an obvious error
        if speed_mbps < 0.1 and status == "OK" and http_code_str.startswith('2'):
            status = "Slow/Failed"
            logger.warning(f"Node {node_name} reported low speed ({speed_mbps:.2f} MB/s) despite OK HTTP status.")

        result = {
            "name": node.get('name', node.get('server')),
            "server": node.get('server'),
            "port": node.get('port'),
            "protocol": node.get('protocol'),
            "uuid": node.get('uuid'),
            "latency_ms": round(latency * 1000, 2) if latency > 0 else 0.0,
            "download_speed_mbps": round(speed_mbps, 2),
            "http_status": http_code,
            "status": status
        }
        logger.info(f"Speed test result for {result['name']}: Speed={result['download_speed_mbps']} MB/s, Latency={result['latency_ms']}ms, Status={result['status']}")
        return result

    except FileNotFoundError:
        logger.error("Error: 'curl' command not found. Please ensure curl is installed and in your PATH.")
        return {"error": "'curl' not found. Please install it."}
    except Exception as e:
        logger.error(f"An error occurred during speed test for {node_name}: {e}", exc_info=True)
        return {"error": f"Speed test failed: {e}"}

# --- For testing ---
if __name__ == "__main__":
    import json
    import base64
    from parser import parse_vmess_link
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Mocked valid vmess link for testing
    mock_vmess_data = {
        "add": "1.2.3.4", # Dummy server address
        "port": 443,
        "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "aid": 2,
        "net": "ws",
        "host": "example.com", # Dummy host
        "path": "/websocket", # Dummy path
        "tls": "tls",
        "ps": "MockedVMessNode",
        "scy": "auto",
        "type": "auto"
    }
    mock_vmess_json = json.dumps(mock_vmess_data)
    mock_vmess_encoded = base64.b64encode(mock_vmess_json.encode('utf-8')).decode('utf-8')
    test_link_vmess_valid = f"vmess://{mock_vmess_encoded}"

    print("\n--- Testing VMess Link Speed ---")
    # Note: This test will likely FAIL if 1.2.3.4:443 is not actually a VMess WS server.
    # It demonstrates the command construction and error handling.
    result = test_node_speed(parse_vmess_link(test_link_vmess_valid))
    print(f"Test Result: {result}")

    # Example of a node that might fail (bad address/port)
    test_node_fail = {
        "name": "FailingNode",
        "server": "10.0.0.1", # Non-routable IP
        "port": 12345,
        "uuid": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "protocol": "vmess",
        "network": "tcp"
    }
    print("\n--- Testing Failing Node Speed ---")
    result_fail = test_node_speed(test_node_fail)
    print(f"Test Result: {result_fail}")

    # Example with HTTP protocol (if supported)
    test_node_http = {
        "name": "HTTPNode",
        "server": "httpbin.org",
        "port": 80,
        "protocol": "http"
    }
    print("\n--- Testing HTTP Node (as proxy) ---")
    result_http = test_node_speed(test_node_http)
    print(f"Test Result: {result_http}")

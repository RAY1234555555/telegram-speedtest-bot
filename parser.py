# parser.py
import base64
import json
import logging
import urllib.parse

logger = logging.getLogger(__name__)

def parse_vmess_link(link: str) -> dict | None:
    """
    Parses a vmess:// link into a dictionary.
    """
    if not link.startswith("vmess://"):
        return None

    try:
        # Remove the prefix and decode Base64
        encoded_data = link[len("vmess://"):].strip() # Added strip() for robustness
        decoded_data = base64.b64decode(encoded_data).decode('utf-8')
        node_info = json.loads(decoded_data)

        # Extract necessary information
        parsed_node = {
            "name": node_info.get("ps", "Unknown Node"), # Display name
            "server": node.get("add"), # Use original link server if available, else from parsed
            "port": node_info.get("port"),
            "uuid": node_info.get("id"),
            "alterId": node_info.get("aid"),
            "protocol": "vmess",
            "tls": node_info.get("tls", ""), # "tls" or ""
            "network": node_info.get("net", "tcp"), # Default to tcp
            "security": node.get("scy", "auto"), # Use original link security if available, else auto
            "host": node_info.get("host", ""), # For WS/gRPC Host header
            "path": node_info.get("path", ""), # For WS path
        }

        # Basic validation
        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VMess link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed VMess node: {parsed_node['name']}")
        return parsed_node

    except (base64.binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Error parsing VMess link '{link}': {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while parsing VMess link '{link}': {e}")
        return None

def parse_subscription_link(sub_link: str) -> list[dict]:
    """
    Parses a subscription link.
    Currently, this is a placeholder. It needs to fetch content from the URL
    and parse various formats (e.g., JSON array of nodes, base64 encoded lines).
    For now, it only handles direct vmess:// link input for simplicity.
    """
    nodes = []
    logger.info(f"Attempting to parse input as link: {sub_link}")
    # --- Placeholder for Subscription Link Fetching and Parsing ---
    # In a real implementation, you would use 'requests' to fetch the content.
    # Then, you would parse the content based on its format (e.g., JSON array, base64 encoded lines).
    # Example:
    # try:
    #     import requests
    #     response = requests.get(sub_link, timeout=10)
    #     response.raise_for_status()
    #     content = response.text
    #     # Process content: split lines, decode base64, parse JSON, etc.
    #     # For example, if content is a list of vmess links on separate lines:
    #     for line in content.splitlines():
    #         if line.startswith("vmess://"):
    #             node = parse_vmess_link(line)
    #             if node:
    #                 nodes.append(node)
    # except requests.exceptions.RequestException as e:
    #     logger.error(f"Failed to fetch subscription {sub_link}: {e}")
    # except Exception as e:
    #     logger.error(f"Error processing subscription {sub_link}: {e}")

    # --- For now, assume the input is a direct node link ---
    if sub_link.startswith("vmess://"):
        node = parse_vmess_link(sub_link)
        if node:
            nodes.append(node)
    elif sub_link.startswith("http://") or sub_link.startswith("https://"):
        # If it's a URL but not a recognized direct link, log and inform it's not supported yet.
        logger.warning(f"Subscription URL parsing not implemented yet: {sub_link}")
    else:
        logger.warning(f"Unrecognized input format: {sub_link}")

    logger.info(f"Parsed {len(nodes)} nodes from input.")
    return nodes

# --- For testing ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Mocked valid vmess link for testing
    mock_vmess_data = {
        "add": "1.2.3.4",
        "port": 443,
        "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
        "aid": 2,
        "net": "ws",
        "host": "example.com",
        "path": "/websocket",
        "tls": "tls",
        "ps": "MyTestVMessNode",
        "scy": "auto",
        "type": "auto"
    }
    mock_vmess_json = json.dumps(mock_vmess_data)
    mock_vmess_encoded = base64.b64encode(mock_vmess_json.encode('utf-8')).decode('utf-8')
    test_link_vmess_valid = f"vmess://{mock_vmess_encoded}"

    print("\n--- Testing VMess Link ---")
    parsed_vmess = parse_vmess_link(test_link_vmess_valid)
    if parsed_vmess:
        print(f"Parsed VMess Node: {parsed_vmess['name']}")
        print(f"  Server: {parsed_vmess['server']}:{parsed_vmess['port']}")
        print(f"  UUID: {parsed_vmess['uuid']}")
        print(f"  Network: {parsed_vmess['network']}, TLS: {parsed_vmess['tls']}")
    else:
        print("Failed to parse VMess link.")

    print("\n--- Testing Subscription Link (Simplified) ---")
    nodes_from_sub = parse_subscription_link(test_link_vmess_valid)
    print(f"Nodes found from input: {len(nodes_from_sub)}")
    if nodes_from_sub:
        print(f"First node: {nodes_from_sub[0]['name']}")

    # Test invalid link
    print("\n--- Testing Invalid Link ---")
    invalid_link = "ss://some_encoded_data"
    parsed_invalid = parse_vmess_link(invalid_link)
    if not parsed_invalid:
        print("Correctly failed to parse invalid link.")

    invalid_base64 = "vmess://invalid_base64_string"
    parsed_invalid_b64 = parse_vmess_link(invalid_base64)
    if not parsed_invalid_b64:
        print("Correctly failed to parse link with invalid Base64.")

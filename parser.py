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
        encoded_data = link[len("vmess://"):]
        decoded_data = base64.b64decode(encoded_data).decode('utf-8')
        node_info = json.loads(decoded_data)

        # Extract necessary information
        parsed_node = {
            "name": node_info.get("ps", "Unknown Node"), # Display name
            "server": node_info.get("add"),
            "port": node_info.get("port"),
            "uuid": node_info.get("id"),
            "alterId": node_info.get("aid"),
            "protocol": "vmess",
            "tls": node_info.get("tls", ""), # "tls": "tls" or ""
            "network": node_info.get("net", "tcp"), # Default to tcp if not specified
            "security": node_info.get("scy", "auto"), # Security type, auto or specific
            "host": node_info.get("host", ""), # For WS/gRPC Host header
            "path": node_info.get("path", ""), # For WS path
            # Add more fields as needed for other protocols or advanced settings
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
    Parses a subscription link (currently only supports direct vmess:// lines as an example).
    In a real scenario, this would fetch content from the URL and parse multiple lines.
    """
    nodes = []
    # For now, assume the input itself is a node or a link that returns nodes.
    # A more complete parser would fetch from the URL.

    # Example: If the input is a single vmess link
    if sub_link.startswith("vmess://"):
        node = parse_vmess_link(sub_link)
        if node:
            nodes.append(node)
    # TODO: Implement fetching from URL and parsing multiple lines (e.g., JSON array of nodes)
    # Example for subscription URL (needs 'requests' library):
    # try:
    #     import requests
    #     response = requests.get(sub_link, timeout=10)
    #     response.raise_for_status() # Raise an exception for bad status codes
    #     # Assuming subscription returns lines of nodes, each line is a link or JSON
    #     # This part depends heavily on the subscription format.
    #     # For now, let's just simulate it if it's a valid link
    #     logger.info(f"Fetched subscription from {sub_link}")
    #     # Placeholder: if sub_link itself is a valid vmess link, parse it.
    #     # In reality, you'd parse the content of response.text
    #     node = parse_vmess_link(sub_link) # This is a simplification
    #     if node:
    #         nodes.append(node)
    # except requests.exceptions.RequestException as e:
    #     logger.error(f"Failed to fetch subscription {sub_link}: {e}")
    # except Exception as e:
    #     logger.error(f"Error processing subscription {sub_link}: {e}")

    logger.info(f"Parsed {len(nodes)} nodes from input.")
    return nodes

# --- For testing ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Example vmess link (replace with a real one if testing)
    # This is a dummy link for demonstration. You need a valid vmess:// link.
    test_link_vmess = "vmess://ey...==" # Replace with a real encoded vmess link

    # You would need a valid vmess link for this to work.
    # For now, let's use a placeholder structure.
    # Example of a valid vmess link structure (encoded):
    # {"add":"1.2.3.4","aid":2,"host":"example.com","id":"your-uuid-here","net":"ws","path":"/","port":443,"ps":"TestNode","tls":"tls","type":"auto"}
    # Base64 encoded: vmess://eyJh...

    # Mocking a vmess link for testing
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

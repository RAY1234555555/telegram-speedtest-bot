import base64
import json
import logging
import urllib.parse
import requests
import re
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

def parse_vmess_link(link: str) -> Optional[Dict]:
    """解析 vmess:// 链接"""
    if not link.startswith("vmess://"):
        return None

    try:
        encoded_data = link[len("vmess://"):].strip()
        decoded_data = base64.b64decode(encoded_data).decode('utf-8')
        node_info = json.loads(decoded_data)

        parsed_node = {
            "name": node_info.get("ps", "Unknown VMess Node"),
            "server": node_info.get("add"),
            "port": int(node_info.get("port", 443)),
            "uuid": node_info.get("id"),
            "alterId": int(node_info.get("aid", 0)),
            "protocol": "vmess",
            "tls": node_info.get("tls", ""),
            "network": node_info.get("net", "tcp"),
            "security": node_info.get("scy", "auto"),
            "host": node_info.get("host", ""),
            "path": node_info.get("path", ""),
            "type": node_info.get("type", "none")
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VMess link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed VMess node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing VMess link: {e}")
        return None

def parse_vless_link(link: str) -> Optional[Dict]:
    """解析 vless:// 链接"""
    if not link.startswith("vless://"):
        return None

    try:
        # vless://uuid@server:port?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=safari&pbk=...
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        # 从fragment中获取节点名称
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown VLess Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "uuid": url_parts.username,
            "protocol": "vless",
            "encryption": query_params.get("encryption", ["none"])[0],
            "flow": query_params.get("flow", [""])[0],
            "security": query_params.get("security", ["none"])[0],
            "sni": query_params.get("sni", [""])[0],
            "fp": query_params.get("fp", [""])[0],
            "pbk": query_params.get("pbk", [""])[0],
            "sid": query_params.get("sid", [""])[0],
            "type": query_params.get("type", ["tcp"])[0],
            "host": query_params.get("host", [""])[0],
            "path": query_params.get("path", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VLess link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed VLess node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing VLess link: {e}")
        return None

def parse_shadowsocks_link(link: str) -> Optional[Dict]:
    """解析 ss:// 链接"""
    if not link.startswith("ss://"):
        return None

    try:
        # ss://method:password@server:port#name
        url_parts = urllib.parse.urlparse(link)
        
        if url_parts.username and url_parts.password:
            # 新格式
            method = url_parts.username
            password = url_parts.password
        else:
            # 旧格式，需要base64解码
            encoded_part = link[5:].split('@')[0]
            decoded = base64.b64decode(encoded_part).decode('utf-8')
            method, password = decoded.split(':', 1)
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown SS Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 8388),
            "method": method,
            "password": password,
            "protocol": "shadowsocks"
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["method"], parsed_node["password"]]):
            logger.warning(f"Shadowsocks link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed Shadowsocks node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Shadowsocks link: {e}")
        return None

def parse_hysteria2_link(link: str) -> Optional[Dict]:
    """解析 hy2:// 或 hysteria2:// 链接"""
    if not (link.startswith("hy2://") or link.startswith("hysteria2://")):
        return None

    try:
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown Hysteria2 Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "password": url_parts.username or query_params.get("auth", [""])[0],
            "protocol": "hysteria2",
            "sni": query_params.get("sni", [""])[0],
            "insecure": query_params.get("insecure", ["0"])[0] == "1",
            "obfs": query_params.get("obfs", [""])[0],
            "obfs_password": query_params.get("obfs-password", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"]]):
            logger.warning(f"Hysteria2 link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed Hysteria2 node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Hysteria2 link: {e}")
        return None

def parse_trojan_link(link: str) -> Optional[Dict]:
    """解析 trojan:// 链接"""
    if not link.startswith("trojan://"):
        return None

    try:
        url_parts = urllib.parse.urlparse(link)
        query_params = urllib.parse.parse_qs(url_parts.query)
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown Trojan Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 443),
            "password": url_parts.username,
            "protocol": "trojan",
            "sni": query_params.get("sni", [""])[0],
            "type": query_params.get("type", ["tcp"])[0],
            "host": query_params.get("host", [""])[0],
            "path": query_params.get("path", [""])[0],
            "security": query_params.get("security", ["tls"])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["password"]]):
            logger.warning(f"Trojan link missing essential fields: {link}")
            return None

        logger.info(f"Successfully parsed Trojan node: {parsed_node['name']}")
        return parsed_node

    except Exception as e:
        logger.error(f"Error parsing Trojan link: {e}")
        return None

def parse_single_node(link: str) -> Optional[Dict]:
    """解析单个节点链接"""
    link = link.strip()
    
    if link.startswith("vmess://"):
        return parse_vmess_link(link)
    elif link.startswith("vless://"):
        return parse_vless_link(link)
    elif link.startswith("ss://"):
        return parse_shadowsocks_link(link)
    elif link.startswith(("hy2://", "hysteria2://")):
        return parse_hysteria2_link(link)
    elif link.startswith("trojan://"):
        return parse_trojan_link(link)
    else:
        logger.warning(f"Unsupported protocol: {link[:20]}...")
        return None

def fetch_subscription(url: str, timeout: int = 10) -> Optional[str]:
    """获取订阅内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Failed to fetch subscription {url}: {e}")
        return None

def parse_subscription_content(content: str) -> List[Dict]:
    """解析订阅内容"""
    nodes = []
    
    try:
        # 尝试base64解码
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            content = decoded_content
        except:
            pass  # 如果不是base64编码，继续使用原内容
        
        # 按行分割并解析每个节点
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            node = parse_single_node(line)
            if node:
                nodes.append(node)
    
    except Exception as e:
        logger.error(f"Error parsing subscription content: {e}")
    
    return nodes

def parse_subscription_link(sub_link: str) -> List[Dict]:
    """解析订阅链接"""
    nodes = []
    logger.info(f"Attempting to parse subscription: {sub_link}")
    
    if sub_link.startswith(("http://", "https://")):
        # 获取订阅内容
        content = fetch_subscription(sub_link)
        if content:
            nodes = parse_subscription_content(content)
    else:
        # 尝试作为单个节点解析
        node = parse_single_node(sub_link)
        if node:
            nodes.append(node)
    
    logger.info(f"Parsed {len(nodes)} nodes from subscription")
    return nodes

def get_node_info_summary(node: Dict) -> str:
    """获取节点信息摘要"""
    protocol = node.get('protocol', 'unknown').upper()
    name = node.get('name', 'Unknown Node')
    server = node.get('server', 'unknown')
    port = node.get('port', 'unknown')
    
    summary = f"📡 {name}\n"
    summary += f"🔗 Protocol: {protocol}\n"
    summary += f"🌐 Server: {server}:{port}\n"
    
    if protocol == "VMESS":
        summary += f"🔑 UUID: {node.get('uuid', 'N/A')[:8]}...\n"
        summary += f"🛡️ Security: {node.get('security', 'auto')}\n"
        summary += f"🌐 Network: {node.get('network', 'tcp')}\n"
    elif protocol == "VLESS":
        summary += f"🔑 UUID: {node.get('uuid', 'N/A')[:8]}...\n"
        summary += f"🔒 Security: {node.get('security', 'none')}\n"
        summary += f"🌊 Flow: {node.get('flow', 'none')}\n"
    elif protocol == "SHADOWSOCKS":
        summary += f"🔐 Method: {node.get('method', 'N/A')}\n"
    elif protocol == "HYSTERIA2":
        summary += f"🔐 Auth: {'Yes' if node.get('password') else 'No'}\n"
        summary += f"🛡️ SNI: {node.get('sni', 'N/A')}\n"
    elif protocol == "TROJAN":
        summary += f"🔑 Password: {'Set' if node.get('password') else 'None'}\n"
        summary += f"🛡️ SNI: {node.get('sni', 'N/A')}\n"
    
    return summary

# 测试函数
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 测试各种协议
    test_links = [
        "vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLCJpZCI6ImExYjJjM2Q0LWU1ZjYtNzg5MC0xMjM0LTU2Nzg5MGFiY2RlZiIsImFpZCI6MiwibmV0Ijoid3MiLCJob3N0IjoiZXhhbXBsZS5jb20iLCJwYXRoIjoiL3dlYnNvY2tldCIsInRscyI6InRscyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0eXBlIjoiYXV0byJ9",
        "vless://uuid@example.com:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=safari#Test%20VLess",
        "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@example.com:8388#Test%20SS",
        "hy2://password@example.com:443?sni=example.com#Test%20Hysteria2",
        "trojan://password@example.com:443?sni=example.com#Test%20Trojan"
    ]
    
    for link in test_links:
        print(f"\n--- Testing: {link[:50]}... ---")
        node = parse_single_node(link)
        if node:
            print(get_node_info_summary(node))
        else:
            print("Failed to parse")

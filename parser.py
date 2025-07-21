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
        # 添加填充以确保正确的base64解码
        missing_padding = len(encoded_data) % 4
        if missing_padding:
            encoded_data += '=' * (4 - missing_padding)
            
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
            "type": node_info.get("type", "none"),
            "sni": node_info.get("sni", ""),
            "alpn": node_info.get("alpn", ""),
            "fp": node_info.get("fp", "")
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VMess link missing essential fields: {link[:50]}...")
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
        # vless://uuid@server:port?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.microsoft.com&fp=safari&pbk=...#name
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
            "path": query_params.get("path", [""])[0],
            "headerType": query_params.get("headerType", ["none"])[0],
            "alpn": query_params.get("alpn", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["uuid"]]):
            logger.warning(f"VLess link missing essential fields: {link[:50]}...")
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
        # ss://method:password@server:port#name 或 ss://base64encoded#name
        url_parts = urllib.parse.urlparse(link)
        
        if url_parts.username and url_parts.password:
            # 新格式: ss://method:password@server:port#name
            method = url_parts.username
            password = url_parts.password
        else:
            # 旧格式: ss://base64encoded@server:port#name 或 ss://base64encoded#name
            if '@' in link:
                encoded_part = link[5:].split('@')[0]
            else:
                encoded_part = link[5:].split('#')[0]
            
            # 添加填充
            missing_padding = len(encoded_part) % 4
            if missing_padding:
                encoded_part += '=' * (4 - missing_padding)
                
            try:
                decoded = base64.b64decode(encoded_part).decode('utf-8')
                if ':' in decoded:
                    method, password = decoded.split(':', 1)
                else:
                    method, password = "aes-256-gcm", decoded
            except:
                logger.error(f"Failed to decode SS credentials: {encoded_part}")
                return None
        
        name = urllib.parse.unquote(url_parts.fragment) if url_parts.fragment else "Unknown SS Node"
        
        parsed_node = {
            "name": name,
            "server": url_parts.hostname,
            "port": int(url_parts.port or 8388),
            "method": method,
            "password": password,
            "protocol": "shadowsocks",
            "plugin": "",
            "plugin_opts": ""
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["method"], parsed_node["password"]]):
            logger.warning(f"Shadowsocks link missing essential fields: {link[:50]}...")
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
            "obfs_password": query_params.get("obfs-password", [""])[0],
            "up": query_params.get("up", [""])[0],
            "down": query_params.get("down", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"]]):
            logger.warning(f"Hysteria2 link missing essential fields: {link[:50]}...")
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
            "security": query_params.get("security", ["tls"])[0],
            "alpn": query_params.get("alpn", [""])[0],
            "fp": query_params.get("fp", [""])[0]
        }

        if not all([parsed_node["server"], parsed_node["port"], parsed_node["password"]]):
            logger.warning(f"Trojan link missing essential fields: {link[:50]}...")
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

def fetch_subscription(url: str, timeout: int = 15) -> Optional[str]:
    """获取订阅内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, verify=False)
        response.raise_for_status()
        
        logger.info(f"Successfully fetched subscription, content length: {len(response.text)}")
        return response.text
        
    except requests.exceptions.Timeout:
        logger.error(f"Subscription fetch timeout: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch subscription {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching subscription {url}: {e}")
        return None

def parse_subscription_content(content: str) -> List[Dict]:
    """解析订阅内容"""
    nodes = []
    
    try:
        # 尝试base64解码
        try:
            decoded_content = base64.b64decode(content).decode('utf-8')
            content = decoded_content
            logger.info("Successfully decoded base64 subscription content")
        except:
            logger.info("Subscription content is not base64 encoded, using as-is")
        
        # 按行分割并解析每个节点
        lines = content.strip().split('\n')
        logger.info(f"Processing {len(lines)} lines from subscription")
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            node = parse_single_node(line)
            if node:
                nodes.append(node)
                logger.debug(f"Parsed node {i+1}: {node['name']}")
            else:
                logger.debug(f"Failed to parse line {i+1}: {line[:50]}...")
    
    except Exception as e:
        logger.error(f"Error parsing subscription content: {e}")
    
    logger.info(f"Successfully parsed {len(nodes)} nodes from subscription")
    return nodes

def parse_subscription_link(sub_link: str) -> List[Dict]:
    """解析订阅链接"""
    nodes = []
    logger.info(f"Attempting to parse subscription: {sub_link[:100]}...")
    
    if sub_link.startswith(("http://", "https://")):
        # 获取订阅内容
        content = fetch_subscription(sub_link)
        if content:
            nodes = parse_subscription_content(content)
        else:
            logger.error("Failed to fetch subscription content")
    else:
        # 尝试作为单个节点解析
        node = parse_single_node(sub_link)
        if node:
            nodes.append(node)
    
    logger.info(f"Final result: {len(nodes)} nodes parsed from subscription")
    return nodes

def get_node_info_summary(node: Dict) -> str:
    """获取节点信息摘要"""
    protocol = node.get('protocol', 'unknown').upper()
    name = node.get('name', 'Unknown Node')
    server = node.get('server', 'unknown')
    port = node.get('port', 'unknown')
    
    summary = f"📡 **{name}**\n"
    summary += f"🔗 协议: {protocol}\n"
    summary += f"🌐 服务器: `{server}:{port}`\n"
    
    if protocol == "VMESS":
        summary += f"🔑 UUID: `{node.get('uuid', 'N/A')[:8]}...`\n"
        summary += f"🛡️ 加密: {node.get('security', 'auto')}\n"
        summary += f"🌐 网络: {node.get('network', 'tcp')}\n"
        if node.get('tls'):
            summary += f"🔒 TLS: {node.get('tls')}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
    elif protocol == "VLESS":
        summary += f"🔑 UUID: `{node.get('uuid', 'N/A')[:8]}...`\n"
        summary += f"🔒 安全: {node.get('security', 'none')}\n"
        if node.get('flow'):
            summary += f"🌊 流控: {node.get('flow')}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
    elif protocol == "SHADOWSOCKS":
        summary += f"🔐 加密: {node.get('method', 'N/A')}\n"
        summary += f"🔑 密码: `{node.get('password', 'N/A')[:8]}...`\n"
    elif protocol == "HYSTERIA2":
        summary += f"🔐 认证: {'是' if node.get('password') else '否'}\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
        if node.get('obfs'):
            summary += f"🎭 混淆: {node.get('obfs')}\n"
    elif protocol == "TROJAN":
        summary += f"🔑 密码: `{node.get('password', 'N/A')[:8]}...`\n"
        if node.get('sni'):
            summary += f"🏷️ SNI: {node.get('sni')}\n"
        summary += f"🔒 安全: {node.get('security', 'tls')}\n"
    
    return summary

def detect_region_from_server(server: str) -> str:
    """根据服务器地址检测地区"""
    server = server.lower()
    
    # 常见地区关键词映射
    region_keywords = {
        '🇺🇸 美国': ['us', 'usa', 'america', 'united', 'states', 'california', 'newyork', 'texas', 'virginia'],
        '🇯🇵 日本': ['jp', 'japan', 'tokyo', 'osaka', 'kyoto'],
        '🇭🇰 香港': ['hk', 'hongkong', 'hong-kong'],
        '🇸🇬 新加坡': ['sg', 'singapore', 'singapur'],
        '🇩🇪 德国': ['de', 'germany', 'deutsch', 'berlin', 'frankfurt'],
        '🇬🇧 英国': ['uk', 'britain', 'england', 'london'],
        '🇫🇷 法国': ['fr', 'france', 'paris'],
        '🇨🇦 加拿大': ['ca', 'canada', 'toronto', 'vancouver'],
        '🇦🇺 澳大利亚': ['au', 'australia', 'sydney', 'melbourne'],
        '🇰🇷 韩国': ['kr', 'korea', 'seoul'],
        '🇳🇱 荷兰': ['nl', 'netherlands', 'amsterdam'],
        '🇷🇺 俄罗斯': ['ru', 'russia', 'moscow'],
        '🇮🇳 印度': ['in', 'india', 'mumbai', 'delhi'],
        '🇧🇷 巴西': ['br', 'brazil', 'sao', 'paulo'],
        '🇹🇼 台湾': ['tw', 'taiwan', 'taipei'],
        '🇹🇭 泰国': ['th', 'thailand', 'bangkok'],
        '🇲🇾 马来西亚': ['my', 'malaysia', 'kuala', 'lumpur'],
        '🇵🇭 菲律宾': ['ph', 'philippines', 'manila'],
        '🇻🇳 越南': ['vn', 'vietnam', 'hanoi', 'saigon'],
        '🇮🇩 印尼': ['id', 'indonesia', 'jakarta'],
        '🇦🇪 阿联酋': ['ae', 'uae', 'dubai', 'emirates'],
        '🇹🇷 土耳其': ['tr', 'turkey', 'istanbul'],
        '🇮🇱 以色列': ['il', 'israel', 'telaviv'],
        '🇿🇦 南非': ['za', 'south', 'africa', 'cape', 'town'],
        '🇦🇷 阿根廷': ['ar', 'argentina', 'buenos', 'aires'],
        '🇨🇱 智利': ['cl', 'chile', 'santiago'],
        '🇲🇽 墨西哥': ['mx', 'mexico', 'mexico', 'city'],
        '🇪🇸 西班牙': ['es', 'spain', 'madrid', 'barcelona'],
        '🇮🇹 意大利': ['it', 'italy', 'rome', 'milan'],
        '🇨🇭 瑞士': ['ch', 'switzerland', 'zurich', 'geneva'],
        '🇸🇪 瑞典': ['se', 'sweden', 'stockholm'],
        '🇳🇴 挪威': ['no', 'norway', 'oslo'],
        '🇩🇰 丹麦': ['dk', 'denmark', 'copenhagen'],
        '🇫🇮 芬兰': ['fi', 'finland', 'helsinki'],
        '🇵🇱 波兰': ['pl', 'poland', 'warsaw'],
        '🇨🇿 捷克': ['cz', 'czech', 'prague'],
        '🇦🇹 奥地利': ['at', 'austria', 'vienna'],
        '🇧🇪 比利时': ['be', 'belgium', 'brussels'],
        '🇵🇹 葡萄牙': ['pt', 'portugal', 'lisbon'],
        '🇬🇷 希腊': ['gr', 'greece', 'athens'],
        '🇭🇺 匈牙利': ['hu', 'hungary', 'budapest'],
        '🇷🇴 罗马尼亚': ['ro', 'romania', 'bucharest'],
        '🇧🇬 保加利亚': ['bg', 'bulgaria', 'sofia'],
        '🇭🇷 克罗地亚': ['hr', 'croatia', 'zagreb'],
        '🇸🇮 斯洛文尼亚': ['si', 'slovenia', 'ljubljana'],
        '🇸🇰 斯洛伐克': ['sk', 'slovakia', 'bratislava'],
        '🇱🇹 立陶宛': ['lt', 'lithuania', 'vilnius'],
        '🇱🇻 拉脱维亚': ['lv', 'latvia', 'riga'],
        '🇪🇪 爱沙尼亚': ['ee', 'estonia', 'tallinn'],
        '🇺🇦 乌克兰': ['ua', 'ukraine', 'kiev', 'kyiv'],
        '🇧🇾 白俄罗斯': ['by', 'belarus', 'minsk'],
        '🇲🇩 摩尔多瓦': ['md', 'moldova', 'chisinau'],
        '🇷🇸 塞尔维亚': ['rs', 'serbia', 'belgrade'],
        '🇲🇪 黑山': ['me', 'montenegro', 'podgorica'],
        '🇧🇦 波黑': ['ba', 'bosnia', 'sarajevo'],
        '🇲🇰 北马其顿': ['mk', 'macedonia', 'skopje'],
        '🇦🇱 阿尔巴尼亚': ['al', 'albania', 'tirana'],
        '🇽🇰 科索沃': ['xk', 'kosovo', 'pristina'],
        '🇨🇳 中国': ['cn', 'china', 'beijing', 'shanghai', 'guangzhou', 'shenzhen']
    }
    
    for region, keywords in region_keywords.items():
        for keyword in keywords:
            if keyword in server:
                return region
    
    return '🌍 未知地区'

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

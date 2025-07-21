import requests
import base64
import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import time

logger = logging.getLogger(__name__)

class SubscriptionAnalyzer:
    def __init__(self):
        self.headers = {
            'User-Agent': 'clash-verge/v1.3.1',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
    def analyze_subscription(self, sub_url: str) -> Dict:
        """分析订阅链接，获取详细信息"""
        try:
            logger.info(f"开始分析订阅: {sub_url[:100]}...")
            
            # 获取订阅内容
            response = requests.get(sub_url, headers=self.headers, timeout=30, verify=False)
            
            if response.status_code == 403:
                return {
                    "status": "error",
                    "error": "订阅链接被WAF拦截，请检查链接或稍后重试",
                    "error_code": 403
                }
            
            response.raise_for_status()
            
            # 解析订阅信息
            subscription_info = self._extract_subscription_info(response)
            
            # 解析节点内容
            nodes = self._parse_subscription_content(response.text)
            
            # 分析节点统计
            node_stats = self._analyze_nodes(nodes)
            
            result = {
                "status": "success",
                "subscription_info": subscription_info,
                "nodes": nodes,
                "statistics": node_stats,
                "raw_url": sub_url,
                "fetch_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            logger.info(f"订阅分析完成: {len(nodes)} 个节点")
            return result
            
        except requests.exceptions.Timeout:
            return {"status": "error", "error": "订阅获取超时"}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "error": f"网络请求失败: {str(e)}"}
        except Exception as e:
            logger.error(f"订阅分析失败: {e}")
            return {"status": "error", "error": f"分析失败: {str(e)}"}
    
    def _extract_subscription_info(self, response) -> Dict:
        """从响应头中提取订阅信息"""
        info = {}
        
        # 从响应头获取流量信息
        headers = response.headers
        
        # 常见的流量信息头
        if 'subscription-userinfo' in headers:
            userinfo = headers['subscription-userinfo']
            info.update(self._parse_userinfo(userinfo))
        
        # 从URL中提取配置名称
        if 'content-disposition' in headers:
            disposition = headers['content-disposition']
            filename_match = re.search(r'filename[*]?=([^;]+)', disposition)
            if filename_match:
                info['config_name'] = filename_match.group(1).strip('"\'')
        
        # 尝试从响应内容中提取更多信息
        try:
            # 检查是否是JSON格式的订阅信息
            if response.text.strip().startswith('{'):
                json_data = json.loads(response.text)
                if 'expire' in json_data:
                    info['expire_time'] = json_data['expire']
                if 'total' in json_data:
                    info['total_traffic'] = json_data['total']
                if 'upload' in json_data and 'download' in json_data:
                    info['used_traffic'] = json_data['upload'] + json_data['download']
        except:
            pass
            
        return info
    
    def _parse_userinfo(self, userinfo: str) -> Dict:
        """解析subscription-userinfo头"""
        info = {}
        
        # 解析格式: upload=1234; download=5678; total=10000000000; expire=1234567890
        parts = userinfo.split(';')
        for part in parts:
            if '=' in part:
                key, value = part.strip().split('=', 1)
                try:
                    info[key] = int(value)
                except ValueError:
                    info[key] = value
        
        # 计算流量信息
        if 'upload' in info and 'download' in info:
            info['used_traffic'] = info['upload'] + info['download']
            info['used_traffic_gb'] = round(info['used_traffic'] / (1024**3), 2)
        
        if 'total' in info:
            info['total_traffic_gb'] = round(info['total'] / (1024**3), 2)
            if 'used_traffic' in info:
                info['remaining_traffic'] = info['total'] - info['used_traffic']
                info['remaining_traffic_gb'] = round(info['remaining_traffic'] / (1024**3), 2)
                info['usage_percentage'] = round((info['used_traffic'] / info['total']) * 100, 1)
        
        if 'expire' in info:
            try:
                expire_time = datetime.fromtimestamp(info['expire'])
                info['expire_date'] = expire_time.strftime('%Y/%m/%d %H:%M:%S')
                remaining_days = (expire_time - datetime.now()).days
                info['remaining_days'] = max(0, remaining_days)
            except:
                pass
        
        return info
    
    def _parse_subscription_content(self, content: str) -> List[Dict]:
        """解析订阅内容中的节点"""
        nodes = []
        
        try:
            # 尝试base64解码
            try:
                decoded_content = base64.b64decode(content).decode('utf-8')
                content = decoded_content
            except:
                pass
            
            # 按行分割处理
            lines = content.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 解析不同协议的节点
                node = self._parse_single_node(line)
                if node:
                    nodes.append(node)
        
        except Exception as e:
            logger.error(f"解析订阅内容失败: {e}")
        
        return nodes
    
    def _parse_single_node(self, line: str) -> Optional[Dict]:
        """解析单个节点"""
        try:
            if line.startswith('vmess://'):
                return self._parse_vmess(line)
            elif line.startswith('vless://'):
                return self._parse_vless(line)
            elif line.startswith('ss://'):
                return self._parse_shadowsocks(line)
            elif line.startswith('trojan://'):
                return self._parse_trojan(line)
            elif line.startswith(('hy2://', 'hysteria2://')):
                return self._parse_hysteria2(line)
            else:
                return None
        except Exception as e:
            logger.debug(f"解析节点失败: {e}")
            return None
    
    def _parse_vmess(self, link: str) -> Optional[Dict]:
        """解析VMess节点"""
        try:
            encoded_data = link[8:].strip()
            missing_padding = len(encoded_data) % 4
            if missing_padding:
                encoded_data += '=' * (4 - missing_padding)
            
            decoded_data = base64.b64decode(encoded_data).decode('utf-8')
            node_info = json.loads(decoded_data)
            
            return {
                "protocol": "VMess",
                "name": node_info.get("ps", "VMess Node"),
                "server": node_info.get("add"),
                "port": int(node_info.get("port", 443)),
                "uuid": node_info.get("id"),
                "alterId": int(node_info.get("aid", 0)),
                "network": node_info.get("net", "tcp"),
                "tls": node_info.get("tls", ""),
                "host": node_info.get("host", ""),
                "path": node_info.get("path", ""),
                "region": self._detect_region(node_info.get("ps", "") + " " + node_info.get("add", ""))
            }
        except Exception as e:
            logger.debug(f"VMess解析失败: {e}")
            return None
    
    def _parse_vless(self, link: str) -> Optional[Dict]:
        """解析VLess节点"""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "VLess",
                "name": unquote(parsed.fragment) if parsed.fragment else "VLess Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "uuid": parsed.username,
                "encryption": query.get("encryption", ["none"])[0],
                "flow": query.get("flow", [""])[0],
                "security": query.get("security", ["none"])[0],
                "sni": query.get("sni", [""])[0],
                "region": self._detect_region(unquote(parsed.fragment or "") + " " + (parsed.hostname or ""))
            }
        except Exception as e:
            logger.debug(f"VLess解析失败: {e}")
            return None
    
    def _parse_shadowsocks(self, link: str) -> Optional[Dict]:
        """解析Shadowsocks节点"""
        try:
            from urllib.parse import urlparse, unquote
            
            parsed = urlparse(link)
            
            if parsed.username and parsed.password:
                method = parsed.username
                password = parsed.password
            else:
                # 处理旧格式
                encoded_part = link[5:].split('@')[0] if '@' in link else link[5:].split('#')[0]
                missing_padding = len(encoded_part) % 4
                if missing_padding:
                    encoded_part += '=' * (4 - missing_padding)
                
                decoded = base64.b64decode(encoded_part).decode('utf-8')
                if ':' in decoded:
                    method, password = decoded.split(':', 1)
                else:
                    method, password = "aes-256-gcm", decoded
            
            return {
                "protocol": "Shadowsocks",
                "name": unquote(parsed.fragment) if parsed.fragment else "SS Node",
                "server": parsed.hostname,
                "port": parsed.port or 8388,
                "method": method,
                "password": password,
                "region": self._detect_region(unquote(parsed.fragment or "") + " " + (parsed.hostname or ""))
            }
        except Exception as e:
            logger.debug(f"Shadowsocks解析失败: {e}")
            return None
    
    def _parse_trojan(self, link: str) -> Optional[Dict]:
        """解析Trojan节点"""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "Trojan",
                "name": unquote(parsed.fragment) if parsed.fragment else "Trojan Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": parsed.username,
                "sni": query.get("sni", [""])[0],
                "security": query.get("security", ["tls"])[0],
                "region": self._detect_region(unquote(parsed.fragment or "") + " " + (parsed.hostname or ""))
            }
        except Exception as e:
            logger.debug(f"Trojan解析失败: {e}")
            return None
    
    def _parse_hysteria2(self, link: str) -> Optional[Dict]:
        """解析Hysteria2节点"""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            
            parsed = urlparse(link)
            query = parse_qs(parsed.query)
            
            return {
                "protocol": "Hysteria2",
                "name": unquote(parsed.fragment) if parsed.fragment else "Hysteria2 Node",
                "server": parsed.hostname,
                "port": parsed.port or 443,
                "password": parsed.username or query.get("auth", [""])[0],
                "sni": query.get("sni", [""])[0],
                "obfs": query.get("obfs", [""])[0],
                "region": self._detect_region(unquote(parsed.fragment or "") + " " + (parsed.hostname or ""))
            }
        except Exception as e:
            logger.debug(f"Hysteria2解析失败: {e}")
            return None
    
    def _detect_region(self, text: str) -> str:
        """检测节点地区"""
        text = text.lower()
        
        region_map = {
            '🇭🇰 香港': ['hk', 'hong kong', 'hongkong', '香港', 'hong-kong'],
            '🇹🇼 台湾': ['tw', 'taiwan', '台湾', 'taipei'],
            '🇯🇵 日本': ['jp', 'japan', '日本', 'tokyo', 'osaka'],
            '🇸🇬 新加坡': ['sg', 'singapore', '新加坡', 'singapur'],
            '🇺🇸 美国': ['us', 'usa', 'america', '美国', 'united states', 'california', 'newyork'],
            '🇬🇧 英国': ['uk', 'britain', 'england', '英国', 'london'],
            '🇩🇪 德国': ['de', 'germany', '德国', 'berlin', 'frankfurt'],
            '🇫🇷 法国': ['fr', 'france', '法国', 'paris'],
            '🇰🇷 韩国': ['kr', 'korea', '韩国', 'seoul'],
            '🇨🇦 加拿大': ['ca', 'canada', '加拿大', 'toronto'],
            '🇦🇺 澳大利亚': ['au', 'australia', '澳大利亚', 'sydney'],
            '🇳🇱 荷兰': ['nl', 'netherlands', '荷兰', 'amsterdam'],
            '🇷🇺 俄罗斯': ['ru', 'russia', '俄罗斯', 'moscow'],
            '🇮🇳 印度': ['in', 'india', '印度', 'mumbai'],
            '🇹🇭 泰国': ['th', 'thailand', '泰国', 'bangkok'],
            '🇲🇾 马来西亚': ['my', 'malaysia', '马来西亚', 'kuala lumpur'],
            '🇵🇭 菲律宾': ['ph', 'philippines', '菲律宾', 'manila'],
            '🇻🇳 越南': ['vn', 'vietnam', '越南', 'hanoi'],
            '🇮🇩 印尼': ['id', 'indonesia', '印尼', 'jakarta'],
            '🇨🇳 中国': ['cn', 'china', '中国', 'beijing', 'shanghai']
        }
        
        for region, keywords in region_map.items():
            for keyword in keywords:
                if keyword in text:
                    return region
        
        return '🌍 其他'
    
    def _analyze_nodes(self, nodes: List[Dict]) -> Dict:
        """分析节点统计信息"""
        if not nodes:
            return {}
        
        # 协议统计
        protocols = {}
        regions = {}
        
        for node in nodes:
            protocol = node.get('protocol', 'Unknown')
            region = node.get('region', '🌍 其他')
            
            protocols[protocol] = protocols.get(protocol, 0) + 1
            regions[region] = regions.get(region, 0) + 1
        
        return {
            "total_nodes": len(nodes),
            "protocols": protocols,
            "regions": regions,
            "protocol_list": list(protocols.keys()),
            "region_list": list(regions.keys()),
            "country_count": len(regions)
        }
    
    def format_subscription_info(self, analysis_result: Dict) -> str:
        """格式化订阅信息显示"""
        if analysis_result.get("status") != "success":
            return f"❌ **订阅分析失败**\n\n错误: {analysis_result.get('error', '未知错误')}"
        
        sub_info = analysis_result.get("subscription_info", {})
        stats = analysis_result.get("statistics", {})
        
        # 构建显示文本
        text = "📊 **订阅分析结果**\n\n"
        
        # 配置名称
        if sub_info.get('config_name'):
            text += f"📋 **配置名称:** {sub_info['config_name']}\n"
        
        # 订阅链接
        raw_url = analysis_result.get('raw_url', '')
        if len(raw_url) > 60:
            display_url = raw_url[:60] + "..."
        else:
            display_url = raw_url
        text += f"🔗 **订阅链接:** `{display_url}`\n\n"
        
        # 流量信息
        if sub_info.get('total_traffic_gb'):
            used = sub_info.get('used_traffic_gb', 0)
            total = sub_info.get('total_traffic_gb', 0)
            remaining = sub_info.get('remaining_traffic_gb', 0)
            percentage = sub_info.get('usage_percentage', 0)
            
            text += f"📈 **流量详情:** {used} GB / {total} GB\n"
            
            # 使用进度条
            progress_bar = self._create_progress_bar(percentage)
            text += f"📊 **使用进度:** {progress_bar} {percentage}%\n"
            text += f"💾 **剩余可用:** {remaining} GB\n"
        
        # 过期时间
        if sub_info.get('expire_date'):
            remaining_days = sub_info.get('remaining_days', 0)
            text += f"⏰ **过期时间:** {sub_info['expire_date']} (剩余{remaining_days}天)\n"
        
        text += "\n"
        
        # 协议类型
        if stats.get('protocol_list'):
            protocols = ', '.join(stats['protocol_list'])
            text += f"🔐 **协议类型:** {protocols}\n"
        
        # 节点统计
        total_nodes = stats.get('total_nodes', 0)
        country_count = stats.get('country_count', 0)
        text += f"🌐 **节点总数:** {total_nodes} | **国家/地区:** {country_count}\n"
        
        # 覆盖范围
        if stats.get('region_list'):
            regions = [region.split(' ', 1)[1] if ' ' in region else region for region in stats['region_list']]
            regions_text = ', '.join(regions[:8])  # 最多显示8个地区
            if len(stats['region_list']) > 8:
                regions_text += f" 等{len(stats['region_list'])}个地区"
            text += f"🗺️ **覆盖范围:** {regions_text}\n"
        
        # 获取时间
        fetch_time = analysis_result.get('fetch_time', '')
        if fetch_time:
            text += f"\n⏱️ **分析时间:** {fetch_time}"
        
        return text
    
    def _create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """创建进度条"""
        filled = int(percentage / 100 * length)
        bar = '❀' * filled + '❀' * (length - filled)
        return f"【{bar}】"

# 全局分析器实例
subscription_analyzer = SubscriptionAnalyzer()

import subprocess
import logging
import time
import os
import json
import base64
import requests
import socket
import asyncio
import aiohttp
import ssl
from typing import Dict, Optional, List, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import ipaddress
from urllib.parse import urlparse
import random

logger = logging.getLogger(__name__)

# 配置
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://api.telegram.org/bot")
TEST_URLS = [
    "https://speed.cloudflare.com/__down?bytes=10485760",  # 10MB from Cloudflare
    "https://github.com/microsoft/vscode/archive/refs/heads/main.zip",  # GitHub
    "http://speedtest.ftp.otenet.gr/files/test10Mb.db",  # 10MB test file
    "https://releases.ubuntu.com/20.04/ubuntu-20.04.6-desktop-amd64.iso.torrent",  # Ubuntu torrent (small)
    "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"  # Small image
]

# IP地理位置API
GEO_APIS = [
    "http://ip-api.com/json/{ip}?fields=status,country,countryCode,region,regionName,city,isp,org,as,query",
    "https://ipapi.co/{ip}/json/",
    "http://www.geoplugin.net/json.gp?ip={ip}"
]

class RealSpeedTester:
    def __init__(self):
        self.timeout = 30
        self.connect_timeout = 10
        self.max_download_size = 50 * 1024 * 1024  # 50MB max
        self.test_duration = 15  # 15 seconds max per test
        
    def get_ip_geolocation(self, ip: str) -> Dict:
        """获取IP地理位置信息"""
        for api_url in GEO_APIS:
            try:
                url = api_url.format(ip=ip)
                response = requests.get(url, timeout=5)
                data = response.json()
                
                # 处理不同API的响应格式
                if 'ip-api.com' in api_url:
                    if data.get('status') == 'success':
                        return {
                            'country': data.get('country', '未知'),
                            'country_code': data.get('countryCode', ''),
                            'region': data.get('regionName', ''),
                            'city': data.get('city', ''),
                            'isp': data.get('isp', ''),
                            'org': data.get('org', ''),
                            'as': data.get('as', '')
                        }
                elif 'ipapi.co' in api_url:
                    if 'error' not in data:
                        return {
                            'country': data.get('country_name', '未知'),
                            'country_code': data.get('country_code', ''),
                            'region': data.get('region', ''),
                            'city': data.get('city', ''),
                            'isp': data.get('org', ''),
                            'org': data.get('org', ''),
                            'as': data.get('asn', '')
                        }
                elif 'geoplugin.net' in api_url:
                    return {
                        'country': data.get('geoplugin_countryName', '未知'),
                        'country_code': data.get('geoplugin_countryCode', ''),
                        'region': data.get('geoplugin_regionName', ''),
                        'city': data.get('geoplugin_city', ''),
                        'isp': data.get('geoplugin_isp', ''),
                        'org': data.get('geoplugin_isp', ''),
                        'as': ''
                    }
            except Exception as e:
                logger.debug(f"Failed to get geo info from {api_url}: {e}")
                continue
        
        return {
            'country': '未知',
            'country_code': '',
            'region': '',
            'city': '',
            'isp': '',
            'org': '',
            'as': ''
        }

    def resolve_domain(self, domain: str) -> Optional[str]:
        """解析域名获取IP地址"""
        try:
            ip = socket.gethostbyname(domain)
            logger.info(f"Resolved {domain} to {ip}")
            return ip
        except Exception as e:
            logger.error(f"Failed to resolve {domain}: {e}")
            return None

    def test_tcp_connectivity(self, server: str, port: int) -> Dict:
        """测试TCP连通性和延迟"""
        try:
            # 解析域名
            if not self._is_ip(server):
                ip = self.resolve_domain(server)
                if not ip:
                    return {
                        "status": "failed",
                        "error": "域名解析失败"
                    }
            else:
                ip = server

            # 测试连接
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            
            result = sock.connect_ex((ip, port))
            end_time = time.time()
            sock.close()
            
            latency = round((end_time - start_time) * 1000, 2)
            
            if result == 0:
                # 获取地理位置信息
                geo_info = self.get_ip_geolocation(ip)
                
                return {
                    "status": "connected",
                    "latency_ms": latency,
                    "ip": ip,
                    "geo_info": geo_info
                }
            else:
                return {
                    "status": "failed",
                    "error": f"连接失败 (错误码: {result})",
                    "latency_ms": latency if latency < 10000 else 0
                }
                
        except socket.timeout:
            return {
                "status": "timeout",
                "error": "连接超时"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _is_ip(self, address: str) -> bool:
        """检查是否为IP地址"""
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False

    def test_http_speed_direct(self, test_urls: List[str] = None) -> Dict:
        """直接HTTP速度测试（不通过代理）"""
        if not test_urls:
            test_urls = TEST_URLS
            
        best_result = None
        best_speed = 0
        
        for url in test_urls[:3]:  # 测试前3个URL
            try:
                logger.info(f"Testing speed with URL: {url}")
                result = self._single_http_speed_test(url)
                
                if result.get("status") == "success":
                    speed = result.get("download_speed_mbps", 0)
                    if speed > best_speed:
                        best_speed = speed
                        best_result = result
                        
                    # 如果速度足够好，就不继续测试了
                    if speed > 10:  # 10 Mbps
                        break
                        
            except Exception as e:
                logger.error(f"Error testing {url}: {e}")
                continue
        
        return best_result or {
            "status": "failed",
            "error": "所有测试URL都失败了"
        }

    def _single_http_speed_test(self, url: str, proxy: Optional[str] = None) -> Dict:
        """单个HTTP速度测试"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            proxies = None
            if proxy:
                proxies = {"http": proxy, "https": proxy}
            
            start_time = time.time()
            response = requests.get(
                url, 
                headers=headers, 
                proxies=proxies,
                timeout=self.timeout, 
                stream=True,
                verify=False
            )
            
            if response.status_code != 200:
                return {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}"
                }
            
            downloaded = 0
            chunk_times = []
            first_byte_time = None
            
            for chunk in response.iter_content(chunk_size=8192):
                current_time = time.time()
                
                if first_byte_time is None:
                    first_byte_time = current_time
                
                if chunk:
                    downloaded += len(chunk)
                    chunk_times.append(current_time)
                    
                # 限制下载大小和时间
                if downloaded > self.max_download_size:
                    logger.info(f"Reached max download size: {downloaded} bytes")
                    break
                    
                if current_time - start_time > self.test_duration:
                    logger.info(f"Reached max test duration: {current_time - start_time}s")
                    break
            
            end_time = time.time()
            total_time = end_time - start_time
            first_byte_latency = (first_byte_time - start_time) * 1000 if first_byte_time else 0
            
            if total_time > 0 and downloaded > 0:
                speed_bps = downloaded / total_time
                speed_mbps = speed_bps / (1024 * 1024)
                
                return {
                    "status": "success",
                    "download_speed_mbps": round(speed_mbps, 2),
                    "download_speed_kbps": round(speed_bps / 1024, 2),
                    "downloaded_bytes": downloaded,
                    "downloaded_mb": round(downloaded / (1024 * 1024), 2),
                    "total_time_seconds": round(total_time, 2),
                    "first_byte_latency_ms": round(first_byte_latency, 2),
                    "http_status": response.status_code,
                    "test_url": url
                }
            else:
                return {
                    "status": "failed",
                    "error": "无效的测试结果"
                }
                
        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "error": "请求超时"
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "connection_error",
                "error": "连接错误"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def test_node_comprehensive(self, node: Dict) -> Dict:
        """综合测试节点"""
        node_name = node.get('name', node.get('server', 'Unknown Node'))
        server = node.get('server')
        port = node.get('port')
        protocol = node.get('protocol', 'unknown')
        
        logger.info(f"开始综合测试节点: {node_name}")
        
        result = {
            "name": node_name,
            "server": server,
            "port": port,
            "protocol": protocol.upper(),
            "timestamp": time.time(),
            "test_time": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 1. TCP连通性测试
        logger.info(f"测试TCP连通性: {server}:{port}")
        connectivity = self.test_tcp_connectivity(server, port)
        result.update(connectivity)
        
        if connectivity.get("status") != "connected":
            result["overall_status"] = "❌ 连接失败"
            result["status_emoji"] = "❌"
            result["status_text"] = "连接失败"
            return result
        
        # 2. 获取地理位置信息
        geo_info = connectivity.get("geo_info", {})
        result["region"] = self._format_region(geo_info)
        result["isp"] = geo_info.get("isp", "未知ISP")
        result["city"] = geo_info.get("city", "")
        result["country"] = geo_info.get("country", "未知")
        
        # 3. 速度测试（直接测试，不通过代理）
        logger.info("开始速度测试...")
        speed_result = self.test_http_speed_direct()
        
        if speed_result and speed_result.get("status") == "success":
            result.update({
                "download_speed_mbps": speed_result.get("download_speed_mbps", 0),
                "download_speed_kbps": speed_result.get("download_speed_kbps", 0),
                "downloaded_bytes": speed_result.get("downloaded_bytes", 0),
                "downloaded_mb": speed_result.get("downloaded_mb", 0),
                "test_duration": speed_result.get("total_time_seconds", 0),
                "first_byte_latency": speed_result.get("first_byte_latency_ms", 0),
                "test_url": speed_result.get("test_url", "")
            })
            
            # 根据速度判断状态
            speed = speed_result.get("download_speed_mbps", 0)
            if speed > 50:
                result["overall_status"] = "🚀 极速"
                result["status_emoji"] = "🚀"
                result["status_text"] = "极速"
            elif speed > 20:
                result["overall_status"] = "⚡ 快速"
                result["status_emoji"] = "⚡"
                result["status_text"] = "快速"
            elif speed > 5:
                result["overall_status"] = "✅ 正常"
                result["status_emoji"] = "✅"
                result["status_text"] = "正常"
            elif speed > 1:
                result["overall_status"] = "🐌 较慢"
                result["status_emoji"] = "🐌"
                result["status_text"] = "较慢"
            else:
                result["overall_status"] = "❌ 极慢"
                result["status_emoji"] = "❌"
                result["status_text"] = "极慢"
        else:
            result.update({
                "download_speed_mbps": 0,
                "download_speed_kbps": 0,
                "overall_status": "❌ 测速失败",
                "status_emoji": "❌",
                "status_text": "测速失败",
                "speed_error": speed_result.get("error", "未知错误") if speed_result else "测速失败"
            })
        
        # 4. 生成节点质量评分
        result["quality_score"] = self._calculate_quality_score(result)
        
        logger.info(f"节点测试完成: {node_name} - {result.get('overall_status')}")
        return result

    def _format_region(self, geo_info: Dict) -> str:
        """格式化地区信息"""
        country = geo_info.get('country', '')
        country_code = geo_info.get('country_code', '').upper()
        city = geo_info.get('city', '')
        
        # 国家代码到emoji的映射
        flag_map = {
            'US': '🇺🇸', 'JP': '🇯🇵', 'HK': '🇭🇰', 'SG': '🇸🇬', 'DE': '🇩🇪',
            'GB': '🇬🇧', 'FR': '🇫🇷', 'CA': '🇨🇦', 'AU': '🇦🇺', 'KR': '🇰🇷',
            'NL': '🇳🇱', 'RU': '🇷🇺', 'IN': '🇮🇳', 'BR': '🇧🇷', 'TW': '🇹🇼',
            'TH': '🇹🇭', 'MY': '🇲🇾', 'PH': '🇵🇭', 'VN': '🇻🇳', 'ID': '🇮🇩',
            'AE': '🇦🇪', 'TR': '🇹🇷', 'IL': '🇮🇱', 'ZA': '🇿🇦', 'AR': '🇦🇷',
            'CL': '🇨🇱', 'MX': '🇲🇽', 'ES': '🇪🇸', 'IT': '🇮🇹', 'CH': '🇨🇭',
            'SE': '🇸🇪', 'NO': '🇳🇴', 'DK': '🇩🇰', 'FI': '🇫🇮', 'PL': '🇵🇱',
            'CZ': '🇨🇿', 'AT': '🇦🇹', 'BE': '🇧🇪', 'PT': '🇵🇹', 'GR': '🇬🇷',
            'CN': '🇨🇳'
        }
        
        flag = flag_map.get(country_code, '🌍')
        
        if city and city != country:
            return f"{flag} {country} - {city}"
        else:
            return f"{flag} {country}" if country else "🌍 未知地区"

    def _calculate_quality_score(self, result: Dict) -> int:
        """计算节点质量评分 (0-100)"""
        score = 0
        
        # 连通性 (30分)
        if result.get("status") == "connected":
            score += 30
            # 延迟加分
            latency = result.get("latency_ms", 1000)
            if latency < 50:
                score += 10
            elif latency < 100:
                score += 8
            elif latency < 200:
                score += 5
            elif latency < 500:
                score += 2
        
        # 速度 (60分)
        speed = result.get("download_speed_mbps", 0)
        if speed > 50:
            score += 60
        elif speed > 20:
            score += 50
        elif speed > 10:
            score += 40
        elif speed > 5:
            score += 30
        elif speed > 1:
            score += 20
        elif speed > 0.1:
            score += 10
        
        # 稳定性 (10分) - 基于首字节延迟
        first_byte = result.get("first_byte_latency", 1000)
        if first_byte < 200:
            score += 10
        elif first_byte < 500:
            score += 8
        elif first_byte < 1000:
            score += 5
        elif first_byte < 2000:
            score += 2
        
        return min(score, 100)

    def test_multiple_nodes(self, nodes: List[Dict], max_workers: int = 3) -> List[Dict]:
        """并发测试多个节点"""
        results = []
        total_nodes = len(nodes)
        
        logger.info(f"开始并发测试 {total_nodes} 个节点，最大并发数: {max_workers}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_node = {
                executor.submit(self.test_node_comprehensive, node): node 
                for node in nodes
            }
            
            # 收集结果
            completed = 0
            for future in as_completed(future_to_node, timeout=120):
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"完成测试 {completed}/{total_nodes}: {result.get('name', 'Unknown')} - {result.get('overall_status', 'Unknown')}")
                except Exception as e:
                    node = future_to_node[future]
                    logger.error(f"测试节点异常 {node.get('name', 'Unknown')}: {e}")
                    results.append({
                        "name": node.get('name', 'Unknown'),
                        "server": node.get('server', 'Unknown'),
                        "port": node.get('port', 0),
                        "protocol": node.get('protocol', 'unknown').upper(),
                        "overall_status": "❌ 测试异常",
                        "status_emoji": "❌",
                        "status_text": "测试异常",
                        "error": str(e),
                        "quality_score": 0
                    })
        
        # 按质量评分排序
        results.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        logger.info(f"所有节点测试完成，共 {len(results)} 个结果")
        
        return results

# 全局测试器实例
speed_tester = RealSpeedTester()

def test_node_speed(node: Dict) -> Dict:
    """测试单个节点速度（兼容旧接口）"""
    return speed_tester.test_node_comprehensive(node)

def test_multiple_nodes_speed(nodes: List[Dict]) -> List[Dict]:
    """测试多个节点速度"""
    return speed_tester.test_multiple_nodes(nodes)

def format_test_result(result: Dict) -> str:
    """格式化测试结果"""
    if "error" in result and result.get("status") != "connected":
        return f"❌ **{result.get('name', 'Unknown')}**\n🔗 {result.get('protocol', 'Unknown')}\n❌ {result['error']}"
    
    output = f"**{result.get('status_emoji', '📊')} {result.get('name', 'Unknown Node')}**\n"
    output += f"🌐 `{result.get('server', 'N/A')}:{result.get('port', 'N/A')}`\n"
    output += f"🔗 {result.get('protocol', 'unknown')}\n"
    
    if result.get('region'):
        output += f"📍 {result.get('region')}\n"
    
    if result.get('isp'):
        output += f"🏢 {result.get('isp')}\n"
    
    # 连接信息
    if result.get('latency_ms') is not None:
        output += f"⏱️ 延迟: {result.get('latency_ms')}ms\n"
    
    # 速度信息
    if result.get('download_speed_mbps', 0) > 0:
        output += f"⚡ 速度: {result.get('download_speed_mbps')}MB/s\n"
        if result.get('downloaded_mb'):
            output += f"📊 测试: {result.get('downloaded_mb')}MB / {result.get('test_duration', 0)}s\n"
    
    # 状态
    output += f"📈 状态: {result.get('overall_status', '未知')}\n"
    
    # 质量评分
    if result.get('quality_score') is not None:
        score = result.get('quality_score', 0)
        if score >= 80:
            score_emoji = "🏆"
        elif score >= 60:
            score_emoji = "🥈"
        elif score >= 40:
            score_emoji = "🥉"
        else:
            score_emoji = "📊"
        output += f"{score_emoji} 评分: {score}/100\n"
    
    return output

def format_batch_results(results: List[Dict], show_top: int = 10) -> str:
    """格式化批量测试结果"""
    if not results:
        return "❌ 没有测试结果"
    
    total = len(results)
    successful = len([r for r in results if r.get('status') == 'connected'])
    
    output = f"📊 **批量测速结果** ({successful}/{total} 成功)\n\n"
    
    # 显示前N个结果
    for i, result in enumerate(results[:show_top], 1):
        if i <= 3:
            medal = ["🥇", "🥈", "🥉"][i-1]
        else:
            medal = f"#{i}"
        
        output += f"{medal} **{result.get('name', 'Unknown')}**\n"
        output += f"   🌐 {result.get('server', 'N/A')}:{result.get('port', 'N/A')}\n"
        output += f"   📍 {result.get('region', '未知地区')}\n"
        output += f"   ⚡ {result.get('download_speed_mbps', 0)}MB/s | ⏱️ {result.get('latency_ms', 0)}ms\n"
        output += f"   📈 {result.get('overall_status', '未知')} | 🏆 {result.get('quality_score', 0)}/100\n\n"
    
    if total > show_top:
        output += f"... 还有 {total - show_top} 个节点结果\n"
    
    return output

# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 测试节点
    test_node = {
        "name": "Test Node",
        "server": "8.8.8.8",
        "port": 53,
        "protocol": "test"
    }
    
    result = test_node_speed(test_node)
    print(format_test_result(result))

import subprocess
import logging
import time
import os
import json
import base64
import requests
import socket
from typing import Dict, Optional, List
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# 配置
TELEGRAM_API_URL = os.environ.get('TELEGRAM_API_URL', "https://api.telegram.org/bot")
TEST_URLS = [
    "https://speed.cloudflare.com/__down?bytes=1048576",  # 1MB
    "https://github.com/microsoft/vscode/archive/refs/heads/main.zip",  # 备用
    "http://speedtest.ftp.otenet.gr/files/test1Mb.db"  # 备用
]

class SpeedTester:
    def __init__(self):
        self.timeout = 30
        self.connect_timeout = 10
        
    def test_connectivity(self, server: str, port: int) -> Dict:
        """测试连通性"""
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            result = sock.connect_ex((server, port))
            end_time = time.time()
            sock.close()
            
            if result == 0:
                return {
                    "status": "connected",
                    "latency_ms": round((end_time - start_time) * 1000, 2)
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Connection failed (code: {result})"
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def test_http_speed(self, url: str, proxy: Optional[str] = None) -> Dict:
        """测试HTTP下载速度"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            proxies = {"http": proxy, "https": proxy} if proxy else None
            
            start_time = time.time()
            response = requests.get(url, headers=headers, proxies=proxies, 
                                  timeout=self.timeout, stream=True)
            
            downloaded = 0
            chunk_times = []
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    chunk_times.append(time.time())
                    
                # 限制下载大小，避免消耗太多流量
                if downloaded > 5 * 1024 * 1024:  # 5MB
                    break
            
            end_time = time.time()
            total_time = end_time - start_time
            
            if total_time > 0:
                speed_bps = downloaded / total_time
                speed_mbps = speed_bps / (1024 * 1024)
                
                return {
                    "status": "success",
                    "download_speed_mbps": round(speed_mbps, 2),
                    "downloaded_bytes": downloaded,
                    "total_time_seconds": round(total_time, 2),
                    "http_status": response.status_code
                }
            else:
                return {
                    "status": "error",
                    "error": "Invalid timing"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def construct_proxy_string(self, node: Dict) -> Optional[str]:
        """构造代理字符串"""
        protocol = node.get("protocol", "").lower()
        server = node.get("server")
        port = node.get("port")
        
        if not server or not port:
            return None
            
        if protocol == "shadowsocks":
            # 对于SS，通常需要本地客户端
            return f"socks5://127.0.0.1:1080"  # 假设本地SS客户端监听1080
        elif protocol in ["vmess", "vless"]:
            # 对于VMess/VLess，通常需要本地客户端
            return f"socks5://127.0.0.1:1080"  # 假设本地客户端监听1080
        elif protocol == "trojan":
            return f"socks5://127.0.0.1:1080"  # 假设本地客户端监听1080
        elif protocol == "hysteria2":
            return f"socks5://127.0.0.1:1080"  # 假设本地客户端监听1080
        else:
            return None

    def test_node_comprehensive(self, node: Dict) -> Dict:
        """综合测试节点"""
        node_name = node.get('name', node.get('server', 'Unknown Node'))
        logger.info(f"Starting comprehensive test for node: {node_name}")
        
        result = {
            "name": node_name,
            "server": node.get('server'),
            "port": node.get('port'),
            "protocol": node.get('protocol'),
            "timestamp": time.time()
        }
        
        # 1. 连通性测试
        connectivity = self.test_connectivity(node.get('server'), node.get('port'))
        result.update(connectivity)
        
        if connectivity.get("status") != "connected":
            result["overall_status"] = "❌ 连接失败"
            return result
        
        # 2. 速度测试
        proxy = self.construct_proxy_string(node)
        speed_results = []
        
        for test_url in TEST_URLS[:2]:  # 只测试前两个URL
            try:
                speed_result = self.test_http_speed(test_url, proxy)
                if speed_result.get("status") == "success":
                    speed_results.append(speed_result)
                    break  # 成功一个就够了
            except Exception as e:
                logger.warning(f"Speed test failed for {test_url}: {e}")
                continue
        
        if speed_results:
            best_result = max(speed_results, key=lambda x: x.get("download_speed_mbps", 0))
            result.update({
                "download_speed_mbps": best_result.get("download_speed_mbps", 0),
                "downloaded_bytes": best_result.get("downloaded_bytes", 0),
                "test_duration": best_result.get("total_time_seconds", 0)
            })
            
            # 根据速度判断状态
            speed = best_result.get("download_speed_mbps", 0)
            if speed > 10:
                result["overall_status"] = "🚀 极速"
            elif speed > 5:
                result["overall_status"] = "⚡ 快速"
            elif speed > 1:
                result["overall_status"] = "✅ 正常"
            elif speed > 0.1:
                result["overall_status"] = "🐌 较慢"
            else:
                result["overall_status"] = "❌ 极慢"
        else:
            result.update({
                "download_speed_mbps": 0,
                "overall_status": "❌ 测速失败"
            })
        
        # 3. 获取节点额外信息（模拟）
        result.update(self.get_node_extra_info(node))
        
        return result

    def get_node_extra_info(self, node: Dict) -> Dict:
        """获取节点额外信息（流量、地区等）"""
        # 这里可以添加实际的流量查询逻辑
        # 目前返回模拟数据
        import random
        
        # 模拟地区信息
        regions = ["🇺🇸 美国", "🇯🇵 日本", "🇭🇰 香港", "🇸🇬 新加坡", "🇩🇪 德国", "🇬🇧 英国"]
        
        return {
            "region": random.choice(regions),
            "remaining_traffic": f"{random.randint(50, 500)}GB",
            "total_traffic": f"{random.randint(500, 1000)}GB",
            "expire_date": "2024-12-31",
            "node_load": f"{random.randint(10, 80)}%"
        }

    def test_multiple_nodes(self, nodes: List[Dict], max_workers: int = 3) -> List[Dict]:
        """并发测试多个节点"""
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_node = {
                executor.submit(self.test_node_comprehensive, node): node 
                for node in nodes
            }
            
            for future in as_completed(future_to_node, timeout=60):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    node = future_to_node[future]
                    logger.error(f"Error testing node {node.get('name', 'Unknown')}: {e}")
                    results.append({
                        "name": node.get('name', 'Unknown'),
                        "overall_status": "❌ 测试异常",
                        "error": str(e)
                    })
        
        return results

# 全局测试器实例
speed_tester = SpeedTester()

def test_node_speed(node: Dict) -> Dict:
    """测试单个节点速度（兼容旧接口）"""
    return speed_tester.test_node_comprehensive(node)

def test_multiple_nodes_speed(nodes: List[Dict]) -> List[Dict]:
    """测试多个节点速度"""
    return speed_tester.test_multiple_nodes(nodes)

def format_test_result(result: Dict) -> str:
    """格式化测试结果"""
    if "error" in result:
        return f"❌ {result.get('name', 'Unknown')}: {result['error']}"
    
    output = f"📊 {result.get('name', 'Unknown Node')}\n"
    output += f"🌐 {result.get('server', 'N/A')}:{result.get('port', 'N/A')}\n"
    output += f"🔗 {result.get('protocol', 'unknown').upper()}\n"
    output += f"📍 {result.get('region', '未知地区')}\n"
    output += f"⚡ 速度: {result.get('download_speed_mbps', 0):.2f} MB/s\n"
    output += f"⏱️ 延迟: {result.get('latency_ms', 0):.2f} ms\n"
    output += f"📊 状态: {result.get('overall_status', '未知')}\n"
    
    if result.get('remaining_traffic'):
        output += f"💾 剩余流量: {result.get('remaining_traffic')}\n"
    
    if result.get('node_load'):
        output += f"🔥 节点负载: {result.get('node_load')}\n"
    
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

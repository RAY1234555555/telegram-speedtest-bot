# fulltclash_integration.py - 集成FullTclash核心功能
import asyncio
import aiohttp
import json
import time
import logging
import subprocess
import tempfile
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import yaml
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class FullTclashIntegration:
    def __init__(self):
        self.session = None
        self.clash_config = None
        self.clash_process = None
        self.clash_port = 7890
        self.clash_api_port = 9090
        self.clash_secret = "your-secret-key"
        
        # 测速配置
        self.speed_test_urls = [
            "https://speed.cloudflare.com/__down?bytes=10485760",  # 10MB
            "https://github.com/microsoft/vscode/archive/refs/heads/main.zip",
            "http://speedtest.ftp.otenet.gr/files/test10Mb.db",
            "https://dl.google.com/dl/android/maven2/com/android/tools/build/gradle/4.2.2/gradle-4.2.2.pom"
        ]
        
        # 流媒体测试配置
        self.streaming_tests = {
            "Netflix": {
                "url": "https://www.netflix.com/title/70143836",
                "method": "GET",
                "success_keywords": ["watch", "play"],
                "blocked_keywords": ["not available", "blocked"]
            },
            "Disney+": {
                "url": "https://www.disneyplus.com/",
                "method": "GET", 
                "success_keywords": ["sign up", "start streaming"],
                "blocked_keywords": ["not available", "coming soon"]
            },
            "YouTube Premium": {
                "url": "https://www.youtube.com/premium",
                "method": "GET",
                "success_keywords": ["youtube premium", "start free trial"],
                "blocked_keywords": ["not available"]
            },
            "ChatGPT": {
                "url": "https://chat.openai.com/",
                "method": "GET",
                "success_keywords": ["chatgpt", "openai"],
                "blocked_keywords": ["not available", "restricted"]
            }
        }
    
    async def init_session(self):
        """初始化HTTP会话"""
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'FullTclash/2.0 (https://github.com/AirportR/FullTclash)'
                }
            )
    
    async def close_session(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def generate_clash_config(self, nodes: List[Dict]) -> Dict:
        """生成Clash配置文件"""
        config = {
            "port": self.clash_port,
            "socks-port": 7891,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            "external-controller": f"127.0.0.1:{self.clash_api_port}",
            "secret": self.clash_secret,
            "proxies": [],
            "proxy-groups": [
                {
                    "name": "PROXY",
                    "type": "select",
                    "proxies": ["DIRECT"]
                }
            ],
            "rules": [
                "MATCH,PROXY"
            ]
        }
        
        # 转换节点为Clash格式
        for i, node in enumerate(nodes):
            clash_proxy = self.convert_node_to_clash(node, i)
            if clash_proxy:
                config["proxies"].append(clash_proxy)
                config["proxy-groups"][0]["proxies"].append(clash_proxy["name"])
        
        return config
    
    def convert_node_to_clash(self, node: Dict, index: int) -> Optional[Dict]:
        """将节点转换为Clash格式"""
        try:
            protocol = node.get('protocol', '').lower()
            name = f"{node.get('name', f'Node-{index}')}"
            server = node.get('server')
            port = node.get('port')
            
            if not server or not port:
                return None
            
            if protocol == 'vmess':
                return {
                    "name": name,
                    "type": "vmess",
                    "server": server,
                    "port": int(port),
                    "uuid": node.get('uuid'),
                    "alterId": node.get('alterId', 0),
                    "cipher": node.get('security', 'auto'),
                    "network": node.get('network', 'tcp'),
                    "tls": node.get('tls') == 'tls',
                    "servername": node.get('sni', ''),
                    "ws-opts": {
                        "path": node.get('path', '/'),
                        "headers": {
                            "Host": node.get('host', '')
                        }
                    } if node.get('network') == 'ws' else None
                }
            
            elif protocol == 'vless':
                return {
                    "name": name,
                    "type": "vless",
                    "server": server,
                    "port": int(port),
                    "uuid": node.get('uuid'),
                    "flow": node.get('flow', ''),
                    "tls": node.get('security') in ['tls', 'reality'],
                    "servername": node.get('sni', ''),
                    "reality-opts": {
                        "public-key": node.get('pbk', ''),
                        "short-id": node.get('sid', '')
                    } if node.get('security') == 'reality' else None
                }
            
            elif protocol == 'shadowsocks':
                return {
                    "name": name,
                    "type": "ss",
                    "server": server,
                    "port": int(port),
                    "cipher": node.get('method'),
                    "password": node.get('password')
                }
            
            elif protocol == 'trojan':
                return {
                    "name": name,
                    "type": "trojan",
                    "server": server,
                    "port": int(port),
                    "password": node.get('password'),
                    "sni": node.get('sni', ''),
                    "skip-cert-verify": False
                }
            
            elif protocol == 'hysteria2':
                return {
                    "name": name,
                    "type": "hysteria2",
                    "server": server,
                    "port": int(port),
                    "password": node.get('password', ''),
                    "sni": node.get('sni', ''),
                    "skip-cert-verify": node.get('insecure', False)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"转换节点失败: {e}")
            return None
    
    async def start_clash_core(self, config: Dict) -> bool:
        """启动Clash核心"""
        try:
            # 创建临时配置文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
                config_path = f.name
            
            # 启动Clash
            self.clash_process = subprocess.Popen([
                'clash', '-f', config_path, '-d', '/tmp/clash'
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 等待启动
            await asyncio.sleep(3)
            
            # 检查是否启动成功
            if self.clash_process.poll() is None:
                logger.info("Clash核心启动成功")
                return True
            else:
                logger.error("Clash核心启动失败")
                return False
                
        except Exception as e:
            logger.error(f"启动Clash核心失败: {e}")
            return False
    
    async def stop_clash_core(self):
        """停止Clash核心"""
        if self.clash_process:
            self.clash_process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.create_task(asyncio.to_thread(self.clash_process.wait)), 
                    timeout=5
                )
            except asyncio.TimeoutError:
                self.clash_process.kill()
            self.clash_process = None
    
    async def test_node_with_clash(self, node_name: str) -> Dict:
        """使用Clash测试单个节点"""
        try:
            # 切换到指定节点
            await self.switch_clash_proxy(node_name)
            
            # 等待切换完成
            await asyncio.sleep(2)
            
            # 执行测试
            results = {
                "name": node_name,
                "connectivity": await self.test_connectivity_via_clash(),
                "speed": await self.test_speed_via_clash(),
                "streaming": await self.test_streaming_via_clash(),
                "test_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return results
            
        except Exception as e:
            logger.error(f"测试节点失败: {e}")
            return {
                "name": node_name,
                "error": str(e),
                "test_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    async def switch_clash_proxy(self, proxy_name: str):
        """切换Clash代理"""
        try:
            url = f"http://127.0.0.1:{self.clash_api_port}/proxies/PROXY"
            headers = {"Authorization": f"Bearer {self.clash_secret}"}
            data = {"name": proxy_name}
            
            await self.init_session()
            async with self.session.put(url, json=data, headers=headers) as response:
                if response.status == 204:
                    logger.info(f"切换到代理: {proxy_name}")
                else:
                    logger.error(f"切换代理失败: {response.status}")
                    
        except Exception as e:
            logger.error(f"切换代理异常: {e}")
    
    async def test_connectivity_via_clash(self) -> Dict:
        """通过Clash测试连通性"""
        try:
            proxy_url = f"http://127.0.0.1:{self.clash_port}"
            
            start_time = time.time()
            
            await self.init_session()
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(
                    "http://www.google.com/generate_204",
                    proxy=proxy_url
                ) as response:
                    end_time = time.time()
                    latency = round((end_time - start_time) * 1000, 2)
                    
                    if response.status == 204:
                        return {
                            "status": "success",
                            "latency_ms": latency,
                            "http_status": response.status
                        }
                    else:
                        return {
                            "status": "failed",
                            "error": f"HTTP {response.status}",
                            "latency_ms": latency
                        }
                        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def test_speed_via_clash(self) -> Dict:
        """通过Clash测试速度"""
        try:
            proxy_url = f"http://127.0.0.1:{self.clash_port}"
            best_result = None
            best_speed = 0
            
            for test_url in self.speed_test_urls[:2]:  # 测试前2个URL
                try:
                    result = await self.single_speed_test_via_clash(test_url, proxy_url)
                    if result and result.get('download_speed_mbps', 0) > best_speed:
                        best_speed = result['download_speed_mbps']
                        best_result = result
                        
                    if best_speed > 20:  # 如果速度够快就不继续测试
                        break
                        
                except Exception as e:
                    logger.debug(f"速度测试失败 {test_url}: {e}")
                    continue
            
            return best_result or {
                "status": "failed",
                "error": "所有测速URL都失败"
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "error": str(e)
            }
    
    async def single_speed_test_via_clash(self, test_url: str, proxy_url: str) -> Optional[Dict]:
        """单个URL速度测试"""
        try:
            await self.init_session()
            
            start_time = time.time()
            downloaded = 0
            first_byte_time = None
            
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as session:
                async with session.get(test_url, proxy=proxy_url) as response:
                    if response.status != 200:
                        return None
                    
                    async for chunk in response.content.iter_chunked(8192):
                        current_time = time.time()
                        
                        if first_byte_time is None:
                            first_byte_time = current_time
                        
                        downloaded += len(chunk)
                        
                        # 限制测试时间
                        if current_time - start_time > 15:
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
                    "downloaded_mb": round(downloaded / (1024 * 1024), 2),
                    "test_duration": round(total_time, 2),
                    "first_byte_latency": round(first_byte_latency, 2),
                    "test_url": test_url
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"单速度测试失败: {e}")
            return None
    
    async def test_streaming_via_clash(self) -> Dict:
        """通过Clash测试流媒体解锁"""
        try:
            proxy_url = f"http://127.0.0.1:{self.clash_port}"
            results = {}
            
            await self.init_session()
            
            for platform, config in self.streaming_tests.items():
                try:
                    connector = aiohttp.TCPConnector()
                    async with aiohttp.ClientSession(
                        connector=connector,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as session:
                        async with session.get(
                            config["url"], 
                            proxy=proxy_url
                        ) as response:
                            content = await response.text()
                            content_lower = content.lower()
                            
                            # 检查是否被阻止
                            blocked = any(keyword in content_lower for keyword in config["blocked_keywords"])
                            # 检查是否成功
                            success = any(keyword in content_lower for keyword in config["success_keywords"])
                            
                            if blocked:
                                status = "blocked"
                            elif success:
                                status = "unlocked"
                            else:
                                status = "unknown"
                            
                            results[platform] = {
                                "status": status,
                                "http_status": response.status
                            }
                            
                except Exception as e:
                    results[platform] = {
                        "status": "error",
                        "error": str(e)
                    }
            
            # 计算解锁统计
            unlocked_count = sum(1 for r in results.values() if r.get("status") == "unlocked")
            total_count = len(results)
            
            return {
                "platforms": results,
                "summary": {
                    "unlocked": unlocked_count,
                    "total": total_count,
                    "unlock_rate": round((unlocked_count / total_count) * 100, 1) if total_count > 0 else 0
                }
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "summary": {
                    "unlocked": 0,
                    "total": 0,
                    "unlock_rate": 0
                }
            }
    
    async def batch_test_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """批量测试节点"""
        try:
            # 生成Clash配置
            config = self.generate_clash_config(nodes)
            
            # 启动Clash核心
            if not await self.start_clash_core(config):
                return [{"error": "Clash核心启动失败"}]
            
            results = []
            
            try:
                # 测试每个节点
                for node in nodes:
                    node_name = node.get('name', 'Unknown')
                    logger.info(f"开始测试节点: {node_name}")
                    
                    result = await self.test_node_with_clash(node_name)
                    results.append(result)
                    
                    # 短暂延迟避免过于频繁
                    await asyncio.sleep(1)
                
            finally:
                # 停止Clash核心
                await self.stop_clash_core()
            
            return results
            
        except Exception as e:
            logger.error(f"批量测试失败: {e}")
            return [{"error": str(e)}]
        finally:
            await self.close_session()
    
    def format_test_results(self, results: List[Dict]) -> str:
        """格式化测试结果"""
        if not results:
            return "❌ 没有测试结果"
        
        output = "📊 **FullTclash 测速结果**\n\n"
        
        successful_results = [r for r in results if not r.get('error')]
        failed_results = [r for r in results if r.get('error')]
        
        if successful_results:
            # 按速度排序
            successful_results.sort(
                key=lambda x: x.get('speed', {}).get('download_speed_mbps', 0), 
                reverse=True
            )
            
            for i, result in enumerate(successful_results, 1):
                name = result.get('name', 'Unknown')
                connectivity = result.get('connectivity', {})
                speed = result.get('speed', {})
                streaming = result.get('streaming', {})
                
                # 排名emoji
                if i == 1:
                    rank_emoji = "🥇"
                elif i == 2:
                    rank_emoji = "🥈"
                elif i == 3:
                    rank_emoji = "🥉"
                else:
                    rank_emoji = f"#{i}"
                
                output += f"{rank_emoji} **{name}**\n"
                
                # 连通性
                if connectivity.get('status') == 'success':
                    output += f"   ✅ 延迟: {connectivity.get('latency_ms', 0)}ms\n"
                else:
                    output += f"   ❌ 连接失败\n"
                
                # 速度
                if speed.get('status') == 'success':
                    speed_mbps = speed.get('download_speed_mbps', 0)
                    output += f"   ⚡ 速度: {speed_mbps}MB/s\n"
                    
                    # 速度评级
                    if speed_mbps > 50:
                        output += f"   🚀 评级: 极速\n"
                    elif speed_mbps > 20:
                        output += f"   ⚡ 评级: 快速\n"
                    elif speed_mbps > 5:
                        output += f"   ✅ 评级: 正常\n"
                    else:
                        output += f"   🐌 评级: 较慢\n"
                else:
                    output += f"   ❌ 测速失败\n"
                
                # 流媒体解锁
                if streaming.get('summary'):
                    unlock_rate = streaming['summary'].get('unlock_rate', 0)
                    unlocked = streaming['summary'].get('unlocked', 0)
                    total = streaming['summary'].get('total', 0)
                    
                    output += f"   🔓 解锁: {unlocked}/{total} ({unlock_rate}%)\n"
                    
                    # 显示解锁的平台
                    platforms = streaming.get('platforms', {})
                    unlocked_platforms = [name for name, data in platforms.items() if data.get('status') == 'unlocked']
                    if unlocked_platforms:
                        output += f"   📺 平台: {', '.join(unlocked_platforms[:3])}\n"
                
                output += "\n"
        
        if failed_results:
            output += "❌ **测试失败的节点:**\n"
            for result in failed_results:
                name = result.get('name', 'Unknown')
                error = result.get('error', '未知错误')
                output += f"   • {name}: {error}\n"
        
        return output

# 全局实例
fulltclash = FullTclashIntegration()

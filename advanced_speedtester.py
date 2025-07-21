import asyncio
import aiohttp
import time
import socket
import logging
import json
import random
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl
import ipaddress

logger = logging.getLogger(__name__)

class AdvancedSpeedTester:
    def __init__(self):
        self.timeout = 30
        self.connect_timeout = 10
        self.max_download_size = 100 * 1024 * 1024  # 100MB
        self.test_duration = 20  # 20秒最大测试时间
        
        # 多个测速服务器
        self.speed_test_urls = [
            {
                'name': 'Cloudflare',
                'url': 'https://speed.cloudflare.com/__down?bytes={}',
                'sizes': [1024*1024, 10*1024*1024, 50*1024*1024]  # 1MB, 10MB, 50MB
            },
            {
                'name': 'Fast.com',
                'url': 'https://api.fast.com/netflix/speedtest/v2/download',
                'sizes': [1024*1024, 10*1024*1024]
            },
            {
                'name': 'GitHub',
                'url': 'https://github.com/microsoft/vscode/archive/refs/heads/main.zip',
                'sizes': [None]  # 固定大小
            },
            {
                'name': 'Google',
                'url': 'https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png',
                'sizes': [None]
            }
        ]
        
        # IP地理位置API
        self.geo_apis = [
            'http://ip-api.com/json/{}?fields=status,country,countryCode,region,regionName,city,isp,org,as,query',
            'https://ipapi.co/{}/json/',
            'http://www.geoplugin.net/json.gp?ip={}'
        ]
    
    async def comprehensive_test(self, node: Dict) -> Dict:
        """综合测试节点"""
        node_name = node.get('name', 'Unknown Node')
        server = node.get('server')
        port = node.get('port')
        protocol = node.get('protocol', 'unknown')
        
        logger.info(f"开始综合测试: {node_name}")
        
        result = {
            'name': node_name,
            'server': server,
            'port': port,
            'protocol': protocol,
            'test_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': time.time()
        }
        
        try:
            # 1. 基础连通性测试
            connectivity = await self._test_connectivity(server, port)
            result.update(connectivity)
            
            if connectivity.get('status') != 'connected':
                result['overall_status'] = '❌ 连接失败'
                result['quality_score'] = 0
                return result
            
            # 2. 多线程速度测试
            speed_results = await self._multi_thread_speed_test()
            result.update(speed_results)
            
            # 3. 延迟稳定性测试
            latency_test = await self._latency_stability_test(server, port)
            result.update(latency_test)
            
            # 4. 平台解锁测试
            from platform_unlock_tester import platform_unlock_tester
            unlock_results = await platform_unlock_tester.test_platform_unlock()
            result['unlock_test'] = unlock_results
            
            # 5. 计算综合评分
            result['quality_score'] = self._calculate_advanced_score(result)
            result['overall_status'] = self._get_status_by_score(result['quality_score'])
            
            logger.info(f"测试完成: {node_name} - 评分: {result['quality_score']}")
            return result
            
        except Exception as e:
            logger.error(f"综合测试失败: {e}")
            result.update({
                'overall_status': '❌ 测试异常',
                'quality_score': 0,
                'error': str(e)
            })
            return result
    
    async def _test_connectivity(self, server: str, port: int) -> Dict:
        """测试连通性"""
        try:
            # 解析域名
            if not self._is_ip(server):
                ip = await self._resolve_domain_async(server)
                if not ip:
                    return {'status': 'failed', 'error': '域名解析失败'}
            else:
                ip = server
            
            # TCP连接测试
            start_time = time.time()
            
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=self.connect_timeout
                )
                writer.close()
                await writer.wait_closed()
                
                latency = round((time.time() - start_time) * 1000, 2)
                
                # 获取地理位置信息
                geo_info = await self._get_geo_info_async(ip)
                
                return {
                    'status': 'connected',
                    'ip': ip,
                    'latency_ms': latency,
                    'geo_info': geo_info,
                    'region': self._format_region(geo_info),
                    'isp': geo_info.get('isp', '未知ISP')
                }
                
            except asyncio.TimeoutError:
                return {'status': 'timeout', 'error': '连接超时'}
            except Exception as e:
                return {'status': 'failed', 'error': f'连接失败: {str(e)}'}
                
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    async def _multi_thread_speed_test(self) -> Dict:
        """多线程速度测试"""
        try:
            best_result = None
            best_speed = 0
            
            # 测试多个服务器
            for test_server in self.speed_test_urls[:3]:  # 测试前3个
                try:
                    result = await self._test_single_server(test_server)
                    if result and result.get('download_speed_mbps', 0) > best_speed:
                        best_speed = result['download_speed_mbps']
                        best_result = result
                        best_result['test_server'] = test_server['name']
                        
                        # 如果速度足够好，提前结束
                        if best_speed > 20:  # 20 Mbps
                            break
                            
                except Exception as e:
                    logger.debug(f"测试服务器 {test_server['name']} 失败: {e}")
                    continue
            
            if best_result:
                return {
                    'download_speed_mbps': best_result['download_speed_mbps'],
                    'download_speed_kbps': best_result.get('download_speed_kbps', 0),
                    'upload_speed_mbps': best_result.get('upload_speed_mbps', 0),
                    'test_server': best_result.get('test_server', '未知'),
                    'downloaded_mb': best_result.get('downloaded_mb', 0),
                    'test_duration': best_result.get('test_duration', 0),
                    'first_byte_latency': best_result.get('first_byte_latency', 0)
                }
            else:
                return {
                    'download_speed_mbps': 0,
                    'download_speed_kbps': 0,
                    'upload_speed_mbps': 0,
                    'speed_test_error': '所有测速服务器都失败'
                }
                
        except Exception as e:
            return {
                'download_speed_mbps': 0,
                'speed_test_error': str(e)
            }
    
    async def _test_single_server(self, test_server: Dict) -> Optional[Dict]:
        """测试单个服务器"""
        try:
            url_template = test_server['url']
            sizes = test_server['sizes']
            
            # 选择合适的测试大小
            test_size = sizes[0] if sizes[0] else None
            
            if '{}' in url_template and test_size:
                test_url = url_template.format(test_size)
            else:
                test_url = url_template
            
            # 执行下载测试
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                
                start_time = time.time()
                first_byte_time = None
                downloaded = 0
                
                async with session.get(test_url) as response:
                    if response.status != 200:
                        return None
                    
                    async for chunk in response.content.iter_chunked(8192):
                        current_time = time.time()
                        
                        if first_byte_time is None:
                            first_byte_time = current_time
                        
                        downloaded += len(chunk)
                        
                        # 限制测试时间和大小
                        if current_time - start_time > self.test_duration:
                            break
                        if downloaded > self.max_download_size:
                            break
                
                end_time = time.time()
                total_time = end_time - start_time
                first_byte_latency = (first_byte_time - start_time) * 1000 if first_byte_time else 0
                
                if total_time > 0 and downloaded > 0:
                    speed_bps = downloaded / total_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    
                    return {
                        'download_speed_mbps': round(speed_mbps, 2),
                        'download_speed_kbps': round(speed_bps / 1024, 2),
                        'downloaded_mb': round(downloaded / (1024 * 1024), 2),
                        'test_duration': round(total_time, 2),
                        'first_byte_latency': round(first_byte_latency, 2)
                    }
                
                return None
                
        except Exception as e:
            logger.debug(f"单服务器测试失败: {e}")
            return None
    
    async def _latency_stability_test(self, server: str, port: int, count: int = 5) -> Dict:
        """延迟稳定性测试"""
        try:
            latencies = []
            
            for i in range(count):
                try:
                    start_time = time.time()
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(server, port),
                        timeout=5
                    )
                    latency = (time.time() - start_time) * 1000
                    latencies.append(latency)
                    
                    writer.close()
                    await writer.wait_closed()
                    
                    # 间隔测试
                    if i < count - 1:
                        await asyncio.sleep(0.5)
                        
                except Exception:
                    continue
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                min_latency = min(latencies)
                max_latency = max(latencies)
                jitter = max_latency - min_latency
                
                return {
                    'avg_latency': round(avg_latency, 2),
                    'min_latency': round(min_latency, 2),
                    'max_latency': round(max_latency, 2),
                    'jitter': round(jitter, 2),
                    'packet_loss': round((count - len(latencies)) / count * 100, 1)
                }
            else:
                return {
                    'avg_latency': 0,
                    'packet_loss': 100.0
                }
                
        except Exception as e:
            return {
                'latency_test_error': str(e),
                'avg_latency': 0
            }
    
    async def _resolve_domain_async(self, domain: str) -> Optional[str]:
        """异步域名解析"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.getaddrinfo(domain, None)
            return result[0][4][0]
        except Exception:
            return None
    
    async def _get_geo_info_async(self, ip: str) -> Dict:
        """异步获取地理位置信息"""
        for api_url in self.geo_apis:
            try:
                url = api_url.format(ip)
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.get(url) as response:
                        data = await response.json()
                        
                        # 处理不同API的响应格式
                        if 'ip-api.com' in api_url and data.get('status') == 'success':
                            return {
                                'country': data.get('country', '未知'),
                                'country_code': data.get('countryCode', ''),
                                'region': data.get('regionName', ''),
                                'city': data.get('city', ''),
                                'isp': data.get('isp', ''),
                                'org': data.get('org', ''),
                                'as': data.get('as', '')
                            }
                        elif 'ipapi.co' in api_url and 'error' not in data:
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
            except Exception:
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
    
    def _is_ip(self, address: str) -> bool:
        """检查是否为IP地址"""
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False
    
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
            'CN': '🇨🇳'
        }
        
        flag = flag_map.get(country_code, '🌍')
        
        if city and city != country:
            return f"{flag} {country} - {city}"
        else:
            return f"{flag} {country}" if country else "🌍 未知地区"
    
    def _calculate_advanced_score(self, result: Dict) -> int:
        """计算高级评分"""
        score = 0
        
        # 连通性 (25分)
        if result.get('status') == 'connected':
            score += 25
            
            # 延迟评分 (15分)
            latency = result.get('latency_ms', 1000)
            if latency < 50:
                score += 15
            elif latency < 100:
                score += 12
            elif latency < 200:
                score += 8
            elif latency < 500:
                score += 4
        
        # 速度评分 (40分)
        speed = result.get('download_speed_mbps', 0)
        if speed > 100:
            score += 40
        elif speed > 50:
            score += 35
        elif speed > 20:
            score += 30
        elif speed > 10:
            score += 25
        elif speed > 5:
            score += 20
        elif speed > 1:
            score += 15
        elif speed > 0.1:
            score += 10
        
        # 稳定性评分 (10分)
        jitter = result.get('jitter', 1000)
        packet_loss = result.get('packet_loss', 100)
        
        if packet_loss == 0:
            score += 5
        elif packet_loss < 5:
            score += 3
        elif packet_loss < 10:
            score += 1
        
        if jitter < 10:
            score += 5
        elif jitter < 50:
            score += 3
        elif jitter < 100:
            score += 1
        
        # 解锁评分 (10分)
        unlock_test = result.get('unlock_test', {})
        if unlock_test:
            unlock_rate = unlock_test.get('summary', {}).get('unlock_rate', 0)
            score += int(unlock_rate / 10)  # 每10%解锁率得1分
        
        return min(score, 100)
    
    def _get_status_by_score(self, score: int) -> str:
        """根据评分获取状态"""
        if score >= 90:
            return "🏆 优秀"
        elif score >= 80:
            return "🚀 极速"
        elif score >= 70:
            return "⚡ 快速"
        elif score >= 60:
            return "✅ 良好"
        elif score >= 40:
            return "🐌 一般"
        elif score >= 20:
            return "❌ 较差"
        else:
            return "💀 极差"
    
    def format_advanced_result(self, result: Dict) -> str:
        """格式化高级测试结果"""
        if result.get('error'):
            return f"❌ **{result.get('name', 'Unknown')}**\n错误: {result['error']}"
        
        text = f"**{result.get('overall_status', '📊')} {result.get('name', 'Unknown Node')}**\n"
        text += f"🌐 `{result.get('server', 'N/A')}:{result.get('port', 'N/A')}`\n"
        text += f"🔗 {result.get('protocol', 'unknown').upper()}\n"
        
        # 地理位置信息
        if result.get('region'):
            text += f"📍 {result.get('region')}\n"
        
        if result.get('isp'):
            text += f"🏢 {result.get('isp')}\n"
        
        # 连接信息
        if result.get('latency_ms') is not None:
            text += f"⏱️ 延迟: {result.get('latency_ms')}ms"
            if result.get('avg_latency'):
                text += f" (平均: {result.get('avg_latency')}ms)"
            text += "\n"
        
        # 稳定性信息
        if result.get('jitter') is not None:
            text += f"📊 抖动: {result.get('jitter')}ms"
            if result.get('packet_loss') is not None:
                text += f" | 丢包: {result.get('packet_loss')}%"
            text += "\n"
        
        # 速度信息
        if result.get('download_speed_mbps', 0) > 0:
            text += f"⚡ 下载: {result.get('download_speed_mbps')}MB/s"
            if result.get('upload_speed_mbps', 0) > 0:
                text += f" | 上传: {result.get('upload_speed_mbps')}MB/s"
            text += "\n"
            
            if result.get('test_server'):
                text += f"🎯 测试服务器: {result.get('test_server')}\n"
        
        # 解锁信息
        unlock_test = result.get('unlock_test', {})
        if unlock_test:
            summary = unlock_test.get('summary', {})
            unlock_rate = summary.get('unlock_rate', 0)
            unlocked_count = summary.get('unlocked_platforms', 0)
            total_count = summary.get('total_platforms', 0)
            
            text += f"🔓 解锁: {unlocked_count}/{total_count} ({unlock_rate}%)\n"
        
        # 综合评分
        score = result.get('quality_score', 0)
        if score >= 90:
            score_emoji = "🏆"
        elif score >= 80:
            score_emoji = "🥇"
        elif score >= 60:
            score_emoji = "🥈"
        elif score >= 40:
            score_emoji = "🥉"
        else:
            score_emoji = "📊"
        
        text += f"{score_emoji} 综合评分: {score}/100\n"
        
        return text

# 全局高级测速器实例
advanced_speed_tester = AdvancedSpeedTester()

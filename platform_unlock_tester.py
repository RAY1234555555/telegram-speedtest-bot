import asyncio
import aiohttp
import logging
import time
from typing import Dict, List, Optional
import json
import re

logger = logging.getLogger(__name__)

class PlatformUnlockTester:
    def __init__(self):
        self.timeout = 15
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 平台测试配置
        self.platforms = {
            'Netflix': {
                'test_url': 'https://www.netflix.com/title/70143836',
                'success_indicators': ['watch', 'play', 'video'],
                'blocked_indicators': ['not available', 'blocked', 'restricted'],
                'region_api': 'https://www.netflix.com/api/shakti/v1/pathEvaluator'
            },
            'Disney+': {
                'test_url': 'https://www.disneyplus.com/',
                'success_indicators': ['sign up', 'start streaming'],
                'blocked_indicators': ['not available', 'coming soon']
            },
            'YouTube Premium': {
                'test_url': 'https://www.youtube.com/premium',
                'success_indicators': ['youtube premium', 'start free trial'],
                'blocked_indicators': ['not available']
            },
            'ChatGPT': {
                'test_url': 'https://chat.openai.com/',
                'success_indicators': ['chatgpt', 'openai'],
                'blocked_indicators': ['not available', 'restricted', 'blocked']
            },
            'TikTok': {
                'test_url': 'https://www.tiktok.com/',
                'success_indicators': ['for you', 'following'],
                'blocked_indicators': ['not available', 'banned']
            },
            'Spotify': {
                'test_url': 'https://www.spotify.com/',
                'success_indicators': ['music', 'playlist'],
                'blocked_indicators': ['not available']
            },
            'Instagram': {
                'test_url': 'https://www.instagram.com/',
                'success_indicators': ['instagram', 'sign up'],
                'blocked_indicators': ['not available']
            },
            'Twitter/X': {
                'test_url': 'https://twitter.com/',
                'success_indicators': ['twitter', 'what\'s happening'],
                'blocked_indicators': ['not available']
            }
        }
    
    async def test_platform_unlock(self, proxy_config: Optional[Dict] = None) -> Dict:
        """测试平台解锁情况"""
        results = {}
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers=self.headers,
            connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            
            # 并发测试所有平台
            tasks = []
            for platform_name, config in self.platforms.items():
                task = self._test_single_platform(session, platform_name, config, proxy_config)
                tasks.append(task)
            
            # 等待所有测试完成
            platform_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 整理结果
            for i, result in enumerate(platform_results):
                platform_name = list(self.platforms.keys())[i]
                if isinstance(result, Exception):
                    results[platform_name] = {
                        'status': 'error',
                        'message': str(result),
                        'unlocked': False
                    }
                else:
                    results[platform_name] = result
        
        # 添加总结信息
        unlocked_count = sum(1 for r in results.values() if r.get('unlocked', False))
        total_count = len(results)
        
        summary = {
            'total_platforms': total_count,
            'unlocked_platforms': unlocked_count,
            'unlock_rate': round((unlocked_count / total_count) * 100, 1) if total_count > 0 else 0,
            'test_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return {
            'summary': summary,
            'platforms': results
        }
    
    async def _test_single_platform(self, session: aiohttp.ClientSession, platform_name: str, config: Dict, proxy_config: Optional[Dict]) -> Dict:
        """测试单个平台"""
        try:
            test_url = config['test_url']
            
            # 配置代理（如果提供）
            proxy = None
            if proxy_config:
                proxy = f"http://{proxy_config.get('server')}:{proxy_config.get('port')}"
            
            start_time = time.time()
            
            async with session.get(test_url, proxy=proxy) as response:
                content = await response.text()
                response_time = round((time.time() - start_time) * 1000, 2)
                
                # 分析响应内容
                unlocked = self._analyze_response(content, config)
                
                # 获取地区信息
                region = self._extract_region_info(content, platform_name)
                
                return {
                    'status': 'success',
                    'unlocked': unlocked,
                    'region': region,
                    'response_time': response_time,
                    'http_status': response.status,
                    'message': '✅ 解锁' if unlocked else '❌ 受限'
                }
                
        except asyncio.TimeoutError:
            return {
                'status': 'timeout',
                'unlocked': False,
                'message': '⏱️ 超时',
                'response_time': self.timeout * 1000
            }
        except Exception as e:
            return {
                'status': 'error',
                'unlocked': False,
                'message': f'❌ 错误: {str(e)}',
                'response_time': 0
            }
    
    def _analyze_response(self, content: str, config: Dict) -> bool:
        """分析响应内容判断是否解锁"""
        content_lower = content.lower()
        
        # 检查阻塞指示器
        for indicator in config.get('blocked_indicators', []):
            if indicator.lower() in content_lower:
                return False
        
        # 检查成功指示器
        for indicator in config.get('success_indicators', []):
            if indicator.lower() in content_lower:
                return True
        
        # 如果没有明确的指示器，根据HTTP状态码判断
        return True  # 默认认为可访问即为解锁
    
    def _extract_region_info(self, content: str, platform_name: str) -> str:
        """从响应中提取地区信息"""
        try:
            if platform_name == 'Netflix':
                # Netflix特殊处理，尝试提取地区信息
                region_match = re.search(r'"country":"([^"]+)"', content)
                if region_match:
                    return region_match.group(1)
            
            # 通用地区检测
            region_patterns = [
                r'"country[_-]?code?":"([^"]+)"',
                r'"region":"([^"]+)"',
                r'"locale":"([^"]+)"',
                r'country[=:]"?([A-Z]{2})"?'
            ]
            
            for pattern in region_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            return '未知'
            
        except Exception:
            return '未知'
    
    def format_unlock_results(self, results: Dict) -> str:
        """格式化解锁测试结果"""
        if not results:
            return "❌ 解锁测试失败"
        
        summary = results.get('summary', {})
        platforms = results.get('platforms', {})
        
        text = "🔓 **平台解锁检测结果**\n\n"
        
        # 总结信息
        total = summary.get('total_platforms', 0)
        unlocked = summary.get('unlocked_platforms', 0)
        rate = summary.get('unlock_rate', 0)
        
        text += f"📊 **解锁统计:** {unlocked}/{total} ({rate}%)\n"
        text += f"⏱️ **检测时间:** {summary.get('test_time', '')}\n\n"
        
        # 平台详情
        text += "🎯 **平台详情:**\n"
        
        # 按解锁状态分组显示
        unlocked_platforms = []
        blocked_platforms = []
        error_platforms = []
        
        for platform, result in platforms.items():
            status_emoji = "✅" if result.get('unlocked') else "❌"
            region = result.get('region', '')
            response_time = result.get('response_time', 0)
            
            platform_info = f"{status_emoji} **{platform}**"
            
            if result.get('unlocked'):
                if region and region != '未知':
                    platform_info += f" ({region})"
                if response_time > 0:
                    platform_info += f" - {response_time}ms"
                unlocked_platforms.append(platform_info)
            elif result.get('status') == 'error' or result.get('status') == 'timeout':
                platform_info += f" - {result.get('message', '未知错误')}"
                error_platforms.append(platform_info)
            else:
                if response_time > 0:
                    platform_info += f" - {response_time}ms"
                blocked_platforms.append(platform_info)
        
        # 显示解锁的平台
        if unlocked_platforms:
            text += "\n🟢 **已解锁:**\n"
            for platform in unlocked_platforms:
                text += f"  {platform}\n"
        
        # 显示受限的平台
        if blocked_platforms:
            text += "\n🔴 **受限制:**\n"
            for platform in blocked_platforms:
                text += f"  {platform}\n"
        
        # 显示错误的平台
        if error_platforms:
            text += "\n⚠️ **检测异常:**\n"
            for platform in error_platforms:
                text += f"  {platform}\n"
        
        return text

# 全局解锁测试器实例
platform_unlock_tester = PlatformUnlockTester()

"""
统计管理器 - 收集和管理统计数据
"""
import time
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional
import threading


class StatisticsManager:
    """统计管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StatisticsManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._internal_lock = threading.Lock()
        
        # 回复统计
        self._reply_counts: Dict[str, int] = defaultdict(int)  # {account_name: count}
        self._keyword_hits: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))  # {account_name: {keyword: count}}
        self._reply_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # {account_name: [timestamps]}
        
        # 弹幕统计
        self._danmu_total_count = 0
        self._danmu_users: Dict[str, int] = defaultdict(int)  # {username: count}
        self._danmu_keywords: Dict[str, int] = defaultdict(int)  # {keyword: count}
        self._danmu_contents: deque = deque(maxlen=1000)  # 最近1000条弹幕内容（用于分析）
        
        # 未匹配关键词统计（高频出现但未设置回复的关键词）
        self._unmatched_danmu: deque = deque(maxlen=500)  # 最近500条未匹配的弹幕
        self._unmatched_keywords: Dict[str, int] = defaultdict(int)  # {keyword: count} 未匹配关键词及其出现次数
        
        # 性能指标
        self._response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # {account_name: [response_times]}
        self._queue_sizes: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # {account_name: [queue_sizes]}
        self._lock_contentions: deque = deque(maxlen=100)  # 锁竞争次数记录 [(timestamp, count)]
        
        # 时间戳记录
        self._start_time = time.time()
        
    def record_reply(self, account_name: str, keyword: Optional[str] = None):
        """记录回复"""
        with self._internal_lock:
            self._reply_counts[account_name] += 1
            if keyword:
                self._keyword_hits[account_name][keyword] += 1
            self._reply_times[account_name].append(time.time())
    
    def record_danmu(self, user: str, content: str):
        """记录弹幕"""
        with self._internal_lock:
            self._danmu_total_count += 1
            self._danmu_users[user] += 1
            self._danmu_contents.append({
                'user': user,
                'content': content,
                'timestamp': time.time()
            })
    
    def record_response_time(self, account_name: str, response_time: float):
        """记录响应时间（秒）"""
        with self._internal_lock:
            self._response_times[account_name].append(response_time)
    
    def record_queue_size(self, account_name: str, queue_size: int):
        """记录队列大小"""
        with self._internal_lock:
            self._queue_sizes[account_name].append(queue_size)
    
    def record_lock_contention(self, contention_count: int = 1):
        """记录锁竞争"""
        with self._internal_lock:
            self._lock_contentions.append((time.time(), contention_count))
    
    def record_unmatched_danmu(self, content: str):
        """
        记录未匹配的弹幕（用于统计高频未匹配关键词）
        
        Args:
            content: 弹幕内容
        """
        if not content or len(content.strip()) < 2:
            return
        
        with self._internal_lock:
            self._unmatched_danmu.append({
                'content': content,
                'timestamp': time.time()
            })
            
            # 提取关键词（简单的分词，提取2-10个字符的词语）
            # 方法1: 按空格和标点符号分词
            import re
            # 提取中文词语（2-10个字符）
            chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,10}', content)
            # 提取英文单词（2-20个字符）
            english_words = re.findall(r'[a-zA-Z]{2,20}', content)
            # 提取数字+单位组合（如"100个"、"50次"等）
            number_words = re.findall(r'\d+[个次条张本]', content)
            
            # 合并所有关键词
            keywords = chinese_words + english_words + number_words
            
            # 统计每个关键词的出现次数
            for keyword in keywords:
                if len(keyword) >= 2:  # 至少2个字符
                    self._unmatched_keywords[keyword] += 1
    
    def get_reply_statistics(self) -> Dict:
        """获取回复统计"""
        with self._internal_lock:
            # 计算平均响应时间
            avg_response_times = {}
            for account_name, times in self._response_times.items():
                if times:
                    avg_response_times[account_name] = sum(times) / len(times)
            
            # 获取每个账户的关键词命中Top10
            keyword_top = {}
            for account_name, keywords in self._keyword_hits.items():
                sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
                keyword_top[account_name] = sorted_keywords[:10]
            
            return {
                'reply_counts': dict(self._reply_counts),
                'keyword_hits': {k: dict(v) for k, v in self._keyword_hits.items()},
                'keyword_top': keyword_top,
                'avg_response_times': avg_response_times,
                'total_replies': sum(self._reply_counts.values())
            }
    
    def get_danmu_statistics(self, configured_keywords: set = None) -> Dict:
        """
        获取弹幕统计
        
        Args:
            configured_keywords: 已配置的关键词集合（用于过滤，只显示真正未配置的高频关键词）
        """
        with self._internal_lock:
            # 活跃用户Top20
            active_users = sorted(self._danmu_users.items(), key=lambda x: x[1], reverse=True)[:20]
            
            # 分析最近弹幕中的热门关键词（简单的分词，基于常见词汇）
            # 这里简化处理，可以后续优化
            recent_keywords = {}
            for item in list(self._danmu_contents)[-500:]:  # 分析最近500条
                content = item['content']
                # 简单的关键词提取（可以根据需要优化）
                words = content.split()
                for word in words:
                    if len(word) >= 2:  # 至少2个字符
                        recent_keywords[word] = recent_keywords.get(word, 0) + 1
            
            hot_keywords = sorted(recent_keywords.items(), key=lambda x: x[1], reverse=True)[:20]
            
            # 获取高频未匹配关键词Top20，并过滤掉已配置的关键词
            unmatched_top = sorted(self._unmatched_keywords.items(), key=lambda x: x[1], reverse=True)
            
            # 如果提供了已配置的关键词集合，过滤掉已配置的关键词
            if configured_keywords:
                filtered_unmatched = []
                for keyword, count in unmatched_top:
                    # 检查关键词是否在已配置的关键词中（支持部分匹配，因为已配置的关键词可能是更长的短语）
                    is_configured = False
                    for configured_kw in configured_keywords:
                        # 如果未匹配关键词包含已配置关键词，或者已配置关键词包含未匹配关键词，则认为已配置
                        if keyword in configured_kw or configured_kw in keyword:
                            is_configured = True
                            break
                    if not is_configured:
                        filtered_unmatched.append((keyword, count))
                unmatched_top = filtered_unmatched[:20]
            else:
                unmatched_top = unmatched_top[:20]
            
            return {
                'total_count': self._danmu_total_count,
                'active_users': dict(active_users),
                'unique_users': len(self._danmu_users),
                'hot_keywords': dict(hot_keywords),
                'unmatched_keywords': dict(unmatched_top),
                'unmatched_count': len(self._unmatched_danmu)
            }
    
    def get_performance_metrics(self) -> Dict:
        """获取性能指标"""
        with self._internal_lock:
            # 队列积压情况
            queue_stats = {}
            for account_name, sizes in self._queue_sizes.items():
                if sizes:
                    queue_stats[account_name] = {
                        'current': sizes[-1] if sizes else 0,
                        'max': max(sizes) if sizes else 0,
                        'avg': sum(sizes) / len(sizes) if sizes else 0
                    }
            
            # 锁竞争统计（最近100次）
            lock_contention_total = sum(count for _, count in self._lock_contentions)
            
            return {
                'queue_stats': queue_stats,
                'lock_contention_total': lock_contention_total,
                'lock_contention_recent': len([t for t, _ in self._lock_contentions if time.time() - t < 3600])  # 最近1小时
            }
    
    def get_all_statistics(self, configured_keywords: set = None) -> Dict:
        """
        获取所有统计数据
        
        Args:
            configured_keywords: 已配置的关键词集合（用于过滤未匹配关键词）
        """
        return {
            'reply': self.get_reply_statistics(),
            'danmu': self.get_danmu_statistics(configured_keywords),
            'performance': self.get_performance_metrics(),
            'runtime': time.time() - self._start_time
        }
    
    def reset_statistics(self):
        """重置所有统计数据"""
        with self._internal_lock:
            self._reply_counts.clear()
            self._keyword_hits.clear()
            self._reply_times.clear()
            self._danmu_total_count = 0
            self._danmu_users.clear()
            self._danmu_keywords.clear()
            self._danmu_contents.clear()
            self._response_times.clear()
            self._queue_sizes.clear()
            self._lock_contentions.clear()
            self._unmatched_danmu.clear()
            self._unmatched_keywords.clear()
            self._start_time = time.time()
    
    def export_to_dict(self) -> Dict:
        """导出统计数据为字典（用于JSON/CSV导出）"""
        stats = self.get_all_statistics()
        return {
            'timestamp': datetime.now().isoformat(),
            'runtime_seconds': stats['runtime'],
            'reply_statistics': stats['reply'],
            'danmu_statistics': stats['danmu'],
            'performance_metrics': stats['performance']
        }
    
    def export_to_csv_rows(self) -> List[List[str]]:
        """导出统计数据为CSV格式的行列表"""
        rows = []
        stats = self.get_all_statistics()
        
        # 回复统计
        rows.append(['=== 回复统计 ==='])
        rows.append(['账户名', '回复次数', '平均响应时间(秒)'])
        for account_name, count in stats['reply']['reply_counts'].items():
            avg_time = stats['reply']['avg_response_times'].get(account_name, 0)
            rows.append([account_name, str(count), f"{avg_time:.3f}"])
        
        rows.append([])
        rows.append(['=== 关键词命中统计 ==='])
        rows.append(['账户名', '关键词', '命中次数'])
        for account_name, keywords in stats['reply']['keyword_top'].items():
            for keyword, count in keywords:
                rows.append([account_name, keyword, str(count)])
        
        rows.append([])
        rows.append(['=== 弹幕统计 ==='])
        rows.append(['弹幕总数', str(stats['danmu']['total_count'])])
        rows.append(['活跃用户数', str(stats['danmu']['unique_users'])])
        rows.append([])
        rows.append(['活跃用户Top20'])
        rows.append(['用户名', '弹幕数'])
        for user, count in list(stats['danmu']['active_users'].items())[:20]:
            rows.append([user, str(count)])
        
        rows.append([])
        rows.append(['=== 高频未匹配关键词 ==='])
        rows.append(['排名', '关键词', '出现次数', '建议'])
        for idx, (keyword, count) in enumerate(list(stats['danmu'].get('unmatched_keywords', {}).items())[:20], 1):
            if count >= 10:
                suggestion = "强烈建议添加"
            elif count >= 5:
                suggestion = "建议添加"
            else:
                suggestion = "可考虑添加"
            rows.append([str(idx), keyword, str(count), suggestion])
        
        rows.append([])
        rows.append(['未匹配弹幕总数', str(stats['danmu'].get('unmatched_count', 0))])
        
        rows.append([])
        rows.append(['=== 性能指标 ==='])
        rows.append(['账户名', '当前队列', '最大队列', '平均队列'])
        for account_name, queue_stat in stats['performance']['queue_stats'].items():
            rows.append([
                account_name,
                str(queue_stat['current']),
                str(queue_stat['max']),
                f"{queue_stat['avg']:.2f}"
            ])
        rows.append([])
        rows.append(['锁竞争总数', str(stats['performance']['lock_contention_total'])])
        rows.append(['锁竞争（最近1小时）', str(stats['performance']['lock_contention_recent'])])
        
        return rows


# 全局单例实例
statistics_manager = StatisticsManager()


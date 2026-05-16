"""
LRU 缓存实现
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class LRUCache:
    """LRU 缓存实现"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict = {}
    
    def get(self, key) -> Optional[Any]:
        """获取缓存值"""
        if key not in self.cache:
            return None
        
        # 检查是否过期
        if datetime.now() - self.timestamps[key] > timedelta(seconds=self.ttl):
            self.delete(key)
            return None
        
        # 移动到末尾（最近使用）
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key, value) -> None:
        """设置缓存值"""
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # 删除最早的项
                oldest = next(iter(self.cache))
                self.delete(oldest)
        
        self.cache[key] = value
        self.timestamps[key] = datetime.now()
    
    def delete(self, key) -> None:
        """删除缓存项"""
        if key in self.cache:
            del self.cache[key]
            del self.timestamps[key]
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.timestamps.clear()

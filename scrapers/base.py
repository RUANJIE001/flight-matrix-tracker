"""
scrapers/base.py - 平台抓取基类与统一数据结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class FlightOffer:
    """航班报价实体"""
    platform: str                # 平台名称 (Google Flights / Ctrip / Skyscanner)
    price: float                 # 最低价格
    currency: str = "CNY"        # 货币
    depart_date: str = ""        # 出发日期 YYYY-MM-DD
    return_date: Optional[str] = None # 返程日期 YYYY-MM-DD
    airline: Optional[str] = None# 航司名称
    nonstop: bool = False        # 是否直飞
    booking_url: str = ""        # 预订链接
    raw_info: Dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

class BaseScraper(ABC):
    """抓取器抽象基类"""
    name: str = "base"

    @abstractmethod
    async def search(
        self,
        origin: str,
        dest: str,
        depart_date: str,
        return_date: Optional[str] = None,
        nonstop: bool = False
    ) -> Optional[FlightOffer]:
        """
        异步查询指定航线及日期的最低机票价格
        """
        pass

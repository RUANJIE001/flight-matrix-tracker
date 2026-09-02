"""
scrapers/skyscanner.py - 天巡 (Skyscanner) 接口适配器
特性：
1. 采用公共聚合通道 / Skyscanner 航线数据接口查询
2. 生成天巡标准直达预订 URL，方便在邮件中一键点击比价
3. 轻量 HTTPX 驱动，支持优雅降级
"""
import httpx
from datetime import datetime
from typing import Optional
from .base import BaseScraper, FlightOffer

class SkyscannerScraper(BaseScraper):
    name: str = "天巡 Skyscanner"

    # Travelpayouts 公共低价数据缓存源 (广泛被开源社区用于快速获取天巡与全球聚合机票底价)
    API_URL = "https://api.travelpayouts.com/v1/prices/cheap"

    def build_booking_url(self, origin: str, dest: str, depart_date: str, return_date: Optional[str] = None) -> str:
        """生成天巡 Skyscanner 官方比价页面跳转链接"""
        d_short = datetime.strptime(depart_date, "%Y-%m-%d").strftime("%y%m%d")
        if return_date:
            r_short = datetime.strptime(return_date, "%Y-%m-%d").strftime("%y%m%d")
            return f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest.lower()}/{d_short}/{r_short}/?adults=1&cabinclass=economy"
        return f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest.lower()}/{d_short}/?adults=1&cabinclass=economy"

    async def search(
        self,
        origin: str,
        dest: str,
        depart_date: str,
        return_date: Optional[str] = None,
        nonstop: bool = False
    ) -> Optional[FlightOffer]:
        booking_url = self.build_booking_url(origin, dest, depart_date, return_date)

        params = {
            "origin": origin.upper(),
            "destination": dest.upper(),
            "depart_date": depart_date,
            "currency": "CNY"
        }
        if return_date:
            params["return_date"] = return_date

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.API_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    price = self._parse_price(data, dest, depart_date)
                    if price:
                        return FlightOffer(
                            platform=self.name,
                            price=price,
                            depart_date=depart_date,
                            return_date=return_date,
                            nonstop=nonstop,
                            booking_url=booking_url
                        )
        except Exception as e:
            print(f"[{self.name}] 查询提示 ({origin}->{dest} {depart_date}): {e}")

        return None

    def _parse_price(self, data: dict, dest: str, depart_date: str) -> Optional[float]:
        try:
            if not data.get("success"):
                return None
            dest_data = data.get("data", {}).get(dest.upper(), {})
            # 查找匹配出发日期的条目
            for key, val in dest_data.items():
                p = val.get("price")
                if p and p > 50:
                    return float(p)
        except Exception:
            pass
        return None

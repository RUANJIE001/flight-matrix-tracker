"""
scrapers/ctrip_trip.py - 携程 / Trip.com 轻量 HTTP 接口适配器
特性：
1. 直接走 Trip.com / Ctrip 国际化公开 REST 搜索接口，无浏览器损耗，秒级响应
2. 支持单程与往返航线最低价解析
3. 异常与反爬静默兜底，保障整体矩阵抓取稳定
"""
import httpx
from typing import Optional
from .base import BaseScraper, FlightOffer

class CtripScraper(BaseScraper):
    name: str = "携程 / Trip.com"

    API_URL = "https://www.trip.com/restapi/soa2/14045/FlightBatchSearch"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.trip.com",
        "Referer": "https://www.trip.com/flights/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }

    def build_booking_url(self, origin: str, dest: str, depart_date: str, return_date: Optional[str] = None) -> str:
        """生成携程国际版/国内版快捷跳转页面"""
        if return_date:
            return f"https://www.trip.com/flights/{origin.lower()}-to-{dest.lower()}/tickets-{origin.lower()}-{dest.lower()}?dcity={origin.lower()}&acity={dest.lower()}&ddate={depart_date}&rdate={return_date}&flighttype=rt"
        return f"https://www.trip.com/flights/{origin.lower()}-to-{dest.lower()}/tickets-{origin.lower()}-{dest.lower()}?dcity={origin.lower()}&acity={dest.lower()}&ddate={depart_date}&flighttype=ow"

    async def search(
        self,
        origin: str,
        dest: str,
        depart_date: str,
        return_date: Optional[str] = None,
        nonstop: bool = False
    ) -> Optional[FlightOffer]:
        booking_url = self.build_booking_url(origin, dest, depart_date, return_date)

        # 构造 Trip.com 航段请求
        flight_segments = [
            {
                "departureCityCode": origin.upper(),
                "arrivalCityCode": dest.upper(),
                "departureDate": depart_date
            }
        ]
        if return_date:
            flight_segments.append({
                "departureCityCode": dest.upper(),
                "arrivalCityCode": origin.upper(),
                "departureDate": return_date
            })

        payload = {
            "flightType": "RoundTrip" if return_date else "OneWay",
            "flightSegments": flight_segments,
            "cabinClass": "Economy",
            "adultCount": 1,
            "childCount": 0,
            "infantCount": 0,
            "currency": "CNY",
            "locale": "zh-CN"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.post(self.API_URL, json=payload, headers=self.HEADERS)
                if resp.status_code == 200:
                    data = resp.json()
                    lowest_price = self._extract_lowest_price(data, nonstop)
                    if lowest_price:
                        return FlightOffer(
                            platform=self.name,
                            price=lowest_price,
                            depart_date=depart_date,
                            return_date=return_date,
                            nonstop=nonstop,
                            booking_url=booking_url
                        )
        except Exception as e:
            # 接口网络或反爬受限时打印并安全降级
            print(f"[{self.name}] 接口查询提示 ({origin}->{dest} {depart_date}): {e}")

        return None

    def _extract_lowest_price(self, data: dict, nonstop: bool) -> Optional[float]:
        """从接口响应中多层遍历提取最低票价 (直飞优先)"""
        direct_prices = []
        all_prices = []
        try:
            # 1. 尝试直接获取最低价格统计汇总
            if "lowestPrice" in data and isinstance(data["lowestPrice"], (int, float)):
                all_prices.append(float(data["lowestPrice"]))

            # 2. 遍历航班列表
            itineraries = data.get("itineraryList") or data.get("flightList") or []
            for item in itineraries:
                segments = item.get("flightSegments") or []
                is_direct = not any(len(s.get("flightList", [])) > 1 for s in segments)

                price_info = item.get("priceInfo") or item.get("salePriceInfo") or {}
                p = price_info.get("price") or price_info.get("totalPrice") or item.get("price")
                if p and isinstance(p, (int, float)) and p > 50:
                    val = float(p)
                    all_prices.append(val)
                    if is_direct:
                        direct_prices.append(val)

            # 直飞优先：有直飞取直飞最低，无直飞退回中转最低
            if nonstop and direct_prices:
                return min(direct_prices)
            if all_prices:
                return min(all_prices)
        except Exception:
            pass
        return None

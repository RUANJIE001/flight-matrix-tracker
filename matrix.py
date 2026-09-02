"""
matrix.py - 弹性日期矩阵计算器 (Cartesian Matrix Calculator)
功能：
1. 计算 a±1 与 b±1 的 9 组往返日期笛卡尔积组合
2. 过滤已过期或非法组合 (例如返程早于出发)
3. 汇总计算各平台最低价、全局最低价与基准日节省金额
4. 生成 Markdown 预览表格与响应式 HTML 矩阵热力表格
"""
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Any
from scrapers.base import FlightOffer

def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str.strip(), "%Y-%m-%d")

def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def generate_date_pairs(
    base_depart: str,
    base_return: Optional[str] = None,
    flexible_days: int = 1
) -> List[Tuple[str, Optional[str], str]]:
    """
    生成弹性日期矩阵组合。
    返回列表元素: (depart_date, return_date, label)
    例如: ("2026-10-23", "2026-10-30", "a-1, b-1")
    """
    dt_dep = parse_date(base_depart)
    today = datetime.now().date()

    dep_offsets = list(range(-flexible_days, flexible_days + 1)) if flexible_days > 0 else [0]
    
    # 单程模式
    if not base_return:
        pairs = []
        for d_off in dep_offsets:
            dep_d = dt_dep + timedelta(days=d_off)
            if dep_d.date() < today:
                continue
            lbl = "原定 (a)" if d_off == 0 else f"a{'+' if d_off > 0 else ''}{d_off}"
            pairs.append((format_date(dep_d), None, lbl))
        return pairs

    # 往返模式
    dt_ret = parse_date(base_return)
    ret_offsets = list(range(-flexible_days, flexible_days + 1)) if flexible_days > 0 else [0]

    pairs = []
    for d_off in dep_offsets:
        dep_d = dt_dep + timedelta(days=d_off)
        if dep_d.date() < today:
            continue
        for r_off in ret_offsets:
            ret_d = dt_ret + timedelta(days=r_off)
            if ret_d <= dep_d:
                continue  # 返程必须晚于出发
            
            d_tag = "a" if d_off == 0 else f"a{'+' if d_off > 0 else ''}{d_off}"
            r_tag = "b" if r_off == 0 else f"b{'+' if r_off > 0 else ''}{r_off}"
            lbl = "原定 (a ⇄ b)" if (d_off == 0 and r_off == 0) else f"{d_tag} ⇄ {r_tag}"
            
            pairs.append((format_date(dep_d), format_date(ret_d), lbl))

    return pairs

class MatrixAnalysis:
    """价格矩阵深度分析"""
    def __init__(
        self,
        base_depart: str,
        base_return: Optional[str],
        target_price: float,
        results_map: Dict[Tuple[str, Optional[str]], List[FlightOffer]]
    ):
        self.base_depart = base_depart
        self.base_return = base_return
        self.target_price = target_price
        self.results_map = results_map
        self.global_min_offer: Optional[FlightOffer] = None
        self.baseline_min_offer: Optional[FlightOffer] = None
        self.savings: float = 0.0
        self.best_recommendation: str = ""
        self._analyze()

    def _analyze(self):
        all_offers = []
        for key, offers in self.results_map.items():
            all_offers.extend(offers)

        if not all_offers:
            return

        # 全局最低价
        self.global_min_offer = min(all_offers, key=lambda x: x.price)

        # 基准日期的最低价
        baseline_key = (self.base_depart, self.base_return)
        baseline_offers = self.results_map.get(baseline_key, [])
        if baseline_offers:
            self.baseline_min_offer = min(baseline_offers, key=lambda x: x.price)

        # 比价与省钱计算
        if self.baseline_min_offer and self.global_min_offer:
            diff = self.baseline_min_offer.price - self.global_min_offer.price
            if diff > 0:
                self.savings = diff
                self.best_recommendation = (
                    f"若调整出行日期为 【{self.global_min_offer.depart_date}"
                    + (f" ⇄ {self.global_min_offer.return_date}】" if self.global_min_offer.return_date else "】")
                    + f"，最低价仅 ¥{int(self.global_min_offer.price)} ({self.global_min_offer.platform})，"
                    + f"比原定日期立省 ¥{int(diff)}！"
                )

    def render_markdown(self) -> str:
        """生成 Markdown 格式的表格"""
        lines = []
        lines.append("| 出发日期 | 返程日期 | 最低票价 | 平台来源 | 状态 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")

        for (dep, ret), offers in self.results_map.items():
            ret_str = ret if ret else "单程"
            if offers:
                best = min(offers, key=lambda x: x.price)
                is_hit = best.price <= self.target_price
                is_global = (self.global_min_offer and best.price == self.global_min_offer.price)
                
                tag = ""
                if is_global:
                    tag += "🔥 全局最低 "
                if is_hit:
                    tag += "✅ 达标 "
                if not tag:
                    tag = "正常"

                lines.append(f"| {dep} | {ret_str} | **¥{int(best.price)}** | {best.platform} | {tag} |")
            else:
                lines.append(f"| {dep} | {ret_str} | 未检索到 | -- | -- |")

        return "\n".join(lines)

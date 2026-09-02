"""
tracker.py - 机票价格监控主调度引擎
功能：
1. 读取配置 (支持 config.yaml 与 环境变量双重覆盖)
2. 调度 Google Flights、携程、天巡 并发查询 ±1 天矩阵航线
3. 统计比价结果并保存至 history.json
4. 根据判定条件触发 HTML 邮件与 Webhook 发送
"""
import os
import sys
import json
import yaml
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Tuple

from scrapers import GoogleFlightsScraper, CtripScraper, SkyscannerScraper, FlightOffer
from matrix import generate_date_pairs, MatrixAnalysis
from notifier import Notifier

HISTORY_FILE = "history.json"

def clean_val(v: Any) -> str:
    if not v:
        return ""
    return str(v).strip().strip("'").strip('"').replace("\n", "").replace("\r", "")

def load_config() -> Dict[str, Any]:
    """加载配置文件并支持 GitHub Actions 环境变量覆盖敏感项"""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        config_path = "config.example.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 环境变量覆盖 (常用于 GitHub Secrets / Vars)
    if os.getenv("ORIGIN"):
        config["flight"]["origin"] = clean_val(os.getenv("ORIGIN")).upper()
    if os.getenv("DEST"):
        config["flight"]["dest"] = clean_val(os.getenv("DEST")).upper()
    if os.getenv("DEPART_DATE"):
        config["flight"]["depart_date"] = clean_val(os.getenv("DEPART_DATE"))
    if os.getenv("RETURN_DATE"):
        config["flight"]["return_date"] = clean_val(os.getenv("RETURN_DATE"))
    if os.getenv("TARGET_PRICE"):
        config["flight"]["target_price"] = float(clean_val(os.getenv("TARGET_PRICE")))
    if os.getenv("NONSTOP"):
        config["flight"]["nonstop"] = clean_val(os.getenv("NONSTOP")).lower() in ["true", "1", "yes"]

    # 邮件 Secret 覆盖 (支持规范别名 EMAIL_USER / EMAIL_AUTH_TOKEN / EMAIL_HOST)
    sender = clean_val(os.getenv("EMAIL_SENDER") or os.getenv("EMAIL_USER"))
    if sender and sender.lower() not in ["false", "none", ""]:
        config["email"]["sender_email"] = sender

    auth_token = clean_val(os.getenv("EMAIL_AUTH_CODE") or os.getenv("EMAIL_AUTH_TOKEN") or os.getenv("EMAIL_PASSWORD"))
    if auth_token and auth_token.lower() not in ["false", "none", ""]:
        # 严格清洗内部空格 (针对 Google 16位应用专用密码)
        config["email"]["sender_auth_code"] = auth_token.replace(" ", "")

    recipient = clean_val(os.getenv("EMAIL_RECIPIENT") or os.getenv("RECEIVER_EMAIL"))
    if recipient and recipient.lower() not in ["false", "none", ""]:
        config["email"]["recipient_email"] = recipient

    host = clean_val(os.getenv("SMTP_SERVER") or os.getenv("EMAIL_HOST"))
    if host and host.lower() not in ["false", "none", ""]:
        config["email"]["smtp_server"] = host.replace("http://", "").replace("https://", "").split(":")[0]

    port = clean_val(os.getenv("SMTP_PORT") or os.getenv("EMAIL_PORT"))
    if port and port.lower() not in ["false", "none", ""]:
        config["email"]["smtp_port"] = int(port)

    return config

async def process_pair(
    pair: Tuple[str, str, str],
    origin: str,
    dest: str,
    nonstop: bool,
    scrapers: list,
    semaphore: asyncio.Semaphore
) -> Tuple[Tuple[str, str], List[FlightOffer]]:
    """异步抓取单组日期在各平台的报价"""
    dep, ret, lbl = pair
    async with semaphore:
        tasks = []
        for s in scrapers:
            tasks.append(s.search(origin, dest, dep, ret, nonstop))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_offers = [r for r in results if isinstance(r, FlightOffer) and r is not None]
        return (dep, ret), valid_offers

async def main():
    config = load_config()
    flight_cfg = config.get("flight", {})
    platforms_cfg = config.get("platforms", {})

    origin = flight_cfg.get("origin")
    dest = flight_cfg.get("dest")
    depart_date = flight_cfg.get("depart_date")
    return_date = flight_cfg.get("return_date") if flight_cfg.get("trip_type") == "roundtrip" else None
    nonstop = flight_cfg.get("nonstop", False)
    target_price = float(flight_cfg.get("target_price", 2000))
    flexible_days = int(flight_cfg.get("flexible_days", 1))

    print(f"==================================================")
    print(f"✈️  启动机票价格矩阵监控: {origin} ⇄ {dest}")
    print(f"📅 基准日期: 出发 {depart_date}" + (f", 返程 {return_date}" if return_date else " (单程)"))
    print(f"🎯 期望目标价: ¥{target_price} | 仅直飞: {nonstop} | 弹性天数: ±{flexible_days}天")
    print(f"==================================================")

    # 1. 生成弹性日期矩阵 (通常往返为 3x3=9 组)
    date_pairs = generate_date_pairs(depart_date, return_date, flexible_days)
    print(f"[Matrix] 已生成 {len(date_pairs)} 组待查询日期组合:")
    for d, r, lbl in date_pairs:
        print(f"   · {d} ⇄ {r or '单程'} ({lbl})")

    # 2. 初始化抓取器
    active_scrapers = []
    playwright_instance = None
    browser = None

    if platforms_cfg.get("google_flights", True):
        from playwright.async_api import async_playwright
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=True)
        active_scrapers.append(GoogleFlightsScraper(browser=browser))

    if platforms_cfg.get("ctrip", True):
        active_scrapers.append(CtripScraper())

    if platforms_cfg.get("skyscanner", True):
        active_scrapers.append(SkyscannerScraper())

    print(f"[Scrapers] 启用的数据源: {[s.name for s in active_scrapers]}")

    # 3. 并发抓取 (设置并发度上限为 3，兼顾速度与避免被流控)
    semaphore = asyncio.Semaphore(3)
    fetch_tasks = [
        process_pair(pair, origin, dest, nonstop, active_scrapers, semaphore)
        for pair in date_pairs
    ]

    results_list = await asyncio.gather(*fetch_tasks)
    results_map = dict(results_list)

    # 清理浏览器资源
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()

    # 4. 分析与比价
    analysis = MatrixAnalysis(depart_date, return_date, target_price, results_map)

    print("\n---------------- 监控结果汇总 ----------------")
    print(analysis.render_markdown())
    if analysis.best_recommendation:
        print(f"\n💡 {analysis.best_recommendation}")

    # 5. 持久化记录到 history.json
    save_history(origin, dest, analysis)

    # 6. 发送邮件与消息通知
    notifier = Notifier(config)
    try:
        notifier.send_notification(flight_cfg, analysis)
    except Exception as e:
        print(f"\n❌ [Tracker] 邮件推送失败: {e}")
        print("💡 请确认在 GitHub 仓库 Settings -> Secrets -> Actions 中配置了真实的 EMAIL_SENDER 与 EMAIL_AUTH_CODE (Google 16位应用专用密码)！")
        sys.exit(1)

def save_history(origin: str, dest: str, analysis: MatrixAnalysis):
    """保存抓取历史到本地文件"""
    history_data = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            history_data = []

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "origin": origin,
        "dest": dest,
        "global_lowest": analysis.global_min_offer.price if analysis.global_min_offer else None,
        "global_platform": analysis.global_min_offer.platform if analysis.global_min_offer else None,
        "target_price": analysis.target_price,
        "is_hit": bool(analysis.global_min_offer and analysis.global_min_offer.price <= analysis.target_price)
    }

    history_data.append(record)
    # 保留最近 500 次历史
    history_data = history_data[-500:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    print(f"[History] 已归档历史记录至 {HISTORY_FILE} (共 {len(history_data)} 条)")

if __name__ == "__main__":
    asyncio.run(main())

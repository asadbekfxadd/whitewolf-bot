import feedparser
import httpx
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

FOREX_FEEDS = [
    "https://www.forexlive.com/feed/news",
    "https://www.fxstreet.com/rss/news",
    "https://www.investing.com/rss/news_25.rss",
    "https://www.investing.com/rss/news_1.rss",
]

FOREX_KEYWORDS = [
    "gold", "xauusd", "eurusd", "gbpusd", "dollar", "fed",
    "inflation", "nfp", "interest rate", "forex", "oil",
    "sp500", "dxy", "доллар", "золото", "фрс", "инфляция",
    "rate", "fomc", "powell", "ecb", "bank",
]


async def fetch_forex_news(hours_back: int = 8) -> list[dict]:
    all_news = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    for feed_url in FOREX_FEEDS:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(feed_url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; WhiteWolfBot/1.0)"
                })
                feed = feedparser.parse(response.text)

            for entry in feed.entries[:8]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")

                text_lower = (title + " " + summary).lower()
                if not any(kw in text_lower for kw in FOREX_KEYWORDS):
                    continue

                published = entry.get("published_parsed")
                if published:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue

                all_news.append({
                    "title": title,
                    "summary": summary[:400],
                    "link": link,
                    "source": feed.feed.get("title", feed_url)
                })

        except Exception as e:
            logger.warning(f"Ошибка {feed_url}: {e}")

    seen = set()
    unique = []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    logger.info(f"Новостей: {len(unique)}")
    return unique[:5]


async def get_market_data() -> dict:
    """Котировки: XAUUSD, EURUSD, GBPUSD, USDJPY, USDCHF"""
    results = {}

    # --- XAUUSD через gold-api.io (бесплатно без ключа) ---
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://data-asg.goldprice.org/dbXRates/USD")
            if resp.status_code == 200:
                data = resp.json()
                xau = data.get("items", [{}])[0].get("xauPrice")
                if xau:
                    results["XAUUSD"] = round(float(xau), 2)
    except Exception as e:
        logger.warning(f"goldprice.org: {e}")

    # --- XAUUSD резерв через metals-api ---
    if "XAUUSD" not in results:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.frankfurter.app/latest",
                    params={"from": "XAU", "to": "USD"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    xau = data.get("rates", {}).get("USD")
                    if xau:
                        results["XAUUSD"] = round(float(xau), 2)
        except Exception as e:
            logger.warning(f"frankfurter XAU: {e}")

    # --- Форекс пары через Coinbase ---
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coinbase.com/v2/exchange-rates?currency=USD"
            )
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("data", {}).get("rates", {})
                if "EUR" in rates:
                    results["EURUSD"] = round(1 / float(rates["EUR"]), 5)
                if "GBP" in rates:
                    results["GBPUSD"] = round(1 / float(rates["GBP"]), 5)
                if "JPY" in rates:
                    results["USDJPY"] = round(float(rates["JPY"]), 3)
                if "CHF" in rates:
                    results["USDCHF"] = round(float(rates["CHF"]), 5)
    except Exception as e:
        logger.warning(f"Coinbase: {e}")

    # --- DXY приблизительно ---
    if "EURUSD" in results:
        eurusd = results["EURUSD"]
        results["DXY≈"] = round(103.82 / (eurusd / 1.0827), 2)

    logger.info(f"Котировки: {results}")
    return results

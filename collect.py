# -*- coding: utf-8 -*-
"""매일 1회 시세 수집 → data/market_history.json 축적 (GitHub Actions용)
수집원: TrendForce 공개 시세 페이지(DRAM/NAND 스팟·계약), Frankfurter(ECB 환율)
원칙: 조회 실패 항목은 건너뜀(추정 금지). 같은 날짜는 교체(중복 방지)."""
import json, re, datetime, requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; S1-procurement-monitor/1.0)"}
DB = "data/market_history.json"

def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")

def get(url):
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    return r.text

def parse_tables(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue
        hs = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        body = [[c.get_text(strip=True) for c in r.find_all(["th", "td"])] for r in rows[1:]]
        out.append((hs, body))
    return out

def idx_of(hs, names):
    for n in names:
        if n in hs:
            return hs.index(n)
    return -1

def extract(html, page):
    """페이지에서 {품목: 세션/평균가} 추출"""
    items = {}
    for hs, body in parse_tables(html):
        if "Daily High" in hs and "Session Change" in hs:      # 스팟
            ai = idx_of(hs, ["Session Average"])
        elif "Weekly High" in hs and "Session Change" in hs:   # 웨이퍼 스팟
            ai = idx_of(hs, ["Session Average"])
        elif "Average Change" in hs and "Low Change" in hs:    # 계약가
            ai = idx_of(hs, ["Session Average", "Average"])
        else:
            continue
        for c in body:
            if not c or ai < 0 or ai >= len(c):
                continue
            item = c[0]
            if not re.search(r"(DDR|SLC|MLC|TLC|Gb)", item) or item.startswith("["):
                continue
            try:
                items[item] = float(c[ai].replace(",", ""))
            except ValueError:
                pass
    return items

def main():
    p = {}
    for url in ("https://www.trendforce.com/price/dram/dram_spot",
                "https://www.trendforce.com/price/flash/flash_spot"):
        try:
            p.update(extract(get(url), url))
        except Exception as e:
            print("WARN page fail:", url, e)
    fx = {}
    try:
        j = requests.get("https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,CNY,JPY,EUR",
                         headers=UA, timeout=30).json()
        r = j["rates"]
        fx = {"USD": round(r["KRW"], 2), "CNY": round(r["KRW"] / r["CNY"], 2),
              "JPY": round(r["KRW"] / r["JPY"] * 100, 2), "EUR": round(r["KRW"] / r["EUR"], 2)}
    except Exception as e:
        print("WARN fx fail:", e)

    if not p and not fx:
        raise SystemExit("nothing collected")

    try:
        db = json.load(open(DB, encoding="utf-8"))
    except Exception:
        db = []
    d = kst_today()
    entry = {"d": d, "fx": fx, "p": p}
    db = [e for e in db if e.get("d") != d] + [entry]
    db.sort(key=lambda e: e["d"])
    json.dump(db, open(DB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", d, "items:", len(p), "fx:", bool(fx), "total days:", len(db))

if __name__ == "__main__":
    main()

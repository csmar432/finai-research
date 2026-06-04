#!/usr/bin/env python3
"""批量获取许哲逸负责股票的MSCI ESG评级"""
import json
import os
import ssl
import time
import urllib.request

import openpyxl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://finance.sina.com.cn/esg/grade.shtml',
}

EXCEL_PATH = str(Path.home() / 'Desktop' / '2026MSCI级别6.1.xlsx')
OUTPUT_PATH = str(Path.home() / 'Desktop' / '2026MSCI级别6.1_已填充.xlsx')
CACHE_FILE = str(Path.home() / 'Desktop' / '论文-研报工作流/data/msci_esg_ratings_xu.json')

print("1. 读取Excel...")
wb = openpyxl.load_workbook(EXCEL_PATH)
ws = wb['2025年度上市公司名单']

xu_stocks = []
for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
    if row[6] == '许哲逸':
        ts_code = row[1]
        hk_code = row[2]
        if ts_code and ts_code.endswith('.SH'):
            symbol = 'sh' + ts_code.replace('.SH', '')
        elif ts_code and ts_code.endswith('.SZ'):
            symbol = 'sz' + ts_code.replace('.SZ', '')
        else:
            symbol = None
        xu_stocks.append({
            'row_idx': row_idx,
            'name': row[0],
            'ts_code': ts_code,
            'hk_code': hk_code,
            'short_name': row[3],
            'symbol': symbol,
        })

print(f"   股票总数: {len(xu_stocks)}")
stocks_with_sym = [s for s in xu_stocks if s['symbol']]
print(f"   有API符号: {len(stocks_with_sym)}")
no_sym = [s for s in xu_stocks if not s['symbol']]
if no_sym:
    print(f"   无符号(北交所等): {len(no_sym)}")

# Load cache
cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, encoding='utf-8') as f:
        cache = json.load(f)
    print(f"   缓存已有: {len(cache)} 条")

to_fetch = [s for s in stocks_with_sym if s['symbol'].upper() not in cache]
print(f"   需新获取: {len(to_fetch)} 只")

def get_msci(symbol):
    url = f'https://global.finance.sina.com.cn/api/openapi.php/EsgService.getEsgStockInfo?symbol={symbol}'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            for info in data.get('result', {}).get('data', {}).get('info', []):
                if info.get('agency_name') == 'MSCI':
                    return info.get('esg_score'), info.get('esg_dt')
    except Exception:
        pass
    return None, None

if to_fetch:
    print("\n2. 开始获取...")
    fetched = 0
    start = time.time()
    for i, s in enumerate(to_fetch):
        sym = s['symbol']
        rating, date = get_msci(sym)
        cache[sym.upper()] = {'msci_rating': rating, 'msci_date': date}
        if rating:
            fetched += 1
        if (i+1) % 50 == 0:
            elapsed = time.time() - start
            rate = elapsed / (i+1)
            eta = rate * (len(to_fetch) - i - 1) if (i+1) > 0 else 0
            print(f"   {i+1}/{len(to_fetch)} | 成功: {fetched} | ETA: {eta/60:.1f}min")
        time.sleep(0.3)

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"   缓存已保存, 新增成功: {fetched}")

# Fill Excel
print("\n3. 回填Excel...")
filled = 0
no_rating = 0
no_sym_count = 0

for s in xu_stocks:
    row_idx = s['row_idx']
    if not s['symbol']:
        no_sym_count += 1
        continue
    sym_upper = s['symbol'].upper()
    if sym_upper in cache:
        result = cache[sym_upper]
        rating = result.get('msci_rating')
        date = result.get('msci_date')
        if rating and rating != '-':
            ws.cell(row=row_idx, column=5, value=rating)
            ws.cell(row=row_idx, column=6, value=date)
            filled += 1
        else:
            no_rating += 1
    else:
        no_rating += 1

wb.save(OUTPUT_PATH)
print(f"   保存: {OUTPUT_PATH}")
print(f"   成功填充: {filled}/{len(xu_stocks)}")
print(f"   无MSCI评级: {no_rating}")
print(f"   无API符号: {no_sym_count}")

dist = {}
for s in xu_stocks:
    if s['symbol']:
        r = cache.get(s['symbol'].upper(), {}).get('msci_rating')
        if r and r != '-':
            dist[r] = dist.get(r, 0) + 1

print("\n=== 评级分布 ===")
for r in sorted(dist.keys()):
    print(f"  {r}: {dist[r]}")
print("Done!")

# External Data Sources for Academic Finance & Economics Research

A curated, practical guide to high-quality free and low-cost data sources for academic research in finance and economics. Sources marked ✅ are already integrated into this workspace as MCP servers.

---

## A. Macroeconomic Data

### A1. FRED (Federal Reserve Economic Data) ✅
| Attribute | Details |
|---|---|
| **URL** | https://fred.stlouisfed.org |
| **Data Provided** | 800,000+ US and international economic series: GDP, CPI, interest rates, exchange rates, monetary aggregates, employment, housing, consumer sentiment |
| **Coverage** | US data from 1913; international data varies by series |
| **Access** | REST API: https://api.stlouisfed.org/fred |
| **Python Package** | `fredapi`, `full_fred`, `frb` |
| **API Key** | Required (free at https://fred.stlouisfed.org/docs/api/api_key.html) |
| **Rate Limits** | 120 requests/second for registered users |
| **Best Strategy** | Use `fredapi` for quick Pandas integration; cache data locally to minimize API calls |

```python
from fredapi import Fred
fred = Fred(api_key='YOUR_KEY')
gdp = fred.get_series('GDP')
```

### A2. World Bank API ✅
| Attribute | Details |
|---|---|
| **URL** | https://databank.worldbank.org |
| **Data Provided** | GDP, population, trade, FDI, debt, education, health, gender indicators for 200+ countries |
| **Coverage** | 1960–present, 200+ countries |
| **Access** | REST API: https://api.worldbank.org/v2; also SDMX endpoint |
| **Python Package** | `wbgapi`, `wbdata`, `pandas` (read_csv directly) |
| **API Key** | None required |
| **Rate Limits** | No official limit; be respectful |
| **Best Strategy** | `wbgapi` provides pandas DataFrame output; batch requests for multiple indicators |

```python
import wbgapi as wb
wb.data.DataFrame('NY.GDP.MKTP.CD', time='YR2020', columns='economy')
```

### A3. IMF Data ✅
| Attribute | Details |
|---|---|
| **URL** | https://data.imf.org |
| **Data Provided** | Balance of payments, WEO (World Economic Outlook), IFS (International Financial Statistics), Direction of Trade, Government Finance Statistics |
| **Coverage** | 1945–present, 200+ countries |
| **Access** | REST API: https://dataservices.imf.org/REST/SDMX_JSON.svc; also SDMX at https://sdmxcentral.imf.org |
| **Python Package** | `imfpy`, `requests` with JSON parsing |
| **API Key** | None required |
| **Rate Limits** | No published limits |
| **Best Strategy** | IMF API uses SDMX; use `imfpy` for simpler interface; identify dataflow IDs first |

```python
import imfpy
data = imfpy.OECDData.fetch('MEI', 'USA.BRC_GFCI_IX')
```

### A4. OECD Data ✅
| Attribute | Details |
|---|---|
| **URL** | https://data.oecd.org |
| **Data Provided** | GDP, employment, trade, education, health, productivity, agricultural, development indicators |
| **Coverage** | 1960–present, 38 OECD member countries + partner economies |
| **Access** | REST API: https://sdmx.oecd.org/public/rest/data; also JSON format endpoint |
| **Python Package** | `OECD`, `pandaSDMX` |
| **API Key** | None required |
| **Rate Limits** | No published limits; polite usage expected |
| **Best Strategy** | Discover dataset IDs via browser first; use CSV format for bulk downloads |

```python
import OECD
datasets = OECD.search.datasets('gdp')
```

### A5. UN Comtrade
| Attribute | Details |
|---|---|
| **URL** | https://comtrade.un.org & https://comtradedeveloper.un.org |
| **Data Provided** | International merchandise trade by commodity (HS/SITC classification), trade flows (imports/exports), bilateral trade, tariff data |
| **Coverage** | 1962–present, 200+ reporter countries, monthly and annual |
| **Access** | REST API with subscription key; also bulk download for registered users |
| **Python Package** | `comtradeapicall` |
| **API Key** | Required (free registration at https://comtradedeveloper.un.org) |
| **Rate Limits** | Free tier: 500 requests/day, 100,000 records/call |
| **Best Strategy** | Preview data first with `previewFinalData()` to avoid consuming quota; use wildcard periods for multi-year queries |

```python
import comtradeapicall
df = comtradeapicall.getFinalData(
    subscription_key='YOUR_KEY',
    typeCode='C', freqCode='A', period='2022',
    reporterCode='156',  # China
    cmdCode='TOTAL', flowCode='X'
)
```

### A6. BIS (Bank for International Settlements)
| Attribute | Details |
|---|---|
| **URL** | https://data.bis.org |
| **Data Provided** | OTC derivatives statistics, international banking statistics, global liquidity, debt securities, exchange rates, policy rates |
| **Coverage** | 1970s–present, 60+ reporting economies |
| **Access** | SDMX REST API: https://stats.bis.org/api/v1 |
| **Python Package** | `sdmx`, `sdmxthon` |
| **API Key** | None required |
| **Rate Limits** | No published limits; use gzip compression |
| **Best Strategy** | BIS SDMX API follows the standard pattern across all international orgs; start with dataflow discovery |

```python
import sdmx
client = sdmx.Client('BIS')
data = client.data('BIS', 'WS_OTC_DER2', start='2023')
dataframe = data.to_pandas()
```

### A7. ECB (European Central Bank)
| Attribute | Details |
|---|---|
| **URL** | https://data.ecb.europa.eu |
| **Data Provided** | Exchange rates (40+ currencies), monetary aggregates (M1/M2/M3), balance of payments, securities holdings, interest rates, HICP inflation, bank lending |
| **Coverage** | 1999–present (some series back to 1970s), euro area + trading partners |
| **Access** | SDMX REST API: https://data-api.ecb.europa.eu/service |
| **Python Package** | `ecbdata`, `pandaSDMX` |
| **API Key** | None required |
| **Rate Limits** | No formal limit; use `Accept-Encoding: gzip` header |
| **Best Strategy** | ECB series follow strict naming conventions; use CSV format (`format=csvdata`) for easier parsing |

```python
from ecbdata import ecbdata
df = ecbdata.get_series('EXR.M.USD.EUR.SP00.A', start='2024-01', end='2024-12')
```

### A8. UK ONS (Office for National Statistics)
| Attribute | Details |
|---|---|
| **URL** | https://developer.ons.gov.uk |
| **Data Provided** | UK GDP, CPI/RPI, unemployment, trade, population, health, crime, housing, business surveys |
| **Coverage** | 1955–present, UK-wide and subnational |
| **Access** | REST API: https://api.beta.ons.gov.uk/v1 |
| **Python Package** | `pyONS` (community), `requests` directly |
| **API Key** | None required |
| **Rate Limits** | 120 requests/10 seconds, 200 requests/minute |
| **Best Strategy** | Beta API is free and open; browse datasets at https://api.beta.ons.gov.uk/v1/datasets first |

```python
import requests
url = "https://api.beta.ons.gov.uk/data?uri=/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/jp9p/lms"
df = pd.DataFrame(requests.get(url).json()["months"])
```

### A9. China NBS (National Bureau of Statistics)
| Attribute | Details |
|---|---|
| **URL** | https://www.stats.gov.cn/english/ |
| **Data Provided** | China GDP, CPI, PPI, industrial output, fixed asset investment, retail sales, population, trade |
| **Coverage** | 1952–present, national and provincial |
| **Access** | Web scraping via unofficial API; official data portal; bulk downloads |
| **Python Package** | `cn-stats`, `akshare` (macro_china_*), `nbsc` |
| **API Key** | None required (web scraping-based) |
| **Rate Limits** | Varies; avoid excessive requests |
| **Best Strategy** | AKShare provides the most reliable Python interface; cn-stats for direct NBS queries; verify data against official releases for formal research |

```python
import akshare as ak
macro_china_gdp_yearly_df = ak.macro_china_gdp_yearly()
macro_china_cpi_df = ak.macro_china_cpi()
```

### A10. Penn World Table
| Attribute | Details |
|---|---|
| **URL** | https://www.rug.nl/ggdc/productivity/pwt/ |
| **Data Provided** | PPP-adjusted GDP, capital stock, TFP, employment, hours worked, human capital — cross-country comparable |
| **Coverage** | PWT 11.0: 185 countries, 1950–2023 |
| **Access** | Direct download: Excel (.xlsx) and Stata (.dta) files from DataverseNL |
| **Python Package** | `PWTLoader` |
| **API Key** | None required |
| **Rate Limits** | File download, no API |
| **Best Strategy** | Use `PWTLoader` for automatic version detection and pandas output; download Stata file directly for latest version |

```python
from PWTLoader import PWTLoader
pwt = PWTLoader()
df = pwt.load_data()
```

### A11. Maddison Project Database
| Attribute | Details |
|---|---|
| **URL** | https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2023 |
| **Data Provided** | GDP per capita, population, PPP-adjusted GDP — very long-run historical estimates |
| **Coverage** | MPD 2023: 169 countries, 1 AD–2022 (regional estimates from 1820) |
| **Access** | Direct download: Excel and Stata from DataverseNL (DOI: 10.34894/INZBF2); Our World in Data CSV |
| **Python Package** | None (direct download) |
| **API Key** | None required |
| **Rate Limits** | File download, no API |
| **Best Strategy** | Our World in Data provides a CSV download URL for easy programmatic access; cite the original paper |

```python
url = "https://ourworldindata.org/grapher/gdp-per-capita-maddison-project-database.csv?v=1&csvType=full"
df = pd.read_csv(url)
```

---

## B. Financial Market Data

### B1. Yahoo Finance ✅
| Attribute | Details |
|---|---|
| **URL** | https://finance.yahoo.com |
| **Data Provided** | Stock prices, dividends, splits, financials, options, crypto, ETFs, mutual funds, news |
| **Coverage** | Global markets; daily/hourly/minute granularity; back to 1970s for US stocks |
| **Access** | yfinance Python library; also MCP `user-yfinance` |
| **Python Package** | `yfinance` |
| **API Key** | None required |
| **Rate Limits** | Respectful usage; cache data locally |
| **Best Strategy** | Use `yf.download()` for batch fetches; `Ticker.financials` for income statements; avoid per-ticker loops in bulk |

```python
import yfinance as yf
ticker = yf.Ticker("AAPL")
hist = ticker.history(period="5y")
financials = ticker.financials
```

### B2. Alpha Vantage
| Attribute | Details |
|---|---|
| **URL** | https://www.alphavantage.co |
| **Data Provided** | Intraday equity data, daily/weekly/monthly series, forex, crypto, sector performance, technical indicators, fundamental data |
| **Coverage** | US and global equities; forex; crypto |
| **Access** | REST API: https://www.alphavantage.co/query |
| **Python Package** | `alpha_vantage` |
| **API Key** | Required (free tier: 25 requests/day; premium tiers available) |
| **Rate Limits** | Free: 5 requests/minute, 500 requests/day |
| **Best Strategy** | Use for US equity fundamentals (income_statement, balance_sheet, cash_flow); supplement with yfinance for price data |

### B3. Tiingo
| Attribute | Details |
|---|---|
| **URL** | https://www.tiingo.com |
| **Data Provided** | End-of-day prices (US equities, ETFs, mutual funds), fundamentals, news, crypto |
| **Coverage** | US markets; back to 2007 |
| **Access** | REST API: https://api.tiingo.com |
| **Python Package** | `tiingo-python` |
| **API Key** | Required (free tier with daily limits; premium available) |
| **Rate Limits** | Free: 500 requests/day; 1 request/second |
| **Best Strategy** | Best for after-hours EOD data; combine with yfinance (which covers pre/after market) |

### B4. SEC EDGAR
| Attribute | Details |
|---|---|
| **URL** | https://www.sec.gov/cgi-bin/browse-edgar |
| **Data Provided** | 10-K (annual), 10-Q (quarterly), 8-K, DEF 14A (proxy), 13F (institutional holdings), Form 4 (insider), S-1 filings; XBRL financial statements |
| **Coverage** | 1994–present; all SEC registrants |
| **Access** | EFTS full-text search; XBRL structured data; bulk download |
| **Python Package** | `edgartools` (recommended), `sec-api` (paid), `python-edgar` |
| **API Key** | Not required for `edgartools` |
| **Rate Limits** | EFTS: be respectful; auto-handled by `edgartools` |
| **Best Strategy** | `edgartools` provides typed Python objects, XBRL parsing, and full-text search without any API key; set identity for EFTS |

```python
from edgartools import Company, search_filings
set_identity("Name email@example.com")
results = search_filings("revenue growth", forms=["10-K"])
company = Company("AAPL")
balance_sheet = company.get_financials().balance_sheet()
```

### B5. FINRA TRACE ⚠️
| Attribute | Details |
|---|---|
| **URL** | https://www.finra.org/awards/programs/trace |
| **Data Provided** | Corporate bond trade reports (price, yield, volume, trade time) |
| **Coverage** | US corporate bond market; 2002–present |
| **Access** | FINRA TRAQS Web API (authorized accounts only); WRDS (subscription) |
| **Python Package** | None official; `tidy-finance` (R) has Python guide; openbondassetpricing.com provides clean parquet files |
| **API Key** | Requires authorized TRAQS account |
| **Rate Limits** | API access controlled by TRAQS |
| **Best Strategy** | Academic access via WRDS (check institutional subscription); Open Bond Asset Pricing project provides cleaned TRACE data at openbondassetpricing.com |

### B6–B9. CRSP, Compustat, Refinitiv Eikon, Bloomberg
These are **institutional/subscription-only** datasets. Not suitable for individual academic researchers without university access:

| Dataset | Provider | Best Academic Access |
|---|---|---|
| CRSP (stock prices, delistings) | WRDS/Wharton | University subscription |
| Compustat (financial statements) | S&P Global | University subscription |
| Refinitiv Eikon | Refinitiv | Institutional license |
| Bloomberg Terminal | Bloomberg LP | Institutional license |

**Strategy:** Check your university's WRDS subscription — most major research universities have access to CRSP, Compustat, TRACE, and mutual fund data through Wharton Research Data Services.

---

## C. Alternative Data

### C1. Kaggle Datasets
| Attribute | Details |
|---|---|
| **URL** | https://www.kaggle.com/datasets |
| **Data Provided** | 100,000+ datasets covering finance, economics, ML, NLP, image, IoT — uploaded by community and organizations |
| **Coverage** | Varies by dataset |
| **Access** | Kaggle API (CLI + Python); direct download from browser |
| **Python Package** | `kagglehub` (recommended), `kaggle` (CLI) |
| **API Key** | Required (generate at https://www.kaggle.com/account → API → Create New Token) |
| **Rate Limits** | Dynamic; HTTP 429 on overuse |
| **Best Strategy** | Search for "stock", "financial", "economic" datasets; many finance competitions provide structured datasets; use `kagglehub` for ML workflow integration |

```python
import kagglehub
path = kagglehub.dataset_download("如愿")
```

### C2. US Government Open Data (data.gov)
| Attribute | Details |
|---|---|
| **URL** | https://data.gov |
| **Data Provided** | 358,000+ datasets from federal, state, local, tribal agencies; covers agriculture, climate, health, consumer, economy, education, energy, finance, etc. |
| **Coverage** | Varies by dataset |
| **Access** | Catalog API: https://catalog.data.gov/api/3/action/package_search |
| **Python Package** | `requests` (direct API) |
| **API Key** | None required |
| **Rate Limits** | No published limits |
| **Best Strategy** | Use Catalog API to discover relevant datasets; many provide direct download links (CSV, JSON, XML) |

```python
import requests
url = "https://catalog.data.gov/api/3/action/package_search"
params = {"q": "stock market", "rows": 10}
results = requests.get(url, params=params).json()
```

### C3. Federal Reserve Board Data
| Attribute | Details |
|---|---|
| **URL** | https://www.federalreserve.gov/data.htm |
| **Data Provided** | H.15 (interest rates), H.4.1 (reserve balances), H.6 (money stock), Z.1 (Flow of Funds), commercial paper, G.19 (consumer credit) |
| **Coverage** | Varies by series; most from 1910s–present |
| **Access** | Via FRED API (integrated with FRED); also direct download from Fed website |
| **Python Package** | Same as FRED (`fredapi`) |
| **API Key** | Same as FRED |
| **Rate Limits** | Same as FRED |
| **Best Strategy** | Many Fed Board series are in FRED database; search FRED by series ID (e.g., "M2SL" for M2 money stock) |

### C4. BIS Derivatives Statistics
| Attribute | Details |
|---|---|
| **URL** | https://data.bis.org/topics/OTC_DER |
| **Data Provided** | OTC derivatives: notional outstanding, market value, credit exposure; broken down by instrument (FX, IR, equity, commodity, credit), counterparty, location |
| **Coverage** | Semi-annual from 1998; Triennial from 1986; 12 core jurisdictions + 30+ additional |
| **Access** | SDMX API: https://stats.bis.org/api/v1 |
| **Python Package** | `sdmx`, `sdmxthon` |
| **API Key** | None required |
| **Rate Limits** | No published limits |
| **Best Strategy** | Use same SDMX pattern as BIS; key dataflows: `BIS_DER` for main derivatives; filter by `type_not` for notional, `type_mv` for market value |

### C5. USDA Data
| Attribute | Details |
|---|---|
| **URL** | https://www.ers.usda.gov/developer |
| **Data Provided** | Agricultural prices, farm income, food availability, trade, ARMS (Agricultural Resource Management Survey) |
| **Coverage** | US agriculture; varying historical depth |
| **Access** | REST API: https://api.ers.usda.gov/data/; GraphQL endpoint; bulk download |
| **Python Package** | `requests` (direct API) |
| **API Key** | Required from https://api.data.gov (free registration) |
| **Rate Limits** | Per api.data.gov policy |
| **Best Strategy** | ARMS data covers farm financial performance; combine with macro data for agricultural economics research |

```python
import requests
response = requests.get(
    'https://api.ers.usda.gov/data/arms/variable',
    params={'api_key': 'YOUR_API_KEY'}
)
```

### C6. USPTO Patent Data
| Attribute | Details |
|---|---|
| **URL** | https://data.uspto.gov |
| **Data Provided** | Patent applications, grants, patent trial data (PTAB), citations, inventor information, technology classifications |
| **Coverage** | 1790–present; millions of patents |
| **Access** | Bulk Data API: https://api.uspto.gov; Patent Data API |
| **Python Package** | `pyUSPTO` (recommended) |
| **API Key** | Required (free at https://data.uspto.gov/myodp/landing); USPTO.gov account required from June 2026 |
| **Rate Limits** | Per API terms |
| **Best Strategy** | Use `pyUSPTO` for bulk downloads; good for innovation/patent analysis in finance (green patents, fintech patents, etc.) |

```python
from pyUSPTO import BulkDataClient, USPTOConfig
config = USPTOConfig(api_key="YOUR_API_KEY")
client = BulkDataClient(config=config)
product = client.get_product_by_id("PATGRXML", include_files=True, latest=True)
```

---

## D. Academic / Research Data

### D1. NBER Working Papers ✅
| Attribute | Details |
|---|---|
| **URL** | https://www.nber.org/papers |
| **Data Provided** | NBER working papers (13 research programs: Economic Fluctuations & Growth, Labor Studies, Monetary Economics, Corporate Finance, etc.) with abstracts |
| **Coverage** | 1973–present; 40,000+ papers |
| **Access** | MCP `user-nber-wp` already integrated; web download |
| **Python Package** | MCP available; `nber` (PyPI) |
| **API Key** | None required |
| **Rate Limits** | None published |
| **Best Strategy** | Use MCP for paper search and metadata; combine with Semantic Scholar for full-text access |

### D2. ICPSR (Inter-university Consortium for Political and Social Research)
| Attribute | Details |
|---|---|
| **URL** | https://www.icpsr.umich.edu |
| **Data Provided** | 350,000+ files: political behavior, health, criminal justice, education, substance abuse, aging, terrorism research |
| **Coverage** | 1960s–present |
| **Access** | Web download (MyData account); direct download for public-use files |
| **Python Package** | None (direct download) |
| **API Key** | Free MyData account required for all downloads |
| **Rate Limits** | None |
| **Best Strategy** | Create free MyData account (supports Google/Facebook/ORCID login); most public-use data is freely downloadable; restricted data requires formal application |

### D3. Harvard Dataverse
| Attribute | Details |
|---|---|
| **URL** | https://dataverse.harvard.edu |
| **Data Provided** | Research data across all disciplines; thousands of datasets from researchers worldwide |
| **Coverage** | Varies by dataset |
| **Access** | Dataverse API (REST); direct download |
| **Python Package** | `pyDataverse`, `easyDataverse` |
| **API Key** | Required only for uploading; public datasets need no key |
| **Rate Limits** | None for public downloads |
| **Best Strategy** | Use `easyDataverse` for dataset fetch by DOI; many economics/finance datasets available; check for CC-BY license compliance |

```python
from pyDataverse.api import NativeApi, DataAccessApi
base_url = 'https://dataverse.harvard.edu/'
api = NativeApi(base_url)
data_api = DataAccessApi(base_url)
dataset = api.get_dataset("doi:10.7910/DVN/KBHLOD")
```

### D4. SSRN ⚠️
| Attribute | Details |
|---|---|
| **URL** | https://www.ssrn.com |
| **Data Provided** | Pre-prints and early research in economics, finance, law, business |
| **Coverage** | 1994–present |
| **Access** | No official public API; website access with login |
| **Python Package** | None recommended |
| **API Key** | N/A |
| **Rate Limits** | Active bot detection; HTTP 403 on scraping attempts |
| **Best Strategy** | **Do not scrape** — active bot detection causes IP blocks; use alternatives: (1) arXiv for CS/ML papers, (2) Semantic Scholar for paper discovery, (3) NBER for economics, (4) paper-search-mcp for discovery then manual download |

### D5. RePEc (Research Papers in Economics)
| Attribute | Details |
|---|---|
| **URL** | https://ideas.repec.org |
| **Data Provided** | Working papers, journal articles, books, software from economics departments worldwide; author rankings, institution rankings, JEL codes |
| **Coverage** | 1990s–present; 3 million+ items |
| **Access** | API available by application; FTP download for full database |
| **Python Package** | `econpapers` (simple journal metadata), `repec` (GitHub scripts for full DB) |
| **API Key** | Requires email application to Christian Zimmermann (ideas.repec.org/api.html) |
| **Rate Limits** | API not open; courtesy access only |
| **Best Strategy** | `econpapers` package provides quick journal paper metadata without API key; for full database, use the FTP-based approach via `repec` GitHub scripts |

```python
import econpapers as econ
df = econ.papers_dataframe(["Econometrica", "Quarterly Journal of Economics"])
```

### D6. Semantic Scholar (Bonus)
| Attribute | Details |
|---|---|
| **URL** | https://api.semanticscholar.org |
| **Data Provided** | 200M+ academic papers, citations, author profiles, paper recommendations, SPECTER2 embeddings |
| **Coverage** | All fields; major CS, economics, finance coverage |
| **Access** | REST API: https://api.semanticscholar.org/graph/v1 |
| **Python Package** | `papermage`, `paper-search-mcp` |
| **API Key** | Optional (free; higher rate limits with key) |
| **Rate Limits** | 100 req/s unauthenticated; authenticated: higher |
| **Best Strategy** | Best academic paper discovery tool; use for citation graph analysis, finding related papers, bulk metadata; combine with arXiv MCP for open-access full text |

```python
import requests
headers = {"x-api-key": "YOUR_KEY"}  # optional
url = "https://api.semanticscholar.org/graph/v1/paper/search?query=fintech&limit=10"
papers = requests.get(url, headers=headers).json()
```

---

## Summary: Quick Reference Table

| Source | Category | Cost | API Key | Python Package | Best For |
|---|---|---|---|---|---|
| FRED | Macro | Free | ✅ | fredapi | US macro, monetary |
| World Bank | Macro | Free | ❌ | wbgapi | Global development |
| IMF | Macro | Free | ❌ | imfpy | BoP, WEO forecasts |
| OECD | Macro | Free | ❌ | OECD | Developed economies |
| UN Comtrade | Macro | Free tier | ✅ | comtradeapicall | Trade flows |
| BIS | Macro | Free | ❌ | sdmx | Derivatives, banking |
| ECB | Macro | Free | ❌ | ecbdata | Euro area |
| UK ONS | Macro | Free | ❌ | pyONS | UK economy |
| China NBS | Macro | Free | ❌ | akshare, cn-stats | China economy |
| Penn World Table | Macro | Free | ❌ | PWTLoader | PPP, productivity |
| Maddison MPD | Macro | Free | ❌ | — (CSV) | Historical GDP |
| Yahoo Finance | Market | Free | ❌ | yfinance | Prices, fundamentals |
| SEC EDGAR | Market | Free | ❌ | edgartools | Filings, XBRL |
| Tiingo | Market | Free tier | ✅ | tiingo-python | EOD data |
| Kaggle | Alt | Free | ✅ | kagglehub | ML datasets |
| data.gov | Alt | Free | ❌ | requests | US govt data |
| USDA ERS | Alt | Free | ✅ | requests | Agriculture |
| USPTO | Alt | Free | ✅ | pyUSPTO | Patents |
| ICPSR | Academic | Free* | ✅ (account) | — | Social science data |
| Harvard Dataverse | Academic | Free | ❌* | pyDataverse | Research datasets |
| RePEc | Academic | Free | ⚠️ | econpapers | Economics papers |
| NBER | Academic | Free | ❌ | MCP / nber | Economics WPs |
| Semantic Scholar | Academic | Free | Optional | — | Paper discovery |

---

## Research Strategy by Data Type

### For Cross-Country Macro Analysis
1. **Penn World Table** → PPP GDP, TFP, capital stock
2. **Maddison Project** → Historical GDP per capita
3. **World Bank** → Development indicators
4. **UN Comtrade** → Trade openness
5. **BIS** → Cross-border banking flows

### For Corporate Finance Research
1. **SEC EDGAR (edgartools)** → 10-K/10-Q, XBRL financials
2. **WRDS** → CRSP + Compustat (institutional access)
3. **Federal Reserve** → Z.1 Flow of Funds
4. **SEC EDGAR** → 13F institutional holdings, Form 4 insider trades

### For Market Microstructure
1. **FINRA TRACE** → Corporate bond trades (via WRDS or institutional)
2. **CRSP** → Daily stock returns, bid-ask spreads (via WRDS)
3. **FRED** → VIX, market volatility indicators

### For Innovation & Patents
1. **USPTO** → Patent grants, citations, technology classes
2. **NBER** → Patent databases (NBER Tech Transfer)
3. **Semantic Scholar** → Paper discovery and citation analysis

### For Macro-Finance
1. **FRED** → Interest rates, monetary aggregates
2. **ECB / BIS** → International monetary data
3. **China NBS (akshare)** → Chinese macro data
4. **OECD** → Leading indicators, productivity

---

## Data Source Discovery Workflow

```
1. Identify needed variables
       ↓
2. Check MCP servers first (no extra setup)
       ↓
3. Free API sources (no key needed)
       ↓
4. Free API sources (key required)
       ↓
5. Direct download (Excel/CSV)
       ↓
6. Institutional subscriptions (WRDS, Bloomberg)
```

**Golden Rule:** Always cite data sources with version date and access URL in academic work. For simulation/validation, note data vintage.

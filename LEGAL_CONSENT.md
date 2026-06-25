# Legal Risk MCP Servers — User Consent Framework

> **Status**: These servers are **disabled by default** for all users (including `full` profile).
> You must explicitly opt-in to use them. The project maintainer is not liable
> for how you use them.

---

## What This Means

The following MCP servers scrape websites that prohibit automated access in their
Terms of Service (TOS):

| Server | Data Source | TOS Prohibition |
|--------|------------|----------------|
| `user-cnki` | cnki.net | ❌ Prohibits automated scraping |
| `user-wanfang` | wanfangdata.com.cn | ❌ Prohibits automated scraping |
| `user-chinese-literature` | baidu.com/xueshu | ❌ Prohibits automated scraping |

Using these servers without understanding the legal implications may expose you
to civil or criminal liability under:
- China's **网络安全法 (Cybersecurity Law)**
- China's **数据安全法 (Data Security Law)**
- CNKI/Wanfang's **specific Terms of Service**

The project maintainer is **not a law firm**. This document is not legal advice.

---

## How to Enable (Opt-In Only)

### Option 1: Environment Variable

```bash
# Enable specific servers
export CLI_ACCEPT_RISK=cnki,wanfang,chinese-literature

# Or in .env.local (NEVER commit this file):
CLI_ACCEPT_RISK=cnki,wanfang,chinese-literature

# Or enable ALL legal-risk servers (explicit, not default):
export CLI_ACCEPT_RISK=ALL
```

### Option 2: One-Time Setup Wizard

```bash
python scripts/setup_wizard.py --guided
# When prompted about legal-risk servers, choose "Enable with warning" or "Keep disabled"
```

---

## Verification

After enabling, verify your consent is registered:

```bash
python scripts/check_legal_consent.py --list     # see which servers need consent
python scripts/check_legal_consent.py --check cnki  # check specific server
python scripts/check_legal_consent.py --enforce    # hard stop without consent
```

---

## Risk Assessment by Use Case

| Use Case | Recommended Servers | Notes |
|----------|--------------------|-------|
| **Published research** | OpenAlex, ArXiv, NBER | No legal risk; cite via DOI |
| **Course assignments** | OpenAlex, ArXiv | No legal risk |
| **Internal working papers** | OpenAlex, NBER | No legal risk |
| **Published journal submission** | ❌ CNKI/Wanfang爬虫 | ⚠️ Legal risk; use institutional access instead |
| **Commercial use** | ❌ All three | ⚠️ High risk; contact CNKI/Wanfang for commercial API |

**Bottom line**: If your work will be published or used commercially,
apply for institutional access to CNKI/Wanfang through your university or employer.
Do not rely on these scrapers.

---

## Legal Alternatives

| What you need | Free & Legal alternative |
|---------------|--------------------------|
| Chinese economics papers | OpenAlex (indexes many Chinese journals) |
| Chinese finance research | NBER + working paper repositories |
| CSSCI coverage | OpenAlex + institutional library access |
| Paper full-text | ArXiv, RePEc, institutional repositories |
| Citation data | OpenAlex (free, comprehensive) |

---

## If You Still Want to Use These Servers

1. Read the relevant TOS:
   - [CNKI Terms](https://kns.cnki.net/kns8/DefaultResult/Index?dbcode=SCDB)
   - [Wanfang Terms](https://www.wanfangdata.com.cn/index.do)
   - [Baidu Scholar Terms](https://xueshu.baidu.com/)

2. Consult your institution's legal counsel if you are affiliated with a university or company

3. Set `CLI_ACCEPT_RISK` as documented above

4. Use with extreme caution:
   - Add request delays (≥3 seconds between calls)
   - Cache results locally to minimize repeated scraping
   - Do NOT redistribute scraped data
   - Do NOT use for commercial purposes

---

## Default Behavior

- **`minimal` profile**: These servers are NOT included ✅
- **`academic` profile**: These servers are NOT included ✅
- **`quant` profile**: These servers are NOT included ✅
- **`full` profile**: These servers are **excluded by default** and require `CLI_ACCEPT_RISK` to activate ⚠️

Even with `CLI_ACCEPT_RISK=ALL`, these servers will only load after a
warning is printed. There is no silent opt-in.

---

## Project Maintainer's Position

The maintainer provides these servers as-is for users who:
1. Understand the legal risks
2. Take personal responsibility for their use
3. Have consulted appropriate legal counsel if needed

The maintainer does **not** encourage, recommend, or endorse using these servers
in published research. Use institutional access instead.

---

*Last updated: 2026-06-25*

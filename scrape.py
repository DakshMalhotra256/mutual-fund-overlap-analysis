"""Scrape portfolio holdings for 45 Indian equity mutual funds from Moneycontrol.

This script produced the snapshot committed under data/ in Feb/Mar 2026:

    data/mutual_fund_holdings.csv    3,421 holdings across 45 funds
    data/mutual_fund_overlap.db      the same rows as a SQLite `holdings` table

Moneycontrol has since changed its portfolio-holdings URLs, so running this against the
live site now fails. It is kept as the record of how the dataset was acquired. The
analysis in analysis/ reads the committed snapshot and never touches the network, so it
stays reproducible regardless.

Freezing the data is deliberate rather than unfortunate: fund holdings change every month,
and a fixed snapshot is what keeps the notebooks, the dashboard and the README consistent
with one another.

Fund URLs are read from data/funds_list.json.

    python scrape.py
"""

import json
import sqlite3
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent / "data"
FUNDS_JSON = DATA_DIR / "funds_list.json"
HOLDINGS_CSV = DATA_DIR / "mutual_fund_holdings.csv"
OVERLAP_DB = DATA_DIR / "mutual_fund_overlap.db"

REQUEST_DELAY_SECONDS = 2


def scrape_fund_holdings(fund_name, url):
    """Scrape stock holdings for a mutual fund from Moneycontrol"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch {fund_name}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', {'id': 'equityCompleteHoldingTable'})

    if not table:
        print(f"No holdings table found for {fund_name}")
        return []

    rows = table.find('tbody').find_all('tr')
    holdings = []

    for row in rows:
        # Moneycontrol keeps exited holdings in the same table, hidden with inline CSS.
        # Including them does not raise anything - it just quietly corrupts every
        # overlap number downstream.
        if row.get('style') == 'display: none;':
            continue

        cols = row.find_all('td')
        if len(cols) >= 11:
            stock_name = cols[0].text.strip()
            # Clean stock name - remove leading symbols and newlines. Left in, the
            # markers split one stock into several keys and break every GROUP BY.
            stock_name = stock_name.replace('\n', ' ').lstrip('-# ').strip()
            if len(stock_name) > 2:
                holdings.append({
                    'fund_name': fund_name,
                    'stock_name': stock_name,
                    'sector': cols[1].text.strip(),
                    'holding_pct': cols[4].text.strip().replace('%', ''),
                    'market_cap': cols[10].text.strip()
                })

    print(f"{fund_name}: {len(holdings)} stocks found")
    return holdings


def main():
    with open(FUNDS_JSON, encoding="utf-8") as f:
        funds = json.load(f)

    all_holdings = []
    failed = []

    for fund_name, url in funds.items():
        holdings = scrape_fund_holdings(fund_name, url)
        if holdings:
            all_holdings.extend(holdings)
        else:
            failed.append(fund_name)
        # Polite scraping - 2 second gap between requests so we don't overload Moneycontrol
        time.sleep(REQUEST_DELAY_SECONDS)

    if not all_holdings:
        print("\nNo holdings scraped. The Moneycontrol URLs in funds_list.json are stale.")
        return

    df = pd.DataFrame(all_holdings)
    df['holding_pct'] = pd.to_numeric(df['holding_pct'], errors='coerce')

    # Clean text columns so they survive a round trip through CSV
    for col in ['stock_name', 'sector', 'market_cap']:
        df[col] = (df[col].str.replace(',', ' ')
                          .str.replace('"', '')
                          .str.replace('\n', ' ')
                          .str.strip())

    df.to_csv(HOLDINGS_CSV, index=False, encoding='utf-8-sig')

    conn = sqlite3.connect(OVERLAP_DB)
    df.to_sql('holdings', conn, if_exists='replace', index=False)
    conn.close()

    print(f"\n{len(funds) - len(failed)}/{len(funds)} funds scraped, {len(df)} holdings, "
          f"{df['stock_name'].nunique()} unique stocks")
    print(f"  wrote {HOLDINGS_CSV}")
    print(f"  wrote {OVERLAP_DB}")
    if failed:
        print(f"  failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()

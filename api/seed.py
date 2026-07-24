import csv
import sys
import os

API_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(API_DIR)

# Holdings CSV lives in the repo-level data/ folder, shared with the analysis notebooks
HOLDINGS_CSV = os.path.join(os.path.dirname(API_DIR), "data", "mutual_fund_holdings.csv")

from app.database import SessionLocal, engine
from app.models import Base, Fund, Holding

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Clear old data if re-running
    db.query(Holding).delete()
    db.query(Fund).delete()
    db.commit()

    # Track funds we've already added
    fund_map = {}

    with open(HOLDINGS_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fund_name = row["fund_name"].strip()

            # Add fund if not already added
            if fund_name not in fund_map:
                # Figure out category from fund name
                name_lower = fund_name.lower()
                if "index" in name_lower or "nifty" in name_lower or "sensex" in name_lower:
                    category = "Index"
                elif "small cap" in name_lower or "smallcap" in name_lower:
                    category = "Small Cap"
                elif "mid cap" in name_lower or "midcap" in name_lower:
                    category = "Mid Cap"
                elif "large cap" in name_lower or "largecap" in name_lower:
                    category = "Large Cap"
                elif "flexi" in name_lower or "flexicap" in name_lower or "multicap" in name_lower or "multi cap" in name_lower:
                    category = "Flexi Cap"
                else:
                    category = "Other"

                fund = Fund(fund_name=fund_name, category=category)
                db.add(fund)
                db.flush()  # Gets the fund_id without committing
                fund_map[fund_name] = fund.fund_id

            # Add holding
            holding = Holding(
                fund_id=fund_map[fund_name],
                stock_name=row["stock_name"].strip(),
                sector=row["sector"].strip(),
                holding_pct=float(row["holding_pct"]),
                market_cap=row["market_cap"].strip()
            )
            db.add(holding)

    db.commit()
    db.close()

    print(f"Seeded {len(fund_map)} funds and their holdings!")

if __name__ == "__main__":
    seed()
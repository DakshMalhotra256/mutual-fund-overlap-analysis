from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from app.database import get_db
from app.models import Fund, Holding

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])

@router.get("/overlap")
def get_overlap(
    fund1_id: int,
    fund2_id: int,
    db: Session = Depends(get_db)
):
    # Get holdings for both funds
    holdings1 = db.query(Holding).filter(Holding.fund_id == fund1_id).all()
    holdings2 = db.query(Holding).filter(Holding.fund_id == fund2_id).all()

    # Get fund names
    f1 = db.query(Fund).filter(Fund.fund_id == fund1_id).first()
    f2 = db.query(Fund).filter(Fund.fund_id == fund2_id).first()

    if not f1 or not f2:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Fund not found")

    # Build stock maps: stock_name -> holding_pct
    map1 = {h.stock_name: h.holding_pct for h in holdings1}
    map2 = {h.stock_name: h.holding_pct for h in holdings2}

    # Find common stocks and calculate overlap
    common_stocks = set(map1.keys()) & set(map2.keys())
    overlap_pct = sum(min(map1[s], map2[s]) for s in common_stocks)

    common_details = [
        {
            "stock_name": s,
            "fund1_pct": map1[s],
            "fund2_pct": map2[s]
        }
        for s in sorted(common_stocks, key=lambda x: min(map1[x], map2[x]), reverse=True)
    ]

    return {
        "fund1": f1.fund_name,
        "fund2": f2.fund_name,
        "overlap_pct": round(overlap_pct, 2),
        "common_stocks_count": len(common_stocks),
        "total_stocks_fund1": len(map1),
        "total_stocks_fund2": len(map2),
        "common_stocks": common_details
    }

@router.get("/most-held-stocks")
def most_held_stocks(
    top_n: int = Query(default=10, le=50),
    db: Session = Depends(get_db)
):
    results = (
        db.query(
            Holding.stock_name,
            func.count(func.distinct(Holding.fund_id)).label("fund_count"),
            func.round(func.avg(Holding.holding_pct), 2).label("avg_holding_pct")
        )
        .group_by(Holding.stock_name)
        .order_by(func.count(func.distinct(Holding.fund_id)).desc())
        .limit(top_n)
        .all()
    )

    return [
        {
            "stock_name": r.stock_name,
            "held_by_funds": r.fund_count,
            "avg_holding_pct": float(r.avg_holding_pct)
        }
        for r in results
    ]

@router.get("/sectors")
def sector_analysis(db: Session = Depends(get_db)):
    results = (
        db.query(
            Holding.sector,
            func.count(func.distinct(Holding.fund_id)).label("fund_count"),
            func.count(Holding.holding_id).label("total_holdings"),
            func.round(func.avg(Holding.holding_pct), 2).label("avg_holding_pct")
        )
        .group_by(Holding.sector)
        .order_by(func.count(Holding.holding_id).desc())
        .all()
    )

    return [
        {
            "sector": r.sector,
            "funds_invested": r.fund_count,
            "total_holdings": r.total_holdings,
            "avg_holding_pct": float(r.avg_holding_pct)
        }
        for r in results
    ]
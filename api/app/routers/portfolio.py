from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.database import get_db
from app.models import Fund, Holding, User, SavedPortfolio, PortfolioFund
from app.auth import get_current_user

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

class PortfolioRequest(BaseModel):
    fund_ids: List[int]

@router.post("/xray")
def portfolio_xray(req: PortfolioRequest, db: Session = Depends(get_db)):
    if len(req.fund_ids) < 2:
        raise HTTPException(status_code=400, detail="Send at least 2 fund IDs")

    funds = db.query(Fund).filter(Fund.fund_id.in_(req.fund_ids)).all()
    if len(funds) != len(req.fund_ids):
        raise HTTPException(status_code=404, detail="One or more funds not found")

    # Get all holdings for these funds
    all_holdings = db.query(Holding).filter(Holding.fund_id.in_(req.fund_ids)).all()

    # Stock exposure across portfolio
    stock_exposure = {}
    sector_exposure = {}
    market_cap_breakdown = {}

    for h in all_holdings:
        # Average holding across funds
        weight = h.holding_pct / len(req.fund_ids)

        # Stock exposure
        if h.stock_name not in stock_exposure:
            stock_exposure[h.stock_name] = {"total_weight": 0, "fund_count": 0, "sector": h.sector}
        stock_exposure[h.stock_name]["total_weight"] += weight
        stock_exposure[h.stock_name]["fund_count"] += 1

        # Sector exposure
        if h.sector not in sector_exposure:
            sector_exposure[h.sector] = 0
        sector_exposure[h.sector] += weight

        # Market cap breakdown
        if h.market_cap not in market_cap_breakdown:
            market_cap_breakdown[h.market_cap] = 0
        market_cap_breakdown[h.market_cap] += weight

    # Find duplicate holdings (stocks in more than 1 fund)
    duplicates = {k: v for k, v in stock_exposure.items() if v["fund_count"] > 1}

    # Sort by weight
    top_stocks = sorted(stock_exposure.items(), key=lambda x: x[1]["total_weight"], reverse=True)[:15]
    top_sectors = sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "funds_analyzed": [f.fund_name for f in funds],
        "total_unique_stocks": len(stock_exposure),
        "duplicate_stocks": len(duplicates),
        "top_holdings": [
            {
                "stock_name": name,
                "total_weight": round(data["total_weight"], 2),
                "found_in_funds": data["fund_count"],
                "sector": data["sector"]
            }
            for name, data in top_stocks
        ],
        "sector_exposure": [
            {"sector": s, "weight": round(w, 2)}
            for s, w in top_sectors
        ],
        "market_cap_breakdown": {k: round(v, 2) for k, v in market_cap_breakdown.items()},
        "duplicate_holdings": [
            {
                "stock_name": name,
                "found_in_funds": data["fund_count"],
                "total_weight": round(data["total_weight"], 2)
            }
            for name, data in sorted(duplicates.items(), key=lambda x: x[1]["fund_count"], reverse=True)[:10]
        ]
    }

@router.post("/score")
def portfolio_score(req: PortfolioRequest, db: Session = Depends(get_db)):
    if len(req.fund_ids) < 2:
        raise HTTPException(status_code=400, detail="Send at least 2 fund IDs")

    funds = db.query(Fund).filter(Fund.fund_id.in_(req.fund_ids)).all()
    if len(funds) != len(req.fund_ids):
        raise HTTPException(status_code=404, detail="One or more funds not found")

    all_holdings = db.query(Holding).filter(Holding.fund_id.in_(req.fund_ids)).all()

    # Build per-fund stock maps
    fund_holdings = {}
    for h in all_holdings:
        if h.fund_id not in fund_holdings:
            fund_holdings[h.fund_id] = {}
        fund_holdings[h.fund_id][h.stock_name] = h.holding_pct

    # 1. Overlap penalty (0-30 points lost)
    overlaps = []
    fund_id_list = list(fund_holdings.keys())
    for i in range(len(fund_id_list)):
        for j in range(i + 1, len(fund_id_list)):
            map1 = fund_holdings[fund_id_list[i]]
            map2 = fund_holdings[fund_id_list[j]]
            common = set(map1.keys()) & set(map2.keys())
            overlap = sum(min(map1[s], map2[s]) for s in common)
            overlaps.append(overlap)

    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
    overlap_penalty = min(30, avg_overlap * 0.6)

    # 2. Concentration penalty (0-25 points lost)
    stock_exposure = {}
    for h in all_holdings:
        weight = h.holding_pct / len(req.fund_ids)
        if h.stock_name not in stock_exposure:
            stock_exposure[h.stock_name] = 0
        stock_exposure[h.stock_name] += weight

    top5_weight = sum(sorted(stock_exposure.values(), reverse=True)[:5])
    concentration_penalty = min(25, top5_weight * 0.5)

    # 3. Sector concentration penalty (0-25 points lost)
    sector_exposure = {}
    for h in all_holdings:
        weight = h.holding_pct / len(req.fund_ids)
        if h.sector not in sector_exposure:
            sector_exposure[h.sector] = 0
        sector_exposure[h.sector] += weight

    top_sector_weight = max(sector_exposure.values()) if sector_exposure else 0
    sector_penalty = min(25, top_sector_weight * 0.8)

    # 4. Category diversity bonus (0-20 points)
    categories = set(f.category for f in funds)
    category_bonus = min(20, len(categories) * 7)

    # Final score
    score = max(0, min(100, 100 - overlap_penalty - concentration_penalty - sector_penalty + category_bonus))

    return {
        "funds_analyzed": [f.fund_name for f in funds],
        "diversification_score": round(score, 1),
        "max_score": 100,
        "breakdown": {
            "overlap_penalty": round(overlap_penalty, 1),
            "concentration_penalty": round(concentration_penalty, 1),
            "sector_penalty": round(sector_penalty, 1),
            "category_bonus": round(category_bonus, 1)
        },
        "insights": {
            "avg_pairwise_overlap": round(avg_overlap, 2),
            "top5_stock_weight": round(top5_weight, 2),
            "top_sector": max(sector_exposure, key=sector_exposure.get) if sector_exposure else "N/A",
            "top_sector_weight": round(top_sector_weight, 2),
            "categories_covered": list(categories)
        }
    }
    
@router.post("/smart-switch")
def smart_switch(req: PortfolioRequest, db: Session = Depends(get_db)):
    if len(req.fund_ids) < 2:
        raise HTTPException(status_code=400, detail="Send at least 2 fund IDs")

    funds = db.query(Fund).filter(Fund.fund_id.in_(req.fund_ids)).all()
    if len(funds) != len(req.fund_ids):
        raise HTTPException(status_code=404, detail="One or more funds not found")

    all_holdings = db.query(Holding).filter(Holding.fund_id.in_(req.fund_ids)).all()

    # Build per-fund stock maps
    fund_holdings = {}
    for h in all_holdings:
        if h.fund_id not in fund_holdings:
            fund_holdings[h.fund_id] = {}
        fund_holdings[h.fund_id][h.stock_name] = h.holding_pct

    # Calculate overlap each fund has with the rest
    fund_overlap_scores = {}
    fund_id_list = list(fund_holdings.keys())

    for fid in fund_id_list:
        others = [f for f in fund_id_list if f != fid]
        total_overlap = 0
        for other_fid in others:
            common = set(fund_holdings[fid].keys()) & set(fund_holdings[other_fid].keys())
            total_overlap += sum(min(fund_holdings[fid][s], fund_holdings[other_fid][s]) for s in common)
        fund_overlap_scores[fid] = total_overlap / len(others) if others else 0

    # Find the worst fund (highest overlap with others)
    worst_fund_id = max(fund_overlap_scores, key=fund_overlap_scores.get)
    worst_fund = db.query(Fund).filter(Fund.fund_id == worst_fund_id).first()

    # Find replacement candidates (different category, not already in portfolio)
    current_categories = set(f.category for f in funds)
    remaining_fund_ids = [fid for fid in req.fund_ids if fid != worst_fund_id]

    # Get all funds not in portfolio
    all_funds = db.query(Fund).filter(Fund.fund_id.notin_(req.fund_ids)).all()

    # Score each candidate
    candidates = []
    for candidate in all_funds:
        candidate_holdings = db.query(Holding).filter(Holding.fund_id == candidate.fund_id).all()
        cand_map = {h.stock_name: h.holding_pct for h in candidate_holdings}

        # Calculate overlap with remaining funds
        total_overlap = 0
        for rem_id in remaining_fund_ids:
            common = set(cand_map.keys()) & set(fund_holdings[rem_id].keys())
            total_overlap += sum(min(cand_map[s], fund_holdings[rem_id][s]) for s in common)

        avg_overlap = total_overlap / len(remaining_fund_ids) if remaining_fund_ids else 0
        new_category = candidate.category not in current_categories

        candidates.append({
            "fund_id": candidate.fund_id,
            "fund_name": candidate.fund_name,
            "category": candidate.category,
            "avg_overlap_with_remaining": round(avg_overlap, 2),
            "adds_new_category": new_category
        })

    # Sort: prefer new categories first, then lowest overlap
    candidates.sort(key=lambda x: (-x["adds_new_category"], x["avg_overlap_with_remaining"]))

    return {
        "current_portfolio": [f.fund_name for f in funds],
        "weakest_fund": {
            "fund_name": worst_fund.fund_name,
            "reason": f"Highest average overlap ({round(fund_overlap_scores[worst_fund_id], 2)}%) with other funds in portfolio"
        },
        "top_replacements": candidates[:5]
    }

@router.post("/recommend")
def recommend_funds(
    risk_level: str,
    monthly_amount: int = 5000,
    db: Session = Depends(get_db)
):
    risk_level = risk_level.lower()
    if risk_level not in ["low", "medium", "high"]:
        raise HTTPException(status_code=400, detail="risk_level must be low, medium, or high")

    # Define allocation strategy based on risk
    if risk_level == "low":
        allocation = {"Large Cap": 60, "Mid Cap": 20, "Index": 20}
    elif risk_level == "medium":
        allocation = {"Large Cap": 30, "Flexi Cap": 30, "Mid Cap": 25, "Small Cap": 15}
    else:
        allocation = {"Mid Cap": 30, "Small Cap": 35, "Flexi Cap": 25, "Large Cap": 10}

    recommendations = []

    for category, pct in allocation.items():
        # Get all funds in this category
        category_funds = db.query(Fund).filter(Fund.category == category).all()

        if not category_funds:
            continue

        # Pick the fund with the most holdings (proxy for well-diversified)
        best_fund = None
        max_holdings = 0
        for f in category_funds:
            count = db.query(Holding).filter(Holding.fund_id == f.fund_id).count()
            if count > max_holdings:
                max_holdings = count
                best_fund = f

        if best_fund:
            amount = int(monthly_amount * pct / 100)
            recommendations.append({
                "fund_name": best_fund.fund_name,
                "category": category,
                "allocation_pct": pct,
                "monthly_amount": amount,
                "holdings_count": max_holdings
            })

    return {
        "risk_level": risk_level,
        "monthly_investment": monthly_amount,
        "strategy": allocation,
        "recommended_funds": recommendations
    }
class SavePortfolioRequest(BaseModel):
    name: str
    fund_ids: List[int]

@router.post("/save")
def save_portfolio(
    req: SavePortfolioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify all funds exist
    funds = db.query(Fund).filter(Fund.fund_id.in_(req.fund_ids)).all()
    if len(funds) != len(req.fund_ids):
        raise HTTPException(status_code=404, detail="One or more funds not found")

    # Create portfolio
    portfolio = SavedPortfolio(user_id=current_user.user_id, name=req.name)
    db.add(portfolio)
    db.flush()

    # Link funds
    for fid in req.fund_ids:
        pf = PortfolioFund(portfolio_id=portfolio.portfolio_id, fund_id=fid)
        db.add(pf)

    db.commit()
    db.refresh(portfolio)

    return {
        "message": "Portfolio saved",
        "portfolio_id": portfolio.portfolio_id,
        "name": portfolio.name,
        "funds": [f.fund_name for f in funds]
    }

@router.get("/my")
def get_my_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    portfolios = db.query(SavedPortfolio).filter(SavedPortfolio.user_id == current_user.user_id).all()

    result = []
    for p in portfolios:
        portfolio_funds = db.query(PortfolioFund).filter(PortfolioFund.portfolio_id == p.portfolio_id).all()
        fund_ids = [pf.fund_id for pf in portfolio_funds]
        funds = db.query(Fund).filter(Fund.fund_id.in_(fund_ids)).all()

        result.append({
            "portfolio_id": p.portfolio_id,
            "name": p.name,
            "created_at": p.created_at,
            "funds": [{"fund_id": f.fund_id, "fund_name": f.fund_name, "category": f.category} for f in funds]
        })

    return result

@router.delete("/{portfolio_id}")
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    portfolio = db.query(SavedPortfolio).filter(
        SavedPortfolio.portfolio_id == portfolio_id,
        SavedPortfolio.user_id == current_user.user_id
    ).first()

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Delete linked funds first
    db.query(PortfolioFund).filter(PortfolioFund.portfolio_id == portfolio_id).delete()
    db.delete(portfolio)
    db.commit()

    return {"message": "Portfolio deleted"}
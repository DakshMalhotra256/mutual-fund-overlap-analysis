from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import get_db
from app.models import Fund, Holding
from app.schemas import FundOut, FundDetail

router = APIRouter(prefix="/api/funds", tags=["Funds"])

@router.get("/", response_model=List[FundOut])
def get_funds(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Fund)

    if category:
        query = query.filter(Fund.category == category)
    if search:
        query = query.filter(Fund.fund_name.ilike(f"%{search}%"))

    return query.all()

@router.get("/{fund_id}", response_model=FundDetail)
def get_fund(fund_id: int, db: Session = Depends(get_db)):
    fund = db.query(Fund).filter(Fund.fund_id == fund_id).first()
    if not fund:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund
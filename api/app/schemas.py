from pydantic import BaseModel
from typing import List, Optional

class HoldingOut(BaseModel):
    holding_id: int
    stock_name: str
    sector: str
    holding_pct: float
    market_cap: str

    class Config:
        from_attributes = True

class FundOut(BaseModel):
    fund_id: int
    fund_name: str
    category: str

    class Config:
        from_attributes = True

class FundDetail(FundOut):
    holdings: List[HoldingOut] = []

    class Config:
        from_attributes = True
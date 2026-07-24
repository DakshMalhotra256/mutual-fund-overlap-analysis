from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Fund(Base):
    __tablename__ = "funds"

    fund_id = Column(Integer, primary_key=True, index=True)
    fund_name = Column(String(255), unique=True, nullable=False)
    category = Column(String(100))

    holdings = relationship("Holding", back_populates="fund")

class Holding(Base):
    __tablename__ = "holdings"

    holding_id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey("funds.fund_id"))
    stock_name = Column(String(255), nullable=False)
    sector = Column(String(100))
    holding_pct = Column(Float)
    market_cap = Column(String(50))

    fund = relationship("Fund", back_populates="holdings")

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolios = relationship("SavedPortfolio", back_populates="user")

class SavedPortfolio(Base):
    __tablename__ = "saved_portfolios"

    portfolio_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="portfolios")
    funds = relationship("PortfolioFund", back_populates="portfolio")

class PortfolioFund(Base):
    __tablename__ = "portfolio_funds"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("saved_portfolios.portfolio_id"))
    fund_id = Column(Integer, ForeignKey("funds.fund_id"))

    portfolio = relationship("SavedPortfolio", back_populates="funds")
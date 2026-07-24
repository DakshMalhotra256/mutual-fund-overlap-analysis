from fastapi import FastAPI
from app.database import engine
from app import models
from app.routers import funds, analysis, portfolio, auth

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mutual Fund Portfolio Analyzer")

app.include_router(funds.router)
app.include_router(analysis.router)
app.include_router(portfolio.router)
app.include_router(auth.router)

@app.get("/")
def root():
    return {"message": "Mutual Fund Portfolio Analyzer API is running!"}
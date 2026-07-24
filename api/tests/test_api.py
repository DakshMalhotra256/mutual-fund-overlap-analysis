"""API tests. Run `python seed.py` once before these; they use the same
default SQLite database and clean up any users they create.

    cd api && python -m pytest tests/ -q
"""

import sys
import uuid
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Fund, User

client = TestClient(app)


@pytest.fixture(scope="module")
def fund_ids():
    """fund_ids grouped by category, from the seeded database."""
    db = SessionLocal()
    funds = db.query(Fund).all()
    db.close()
    if not funds:
        pytest.skip("database not seeded; run python seed.py first")
    by_cat = {}
    for f in funds:
        by_cat.setdefault(f.category, []).append(f.fund_id)
    return by_cat


def test_list_funds():
    r = client.get("/api/funds/")
    assert r.status_code == 200
    assert len(r.json()) == 45


def test_fund_detail_has_holdings(fund_ids):
    fid = fund_ids["Large Cap"][0]
    r = client.get(f"/api/funds/{fid}")
    assert r.status_code == 200
    assert len(r.json()["holdings"]) > 10


def test_overlap_same_category_higher_than_cross(fund_ids):
    a, b = fund_ids["Large Cap"][:2]
    c = fund_ids["Small Cap"][0]
    same = client.get(f"/api/analysis/overlap?fund1_id={a}&fund2_id={b}").json()
    cross = client.get(f"/api/analysis/overlap?fund1_id={a}&fund2_id={c}").json()
    assert same["overlap_pct"] > cross["overlap_pct"]


def test_xray_finds_duplicates_in_large_caps(fund_ids):
    r = client.post("/api/portfolio/xray", json={"fund_ids": fund_ids["Large Cap"][:3]})
    assert r.status_code == 200
    assert r.json()["duplicate_stocks"] > 10


def test_score_rewards_category_mix(fund_ids):
    same_cat = client.post(
        "/api/portfolio/score", json={"fund_ids": fund_ids["Large Cap"][:3]}
    ).json()
    mixed = client.post(
        "/api/portfolio/score",
        json={"fund_ids": [fund_ids["Large Cap"][0], fund_ids["Mid Cap"][0],
                           fund_ids["Small Cap"][0]]},
    ).json()
    assert mixed["diversification_score"] > same_cat["diversification_score"]
    assert 0 <= same_cat["diversification_score"] <= 100
    assert 0 <= mixed["diversification_score"] <= 100


def test_score_rejects_single_fund(fund_ids):
    r = client.post("/api/portfolio/score", json={"fund_ids": fund_ids["Index"][:1]})
    assert r.status_code == 400


def test_auth_flow_and_protected_routes(fund_ids):
    email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "test-pass-123"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    # Protected route without a token is rejected
    assert client.get("/api/portfolio/my").status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/portfolio/save", headers=headers, json={
        "name": "test portfolio",
        "fund_ids": fund_ids["Large Cap"][:2]})
    assert r.status_code == 200

    r = client.get("/api/portfolio/my", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Clean up: delete the portfolio, then the test user
    pid = r.json()[0]["portfolio_id"]
    assert client.delete(f"/api/portfolio/{pid}", headers=headers).status_code == 200
    db = SessionLocal()
    db.query(User).filter(User.email == email).delete()
    db.commit()
    db.close()

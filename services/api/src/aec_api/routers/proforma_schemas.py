"""Proforma input contract — the Pydantic models that validate a development deal and double as the
OpenAPI schema. Split out of the router so the endpoints stay focused on wiring; the pure engine
(`aec_api.proforma`) consumes the `Assumptions.model_dump()` these produce."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Timing(BaseModel):
    construction_months: int = Field(gt=0)
    leaseup_months: int = 0
    hold_years: float = Field(gt=0)
    start_date: str | None = None


class CostLine(BaseModel):
    category: Literal["land", "hard", "soft", "contingency", "fee"]
    name: str
    amount: float = 0
    curve: Literal["scurve", "linear", "upfront"] = "scurve"
    start_month: int = 0
    end_month: int = 0
    csi_code: str | None = None


class Debt(BaseModel):
    ltc: float = Field(ge=0, le=1)
    rate: float = Field(ge=0)
    points: float = 0.0
    funding: Literal["equity_first", "pari_passu", "loan_first"] = "equity_first"
    # optional debt-sizing constraints; the loan is sized to the lesser of LTC and any of these
    max_ltv: float | None = Field(default=None, ge=0, le=1)        # loan ≤ ltv × stabilized value
    min_dscr: float | None = Field(default=None, gt=0)             # NOI / (loan × rate) ≥ dscr
    min_debt_yield: float | None = Field(default=None, gt=0)       # NOI / loan ≥ debt yield


class Equity(BaseModel):
    lp_pct: float = Field(ge=0, le=1)
    gp_pct: float = Field(ge=0, le=1)


class Ops(BaseModel):
    potential_rent_annual: float
    other_income_annual: float = 0
    opex_annual: float
    reserves_annual: float = 0.0           # capital reserves, deducted above NOI (U2)
    stabilized_occ: float = Field(gt=0, le=1)
    credit_loss_pct: float = 0.0


class Exit(BaseModel):
    exit_cap: float = Field(gt=0)
    selling_cost_pct: float = 0.0


class Tier(BaseModel):
    hurdle: float | None = None
    lp: float
    gp: float


class Waterfall(BaseModel):
    pref_rate: float = 0.08
    style: Literal["american", "european"] = "american"
    clawback: bool = False
    tiers: list[Tier]


class Tax(BaseModel):
    income_tax_rate: float = Field(default=0.25, ge=0, le=1)     # ordinary rate on operating income
    depreciation_years: float = Field(default=27.5, gt=0)        # 27.5 residential · 39 commercial
    capital_gains_rate: float = Field(default=0.20, ge=0, le=1)  # long-term capital gains
    niit_rate: float = Field(default=0.038, ge=0, le=1)          # net investment income tax
    recapture_rate: float = Field(default=0.25, ge=0, le=1)      # §1250 depreciation recapture (≤25%)


class Assumptions(BaseModel):
    timing: Timing
    cost_lines: list[CostLine]
    debt: Debt
    equity: Equity
    operations: Ops
    exit: Exit
    waterfall: Waterfall
    discount_rate: float = 0.10
    tax: Tax | None = None        # optional; financial statements use institutional defaults if absent

# Calculation precision policy (finance)

*R19 FIN-CALC (2026-07-24). Where Decimal is mandatory, where float is permitted, and the rounding
rules — so every financial number the platform reports is reproducible and defensible. Companion:
[backend-standards.md](backend-standards.md) (the general money rules).*

## The boundary

- **Decimal (via `money.py`)** at the **record boundary**: anything stored on, or parsed from, a
  module record or ledger row — invoice amounts, SOV lines, journal debits/credits, contract
  values, payments. These are *accounting* numbers: they must sum exactly, reconcile to the cent,
  and never drift.
- **Float** inside the **analytical engines** (`proforma/*`, benchmarking, estimating
  confidence, Monte Carlo): IRR/NPV/waterfall math is iterative and continuous; Decimal buys
  nothing there and costs clarity. Engines round **once, at the edge** (the solve result rounds
  currency to 2 dp and rates to 4 dp — already the shipped convention).

## Rules

1. Never accumulate stored currency by repeated float addition — aggregate in SQL or through
   `money.py`.
2. One rounding pass per reported number, at the response edge; intermediates stay full-precision.
3. Python `round()` is **banker's rounding** (round-half-even): `round(270.625, 2) == 270.62`.
   Test expectations must match; ledger-style outputs that require half-up use `money.py`.
4. Percentages/rates report at 4 dp; currency at 2 dp; ratios (multiples) at 3 dp.
5. Reconciliation invariants are test-enforced, not assumed: sources == uses, waterfall
   distributions == distributable cash, variance decomposition sums exactly (qty effect + price
   effect), portfolio rollups == Σ projects.
6. **Golden references:** the core metrics (XIRR, NPV, equity multiple, yield-on-cost, the
   waterfall, the residual-land inverse) are pinned to hand-computed closed-form fixtures in
   `test_fin_calc.py` — a refactor that shifts a metric fails loudly.
7. Determinism: no randomness in finance paths except Monte Carlo, which takes an explicit seed.

## Known non-goals

Multi-currency (single-currency deployments; a currency field is presentation), tax-jurisdiction
precision rules (the tax schedule is an estimate, labeled as such), and sub-cent unit pricing
(store unit rates at full precision; extend, then round the extension).

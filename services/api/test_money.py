"""P6 — Decimal money helpers: correct half-up rounding + penny-accurate allocation."""
from aec_api import money


def test_money():
    # q2: money round-half-up beats float round (float round(2.675,2) == 2.67)
    assert money.q2(2.675) == 2.68, "half-up rounding to cents"
    assert money.q2(2.674) == 2.67
    assert money.q2(0.125) == 0.13
    assert money.q2("1.005") == 1.01
    assert money.q2(10) == 10.0

    # to_cents: exact integer cents, no float drift
    assert money.to_cents(19.99) == 1999
    assert money.to_cents(2.675) == 268
    assert money.to_cents("0.1") == 10

    # allocate: parts sum to the total to the cent (no lost penny)
    parts = money.allocate(100, [1, 1, 1])
    assert parts == [33.34, 33.33, 33.33], parts
    assert round(sum(parts), 2) == 100.00

    # weighted split still sums exactly
    w = money.allocate(1000, [2, 3, 5])
    assert round(sum(w), 2) == 1000.00
    assert w == [200.0, 300.0, 500.0], w

    # a nastier remainder — 0.10 across 3 = 4+3+3 cents
    dime = money.allocate("0.10", [1, 1, 1])
    assert money.to_cents(sum(dime)) == 10, dime

    # degenerate inputs
    assert money.allocate(50, []) == []
    assert money.allocate(50, [0, 0]) == [0.0, 0.0]

    print("MONEY OK - q2 half-up (2.675->2.68), to_cents exact, allocate splits $100/3 = "
          "33.34+33.33+33.33 (sums to 100.00, no lost penny)")


if __name__ == "__main__":
    test_money()

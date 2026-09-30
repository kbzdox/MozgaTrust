#!/usr/bin/env python3
"""Пересчёт сценариев плана MozgaTrust (20 млн ₽).

Пример:
  python3 scripts/calc_plan.py
  python3 scripts/calc_plan.py --dep-rate 0.125 --ofz-ytm 0.165 --withdraw 10000000
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEF_DEP = 14_000_000
DEF_OFZ = 6_000_000
DEF_WITHDRAW = 10_000_000
TARGET_MO = 100_000
OFZ_YTM = 0.165
POST_RATE = 0.09


def fv(principal: float, rate: float, years: float) -> float:
    return principal * (1.0 + rate) ** years


def run_scenario(
    name: str,
    dep_rate: float,
    *,
    dep0: float = DEF_DEP,
    ofz0: float = DEF_OFZ,
    withdraw: float = DEF_WITHDRAW,
    ofz_ytm: float = OFZ_YTM,
    post_rate: float = POST_RATE,
) -> dict:
    dep3 = fv(dep0, dep_rate, 3)
    rem = dep3 - withdraw
    income_mo = rem * dep_rate / 12.0
    ofz5 = fv(ofz0, ofz_ytm, 5)
    ofz10 = fv(ofz0, ofz_ytm, 10)
    pool2031 = rem + ofz5
    pool2036 = rem + ofz10
    return {
        "scenario": name,
        "deposit_rate_pct": round(dep_rate * 100, 2),
        "dep_after_3y_rub": round(dep3),
        "withdraw_3y_rub": round(withdraw),
        "dep_remain_3y_rub": round(rem),
        "income_mo_2029_2031_rub": round(income_mo),
        "ok_100k_before_iis_close": income_mo >= TARGET_MO,
        "ofz_after_5y_2031_rub": round(ofz5),
        "pool_2031_rub": round(pool2031),
        "income_mo_after_2031_at_9pct_rub": round(pool2031 * post_rate / 12.0),
        "ofz_after_10y_2036_rub": round(ofz10),
        "pool_2036_rub": round(pool2036),
        "income_mo_after_2036_at_9pct_rub": round(pool2036 * post_rate / 12.0),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="MozgaTrust investment plan calculator")
    p.add_argument("--dep-rate", type=float, default=None, help="Single deposit rate, e.g. 0.125")
    p.add_argument("--ofz-ytm", type=float, default=OFZ_YTM)
    p.add_argument("--withdraw", type=float, default=DEF_WITHDRAW)
    p.add_argument("--dep0", type=float, default=DEF_DEP)
    p.add_argument("--ofz0", type=float, default=DEF_OFZ)
    p.add_argument("--write-csv", action="store_true", help="Refresh data/scenarios.csv")
    args = p.parse_args()

    if args.dep_rate is not None:
        scenarios = [
            run_scenario(
                "custom",
                args.dep_rate,
                dep0=args.dep0,
                ofz0=args.ofz0,
                withdraw=args.withdraw,
                ofz_ytm=args.ofz_ytm,
            )
        ]
    else:
        presets = [
            ("база_ЦБ_13.01", 0.1301),
            ("план_12.50", 0.125),
            ("стресс_11.64", 0.1164),
            ("лестница_12.44", 0.1244),
        ]
        scenarios = [
            run_scenario(
                name,
                rate,
                dep0=args.dep0,
                ofz0=args.ofz0,
                withdraw=args.withdraw,
                ofz_ytm=args.ofz_ytm,
            )
            for name, rate in presets
        ]

    fields = list(scenarios[0].keys())
    print(",".join(fields))
    for row in scenarios:
        print(",".join(str(row[f]) for f in fields))

    if args.write_csv:
        out = Path(__file__).resolve().parents[1] / "data" / "scenarios.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(scenarios)
        print(f"\nWrote {out}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Генерация простого крупного дашборда (для показа старшему родственнику)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cashflow_yearly as cf  # noqa: E402

OUT = ROOT / "dashboard"


def scenario(pension_from_month: int, dep0: float, rows: list, key: str, title: str) -> dict:
    y28 = next(r for r in rows if r.year == 2028)
    y40 = rows[-1]
    return {
        "key": key,
        "title": title,
        "dep0": round(dep0),
        "iis0": round(cf.TOTAL - dep0),
        "pension_from_month": pension_from_month,
        "total_2040": round(y40.total_end),
        "total_pension": round(sum(r.dep_pension for r in rows)),
        "total_tax": round(sum(r.dep_ndfl for r in rows)),
        "years": [
            {
                "year": r.year,
                "dep_end": round(r.dep_end),
                "iis_end": round(r.iis_end),
                "pension": round(r.dep_pension),
                "lump": round(r.dep_lump),
                "tax": round(r.dep_ndfl),
                "total": round(r.total_end),
            }
            for r in rows
        ],
    }


def main() -> None:
    dep_v1 = min(cf.TOTAL, cf.find_min_dep0(1) + 10_000)
    dep_v2 = min(cf.TOTAL, cf.find_min_dep0(37) + 10_000)
    rows_v1 = cf.simulate(dep_v1, 1)
    rows_v2 = cf.simulate(dep_v2, 37)

    data = {
        "v1": scenario(1, dep_v1, rows_v1, "v1", "Пенсия сразу"),
        "v2": scenario(37, dep_v2, rows_v2, "v2", "Пенсия через 3 года"),
    }

    template = (OUT / "index.template.html").read_text(encoding="utf-8")
    html = template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()

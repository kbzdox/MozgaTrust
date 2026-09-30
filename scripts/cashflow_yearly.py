#!/usr/bin/env python3
"""Два варианта кэшфлоу MozgaTrust с рентой 100 тыс. ₽/мес.

Вариант 1 — 100 тыс./мес с первого месяца (+ изъятие 10 млн через 3 года).
Вариант 2 — 3 года капитализации, потом 100 тыс./мес (+ изъятие 10 млн через 3 года).
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHARTS = ROOT / "plan" / "charts"

DEP0 = 14_000_000.0
OFZ0 = 6_000_000.0
LUMP = 10_000_000.0
LIVING_YR = 100_000.0 * 12
TAX_REFUND_2027 = 52_000.0
OFZ_YTM = 0.165
TARGET_MO = 100_000.0

DEP_RATE = {y: 0.125 for y in range(2026, 2031)}
for y in range(2031, 2041):
    DEP_RATE[y] = 0.09


def rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")


def simulate(*, rent_from_start: bool, close_iis_year: int = 2031) -> list[dict]:
    """Год = полный календарный период; изъятие 10 млн в конце 2028.

    Порядок в обычный год: начислить % → снять ренту 1,2 млн (если нужна).
    В год закрытия ИИС: доначислить ОФЗ → влить в депозиты → % на пул → рента.
    """
    rows: list[dict] = []
    dep = DEP0
    ofz = OFZ0

    for year in range(2026, 2041):
        r = DEP_RATE[year]
        dep_start, ofz_start = dep, ofz
        withdraw = 0.0
        tax = TAX_REFUND_2027 if year == 2027 else 0.0
        living = 0.0
        ofz_growth = 0.0
        shortfall = 0.0
        dep_interest = 0.0
        take_rent = rent_from_start or year >= 2029

        closing = ofz > 0 and year == close_iis_year

        if year <= 2028:
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep_interest = dep * r
            dep += dep_interest
            phase = "накопление (рента 0)"
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
                phase = "рента 100к/мес"
            if year == 2028:
                withdraw = min(LUMP, max(dep, 0.0))
                dep -= withdraw
                phase = "изъятие 10 млн" + (" + рента" if take_rent else "")
        elif closing:
            phase = "закрытие ИИС + рента"
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep += ofz
            ofz = 0.0
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
        elif ofz > 0:
            phase = "рента до закрытия ИИС"
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
        else:
            phase = "рента объединённая"
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living

        actual_mo = living / 12.0
        safe_mo = max(dep, 0.0) * r / 12.0
        principal_eaten = max(0.0, living - dep_interest) if take_rent else 0.0

        # ✅ только если сняли ≥100к/мес БЕЗ проедания тела
        if not take_rent and year < 2029:
            covered = True
        else:
            covered = (
                shortfall <= 1e-9
                and actual_mo + 1e-9 >= TARGET_MO
                and principal_eaten <= 1e-9
            )

        rows.append(
            {
                "year": year,
                "phase": phase,
                "dep_rate_pct": round(r * 100, 2),
                "dep_start": round(dep_start),
                "dep_interest": round(dep_interest),
                "principal_eaten": round(principal_eaten),
                "dep_end": round(max(dep, 0.0)),
                "ofz_start": round(ofz_start),
                "ofz_growth": round(ofz_growth),
                "ofz_end": round(ofz),
                "iis_open": ofz > 0,
                "tax_refund": round(tax),
                "living_year": round(living),
                "living_month": round(actual_mo),
                "living_shortfall_year": round(shortfall),
                "lump_withdraw": round(withdraw),
                "net_cash_to_owner": round(living + withdraw + tax),
                "total_capital_end": round(max(dep, 0.0) + ofz),
                "safe_rent_mo_on_remainder": round(safe_mo),
                "ok_100k": covered,
            }
        )

    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def plot_all(v1: list[dict], v2: list[dict]) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    years = [r["year"] for r in v1]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.plot(
        years,
        [r["living_month"] / 1000 for r in v1],
        color="#8b3a3a",
        lw=2.2,
        marker="o",
        ms=4,
        label="Вариант 1: 100к с первого месяца",
    )
    ax.plot(
        years,
        [r["living_month"] / 1000 for r in v2],
        color="#1f6f5b",
        lw=2.2,
        marker="o",
        ms=4,
        label="Вариант 2: 100к после 3 лет",
    )
    ax.axhline(100, color="#333333", ls="--", lw=1.1, label="Цель 100 тыс./мес")
    ax.axvline(2028, color="#666666", ls=":", lw=1, label="Изъятие 10 млн")
    ax.axvline(2031, color="#3a4a8b", ls=":", lw=1, label="Закрытие ИИС")
    ax.set_title("Фактическая рента владельцу, тыс. ₽/мес")
    ax.set_ylabel("тыс. ₽ / мес")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.set_ylim(0, 220)
    ax.legend(loc="best", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "rent_two_variants.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.plot(years, [r["dep_end"] / 1e6 for r in v1], color="#8b3a3a", lw=2.2, label="V1 депозиты")
    ax.plot(years, [r["dep_end"] / 1e6 for r in v2], color="#1f6f5b", lw=2.2, label="V2 депозиты")
    ax.plot(years, [r["ofz_end"] / 1e6 for r in v1], color="#8b3a3a", lw=1.5, ls="--", label="V1 ОФЗ")
    ax.plot(years, [r["ofz_end"] / 1e6 for r in v2], color="#1f6f5b", lw=1.5, ls="--", label="V2 ОФЗ")
    ax.axvline(2028, color="#666666", ls=":")
    ax.axvline(2031, color="#3a4a8b", ls=":")
    ax.set_title("Остатки: депозиты и ОФЗ (ИИС → 2031)")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(loc="best", frameon=False, ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "balances_two_variants.png")
    plt.close(fig)

    for tag, rows, title in [
        ("v1", v1, "Вариант 1: 100к/мес сразу — кэш владельцу, млн ₽"),
        ("v2", v2, "Вариант 2: 100к/мес после 3 лет — кэш владельцу, млн ₽"),
    ]:
        fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
        living = [r["living_year"] / 1e6 for r in rows]
        lump = [r["lump_withdraw"] / 1e6 for r in rows]
        taxv = [r["tax_refund"] / 1e6 for r in rows]
        ax.bar(years, living, color="#1f6f5b", label="Рента 100к×12")
        ax.bar(years, lump, bottom=living, color="#8b3a3a", label="Изъятие 10 млн")
        bottom2 = [a + b for a, b in zip(living, lump)]
        ax.bar(years, taxv, bottom=bottom2, color="#5b7c99", label="Вычет ИИС")
        ax.set_title(title)
        ax.set_ylabel("млн ₽")
        ax.set_xlabel("Год")
        ax.set_xlim(2025.5, 2040.5)
        ax.legend(loc="upper right", frameon=False)
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(CHARTS / f"owner_cash_{tag}.png")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=140)
    width = 0.35
    xs = list(years)
    ax.bar(
        [x - width / 2 for x in xs],
        [r["principal_eaten"] / 1000 for r in v1],
        width=width,
        color="#8b3a3a",
        label="V1 проедание тела",
    )
    ax.bar(
        [x + width / 2 for x in xs],
        [r["principal_eaten"] / 1000 for r in v2],
        width=width,
        color="#1f6f5b",
        label="V2 проедание тела",
    )
    ax.set_title("Проедание тела депозитов (рента > %), тыс. ₽/год")
    ax.set_ylabel("тыс. ₽ / год")
    ax.set_xlabel("Год")
    ax.legend(frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "principal_drawdown.png")
    plt.close(fig)

    # Keep legacy filenames used in older docs as copies of key charts
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.stackplot(
        years,
        [r["dep_end"] / 1e6 for r in v2],
        [r["ofz_end"] / 1e6 for r in v2],
        labels=["Депозиты", "ОФЗ (ИИС-3)"],
        colors=["#1f6f5b", "#c4a35a"],
        alpha=0.92,
    )
    ax.axvline(2028, color="#8b3a3a", ls="--", lw=1, label="Изъятие 10 млн")
    ax.axvline(2031, color="#3a4a8b", ls="--", lw=1, label="Закрытие ИИС")
    ax.set_title("Капитал по годам — вариант 2 (рекомендуемый)")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "capital_path_a.png")
    plt.close(fig)


def md_table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    lines = [
        "| " + " | ".join(h for h, _ in cols) + " |",
        "| " + " | ".join("---:" for _ in cols) + " |",
    ]
    for r in rows:
        cells = []
        for _, k in cols:
            v = r[k]
            if k == "ok_100k":
                cells.append("✅" if v else "❌")
            elif k == "iis_open":
                cells.append("да" if v else "нет")
            elif isinstance(v, (int, float)) and k not in {"year", "dep_rate_pct"}:
                cells.append(rub(float(v)))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_markdown(v1: list[dict], v2: list[dict]) -> None:
    cols = [
        ("Год", "year"),
        ("Фаза", "phase"),
        ("Ставка %", "dep_rate_pct"),
        ("Деп. конец", "dep_end"),
        ("ОФЗ конец", "ofz_end"),
        ("Рента ₽/мес", "living_month"),
        ("Проедание тела/год", "principal_eaten"),
        ("Изъятие", "lump_withdraw"),
        ("Капитал", "total_capital_end"),
        ("≥100к", "ok_100k"),
    ]

    v1_gap = [r["year"] for r in v1 if not r["ok_100k"]]
    v2_gap = [r["year"] for r in v2 if r["year"] >= 2029 and not r["ok_100k"]]
    v1_2028 = next(r for r in v1 if r["year"] == 2028)
    v2_2028 = next(r for r in v2 if r["year"] == 2028)
    v1_2030 = next(r for r in v1 if r["year"] == 2030)
    v1_2031 = next(r for r in v1 if r["year"] == 2031)
    v2_2031 = next(r for r in v2 if r["year"] == 2031)
    pre_lump_v1 = v1_2028["dep_end"] + v1_2028["lump_withdraw"]

    text = f"""# Детальный кэшфлоу: два варианта ренты 100 тыс. ₽/мес

База: **14 млн** депозиты + **6 млн** ОФЗ на ИИС-3.  
Разовое изъятие **10 млн** — конец **2028**. Закрытие ИИС — **2031**.

| Параметр | Значение |
| --- | ---: |
| Рента на расходы | **100 000 ₽/мес** (= 1,2 млн ₽/год) |
| Ставка депозитов 2026–2030 | 12,5% |
| Ставка с 2031 | 9,0% |
| YTM ОФЗ на ИИС | 16,5% |

```bash
python3 scripts/cashflow_yearly.py
```

---

## Короткий вывод

| | Вариант 1: 100к сразу | Вариант 2: 100к после 3 лет |
| --- | --- | --- |
| Рента 2026–2028 | 100к/мес | 0 (капитализация) |
| Депозиты после −10 млн (конец 2028) | **{rub(v1_2028['dep_end'])}** | **{rub(v2_2028['dep_end'])}** |
| 2029–2030 | 100к только с **проеданием тела** | 100к **из процентов**, тело цело |
| 2031+ после ИИС | ≈{rub(v1_2031['living_month'])}/мес | ≈{rub(v2_2031['living_month'])}/мес |
| Без дыр до 2040 | ❌ | ✅ рекомендуемый |

Почему старая модель «не верилась»: в ней в 2026–2028 рента на расходы **не вычиталась** из депозитов. Ниже оба варианта считаются с реальным съёмом 100к/мес.

![Сравнение ренты](charts/rent_two_variants.png)

![Остатки](charts/balances_two_variants.png)

![Проедание тела](charts/principal_drawdown.png)

---

## Вариант 1 — 100 тыс./мес с первого месяца

С депозитов каждый год уходит **1,2 млн**. В конце 2028 ещё **−10 млн**.

![Кэш V1](charts/owner_cash_v1.png)

{md_table(v1, cols)}

### Что происходит

1. На 14 млн @12,5% проценты ≈ 145,8 тыс./мес — **100к тянем**, остаток %% капитализируется.
2. К изъятию на депозитах ≈ **{rub(pre_lump_v1)}** → после −10 млн остаётся ≈ **{rub(v1_2028['dep_end'])}**.
3. С ~5,9 млн проценты дают только ≈ **61 тыс./мес**. Чтобы продолжать 100к, модель **режет тело** (см. колонку «Проедание»).
4. К концу 2030 депозиты ≈ **{rub(v1_2030['dep_end'])}**.
5. В 2031 ОФЗ вливаются в пул — снова можно снимать 100к без аварии.

Годы, где цель формально бьётся только через проедание / где есть дыра: **{', '.join(map(str, v1_gap)) if v1_gap else 'нет'}**.

Чтобы забирать 100к сразу *и* не проедать тело до 2031, разовое изъятие должно быть не 10 млн, а примерно **6,0–6,5 млн**.

---

## Вариант 2 — 100 тыс./мес только после 3 лет

2026–2028 проценты **не трогаем**. Конец 2028: −10 млн. С 2029: 100к/мес с остатка ≈9,93 млн (%% ≈103,5 тыс./мес).

![Кэш V2](charts/owner_cash_v2.png)

{md_table(v2, cols)}

Провалы после старта ренты: **{', '.join(map(str, v2_gap)) if v2_gap else 'нет'}**.

---

## Водопад

```mermaid
flowchart TB
  S["Старт 20 млн\n14 деп + 6 ОФЗ"] --> V1
  S --> V2
  subgraph V1["Вариант 1 — 100к сразу"]
    A1["2026–2028: 100к/мес"] --> A2["2028: −10 млн"]
    A2 --> A3["2029–2030: 100к с проеданием"]
    A3 --> A4["2031: ИИС в пул"]
  end
  subgraph V2["Вариант 2 — 100к после 3 лет"]
    B1["2026–2028: капитализация"] --> B2["2028: −10 млн"]
    B2 --> B3["2029–2030: 100к из %%"]
    B3 --> B4["2031: ИИС в пул"]
  end
```

---

## Файлы

| Файл | Содержание |
| --- | --- |
| [cashflow_v1_rent_now.csv](../data/cashflow_v1_rent_now.csv) | Вариант 1 |
| [cashflow_v2_rent_after_3y.csv](../data/cashflow_v2_rent_after_3y.csv) | Вариант 2 |
| [charts/](charts/) | PNG |

*Модель иллюстративная, не ИИР.*
"""
    out = ROOT / "plan" / "CASHFLOW.md"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    v1 = simulate(rent_from_start=True)
    v2 = simulate(rent_from_start=False)
    write_csv(DATA / "cashflow_v1_rent_now.csv", v1)
    write_csv(DATA / "cashflow_v2_rent_after_3y.csv", v2)
    write_csv(DATA / "cashflow_base.csv", v2)
    write_csv(DATA / "cashflow_hold.csv", v1)
    plot_all(v1, v2)
    write_markdown(v1, v2)
    print("V1:", [(r["year"], r["living_month"], r["dep_end"], r["principal_eaten"], r["ok_100k"]) for r in v1])
    print("V2:", [(r["year"], r["living_month"], r["dep_end"], r["principal_eaten"], r["ok_100k"]) for r in v2])


if __name__ == "__main__":
    main()

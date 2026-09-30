#!/usr/bin/env python3
"""Детальный кэшфлоу плана MozgaTrust по календарным годам 2026–2040.

Генерирует:
  data/cashflow_base.csv   — путь A: закрытие ИИС в 2031
  data/cashflow_hold.csv   — путь B: закрытие ИИС в 2036
  plan/charts/cashflow_*.png
  plan/CASHFLOW.md
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHARTS = ROOT / "plan" / "charts"

DEP0 = 14_000_000.0
OFZ0 = 6_000_000.0
WITHDRAW = 10_000_000.0
TARGET_MO = 100_000.0
TAX_REFUND_2027 = 52_000.0
OFZ_YTM = 0.165

# Ставка депозитов / рентного пула на конец года (начисление за этот год)
DEP_RATE = {y: 0.125 for y in range(2026, 2031)}  # 2026–2030
for y in range(2031, 2041):
    DEP_RATE[y] = 0.09


def rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")


def simulate(close_iis_year: int) -> list[dict]:
    """Модель конец-года.

    2026–2028 — 3 полных года капитализации депозитов (купоны ОФЗ на ИИС).
    Конец 2028 / старт 2029 — изъятие 10 млн с депозитов.
    2029+ — рента процентами с остатка (тело не проедаем).
    close_iis_year — ОФЗ вливаются в рентный пул в конце этого года.
    """
    rows: list[dict] = []
    dep = DEP0
    ofz = OFZ0
    iis_open = True

    for year in range(2026, 2041):
        r = DEP_RATE[year]
        dep_start, ofz_start = dep, ofz

        withdraw = 0.0
        tax_refund = TAX_REFUND_2027 if year == 2027 else 0.0
        living = 0.0
        ofz_growth = 0.0

        if year <= 2028:
            phase = "накопление"
            dep_interest = dep * r
            dep += dep_interest
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            if year == 2028:
                withdraw = WITHDRAW
                dep -= withdraw
                phase = "конец накопления / изъятие"
        elif iis_open and year == close_iis_year:
            # Закрытие в начале года: последняя переоценка ОФЗ → в пул → рента с полного капитала
            phase = "закрытие ИИС"
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep += ofz
            ofz = 0.0
            iis_open = False
            dep_interest = dep * r
            living = dep_interest
        elif iis_open:
            phase = "рента до закрытия ИИС"
            dep_interest = dep * r
            living = dep_interest
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
        else:
            phase = "рента объединённая"
            dep_interest = dep * r
            living = dep_interest

        if year < 2028:
            avail_mo = 0.0
        elif year == 2028:
            avail_mo = dep * r / 12.0
        else:
            avail_mo = living / 12.0

        ok = True if year < 2029 else (avail_mo + 1e-9 >= TARGET_MO)

        rows.append(
            {
                "year": year,
                "phase": phase,
                "dep_rate_pct": round(r * 100, 2),
                "dep_start": round(dep_start),
                "dep_interest": round(dep_interest),
                "dep_withdraw": round(withdraw),
                "dep_end": round(dep),
                "ofz_start": round(ofz_start),
                "ofz_growth": round(ofz_growth),
                "ofz_end": round(ofz),
                "iis_open": ofz > 0,
                "tax_refund": round(tax_refund),
                "living_cash_year": round(living),
                "living_cash_month": round(living / 12.0) if living else 0,
                "lump_withdraw": round(withdraw),
                "net_cash_to_owner": round(living + withdraw + tax_refund),
                "total_capital_end": round(dep + ofz),
                "available_rent_mo": round(avail_mo),
                "ok_100k": ok,
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


def plot_charts(base: list[dict], hold: list[dict]) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    years = [r["year"] for r in base]

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.stackplot(
        years,
        [r["dep_end"] / 1e6 for r in base],
        [r["ofz_end"] / 1e6 for r in base],
        labels=["Депозиты", "ОФЗ (ИИС-3)"],
        colors=["#1f6f5b", "#c4a35a"],
        alpha=0.92,
    )
    ax.axvline(2028, color="#8b3a3a", ls="--", lw=1, label="Изъятие 10 млн")
    ax.axvline(2031, color="#3a4a8b", ls="--", lw=1, label="Закрытие ИИС (A)")
    ax.set_title("Капитал по годам — путь A (ИИС → 2031)")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "capital_path_a.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    rent_a = [r["available_rent_mo"] / 1000 for r in base]
    rent_b = [r["available_rent_mo"] / 1000 for r in hold]
    ax.plot(years, rent_a, color="#1f6f5b", lw=2.2, marker="o", ms=4, label="Путь A: ИИС 2031")
    ax.plot(years, rent_b, color="#c4a35a", lw=2.2, marker="o", ms=4, label="Путь B: ИИС 2036")
    ax.axhline(100, color="#8b3a3a", ls="--", lw=1.2, label="Цель 100 тыс. ₽/мес")
    ax.set_title("Доступная рента, тыс. ₽/мес")
    ax.set_ylabel("тыс. ₽ / мес")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.set_ylim(0, max(max(rent_a), max(rent_b)) * 1.12)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "rent_monthly.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    living = [r["living_cash_year"] / 1e6 for r in base]
    lump = [r["lump_withdraw"] / 1e6 for r in base]
    tax = [r["tax_refund"] / 1e6 for r in base]
    ax.bar(years, living, color="#1f6f5b", label="Рента (проценты)")
    ax.bar(years, lump, bottom=living, color="#8b3a3a", label="Разовое изъятие")
    bottom2 = [a + b for a, b in zip(living, lump)]
    ax.bar(years, tax, bottom=bottom2, color="#5b7c99", label="Налоговый вычет")
    ax.set_title("Кэш владельцу по годам — путь A, млн ₽")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2025.5, 2040.5)
    ax.legend(loc="upper right", frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "owner_cash_path_a.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.plot(years, [r["total_capital_end"] / 1e6 for r in base], color="#1f6f5b", lw=2.2, label="Путь A")
    ax.plot(years, [r["total_capital_end"] / 1e6 for r in hold], color="#c4a35a", lw=2.2, label="Путь B")
    ax.set_title("Совокупный капитал (депозиты + ОФЗ)")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    fig.tight_layout()
    fig.savefig(CHARTS / "total_capital_compare.png")
    plt.close(fig)


def md_table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    head = "| " + " | ".join(h for h, _ in cols) + " |"
    sep = "| " + " | ".join("---:" for _ in cols) + " |"
    lines = [head, sep]
    for r in rows:
        cells = []
        for _, k in cols:
            v = r[k]
            if isinstance(v, (int, float)) and k not in {"year", "dep_rate_pct"}:
                if k == "ok_100k":
                    cells.append("✅" if v else "❌")
                else:
                    cells.append(rub(float(v)))
            elif k == "ok_100k":
                cells.append("✅" if v else "❌")
            elif k == "iis_open":
                cells.append("да" if v else "нет")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_markdown(base: list[dict], hold: list[dict]) -> None:
    cols_main = [
        ("Год", "year"),
        ("Фаза", "phase"),
        ("Ставка %", "dep_rate_pct"),
        ("Деп. конец", "dep_end"),
        ("ОФЗ конец", "ofz_end"),
        ("Капитал", "total_capital_end"),
        ("Рента ₽/мес", "available_rent_mo"),
        ("Кэш владельцу", "net_cash_to_owner"),
        ("≥100к", "ok_100k"),
    ]
    cols_detail = [
        ("Год", "year"),
        ("Деп. старт", "dep_start"),
        ("% за год", "dep_interest"),
        ("Изъятие", "dep_withdraw"),
        ("Деп. конец", "dep_end"),
        ("ОФЗ старт", "ofz_start"),
        ("Рост ОФЗ", "ofz_growth"),
        ("ОФЗ конец", "ofz_end"),
        ("Вычет", "tax_refund"),
        ("Рента/год", "living_cash_year"),
    ]

    gap_b = [r["year"] for r in hold if r["year"] >= 2029 and not r["ok_100k"]]
    if gap_b:
        gap_note = (
            f"**Разрыв цели в пути B:** {gap_b[0]}–{gap_b[-1]} — при ставке 9% рента "
            "только с депозитного остатка (~74,5 тыс. ₽/мес) ниже 100 тыс. "
            "Путь B оправдан, если короткие вклады останутся ≳12,5%, либо изъятие меньше 10 млн, "
            "либо ИИС закрывают раньше (**путь A**)."
        )
    else:
        gap_note = "**Путь B держит цель** во всех годах ренты."

    text = f"""# Детальный кэшфлоу по годам (2026–2040)

Сценарий **«план»**: **14 млн** депозиты + **6 млн** длинные ОФЗ на ИИС-3.

| Параметр | Значение |
| --- | ---: |
| Ставка депозитов 2026–2030 | **12,5%** |
| Ставка ренты с 2031 | **9,0%** (гипотеза нормализации) |
| YTM ОФЗ (реинвест на ИИС) | **16,5%** |
| Изъятие **10 млн** | конец **2028** (после 3 лет капитализации) |
| Цель ренты | ≥ **100 000 ₽/мес** с **2029** |
| Вычет ИИС (оценка) | **52 000 ₽** в **2027** |

Пересчёт графиков и CSV:

```bash
python3 scripts/cashflow_yearly.py
```

---

## Путь A — закрытие ИИС в 2031 (основной)

![Капитал путь A](charts/capital_path_a.png)

![Кэш владельцу путь A](charts/owner_cash_path_a.png)

### Сводка год за годом

{md_table(base, cols_main)}

### Разложение потоков

{md_table(base, cols_detail)}

### Смысл по годам

| Год | Кэш владельцу | Портфель |
| --- | --- | --- |
| 2026 | 0 | Старт 14+6; капитализация |
| 2027 | ~52 тыс. вычет | Капитализация |
| 2028 | **10 млн** изъятие | Деп. ≈19,93 → **9,93 млн** остаток; потенциал ренты ≈**103,5 тыс./мес** |
| 2029–2030 | ≈103,5 тыс./мес с депозитов @12,5% | ОФЗ растут на ИИС |
| 2031 | закрытие ИИС в начале года | ОФЗ (~15,0 млн после роста) → в пул; рента ≈**187 тыс./мес** @9% |
| 2032–2040 | ≈**187 тыс./мес** при 9% | Цель с запасом |

---

## Путь B — закрытие ИИС в 2036

![Сравнение капитала](charts/total_capital_compare.png)

![Рента по месяцам](charts/rent_monthly.png)

### Сводка год за годом

{md_table(hold, cols_main)}

{gap_note}

---

## Водопад

```mermaid
flowchart LR
  A["2026\n20 млн\n14 деп + 6 ОФЗ"] --> B["2026–2028\nКапитализация\nкэш ≈ 0"]
  B --> C["конец 2028\nИзъятие\n10 млн"]
  C --> D["2029–2030\nРента ≥100к\nс депозитов"]
  D --> E["2031 путь A\nили 2036 путь B\nЗакрытие ИИС"]
  E --> F["до 2040\nРента с пула"]
```

---

## Файлы

| Файл | Содержание |
| --- | --- |
| [data/cashflow_base.csv](../data/cashflow_base.csv) | Путь A |
| [data/cashflow_hold.csv](../data/cashflow_hold.csv) | Путь B |
| [plan/charts/](charts/) | PNG |

*Модель иллюстративная, не ИИР.*
"""
    out = ROOT / "plan" / "CASHFLOW.md"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    base = simulate(2031)
    hold = simulate(2036)
    write_csv(DATA / "cashflow_base.csv", base)
    write_csv(DATA / "cashflow_hold.csv", hold)
    plot_charts(base, hold)
    write_markdown(base, hold)
    print("A:", [(r["year"], r["dep_end"], r["available_rent_mo"], r["ok_100k"]) for r in base])
    print("B gaps:", [r["year"] for r in hold if r["year"] >= 2029 and not r["ok_100k"]])


if __name__ == "__main__":
    main()

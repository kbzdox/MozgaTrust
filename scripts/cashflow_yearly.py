#!/usr/bin/env python3
"""Простые годовые таблицы кэшфлоу (депозит + ИИС) для сценариев V1 и V2.

Колонки:
Год | Депозит: ставка, нач., %, НДФЛ, конец | ИИС: нач., %, НДФЛ, конец |
Вывод 100к/мес (сумма за год) | Доп. изъятие | Общий капитал на конец
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PLAN = ROOT / "plan"

DEP0 = 14_000_000.0
IIS0 = 6_000_000.0  # ОФЗ на ИИС-3
LUMP = 10_000_000.0
LIVING_MO = 100_000.0
LIVING_YR = LIVING_MO * 12
OFZ_YTM = 0.165
CLOSE_IIS = 2031
KEY_RATE = 0.14
TAX_FREE = 1_000_000.0 * KEY_RATE
NDFL_RATE = 0.13
IIS_REFUND_2027 = 52_000.0

DEP_RATE = {y: 0.125 for y in range(2026, 2031)}
for y in range(2031, 2041):
    DEP_RATE[y] = 0.09

COLS = [
    "year",
    "dep_rate_pct",
    "dep_start",
    "dep_interest",
    "dep_ndfl",
    "dep_end",
    "iis_start",
    "iis_interest",
    "iis_ndfl",
    "iis_end",
    "living_year",  # вывод 100к/мес × 12
    "extra_withdraw",
    "total_end",
]


def rub(x: float | int) -> str:
    return f"{float(x):,.0f}".replace(",", "\u00a0")


def ndfl_on_interest(interest: float) -> float:
    return max(0.0, interest - TAX_FREE) * NDFL_RATE


def simulate(*, rent_from_start: bool) -> list[dict]:
    dep = DEP0
    iis = IIS0
    rows: list[dict] = []

    for year in range(2026, 2041):
        rate = DEP_RATE[year]
        take_rent = rent_from_start or year >= 2029
        living = LIVING_YR if take_rent else 0.0
        lump = LUMP if year == 2028 else 0.0
        refund = IIS_REFUND_2027 if year == 2027 else 0.0

        dep_start = dep
        iis_start = iis
        closing = iis > 0 and year == CLOSE_IIS

        if closing:
            # ИИС: рост за год, затем перевод в депозиты (НДФЛ по льготе = 0)
            iis_interest = iis_start * OFZ_YTM
            iis_ndfl = 0.0
            transfer = iis_start + iis_interest
            iis_end = 0.0
            # Депозит: после перевода считаем % на объединённую сумму
            base = dep_start + transfer + refund
            dep_interest = base * rate
            dep_ndfl = ndfl_on_interest(dep_interest)
            dep_end = base + dep_interest - dep_ndfl - living - lump
        else:
            iis_interest = iis_start * OFZ_YTM if iis_start > 0 else 0.0
            iis_ndfl = 0.0  # на ИИС налог отложен до закрытия
            iis_end = iis_start + iis_interest

            dep_interest = dep_start * rate
            dep_ndfl = ndfl_on_interest(dep_interest)
            dep_end = dep_start + dep_interest - dep_ndfl + refund - living - lump

        dep_end = max(dep_end, 0.0)
        # если на ренту не хватило — фактически сняли меньше (для прозрачности покажем план living)
        # но капитал не уводим в минус
        rows.append(
            {
                "year": year,
                "dep_rate_pct": round(rate * 100, 2),
                "dep_start": round(dep_start),
                "dep_interest": round(dep_interest),
                "dep_ndfl": round(dep_ndfl),
                "dep_end": round(dep_end),
                "iis_start": round(iis_start),
                "iis_interest": round(iis_interest),
                "iis_ndfl": round(iis_ndfl),
                "iis_end": round(iis_end),
                "living_year": round(living),
                "living_month": round(LIVING_MO if living else 0),
                "extra_withdraw": round(lump),
                "iis_refund": round(refund),
                "total_end": round(dep_end + iis_end),
                "closing_iis": closing,
            }
        )
        dep = dep_end
        iis = iis_end

    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "year",
        "dep_rate_pct",
        "dep_start",
        "dep_interest",
        "dep_ndfl",
        "dep_end",
        "iis_start",
        "iis_interest",
        "iis_ndfl",
        "iis_end",
        "living_year",
        "extra_withdraw",
        "total_end",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def md_main_table(rows: list[dict]) -> str:
    """Одна широкая таблица в точности под запрошенные колонки."""
    header = (
        "| Год | Ставка депозита | Капитал на начало (депозит) | Проценты (депозит) | НДФЛ (депозит) | "
        "Капитал на конец (депозит) | Капитал на начало (ИИС) | Проценты (ИИС) | НДФЛ (ИИС) | "
        "Капитал на конец (ИИС) | Вывод 100 тыс./мес. (за год) | Доп. изъятие | Общий капитал на конец |"
    )
    sep = "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    lines = [header, sep]
    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r["year"]),
                    f"{r['dep_rate_pct']}%".replace(".", ","),
                    rub(r["dep_start"]),
                    rub(r["dep_interest"]),
                    rub(r["dep_ndfl"]),
                    rub(r["dep_end"]),
                    rub(r["iis_start"]),
                    rub(r["iis_interest"]),
                    rub(r["iis_ndfl"]),
                    rub(r["iis_end"]),
                    rub(r["living_year"]),
                    rub(r["extra_withdraw"]),
                    rub(r["total_end"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_scenario(path: Path, rows: list[dict], title: str, blurb: str, csv_name: str) -> None:
    note_close = next((r["year"] for r in rows if r.get("closing_iis")), CLOSE_IIS)
    refund_row = next((r for r in rows if r["iis_refund"] > 0), None)
    text = f"""# {title}

{blurb}

## Как читать таблицу

| Блок | Смысл |
| --- | --- |
| **Депозит** | Деньги во вкладах: ставка → начало → проценты → НДФЛ → конец |
| **ИИС** | ОФЗ на ИИС-3: начало → прирост (YTM 16,5%) → НДФЛ (0, пока счёт открыт) → конец |
| **Вывод 100 тыс./мес.** | Сумма за год: 100 000 × 12 = **1 200 000**, если рента в этом году включена |
| **Доп. изъятие** | Разовые 10 000 000 в конце 2028 |
| **Общий капитал** | Депозит конец + ИИС конец |

В год закрытия ИИС (**{note_close}**) прирост ИИС за год считается, затем всё переводится на депозиты (в таблице ИИС на конец = 0). Проценты депозита в этот год — уже на сумму после перевода. НДФЛ с финрезультата ИИС в модели = **0** (льгота); пока счёт открыт годовой НДФЛ по ИИС = **0** (отложен).

НДФЛ с %% вкладов: 13% с суммы процентов сверх необлагаемого минимума **{rub(TAX_FREE)}** (1 млн × ключ 14%).
{f"В 2027 на депозит также зачислен возврат вычета ИИС **{rub(refund_row['iis_refund'])}** (в строке года он внутри движения капитала депозита)." if refund_row else ""}

## Таблица по годам

{md_main_table(rows)}

## CSV

[`data/{csv_name}`](../data/{csv_name})

```bash
python3 scripts/cashflow_yearly.py
```
"""
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    v1 = simulate(rent_from_start=True)
    v2 = simulate(rent_from_start=False)

    write_csv(DATA / "v1_rent_now.csv", v1)
    write_csv(DATA / "v2_rent_after_3y.csv", v2)
    write_csv(DATA / "cashflow_v1_rent_now.csv", v1)
    write_csv(DATA / "cashflow_v2_rent_after_3y.csv", v2)
    write_csv(DATA / "cashflow_hold.csv", v1)
    write_csv(DATA / "cashflow_base.csv", v2)

    write_scenario(
        PLAN / "CASHFLOW_V1.md",
        v1,
        "Сценарий V1 — вывод 100 тыс./мес сразу",
        "Рента **100 000 ₽/мес с первого года**. В конце **2028** доп. изъятие **10 млн**. ИИС с ОФЗ до **2031**.",
        "v1_rent_now.csv",
    )
    write_scenario(
        PLAN / "CASHFLOW_V2.md",
        v2,
        "Сценарий V2 — вывод 100 тыс./мес после 3 лет",
        "В **2026–2028** рента 0 (капитализация). В конце **2028** изъятие **10 млн**. С **2029** — **100 000 ₽/мес**. ИИС до **2031**.",
        "v2_rent_after_3y.csv",
    )

    index = f"""# Кэшфлоу — простые таблицы по сценариям

Без сложных графиков: одна таблица на сценарий.

| Сценарий | Файл | Суть |
| --- | --- | --- |
| **V1** | [CASHFLOW_V1.md](CASHFLOW_V1.md) | 100к/мес сразу + 10 млн в 2028 |
| **V2** | [CASHFLOW_V2.md](CASHFLOW_V2.md) | 100к/мес с 2029 + 10 млн в 2028 |

### Колонки таблицы

`Год → ставка депозита → депозит (начало / % / НДФЛ / конец) → ИИС (начало / % / НДФЛ / конец) → вывод 100к/мес за год → доп. изъятие → общий капитал на конец`

```bash
python3 scripts/cashflow_yearly.py
```
"""
    (PLAN / "CASHFLOW.md").write_text(index, encoding="utf-8")
    print("Wrote plan/CASHFLOW.md")

    # печать превью V2 в консоль
    print("\nV2 preview:")
    print(
        "year | dep_start | rate | dep% | ndfl | dep_end | iis_start | iis% | iis_end | living | lump | total"
    )
    for r in v2:
        print(
            f"{r['year']} | {r['dep_start']} | {r['dep_rate_pct']} | {r['dep_interest']} | {r['dep_ndfl']} | {r['dep_end']} | "
            f"{r['iis_start']} | {r['iis_interest']} | {r['iis_end']} | {r['living_year']} | {r['extra_withdraw']} | {r['total_end']}"
        )


if __name__ == "__main__":
    main()

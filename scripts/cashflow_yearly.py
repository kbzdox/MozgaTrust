#!/usr/bin/env python3
"""Кэшфлоу MozgaTrust: помесячный учёт → годовая таблица.

План:
- База 20 млн = депозит + ИИС(ОФЗ).
- Долю подбираем так, чтобы:
  1) через 36 мес. с депозита реально снять 10 млн целиком;
  2) пенсия 100к/мес не обрывалась до закрытия ИИС (начало 2031);
  3) на ИИС ушло максимум остатка (там ставка выше → макс. рост за 3 года).
- Каждый месяц: %% по депозиту и ИИС → съём пенсии (если уже началась).
- Дек 2028 (мес. 36): доп. изъятие 10 млн с депозита.
- Начало 2031: ИИС закрывается, сумма переходит на депозит.
- НДФЛ с %% вкладов платится в конце каждого года; по ИИС до закрытия 0.

Сценарии:
  V1 — пенсия с месяца 1
  V2 — пенсия с месяца 37
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PLAN = ROOT / "plan"

TOTAL = 20_000_000.0
LUMP = 10_000_000.0
PENSION_MO = 100_000.0
DEP_APR = 0.125
DEP_APR_AFTER = 0.09
IIS_APR = 0.165
TAX_FREE = 1_000_000.0 * 0.14
NDFL = 0.13
IIS_REFUND = 52_000.0
START_YEAR = 2026
CLOSE_YEAR = 2031  # перевод ИИС на депозит в начале года


def rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")


def mrate(apr: float) -> float:
    return apr / 12.0


def ndfl_on(interest: float) -> float:
    return max(0.0, interest - TAX_FREE) * NDFL


@dataclass
class YearRow:
    year: int
    dep_rate: float
    dep_start: float
    dep_interest: float
    dep_ndfl: float
    dep_pension: float
    dep_lump: float
    dep_refund: float
    dep_from_iis: float
    dep_end: float
    iis_start: float
    iis_interest: float
    iis_ndfl: float
    iis_end: float
    total_end: float
    pension_shortfall: float  # сколько пенсии не смогли выплатить

    def check_dep(self) -> float:
        return (
            self.dep_start
            + self.dep_interest
            + self.dep_from_iis
            + self.dep_refund
            - self.dep_ndfl
            - self.dep_pension
            - self.dep_lump
            - self.dep_end
        )

    def check_iis(self) -> float:
        if self.dep_from_iis > 0:
            return (
                self.iis_start
                + self.iis_interest
                - self.iis_ndfl
                - self.dep_from_iis
                - self.iis_end
            )
        return self.iis_start + self.iis_interest - self.iis_ndfl - self.iis_end


def simulate(dep0: float, pension_from_month: int) -> list[YearRow]:
    dep = dep0
    iis = TOTAL - dep0
    rows: list[YearRow] = []

    for year in range(START_YEAR, 2041):
        apr = DEP_APR if year <= 2030 else DEP_APR_AFTER
        dep_start, iis_start = dep, iis
        dep_interest = iis_interest = 0.0
        pension = lump = 0.0
        shortfall = 0.0
        refund = IIS_REFUND if year == 2027 else 0.0
        from_iis = 0.0

        if year == CLOSE_YEAR and iis > 0:
            from_iis = iis
            dep += from_iis
            iis = 0.0

        if refund:
            dep += refund

        for mon in range(1, 13):
            abs_m = (year - START_YEAR) * 12 + mon

            di = dep * mrate(apr)
            dep += di
            dep_interest += di

            if iis > 0:
                ii = iis * mrate(IIS_APR)
                iis += ii
                iis_interest += ii

            if abs_m >= pension_from_month:
                if dep >= PENSION_MO:
                    dep -= PENSION_MO
                    pension += PENSION_MO
                else:
                    shortfall += PENSION_MO - max(dep, 0.0)
                    pension += max(dep, 0.0)
                    dep = 0.0

            if abs_m == 36:
                if dep >= LUMP:
                    dep -= LUMP
                    lump = LUMP
                else:
                    lump = max(dep, 0.0)
                    dep = 0.0

        tax = ndfl_on(dep_interest)
        # налог не больше остатка
        tax_paid = min(tax, dep)
        dep -= tax_paid

        rows.append(
            YearRow(
                year=year,
                dep_rate=apr,
                dep_start=dep_start,
                dep_interest=dep_interest,
                dep_ndfl=tax_paid,
                dep_pension=pension,
                dep_lump=lump,
                dep_refund=refund,
                dep_from_iis=from_iis,
                dep_end=dep,
                iis_start=iis_start,
                iis_interest=iis_interest,
                iis_ndfl=0.0,
                iis_end=iis,
                total_end=dep + iis,
                pension_shortfall=shortfall,
            )
        )
    return rows


def allocation_ok(rows: list[YearRow]) -> bool:
    """Полное изъятие 10 млн + пенсия без дыр до конца 2030 (пока ИИС закрыт)."""
    lump_ok = any(abs(r.dep_lump - LUMP) < 1.0 for r in rows)
    # до закрытия ИИС (годы 2026–2030) не должно быть недоплаты пенсии
    pre = [r for r in rows if r.year < CLOSE_YEAR]
    pension_ok = all(r.pension_shortfall < 1.0 for r in pre)
    return lump_ok and pension_ok


def find_min_dep0(pension_from_month: int) -> float:
    """Минимальный депозит → максимальный ИИС при выполнимости условий."""
    lo, hi = 0.0, TOTAL
    best = TOTAL
    for _ in range(40):
        mid = (lo + hi) / 2
        rows = simulate(mid, pension_from_month)
        if allocation_ok(rows):
            best = mid
            hi = mid
        else:
            lo = mid
    return best


def write_csv(path: Path, rows: list[YearRow], dep0: float, scenario: str) -> None:
    fields = [
        "scenario",
        "dep0",
        "iis0",
        "year",
        "dep_rate_pct",
        "dep_start",
        "dep_interest",
        "dep_ndfl",
        "pension_year",
        "pension_shortfall",
        "extra_withdraw",
        "iis_refund",
        "from_iis",
        "dep_end",
        "dep_check",
        "iis_start",
        "iis_interest",
        "iis_ndfl",
        "iis_end",
        "iis_check",
        "total_end",
    ]
    iis0 = TOTAL - dep0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "scenario": scenario,
                    "dep0": round(dep0),
                    "iis0": round(iis0),
                    "year": r.year,
                    "dep_rate_pct": round(r.dep_rate * 100, 2),
                    "dep_start": round(r.dep_start),
                    "dep_interest": round(r.dep_interest),
                    "dep_ndfl": round(r.dep_ndfl),
                    "pension_year": round(r.dep_pension),
                    "pension_shortfall": round(r.pension_shortfall),
                    "extra_withdraw": round(r.dep_lump),
                    "iis_refund": round(r.dep_refund),
                    "from_iis": round(r.dep_from_iis),
                    "dep_end": round(r.dep_end),
                    "dep_check": round(r.check_dep(), 2),
                    "iis_start": round(r.iis_start),
                    "iis_interest": round(r.iis_interest),
                    "iis_ndfl": round(r.iis_ndfl),
                    "iis_end": round(r.iis_end),
                    "iis_check": round(r.check_iis(), 2),
                    "total_end": round(r.total_end),
                }
            )


def md_table(rows: list[YearRow]) -> str:
    h = (
        "| Год | Ставка | Депозит начало | Проценты | НДФЛ | "
        "Пенсия 100к/мес (сумма за год) | Доп. изъятие | Перевод с ИИС | "
        "Депозит конец | ИИС начало | Проценты ИИС | НДФЛ ИИС | ИИС конец | "
        "Общий капитал | Проверка |"
    )
    sep = "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    lines = [h, sep]
    for r in rows:
        months = int(round(r.dep_pension / PENSION_MO)) if r.dep_pension else 0
        pens = rub(r.dep_pension)
        if months:
            pens += f" / {months} мес"
        if r.pension_shortfall > 1:
            pens += f" ⚠️ недоплата {rub(r.pension_shortfall)}"
        ok = abs(r.check_dep()) < 1 and abs(r.check_iis()) < 1
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r.year),
                    f"{r.dep_rate*100:.1f}%".replace(".", ","),
                    rub(r.dep_start),
                    rub(r.dep_interest),
                    rub(r.dep_ndfl),
                    pens,
                    rub(r.dep_lump),
                    rub(r.dep_from_iis),
                    rub(r.dep_end),
                    rub(r.iis_start),
                    rub(r.iis_interest),
                    rub(r.iis_ndfl),
                    rub(r.iis_end),
                    rub(r.total_end),
                    "OK" if ok else rub(r.check_dep()),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_md(
    path: Path,
    *,
    title: str,
    blurb: str,
    dep0: float,
    rows: list[YearRow],
    csv_name: str,
    pension_from_month: int,
) -> None:
    iis0 = TOTAL - dep0
    y28 = next(r for r in rows if r.year == 2028)
    text = f"""# {title}

{blurb}

## Старт: как делим 20 млн

| | Сумма | Доля |
| --- | ---: | ---: |
| Депозит | **{rub(dep0)}** | {dep0/TOTAL*100:.1f}% |
| ИИС (ОФЗ, 16,5%) | **{rub(iis0)}** | {iis0/TOTAL*100:.1f}% |
| Итого | {rub(TOTAL)} | 100% |

Почему так: на депозите — **минимум**, при котором
1) в декабре 2028 снимается **ровно 10 млн**,
2) пенсия **100к/мес** не обрывается до закрытия ИИС (начало 2031),
3) всё остальное едет на ИИС (там доходность выше → максимальный рост за первые 3 года).

## Как считается каждый год

Помесячно внутри года:

1. На депозит и ИИС капают проценты  
2. Если пенсия уже началась — с депозита снимается **100 000**  
3. В месяце 36 (дек 2028) — доп. изъятие **10 000 000**  
4. В конце года с депозита платится НДФЛ с процентов  

**Формула депозита (проверка в таблице = OK):**

```text
Конец = Начало + Проценты + Перевод_с_ИИС + Вычет − НДФЛ − Пенсия_за_год − Доп_изъятие
```

Пенсия начинается с месяца **{pension_from_month}**.  
Ставка депозита: 12,5% годовых до 2030 / 9% с 2031 (в модели как APR/12 каждый месяц).  
НДФЛ вкладов: 13% с процентов сверх {rub(TAX_FREE)}. НДФЛ ИИС до закрытия: **0**.

## Таблица

{md_table(rows)}

### Коротко по факту

| Показатель | Значение |
| --- | ---: |
| Доп. изъятие в 2028 | {rub(y28.dep_lump)} |
| Депозит после изъятия (конец 2028) | {rub(y28.dep_end)} |
| ИИС конец 2028 | {rub(y28.iis_end)} |
| Всего пенсия за 2026–2040 | {rub(sum(r.dep_pension for r in rows))} |
| Всего НДФЛ с вкладов | {rub(sum(r.dep_ndfl for r in rows))} |
| Капитал конец 2040 | {rub(rows[-1].total_end)} |

CSV: [`data/{csv_name}`](../data/{csv_name})

```bash
python3 scripts/cashflow_yearly.py
```
"""
    path.write_text(text, encoding="utf-8")
    print("Wrote", path)


def main() -> None:
    dep_v1 = find_min_dep0(pension_from_month=1)
    dep_v2 = find_min_dep0(pension_from_month=37)
    # небольшой запас 10к на округления месяцев
    dep_v1 = min(TOTAL, dep_v1 + 10_000)
    dep_v2 = min(TOTAL, dep_v2 + 10_000)

    rows_v1 = simulate(dep_v1, 1)
    rows_v2 = simulate(dep_v2, 37)

    print(f"V1 dep0={dep_v1:,.0f} iis0={TOTAL-dep_v1:,.0f} ok={allocation_ok(rows_v1)}")
    print(f"V2 dep0={dep_v2:,.0f} iis0={TOTAL-dep_v2:,.0f} ok={allocation_ok(rows_v2)}")

    for tag, rows in ("V1", rows_v1), ("V2", rows_v2):
        fails = [r.year for r in rows if abs(r.check_dep()) >= 1 or abs(r.check_iis()) >= 1]
        short = [r.year for r in rows if r.pension_shortfall > 1]
        print(tag, "check_fail_years", fails, "pension_short_years", short)

    DATA.mkdir(exist_ok=True)
    write_csv(DATA / "v1_rent_now.csv", rows_v1, dep_v1, "V1")
    write_csv(DATA / "v2_rent_after_3y.csv", rows_v2, dep_v2, "V2")
    write_csv(DATA / "cashflow_v1_rent_now.csv", rows_v1, dep_v1, "V1")
    write_csv(DATA / "cashflow_v2_rent_after_3y.csv", rows_v2, dep_v2, "V2")
    write_csv(DATA / "cashflow_base.csv", rows_v2, dep_v2, "V2")
    write_csv(DATA / "cashflow_hold.csv", rows_v1, dep_v1, "V1")

    write_md(
        PLAN / "CASHFLOW_V1.md",
        title="Сценарий V1 — пенсия 100 тыс./мес сразу",
        blurb="Пенсию **100 000 ₽/мес** снимаем **с первого месяца**. Через 3 года дополнительно вынимаем **10 млн** с депозита. "
        "Деньги на ИИС до начала 2031 не трогаем — там капитализация по 16,5%.",
        dep0=dep_v1,
        rows=rows_v1,
        csv_name="v1_rent_now.csv",
        pension_from_month=1,
    )
    write_md(
        PLAN / "CASHFLOW_V2.md",
        title="Сценарий V2 — пенсия 100 тыс./мес после 3 лет",
        blurb="Первые **3 года** пенсия **0** — полная капитализация. В конце 3-го года снимаем **10 млн**. "
        "С 37-го месяца — **100 000 ₽/мес**. ИИС до начала 2031 растёт отдельно.",
        dep0=dep_v2,
        rows=rows_v2,
        csv_name="v2_rent_after_3y.csv",
        pension_from_month=37,
    )

    (PLAN / "CASHFLOW.md").write_text(
        """# Кэшфлоу

База **20 млн** делится между депозитом и ИИС так, чтобы за первые 3 года выжать максимум роста на ИИС, но:

- в декабре 2028 с депозита снималось **ровно 10 млн**;
- пенсия **100к/мес** не обрывалась, пока ИИС закрыт для вывода.

Пенсия и изъятие **реально вычитаются** из депозита каждый месяц/в момент события. В таблице есть колонка **Проверка** (формула конца депозита).

| Сценарий | Отчёт | Пенсия |
| --- | --- | --- |
| **V1** | [CASHFLOW_V1.md](CASHFLOW_V1.md) | с 1-го месяца |
| **V2** | [CASHFLOW_V2.md](CASHFLOW_V2.md) | после 3 лет (с 37-го месяца) |

```bash
python3 scripts/cashflow_yearly.py
```
""",
        encoding="utf-8",
    )

    print("\nV1 ledger:")
    for r in rows_v1:
        print(
            f"{r.year}: start={r.dep_start:,.0f} +%={r.dep_interest:,.0f} -tax={r.dep_ndfl:,.0f} "
            f"-pens={r.dep_pension:,.0f} -lump={r.dep_lump:,.0f} +iis={r.dep_from_iis:,.0f} "
            f"=> end={r.dep_end:,.0f} | iis_end={r.iis_end:,.0f} | chk={r.check_dep():.2f}"
        )

    try:
        from generate_dashboard import main as gen_dash

        gen_dash()
    except Exception as exc:  # noqa: BLE001
        print("dashboard skip:", exc)


if __name__ == "__main__":
    main()

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
  V1 — депозит + ИИС, пенсия с месяца 1
  V2 — депозит + ИИС, пенсия с месяца 37
  V3a — только депозит, пенсия с месяца 1
  V3b — только депозит, пенсия с месяца 37
  V4a — 25% ОФЗ + два депозита по 37,5%, пенсия с месяца 1
  V4b — 25% ОФЗ + два депозита по 37,5%, пенсия с месяца 37
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
# V4: максимум 25% в ОФЗ, остаток пополам в два отдельно управляемых депозита
V4_OFZ_SHARE = 0.25
V4_IIS0 = TOTAL * V4_OFZ_SHARE
V4_DEP_EACH = (TOTAL - V4_IIS0) / 2.0


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
    # опционально: два отдельно управляемых депозита (V4)
    dep_a_start: float = 0.0
    dep_a_end: float = 0.0
    dep_b_start: float = 0.0
    dep_b_end: float = 0.0
    split_deps: bool = False

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


def _draw_from_two(a: float, b: float, amount: float) -> tuple[float, float, float]:
    """Снять amount поровну с A и B; недостачу добрать со второго. Вернуть (a,b,снято)."""
    if amount <= 0:
        return a, b, 0.0
    half = amount / 2.0
    take_a = min(a, half)
    take_b = min(b, half)
    left = amount - take_a - take_b
    if left > 0:
        extra_a = min(a - take_a, left)
        take_a += extra_a
        left -= extra_a
    if left > 0:
        extra_b = min(b - take_b, left)
        take_b += extra_b
        left -= extra_b
    return a - take_a, b - take_b, take_a + take_b


def simulate(dep0: float, pension_from_month: int) -> list[YearRow]:
    dep = dep0
    iis = TOTAL - dep0
    has_iis = iis > 1.0
    rows: list[YearRow] = []

    for year in range(START_YEAR, 2041):
        apr = DEP_APR if year <= 2030 else DEP_APR_AFTER
        dep_start, iis_start = dep, iis
        dep_interest = iis_interest = 0.0
        pension = lump = 0.0
        shortfall = 0.0
        refund = IIS_REFUND if (year == 2027 and has_iis) else 0.0
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


def simulate_v4(pension_from_month: int) -> list[YearRow]:
    """25% ОФЗ на ИИС; остаток пополам в депозиты A и B (короткая ликвидность)."""
    a = V4_DEP_EACH
    b = V4_DEP_EACH
    iis = V4_IIS0
    rows: list[YearRow] = []

    for year in range(START_YEAR, 2041):
        apr = DEP_APR if year <= 2030 else DEP_APR_AFTER
        a_start, b_start, iis_start = a, b, iis
        dep_interest = iis_interest = 0.0
        pension = lump = 0.0
        shortfall = 0.0
        refund = IIS_REFUND if year == 2027 else 0.0
        from_iis = 0.0

        if year == CLOSE_YEAR and iis > 0:
            from_iis = iis
            a += from_iis / 2.0
            b += from_iis / 2.0
            iis = 0.0

        if refund:
            a += refund / 2.0
            b += refund / 2.0

        for mon in range(1, 13):
            abs_m = (year - START_YEAR) * 12 + mon

            ia = a * mrate(apr)
            ib = b * mrate(apr)
            a += ia
            b += ib
            dep_interest += ia + ib

            if iis > 0:
                ii = iis * mrate(IIS_APR)
                iis += ii
                iis_interest += ii

            if abs_m >= pension_from_month:
                a, b, took = _draw_from_two(a, b, PENSION_MO)
                pension += took
                shortfall += PENSION_MO - took

            if abs_m == 36:
                a, b, took = _draw_from_two(a, b, LUMP)
                lump = took

        tax = ndfl_on(dep_interest)
        liquid = a + b
        tax_paid = min(tax, liquid)
        if liquid > 0 and tax_paid > 0:
            # налог пропорционально остаткам A/B
            share_a = a / liquid
            pay_a = min(a, tax_paid * share_a)
            pay_b = min(b, tax_paid - pay_a)
            # добрать остаток налога, если округление
            left_tax = tax_paid - pay_a - pay_b
            if left_tax > 0:
                extra = min(a - pay_a, left_tax)
                pay_a += extra
                left_tax -= extra
            if left_tax > 0:
                pay_b += min(b - pay_b, left_tax)
            a -= pay_a
            b -= pay_b
            tax_paid = pay_a + pay_b
        else:
            tax_paid = 0.0

        dep_start = a_start + b_start
        dep_end = a + b
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
                dep_end=dep_end,
                iis_start=iis_start,
                iis_interest=iis_interest,
                iis_ndfl=0.0,
                iis_end=iis,
                total_end=dep_end + iis,
                pension_shortfall=shortfall,
                dep_a_start=a_start,
                dep_a_end=a,
                dep_b_start=b_start,
                dep_b_end=b,
                split_deps=True,
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


def write_csv(path: Path, rows: list[YearRow], dep0: float, scenario: str, iis0: float | None = None) -> None:
    fields = [
        "scenario",
        "dep0",
        "iis0",
        "dep_a0",
        "dep_b0",
        "year",
        "dep_rate_pct",
        "dep_start",
        "dep_a_start",
        "dep_b_start",
        "dep_interest",
        "dep_ndfl",
        "pension_year",
        "pension_shortfall",
        "extra_withdraw",
        "iis_refund",
        "from_iis",
        "dep_end",
        "dep_a_end",
        "dep_b_end",
        "dep_check",
        "iis_start",
        "iis_interest",
        "iis_ndfl",
        "iis_end",
        "iis_check",
        "total_end",
    ]
    if iis0 is None:
        iis0 = TOTAL - dep0
    dep_a0 = V4_DEP_EACH if rows and rows[0].split_deps else 0.0
    dep_b0 = V4_DEP_EACH if rows and rows[0].split_deps else 0.0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "scenario": scenario,
                    "dep0": round(dep0),
                    "iis0": round(iis0),
                    "dep_a0": round(dep_a0),
                    "dep_b0": round(dep_b0),
                    "year": r.year,
                    "dep_rate_pct": round(r.dep_rate * 100, 2),
                    "dep_start": round(r.dep_start),
                    "dep_a_start": round(r.dep_a_start) if r.split_deps else "",
                    "dep_b_start": round(r.dep_b_start) if r.split_deps else "",
                    "dep_interest": round(r.dep_interest),
                    "dep_ndfl": round(r.dep_ndfl),
                    "pension_year": round(r.dep_pension),
                    "pension_shortfall": round(r.pension_shortfall),
                    "extra_withdraw": round(r.dep_lump),
                    "iis_refund": round(r.dep_refund),
                    "from_iis": round(r.dep_from_iis),
                    "dep_end": round(r.dep_end),
                    "dep_a_end": round(r.dep_a_end) if r.split_deps else "",
                    "dep_b_end": round(r.dep_b_end) if r.split_deps else "",
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
    split = bool(rows and rows[0].split_deps)
    if split:
        h = (
            "| Год | Ставка | Депозит A | Депозит B | Депозит всего | Проценты | НДФЛ | "
            "Пенсия 100к/мес | Доп. изъятие | Перевод с ИИС | "
            "ИИС конец | Общий капитал | Проверка |"
        )
        sep = "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    else:
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
        if split:
            cells = [
                str(r.year),
                f"{r.dep_rate*100:.1f}%".replace(".", ","),
                rub(r.dep_a_end),
                rub(r.dep_b_end),
                rub(r.dep_end),
                rub(r.dep_interest),
                rub(r.dep_ndfl),
                pens,
                rub(r.dep_lump),
                rub(r.dep_from_iis),
                rub(r.iis_end),
                rub(r.total_end),
                "OK" if ok else rub(r.check_dep()),
            ]
        else:
            cells = [
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
        lines.append("| " + " | ".join(cells) + " |")
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
    deposit_only: bool = False,
    v4_split: bool = False,
) -> None:
    iis0 = V4_IIS0 if v4_split else (0.0 if deposit_only else TOTAL - dep0)
    y28 = next(r for r in rows if r.year == 2028)
    if v4_split:
        split = f"""## Старт: куда кладём 20 млн

| Корзина | Сумма | Доля | Зачем |
| --- | ---: | ---: | --- |
| **ОФЗ на ИИС-3** | **{rub(V4_IIS0)}** | 25% | длинный рост ~16,5%, вывод с ~2031 |
| **Депозит A** | **{rub(V4_DEP_EACH)}** | 37,5% | короткие вклады, своё управление |
| **Депозит B** | **{rub(V4_DEP_EACH)}** | 37,5% | короткие вклады, своё управление |
| Итого | {rub(TOTAL)} | 100% | |

Правила управления:

1. В ОФЗ — не больше **25%** капитала.  
2. Остальные **75%** делим **пополам** (A и B) и ведём раздельно.  
3. A и B — в основном **короткие депозиты**, чтобы можно было быстро снять.  
4. Пенсию 100к/мес и изъятие 10 млн снимаем **поровну** с A и B (если одной корзины не хватает — добираем со второй).  
5. НДФЛ считаем как у одного налогоплательщика (один необлагаемый лимит 140 тыс. на %%); если A и B — у разных людей, налог будет ниже.
"""
        how = f"""## Как считается каждый год

Помесячно:

1. На A, B и ИИС капают проценты  
2. Если пенсия началась — с A и B поровну снимается суммарно **100 000**  
3. В месяце 36 — изъятие **10 000 000** поровну с A и B  
4. В конце года — НДФЛ с суммарных %% вкладов  
5. В 2031 ИИС закрывается и делится **пополам** между A и B  

Пенсия с месяца **{pension_from_month}**. Ставка вклада: 12,5% до 2030 / 9% с 2031. ОФЗ на ИИС: 16,5%.
"""
    elif deposit_only:
        split = f"""## Старт: куда кладём 20 млн

| | Сумма | Доля |
| --- | ---: | ---: |
| Депозит | **{rub(dep0)}** | 100% |
| ИИС / ОФЗ | **0** | 0% |
| Итого | {rub(TOTAL)} | 100% |

Вариант без ОФЗ и без ИИС: весь капитал на банковских вкладах (лестница по ставкам ЦБ).
Те же цели — изъятие **10 млн** через 3 года и пенсия **100к/мес** — но без «второго двигателя» на 16,5%.
"""
        how = """## Как считается каждый год

Помесячно внутри года:

1. На депозит капают проценты  
2. Если пенсия уже началась — снимается **100 000**  
3. В месяце 36 (дек 2028) — доп. изъятие **10 000 000**  
4. В конце года платится НДФЛ с процентов  

**Формула депозита (проверка в таблице = OK):**

```text
Конец = Начало + Проценты − НДФЛ − Пенсия_за_год − Доп_изъятие
```

Пенсия начинается с месяца **{pension_from_month}**.  
Ставка депозита: 12,5% годовых до 2030 / 9% с 2031 (в модели как APR/12 каждый месяц).  
НДФЛ вкладов: 13% с процентов сверх {tax_free}. Вычета ИИС нет.
""".format(pension_from_month=pension_from_month, tax_free=rub(TAX_FREE))
    else:
        split = f"""## Старт: как делим 20 млн

| | Сумма | Доля |
| --- | ---: | ---: |
| Депозит | **{rub(dep0)}** | {dep0/TOTAL*100:.1f}% |
| ИИС (ОФЗ, 16,5%) | **{rub(iis0)}** | {iis0/TOTAL*100:.1f}% |
| Итого | {rub(TOTAL)} | 100% |

Почему так: на депозите — **минимум**, при котором
1) в декабре 2028 снимается **ровно 10 млн**,
2) пенсия **100к/мес** не обрывается до закрытия ИИС (начало 2031),
3) всё остальное едет на ИИС (там доходность выше → максимальный рост за первые 3 года).
"""
        how = f"""## Как считается каждый год

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
"""

    extra_facts = ""
    if v4_split:
        extra_facts = f"""| Депозит A конец 2028 | {rub(y28.dep_a_end)} |
| Депозит B конец 2028 | {rub(y28.dep_b_end)} |
"""

    text = f"""# {title}

{blurb}

{split}
{how}
## Таблица

{md_table(rows)}

### Коротко по факту

| Показатель | Значение |
| --- | ---: |
| Доп. изъятие в 2028 | {rub(y28.dep_lump)} |
| Депозит после изъятия (конец 2028) | {rub(y28.dep_end)} |
{extra_facts}| ИИС конец 2028 | {rub(y28.iis_end)} |
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


def summary_line(label: str, dep0: float, rows: list[YearRow], iis0: float | None = None) -> dict:
    y28 = next(r for r in rows if r.year == 2028)
    if iis0 is None:
        iis0 = TOTAL - dep0
    return {
        "label": label,
        "dep0": dep0,
        "iis0": iis0,
        "dep_end_2028": y28.dep_end,
        "iis_end_2028": y28.iis_end,
        "pension": sum(r.dep_pension for r in rows),
        "tax": sum(r.dep_ndfl for r in rows),
        "total_2040": rows[-1].total_end,
        "shortfall": sum(r.pension_shortfall for r in rows),
    }


def write_compare_md(path: Path, summaries: list[dict]) -> None:
    """Сводка V3 (только депозит) vs V1/V2 — сохраняем прежний файл."""
    rows = []
    for s in summaries:
        if not s["label"].startswith(("V1", "V2", "V3")):
            continue
        rows.append(
            "| "
            + " | ".join(
                [
                    s["label"],
                    rub(s["dep0"]),
                    rub(s["iis0"]),
                    rub(s["dep_end_2028"]),
                    rub(s["iis_end_2028"]),
                    rub(s["pension"]),
                    rub(s["tax"]),
                    f"**{rub(s['total_2040'])}**",
                ]
            )
            + " |"
        )
    v1 = next(s for s in summaries if s["label"].startswith("V1"))
    v2 = next(s for s in summaries if s["label"].startswith("V2"))
    v3a = next(s for s in summaries if s["label"].startswith("V3a"))
    v3b = next(s for s in summaries if s["label"].startswith("V3b"))
    text = f"""# Сценарий V3 — только депозит (без ОФЗ / ИИС)

Весь капитал **20 млн** лежит на банковских вкладах. ОФЗ и ИИС-3 не используем.
Те же цели: изъятие **10 млн** в декабре 2028 и пенсия **100 тыс. ₽/мес**.

Два подрежима по дате старта пенсии (чтобы сравнивать с V1 и V2 честно):

| Подрежим | Пенсия | Отчёт / CSV |
| --- | --- | --- |
| **V3a** | с 1-го месяца | [CASHFLOW_V3a.md](CASHFLOW_V3a.md) · [`v3a_deposit_only_rent_now.csv`](../data/v3a_deposit_only_rent_now.csv) |
| **V3b** | после 3 лет (с 37-го месяца) | [CASHFLOW_V3b.md](CASHFLOW_V3b.md) · [`v3b_deposit_only_rent_after_3y.csv`](../data/v3b_deposit_only_rent_after_3y.csv) |

Ставка депозита та же: **12,5%** до 2030 / **9%** с 2031. НДФЛ 13% с %% сверх {rub(TAX_FREE)}. Вычета ИИС нет.

## Сравнение с V1/V2

| Сценарий | Депозит старт | ИИС старт | Депозит конец 2028 | ИИС конец 2028 | Пенсия всего | НДФЛ | Капитал 2040 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

### Что видно из цифр

- **Без ОФЗ цели выполняются**, но к 2040 капитал заметно тоньше.
- Пенсия сразу: V1 **{rub(v1['total_2040'])}** vs V3a **{rub(v3a['total_2040'])}** → ИИС даёт примерно **+{rub(v1['total_2040'] - v3a['total_2040'])}**.
- Пенсия после 3 лет: V2 **{rub(v2['total_2040'])}** vs V3b **{rub(v3b['total_2040'])}** → ИИС даёт примерно **+{rub(v2['total_2040'] - v3b['total_2040'])}**.

Полное сравнение всех семейств (включая V4): [CASHFLOW_V4.md](CASHFLOW_V4.md).

```bash
python3 scripts/cashflow_yearly.py
```
"""
    path.write_text(text, encoding="utf-8")
    print("Wrote", path)


def write_v4_compare_md(path: Path, summaries: list[dict]) -> None:
    rows = []
    for s in summaries:
        rows.append(
            "| "
            + " | ".join(
                [
                    s["label"],
                    rub(s["dep0"]),
                    rub(s["iis0"]),
                    rub(s["dep_end_2028"]),
                    rub(s["iis_end_2028"]),
                    rub(s["pension"]),
                    rub(s["tax"]),
                    f"**{rub(s['total_2040'])}**",
                ]
            )
            + " |"
        )
    def get(prefix: str) -> dict:
        return next(s for s in summaries if s["label"].startswith(prefix))

    v1, v2 = get("V1"), get("V2")
    v3a, v3b = get("V3a"), get("V3b")
    v4a, v4b = get("V4a"), get("V4b")
    text = f"""# Сценарий V4 — 25% ОФЗ + два депозита по 37,5%

Ограничение: в ОФЗ можно вложить **только 25%** (5 млн на ИИС-3).
Остальные **15 млн** делим **пополам** — депозит A и депозит B по **7,5 млн**, каждым управляем отдельно.
Оба депозита — короткие вклады (ликвидность, можно быстро снять).

| Корзина | Старт | Доля |
| --- | ---: | ---: |
| ОФЗ / ИИС-3 | {rub(V4_IIS0)} | 25% |
| Депозит A | {rub(V4_DEP_EACH)} | 37,5% |
| Депозит B | {rub(V4_DEP_EACH)} | 37,5% |

| Подрежим | Пенсия | Отчёт |
| --- | --- | --- |
| **V4a** | с 1-го месяца | [CASHFLOW_V4a.md](CASHFLOW_V4a.md) |
| **V4b** | после 3 лет | [CASHFLOW_V4b.md](CASHFLOW_V4b.md) |

## Сравнение со всеми предыдущими вариантами

| Сценарий | Депозит старт | ИИС/ОФЗ | Депозит конец 2028 | ИИС конец 2028 | Пенсия всего | НДФЛ | Капитал 2040 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

### Что видно

- V4 выполняет те же цели (10 млн в 2028 + 100к/мес без дыр).
- Капитал 2040 при пенсии сразу: **V1 {rub(v1['total_2040'])}** > **V4a {rub(v4a['total_2040'])}** > **V3a {rub(v3a['total_2040'])}**.
  Лимит 25% ОФЗ не дотягивает до оптимизированного V1 (~41% ИИС).
- При пенсии после 3 лет: **V2 {rub(v2['total_2040'])}** > **V4b {rub(v4b['total_2040'])}** > **V3b {rub(v3b['total_2040'])}**.
  V4b сильнее «только вклад», но слабее V2 (там ~57% в ОФЗ).
- Плюс V4 против оптимизированных V1/V2: после −10 млн на вкладах остаётся толстая подушка
  (~{rub(v4a['dep_end_2028'])} / ~{rub(v4b['dep_end_2028'])}), а не тонкий хвост ~2,1 млн.
- Две корзины A/B сами по себе доходность не меняют (одинаковая ставка) — это про **раздельное управление и ликвидность**.

```bash
python3 scripts/cashflow_yearly.py
```
"""
    path.write_text(text, encoding="utf-8")
    print("Wrote", path)


def main() -> None:
    dep_v1 = find_min_dep0(pension_from_month=1)
    dep_v2 = find_min_dep0(pension_from_month=37)
    dep_v1 = min(TOTAL, dep_v1 + 10_000)
    dep_v2 = min(TOTAL, dep_v2 + 10_000)
    dep_v3 = TOTAL
    dep_v4 = TOTAL - V4_IIS0  # 15 млн суммарно в A+B

    rows_v1 = simulate(dep_v1, 1)
    rows_v2 = simulate(dep_v2, 37)
    rows_v3a = simulate(dep_v3, 1)
    rows_v3b = simulate(dep_v3, 37)
    rows_v4a = simulate_v4(1)
    rows_v4b = simulate_v4(37)

    print(f"V1  dep0={dep_v1:,.0f} iis0={TOTAL-dep_v1:,.0f} ok={allocation_ok(rows_v1)}")
    print(f"V2  dep0={dep_v2:,.0f} iis0={TOTAL-dep_v2:,.0f} ok={allocation_ok(rows_v2)}")
    print(f"V3a dep0={dep_v3:,.0f} iis0=0 ok={allocation_ok(rows_v3a)}")
    print(f"V3b dep0={dep_v3:,.0f} iis0=0 ok={allocation_ok(rows_v3b)}")
    print(f"V4a depA=B={V4_DEP_EACH:,.0f} iis0={V4_IIS0:,.0f} ok={allocation_ok(rows_v4a)}")
    print(f"V4b depA=B={V4_DEP_EACH:,.0f} iis0={V4_IIS0:,.0f} ok={allocation_ok(rows_v4b)}")

    for tag, rows in (
        ("V1", rows_v1),
        ("V2", rows_v2),
        ("V3a", rows_v3a),
        ("V3b", rows_v3b),
        ("V4a", rows_v4a),
        ("V4b", rows_v4b),
    ):
        fails = [r.year for r in rows if abs(r.check_dep()) >= 1 or abs(r.check_iis()) >= 1]
        short = [r.year for r in rows if r.pension_shortfall > 1]
        print(tag, "check_fail_years", fails, "pension_short_years", short, "2040", f"{rows[-1].total_end:,.0f}")

    DATA.mkdir(exist_ok=True)
    write_csv(DATA / "v1_rent_now.csv", rows_v1, dep_v1, "V1")
    write_csv(DATA / "v2_rent_after_3y.csv", rows_v2, dep_v2, "V2")
    write_csv(DATA / "v3a_deposit_only_rent_now.csv", rows_v3a, dep_v3, "V3a")
    write_csv(DATA / "v3b_deposit_only_rent_after_3y.csv", rows_v3b, dep_v3, "V3b")
    write_csv(DATA / "v4a_25pct_ofz_rent_now.csv", rows_v4a, dep_v4, "V4a", iis0=V4_IIS0)
    write_csv(DATA / "v4b_25pct_ofz_rent_after_3y.csv", rows_v4b, dep_v4, "V4b", iis0=V4_IIS0)
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
    write_md(
        PLAN / "CASHFLOW_V3a.md",
        title="Сценарий V3a — только депозит, пенсия сразу",
        blurb="**Без ОФЗ и ИИС.** Все **20 млн** на вкладах. Пенсию **100 000 ₽/мес** снимаем **с первого месяца**. "
        "Через 3 года дополнительно вынимаем **10 млн**.",
        dep0=dep_v3,
        rows=rows_v3a,
        csv_name="v3a_deposit_only_rent_now.csv",
        pension_from_month=1,
        deposit_only=True,
    )
    write_md(
        PLAN / "CASHFLOW_V3b.md",
        title="Сценарий V3b — только депозит, пенсия после 3 лет",
        blurb="**Без ОФЗ и ИИС.** Все **20 млн** на вкладах. Первые **3 года** пенсия **0** — полная капитализация. "
        "В конце 3-го года снимаем **10 млн**. С 37-го месяца — **100 000 ₽/мес**.",
        dep0=dep_v3,
        rows=rows_v3b,
        csv_name="v3b_deposit_only_rent_after_3y.csv",
        pension_from_month=37,
        deposit_only=True,
    )
    write_md(
        PLAN / "CASHFLOW_V4a.md",
        title="Сценарий V4a — 25% ОФЗ + два депозита, пенсия сразу",
        blurb="В ОФЗ только **25%** (5 млн на ИИС). Остальное — два депозита A и B по **7,5 млн**, "
        "управляются отдельно, короткие вклады. Пенсия **100 000 ₽/мес с первого месяца**, через 3 года −10 млн.",
        dep0=dep_v4,
        rows=rows_v4a,
        csv_name="v4a_25pct_ofz_rent_now.csv",
        pension_from_month=1,
        v4_split=True,
    )
    write_md(
        PLAN / "CASHFLOW_V4b.md",
        title="Сценарий V4b — 25% ОФЗ + два депозита, пенсия после 3 лет",
        blurb="В ОФЗ только **25%** (5 млн на ИИС). Остальное — два депозита A и B по **7,5 млн**, "
        "управляются отдельно. Первые 3 года пенсия 0, затем −10 млн и **100 000 ₽/мес**.",
        dep0=dep_v4,
        rows=rows_v4b,
        csv_name="v4b_25pct_ofz_rent_after_3y.csv",
        pension_from_month=37,
        v4_split=True,
    )

    summaries = [
        summary_line("V1 — вклад+ИИС (оптимум), пенсия сразу", dep_v1, rows_v1),
        summary_line("V2 — вклад+ИИС (оптимум), пенсия после 3 лет", dep_v2, rows_v2),
        summary_line("V3a — только вклад, пенсия сразу", dep_v3, rows_v3a),
        summary_line("V3b — только вклад, пенсия после 3 лет", dep_v3, rows_v3b),
        summary_line("V4a — 25% ОФЗ + 2 депозита, пенсия сразу", dep_v4, rows_v4a, iis0=V4_IIS0),
        summary_line("V4b — 25% ОФЗ + 2 депозита, пенсия после 3 лет", dep_v4, rows_v4b, iis0=V4_IIS0),
    ]
    write_compare_md(PLAN / "CASHFLOW_V3.md", summaries)
    write_v4_compare_md(PLAN / "CASHFLOW_V4.md", summaries)

    (PLAN / "CASHFLOW.md").write_text(
        """# Кэшфлоу

База **20 млн**. Семейства сценариев:

1. **V1/V2 — депозит + ИИС (оптимум)** — максимум на ОФЗ при условиях 10 млн через 3 года и пенсии 100к/мес.
2. **V3 — только депозит** — без ОФЗ/ИИС.
3. **V4 — 25% ОФЗ + два депозита по 37,5%** — лимит на ОФЗ, остаток пополам, раздельное управление, короткая ликвидность.

| Сценарий | Отчёт | Инструменты | Пенсия |
| --- | --- | --- | --- |
| **V1** | [CASHFLOW_V1.md](CASHFLOW_V1.md) | вклад + ИИС (оптимум) | с 1-го месяца |
| **V2** | [CASHFLOW_V2.md](CASHFLOW_V2.md) | вклад + ИИС (оптимум) | после 3 лет |
| **V3** | [CASHFLOW_V3.md](CASHFLOW_V3.md) | только вклад | сводка V3a/V3b |
| **V3a / V3b** | [V3a](CASHFLOW_V3a.md) / [V3b](CASHFLOW_V3b.md) | только вклад | сразу / после 3 лет |
| **V4** | [CASHFLOW_V4.md](CASHFLOW_V4.md) | 25% ОФЗ + 2 депозита | сводка и сравнение |
| **V4a / V4b** | [V4a](CASHFLOW_V4a.md) / [V4b](CASHFLOW_V4b.md) | 25% ОФЗ + 2 депозита | сразу / после 3 лет |

```bash
python3 scripts/cashflow_yearly.py
python3 scripts/generate_dashboard.py
```

## Дашборд для семьи

- [`dashboard/index.html`](../dashboard/index.html)
- локально: `python3 -m http.server 8765 --directory dashboard`
""",
        encoding="utf-8",
    )

    try:
        from generate_dashboard import main as gen_dash

        gen_dash()
    except Exception as exc:  # noqa: BLE001
        print("dashboard skip:", exc)


if __name__ == "__main__":
    main()


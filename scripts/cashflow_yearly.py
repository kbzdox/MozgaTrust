#!/usr/bin/env python3
"""Подробный кэшфлоу MozgaTrust — отдельный отчёт и графики на каждый сценарий.

Сценарий V1: рента 100 тыс./мес с первого месяца + изъятие 10 млн через 3 года.
Сценарий V2: капитализация 3 года, затем рента 100 тыс./мес + изъятие 10 млн.

По каждому году: где деньги, суммы, ставки, доходы, расходы, налоги.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHARTS = ROOT / "plan" / "charts"
PLAN = ROOT / "plan"

DEP0 = 14_000_000.0
OFZ0 = 6_000_000.0
LUMP = 10_000_000.0
LIVING_MO = 100_000.0
LIVING_YR = LIVING_MO * 12
OFZ_YTM = 0.165
CLOSE_IIS = 2031

# НДФЛ с %% по вкладам (упрощённо): необлагаемый минимум = 1 млн × макс. ключ. ставка года
KEY_RATE = 0.14
DEPOSIT_TAX_FREE = 1_000_000.0 * KEY_RATE  # 140_000
DEPOSIT_TAX_RATE = 0.13

# Вычет на взнос ИИС-3: база до 400к → возврат ~52к (если есть НДФЛ к зачёту)
IIS_CONTRIB_REFUND = 52_000.0

DEP_RATE = {y: 0.125 for y in range(2026, 2031)}
for y in range(2031, 2041):
    DEP_RATE[y] = 0.09


def rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")


def pct(x: float) -> str:
    return f"{x * 100:.2f}%".replace(".", ",")


def deposit_ndfl(interest: float) -> tuple[float, float]:
    """Возвращает (налог, необлагаемая часть использованная)."""
    taxable = max(0.0, interest - DEPOSIT_TAX_FREE)
    return taxable * DEPOSIT_TAX_RATE, min(interest, DEPOSIT_TAX_FREE)


def simulate(*, rent_from_start: bool, scenario_id: str, title: str) -> list[dict]:
    rows: list[dict] = []
    dep = DEP0
    ofz = OFZ0
    # Накопленная «бумажная» прибыль ОФЗ для справки при закрытии ИИС
    ofz_cost = OFZ0

    for year in range(2026, 2041):
        r = DEP_RATE[year]
        dep_start, ofz_start = dep, ofz
        take_rent = rent_from_start or year >= 2029
        closing = ofz > 0 and year == CLOSE_IIS

        living = 0.0
        lump = 0.0
        ofz_growth = 0.0
        dep_interest = 0.0
        shortfall = 0.0
        iis_transfer_in = 0.0  # перевод с ИИС на «обычный» пул (не расход)
        ofz_finresult_on_close = 0.0
        tax_iis_close_if_no_relief = 0.0
        tax_iis_close_model = 0.0  # в модели = 0 при льготе

        if year <= 2028:
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep_interest = dep * r
            dep += dep_interest
            phase = "накопление"
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
                phase = "рента 100к/мес"
            if year == 2028:
                lump = min(LUMP, max(dep, 0.0))
                dep -= lump
                phase = "изъятие 10 млн" + (" + рента" if take_rent else "")
        elif closing:
            phase = "закрытие ИИС + рента"
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            ofz_finresult_on_close = max(0.0, ofz - ofz_cost)
            # Справочно: НДФЛ 13% если льготы нет (в модели льгота применяется → 0)
            tax_iis_close_if_no_relief = ofz_finresult_on_close * DEPOSIT_TAX_RATE
            tax_iis_close_model = 0.0
            iis_transfer_in = ofz
            dep += ofz
            ofz = 0.0
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
        elif ofz > 0:
            phase = "рента, ИИС открыт"
            ofz_growth = ofz * OFZ_YTM
            ofz += ofz_growth
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living
        else:
            phase = "рента, единый пул"
            dep_interest = dep * r
            dep += dep_interest
            if take_rent:
                living = min(LIVING_YR, max(dep, 0.0))
                shortfall = max(0.0, LIVING_YR - living)
                dep -= living

        tax_dep, tax_free_used = deposit_ndfl(dep_interest)
        # Налог платим из кэша/депозитов: уменьшаем остаток депозитов
        # (упрощение: налог удерживается в конце года)
        if tax_dep > 0:
            pay = min(tax_dep, max(dep, 0.0))
            dep -= pay
            tax_dep = pay  # фактически удержано

        tax_refund = IIS_CONTRIB_REFUND if year == 2027 else 0.0
        if tax_refund:
            dep += tax_refund  # возврат на счёт / кэш, учитываем в активах

        principal_eaten = max(0.0, living - dep_interest) if take_rent else 0.0
        actual_mo = living / 12.0
        if not take_rent and year < 2029:
            ok = True
        else:
            ok = shortfall <= 1e-9 and actual_mo + 1e-9 >= LIVING_MO and principal_eaten <= 1e-9

        # Где деньги (текст)
        parts = []
        if dep > 1:
            parts.append(f"депозиты {rub(dep)}")
        if ofz > 1:
            parts.append(f"ОФЗ на ИИС-3 {rub(ofz)}")
        where = "; ".join(parts) if parts else "—"

        income_total = dep_interest + ofz_growth + tax_refund
        expense_total = living + lump + tax_dep + tax_iis_close_model
        net_owner_cash = living + lump + tax_refund - tax_dep - tax_iis_close_model

        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario": title,
                "year": year,
                "phase": phase,
                "where_money_end": where,
                "dep_start": round(dep_start),
                "dep_rate_pct": round(r * 100, 2),
                "dep_interest_income": round(dep_interest),
                "dep_tax_free_allowance_used": round(tax_free_used),
                "tax_deposit_ndfl": round(tax_dep),
                "dep_end": round(max(dep, 0.0)),
                "ofz_start": round(ofz_start),
                "ofz_ytm_pct": round(OFZ_YTM * 100, 2) if ofz_start > 0 or ofz_growth > 0 else 0.0,
                "ofz_accrued_income": round(ofz_growth),
                "ofz_end": round(ofz),
                "iis_open": ofz > 0,
                "iis_transfer_to_pool": round(iis_transfer_in),
                "ofz_finresult_on_close": round(ofz_finresult_on_close),
                "tax_iis_close_model": round(tax_iis_close_model),
                "tax_iis_close_if_no_relief": round(tax_iis_close_if_no_relief),
                "tax_refund_iis_contrib": round(tax_refund),
                "income_living_withdrawn": round(living),
                "income_living_per_month": round(actual_mo),
                "expense_lump_withdraw": round(lump),
                "expense_principal_eaten": round(principal_eaten),
                "expense_living_shortfall": round(shortfall),
                "total_income_economic": round(income_total),
                "total_expense_cash": round(expense_total),
                "net_cash_to_owner": round(net_owner_cash),
                "total_capital_end": round(max(dep, 0.0) + ofz),
                "ok_100k_sustainable": ok,
            }
        )

    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def md_table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    lines = [
        "| " + " | ".join(h for h, _ in cols) + " |",
        "| " + " | ".join("---:" for _ in cols) + " |",
    ]
    for r in rows:
        cells = []
        for _, k in cols:
            v = r[k]
            if k in {"ok_100k_sustainable", "iis_open"}:
                if k == "ok_100k_sustainable":
                    cells.append("✅" if v else "❌")
                else:
                    cells.append("да" if v else "нет")
            elif isinstance(v, (int, float)) and k not in {"year", "dep_rate_pct", "ofz_ytm_pct"}:
                cells.append(rub(float(v)))
            elif k in {"dep_rate_pct", "ofz_ytm_pct"}:
                cells.append(str(v).replace(".", ","))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def plot_scenario(rows: list[dict], prefix: str, title: str) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    years = [r["year"] for r in rows]

    # 1) Where money — stacked capital
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.stackplot(
        years,
        [r["dep_end"] / 1e6 for r in rows],
        [r["ofz_end"] / 1e6 for r in rows],
        labels=["Депозиты", "ОФЗ на ИИС-3"],
        colors=["#1f6f5b", "#c4a35a"],
        alpha=0.92,
    )
    ax.axvline(2028, color="#8b3a3a", ls="--", lw=1, label="Изъятие 10 млн")
    ax.axvline(2031, color="#3a4a8b", ls="--", lw=1, label="Закрытие ИИС")
    ax.set_title(f"{title}: где деньги (млн ₽)")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{prefix}_capital.png")
    plt.close(fig)

    # 2) Income vs expense
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    income = [r["dep_interest_income"] / 1e6 for r in rows]
    ofz_inc = [r["ofz_accrued_income"] / 1e6 for r in rows]
    living = [r["income_living_withdrawn"] / 1e6 for r in rows]
    lump = [r["expense_lump_withdraw"] / 1e6 for r in rows]
    tax = [r["tax_deposit_ndfl"] / 1e6 for r in rows]
    x = years
    w = 0.35
    ax.bar([i - w / 2 for i in x], income, width=w, color="#1f6f5b", label="Доход: % депозитов")
    ax.bar(
        [i - w / 2 for i in x],
        ofz_inc,
        width=w,
        bottom=income,
        color="#c4a35a",
        label="Доход: прирост ОФЗ (на ИИС)",
    )
    ax.bar([i + w / 2 for i in x], living, width=w, color="#5b7c99", label="Расход: рента 100к×12")
    ax.bar(
        [i + w / 2 for i in x],
        lump,
        width=w,
        bottom=living,
        color="#8b3a3a",
        label="Расход: изъятие 10 млн",
    )
    ax.plot(x, tax, color="#222222", lw=1.5, marker=".", label="НДФЛ с %% вкладов")
    ax.set_title(f"{title}: доходы и расходы, млн ₽")
    ax.set_ylabel("млн ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2025.5, 2040.5)
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{prefix}_income_expense.png")
    plt.close(fig)

    # 3) Taxes detail
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=140)
    ax.bar(
        years,
        [r["tax_deposit_ndfl"] / 1000 for r in rows],
        color="#8b3a3a",
        label="НДФЛ с %% вкладов",
    )
    ax.bar(
        years,
        [-r["tax_refund_iis_contrib"] / 1000 for r in rows],
        color="#1f6f5b",
        label="Возврат вычета ИИС (минус = приток)",
    )
    ax.plot(
        years,
        [r["tax_iis_close_if_no_relief"] / 1000 for r in rows],
        color="#c4a35a",
        lw=1.8,
        marker="o",
        ms=4,
        label="НДФЛ при закрытии ИИС БЕЗ льготы (справка)",
    )
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_title(f"{title}: налоги, тыс. ₽")
    ax.set_ylabel("тыс. ₽")
    ax.set_xlabel("Год")
    ax.legend(loc="best", frameon=False, fontsize=8)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{prefix}_taxes.png")
    plt.close(fig)

    # 4) Monthly living
    fig, ax = plt.subplots(figsize=(11, 4.8), dpi=140)
    ax.plot(
        years,
        [r["income_living_per_month"] / 1000 for r in rows],
        color="#1f6f5b",
        lw=2.2,
        marker="o",
        ms=4,
        label="Фактическая рента",
    )
    ax.axhline(100, color="#8b3a3a", ls="--", label="Цель 100к")
    eaten = [r["expense_principal_eaten"] / 1000 for r in rows]
    ax.bar(years, eaten, color="#c4a35a", alpha=0.55, label="Проедание тела, тыс./год")
    ax.set_title(f"{title}: рента тыс. ₽/мес и проедание тела")
    ax.set_ylabel("тыс. ₽")
    ax.set_xlabel("Год")
    ax.set_xlim(2026, 2040)
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{prefix}_rent.png")
    plt.close(fig)


def write_scenario_md(
    rows: list[dict], path: Path, prefix: str, csv_name: str, title: str, blurb: str
) -> None:
    cols_place = [
        ("Год", "year"),
        ("Фаза", "phase"),
        ("Где деньги на конец года", "where_money_end"),
        ("Деп. %", "dep_rate_pct"),
        ("Деп. конец", "dep_end"),
        ("ОФЗ YTM %", "ofz_ytm_pct"),
        ("ОФЗ конец", "ofz_end"),
        ("Капитал всего", "total_capital_end"),
        ("ИИС открыт", "iis_open"),
    ]
    cols_income = [
        ("Год", "year"),
        ("% по вкладам", "dep_interest_income"),
        ("Прирост ОФЗ (на ИИС)", "ofz_accrued_income"),
        ("Вычет ИИС (возврат)", "tax_refund_iis_contrib"),
        ("Итого экономич. доход", "total_income_economic"),
        ("Рента на руки/мес", "income_living_per_month"),
        ("Рента за год", "income_living_withdrawn"),
        ("Разовое изъятие", "expense_lump_withdraw"),
        ("Кэш владельцу нетто", "net_cash_to_owner"),
    ]
    cols_tax = [
        ("Год", "year"),
        ("% по вкладам", "dep_interest_income"),
        ("Необлаг. минимум исп.", "dep_tax_free_allowance_used"),
        ("НДФЛ с %% вкладов", "tax_deposit_ndfl"),
        ("Возврат вычета ИИС", "tax_refund_iis_contrib"),
        ("Финрез. ОФЗ при закрытии", "ofz_finresult_on_close"),
        ("НДФЛ ИИС в модели", "tax_iis_close_model"),
        ("НДФЛ ИИС без льготы*", "tax_iis_close_if_no_relief"),
        ("Проедание тела", "expense_principal_eaten"),
        ("100к без проедания", "ok_100k_sustainable"),
    ]

    totals = {
        "living": sum(r["income_living_withdrawn"] for r in rows),
        "lump": sum(r["expense_lump_withdraw"] for r in rows),
        "dep_int": sum(r["dep_interest_income"] for r in rows),
        "ofz": sum(r["ofz_accrued_income"] for r in rows),
        "tax_dep": sum(r["tax_deposit_ndfl"] for r in rows),
        "refund": sum(r["tax_refund_iis_contrib"] for r in rows),
        "net": sum(r["net_cash_to_owner"] for r in rows),
    }
    gap = [r["year"] for r in rows if not r["ok_100k_sustainable"]]

    text = f"""# {title}

{blurb}

## Параметры сценария

| Параметр | Значение |
| --- | ---: |
| Старт депозиты | {rub(DEP0)} |
| Старт ОФЗ на ИИС-3 | {rub(OFZ0)} |
| Рента | {rub(LIVING_MO)}/мес = {rub(LIVING_YR)}/год |
| Изъятие | {rub(LUMP)} в конце 2028 |
| Закрытие ИИС | {CLOSE_IIS} |
| Ставка вкладов 2026–2030 / с 2031 | 12,5% / 9% |
| YTM ОФЗ | 16,5% |
| НДФЛ с %% вкладов | 13% с суммы сверх {rub(DEPOSIT_TAX_FREE)} (1 млн × ключ {pct(KEY_RATE)}) |
| Вычет ИИС на взнос | возврат {rub(IIS_CONTRIB_REFUND)} в 2027 |
| НДФЛ при закрытии ИИС | **0 в модели** (льгота на финрезультат); справочно — колонка «без льготы» |

Пересчёт: `python3 scripts/cashflow_yearly.py`

---

## Графики

![Капитал](charts/{prefix}_capital.png)

![Доходы и расходы](charts/{prefix}_income_expense.png)

![Налоги](charts/{prefix}_taxes.png)

![Рента](charts/{prefix}_rent.png)

---

## 1. Где деньги и под какой ставкой

{md_table(rows, cols_place)}

---

## 2. Доходы, рента, изъятия

{md_table(rows, cols_income)}

**Итого за 2026–2040:** рента на руки {rub(totals['living'])}; разовые изъятия {rub(totals['lump'])}; %% вкладов начислено {rub(totals['dep_int'])}; прирост ОФЗ {rub(totals['ofz'])}; нетто-кэш владельцу {rub(totals['net'])}.

---

## 3. Налоги и устойчивость 100к

{md_table(rows, cols_tax)}

\\*«Без льготы» — справочная величина, если вычет на финрезультат ИИС-3 не применить. В основной модели налог при закрытии = 0.

НДФЛ с %% вкладов суммарно: **{rub(totals['tax_dep'])}**. Возврат вычета ИИС: **{rub(totals['refund'])}**.

Годы, где 100к/мес не держатся без проедания тела: **{', '.join(map(str, gap)) if gap else 'нет'}**.

---

## CSV

Полная таблица: [`data/{csv_name}`](../data/{csv_name})
"""
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    v1 = simulate(
        rent_from_start=True,
        scenario_id="v1",
        title="V1 — 100к/мес сразу",
    )
    v2 = simulate(
        rent_from_start=False,
        scenario_id="v2",
        title="V2 — 100к/мес после 3 лет",
    )

    write_csv(DATA / "v1_rent_now.csv", v1)
    write_csv(DATA / "v2_rent_after_3y.csv", v2)
    # aliases
    write_csv(DATA / "cashflow_v1_rent_now.csv", v1)
    write_csv(DATA / "cashflow_v2_rent_after_3y.csv", v2)
    write_csv(DATA / "cashflow_hold.csv", v1)
    write_csv(DATA / "cashflow_base.csv", v2)

    plot_scenario(v1, "v1", "V1 — 100к сразу")
    plot_scenario(v2, "v2", "V2 — 100к после 3 лет")

    write_scenario_md(
        v1,
        PLAN / "CASHFLOW_V1.md",
        "v1",
        "v1_rent_now.csv",
        "Сценарий V1 — рента 100 тыс./мес с первого месяца",
        "Снимаем **100 000 ₽ каждый месяц** сразу. Через 3 года дополнительно забираем **10 млн**. "
        "ОФЗ до 2031 сидят на ИИС-3; купоны/рост там же (кэшем не приходят).",
    )
    write_scenario_md(
        v2,
        PLAN / "CASHFLOW_V2.md",
        "v2",
        "v2_rent_after_3y.csv",
        "Сценарий V2 — рента 100 тыс./мес после 3 лет",
        "Первые **3 года** проценты по вкладам капитализируем (рента 0). В конце 2028 забираем **10 млн**, "
        "с 2029 снимаем **100 000 ₽/мес**. ОФЗ на ИИС-3 до 2031.",
    )
    # Индекс CASHFLOW.md поддерживаем вручную / отдельным шаблоном в репо — не затираем здесь.

    print("V1 gaps", [r["year"] for r in v1 if not r["ok_100k_sustainable"]])
    print("V2 gaps", [r["year"] for r in v2 if not r["ok_100k_sustainable"]])


if __name__ == "__main__":
    main()

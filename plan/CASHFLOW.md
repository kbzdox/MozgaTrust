# Кэшфлоу

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

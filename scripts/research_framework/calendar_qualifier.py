"""Calendar-based qualification of firm-event observations (PR-3.6)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


_CN_HOLIDAYS = None


def _cn_holidays():
    global _CN_HOLIDAYS
    if _CN_HOLIDAYS is not None:
        return _CN_HOLIDAYS
    out = set()
    for y in range(2020, 2031):
        out.add(date(y, 1, 1))
        for d in range(1, 8):
            out.add(date(y, 10, d))
    sf = [
        date(2020, 1, 24), date(2020, 1, 25), date(2020, 1, 26), date(2020, 1, 27),
        date(2020, 1, 28), date(2020, 1, 29), date(2020, 1, 30),
        date(2021, 2, 11), date(2021, 2, 12), date(2021, 2, 13), date(2021, 2, 14),
        date(2021, 2, 15), date(2021, 2, 16), date(2021, 2, 17),
        date(2022, 1, 31), date(2022, 2, 1), date(2022, 2, 2), date(2022, 2, 3),
        date(2022, 2, 4), date(2022, 2, 5), date(2022, 2, 6),
        date(2023, 1, 21), date(2023, 1, 22), date(2023, 1, 23), date(2023, 1, 24),
        date(2023, 1, 25), date(2023, 1, 26), date(2023, 1, 27),
        date(2024, 2, 10), date(2024, 2, 11), date(2024, 2, 12), date(2024, 2, 13),
        date(2024, 2, 14), date(2024, 2, 15), date(2024, 2, 16),
        date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31),
        date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3),
        date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20),
        date(2026, 2, 21), date(2026, 2, 22), date(2026, 2, 23),
    ]
    out.update(sf)
    _CN_HOLIDAYS = out
    return out


@dataclass
class CalendarQualification:
    firm: str
    event_date: datetime
    qualified: bool
    reason: str = ""


def qualify_firm_events(
    df,
    firm_col="ticker",
    date_col="event_date",
    y_col="ret",
    estimation_days=250,
    min_good_days=120,
    holidays=None,
):
    if holidays is None:
        holidays = _cn_holidays()
    result_rows = []
    for _, row in df.iterrows():
        ev_date = row[date_col]
        if isinstance(ev_date, str):
            ev_date = datetime.fromisoformat(ev_date.replace("Z", ""))
        ev_d = ev_date.date() if isinstance(ev_date, datetime) else ev_date
        reason = ""
        qualified = True
        if ev_d in holidays:
            qualified = False
            reason = "holiday_on_event_day"
        result_rows.append({
            "firm": str(row[firm_col]),
            "event_date": ev_date,
            "qualified": qualified,
            "disqualify_reason": reason,
        })
    return pd.DataFrame(result_rows)


def aggregate_qualifications(qual):
    n = len(qual)
    nq = int(qual["qualified"].sum())
    reasons = qual[~qual["qualified"]]["disqualify_reason"].value_counts().to_dict()
    return {
        "n_total": n,
        "n_qualified": nq,
        "n_disqualified": n - nq,
        "disqualify_reasons": reasons,
    }

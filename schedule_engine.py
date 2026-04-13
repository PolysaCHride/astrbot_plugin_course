from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Sequence

from .course_types import CourseEvent


SHANGHAI_TZ = timezone(timedelta(hours=8))


def day_events(events: Sequence[CourseEvent], target_date: date) -> List[CourseEvent]:
    return [
        e for e in events if e.start_time.astimezone(SHANGHAI_TZ).date() == target_date
    ]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass(frozen=True)
class ReminderHit:
    user_id: str
    event: CourseEvent


def upcoming_within_15m(
    *,
    now: datetime,
    user_id: str,
    events: Sequence[CourseEvent],
    advance_minutes: int = 15,
) -> List[ReminderHit]:
    hits: List[ReminderHit] = []
    for e in events:
        delta = (e.start_time - now).total_seconds()
        if 0 < delta <= advance_minutes * 60:
            hits.append(ReminderHit(user_id=user_id, event=e))
    return hits

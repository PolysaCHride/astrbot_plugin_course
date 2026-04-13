from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CourseEvent:
    summary: str
    start_time: datetime
    end_time: datetime
    location: str = ""
    description: str = ""

    def reminder_key(self) -> str:
        return "|".join(
            [
                self.start_time.isoformat(),
                self.end_time.isoformat(),
                self.summary,
                self.location,
            ]
        )


@dataclass
class UserBinding:
    user_id: str
    unified_msg_origin: str
    nickname: str
    ics_file: str
    updated_at_ts: float
    # User-configurable options
    enable_daily_push: bool = False
    daily_push_time: str = "07:00"  # Format: HH:MM
    reminder_advance_minutes: int = 15

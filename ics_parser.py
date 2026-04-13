from __future__ import annotations

import json
import re
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Optional

import aiohttp
from icalendar import Calendar
from dateutil.rrule import rrulestr

try:
    from astrbot.api import logger
except Exception:
    import logging

    logger = logging.getLogger(__name__)

from .course_types import CourseEvent


SHANGHAI_TZ = timezone(timedelta(hours=8))


class IcsParser:
    def __init__(self):
        self._cache: dict[str, list[CourseEvent]] = {}

    def clear_cache(self, ics_path: str) -> None:
        self._cache.pop(ics_path, None)

    def parse_wakeup_token(self, text: str) -> Optional[str]:
        match = re.search(r"「([a-f0-9]{32})」", text)
        if not match:
            return None
        return match.group(1)

    async def fetch_wakeup_schedule(
        self, token: str
    ) -> Optional[list[dict[str, object]]]:
        url = f"https://i.wakeup.fun/share_schedule/get?key={token}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.error(f"[course] WakeUp request failed: {resp.status}")
                        return None
                    data = await resp.json()
                    if data.get("status") != 1:
                        logger.error(
                            f"[course] WakeUp API error: {data.get('message', '')}"
                        )
                        return None
                    parts = str(data.get("data", "")).strip().split("\n")
                    parsed: list[dict[str, object]] = []
                    for p in parts:
                        if not p.strip():
                            continue
                        item = json.loads(p)
                        if isinstance(item, dict):
                            normalized: dict[str, object] = {}
                            for k, v in item.items():
                                if isinstance(k, str):
                                    normalized[k] = v
                            parsed.append(normalized)
                    return parsed
            except Exception as e:
                logger.error(f"[course] WakeUp fetch failed: {e}")
                return None

    def convert_wakeup_to_ics(self, data: list[dict[str, object]]) -> Optional[str]:
        try:
            from icalendar import Calendar, Event

            if len(data) < 5:
                return None

            time_table_info = data[1]
            schedule_settings = data[2]
            course_definitions = data[3]
            course_arrangements = data[4]

            if not isinstance(time_table_info, list):
                return None
            if not isinstance(schedule_settings, dict):
                return None
            if not isinstance(course_definitions, list):
                return None
            if not isinstance(course_arrangements, list):
                return None

            course_id_to_name: dict[int, str] = {}
            for c in course_definitions:
                if not isinstance(c, dict):
                    continue
                cid = c.get("id")
                cname = c.get("courseName")
                if isinstance(cid, int) and isinstance(cname, str):
                    course_id_to_name[cid] = cname

            start_date_str = schedule_settings.get("startDate")
            if not isinstance(start_date_str, str) or not start_date_str:
                return None
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

            cal = Calendar()
            cal.add("prodid", "-//astrbot_plugin_course//")
            cal.add("version", "2.0")

            weekday_map = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

            for arrangement in course_arrangements:
                if not isinstance(arrangement, dict):
                    continue

                course_def_id = arrangement.get("id")
                if not isinstance(course_def_id, int):
                    continue
                course_name = course_id_to_name.get(course_def_id, "未知课程")

                start_week_raw = arrangement.get("startWeek")
                end_week_raw = arrangement.get("endWeek")
                day_of_week_raw = arrangement.get("day")
                start_node_raw = arrangement.get("startNode")
                step_raw = arrangement.get("step", 1)

                if not isinstance(start_week_raw, int):
                    continue
                if not isinstance(end_week_raw, int):
                    continue
                if not isinstance(day_of_week_raw, int):
                    continue
                if not isinstance(start_node_raw, int):
                    continue
                if not isinstance(step_raw, int):
                    continue

                if day_of_week_raw < 1 or day_of_week_raw > 7:
                    continue
                if start_week_raw < 1 or end_week_raw < start_week_raw:
                    continue
                if step_raw < 1:
                    continue

                start_week = start_week_raw
                end_week = end_week_raw
                day_of_week = day_of_week_raw
                start_node = start_node_raw
                step = step_raw

                teacher = str(arrangement.get("teacher", ""))
                room = str(arrangement.get("room", ""))

                start_time_str = "00:00"
                end_time_str = "00:00"
                for time_slot in time_table_info:
                    if not isinstance(time_slot, dict):
                        continue
                    node = time_slot.get("node")
                    if node != start_node:
                        continue
                    start_time_str = str(time_slot.get("startTime", "00:00"))
                    end_node = start_node + step - 1
                    for end_slot in time_table_info:
                        if not isinstance(end_slot, dict):
                            continue
                        if end_slot.get("node") == end_node:
                            end_time_str = str(end_slot.get("endTime", "00:00"))
                            break
                    break

                start_time = dt_time.fromisoformat(start_time_str)
                end_time = dt_time.fromisoformat(end_time_str)

                byday = weekday_map[day_of_week - 1]

                first_day_offset = day_of_week - start_date.weekday() - 1
                if first_day_offset < 0:
                    first_day_offset += 7
                first_day = start_date + timedelta(
                    weeks=start_week - 1, days=first_day_offset
                )

                last_day_offset = day_of_week - start_date.weekday() - 1
                if last_day_offset < 0:
                    last_day_offset += 7
                last_day = start_date + timedelta(
                    weeks=end_week - 1, days=last_day_offset
                )
                until_dt = datetime.combine(last_day, end_time)

                evt = Event()
                evt.add("summary", course_name)
                evt.add("dtstart", datetime.combine(first_day, start_time))
                evt.add("dtend", datetime.combine(first_day, end_time))
                evt.add("rrule", {"freq": "weekly", "byday": byday, "until": until_dt})
                evt.add("location", room)
                evt.add("description", f"教师: {teacher}")
                cal.add_component(evt)

            return cal.to_ical().decode("utf-8")
        except Exception as e:
            logger.error(f"[course] convert_wakeup_to_ics failed: {e}")
            return None

    def parse_ics_file(self, file_path: str) -> list[CourseEvent]:
        if file_path in self._cache:
            return self._cache[file_path]

        try:
            cal_content = open(file_path, "r", encoding="utf-8").read()
        except Exception as e:
            logger.error(f"[course] cannot read ics: {e}")
            return []

        cal = Calendar.from_ical(cal_content)
        today = datetime.now(SHANGHAI_TZ).date()

        events: list[CourseEvent] = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("summary") or "")
            description = str(component.get("description") or "")
            location = str(component.get("location") or "")
            dtstart = component.get("dtstart").dt
            dtend = component.get("dtend").dt
            rrule_str = component.get("rrule")

            if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
                dtstart = datetime.combine(dtstart, dt_time.min)
            if isinstance(dtend, date) and not isinstance(dtend, datetime):
                dtend = datetime.combine(dtend, dt_time.min)

            dtstart = (
                dtstart.astimezone(SHANGHAI_TZ)
                if getattr(dtstart, "tzinfo", None)
                else dtstart.replace(tzinfo=SHANGHAI_TZ)
            )
            dtend = (
                dtend.astimezone(SHANGHAI_TZ)
                if getattr(dtend, "tzinfo", None)
                else dtend.replace(tzinfo=SHANGHAI_TZ)
            )

            duration = dtend - dtstart

            if rrule_str:
                if "UNTIL" in rrule_str:
                    until_dt = rrule_str["UNTIL"][0]
                    if isinstance(until_dt, date) and not isinstance(
                        until_dt, datetime
                    ):
                        until_dt = datetime.combine(until_dt, dt_time.max)
                    if until_dt.tzinfo is None:
                        until_dt = until_dt.replace(tzinfo=SHANGHAI_TZ)
                    rrule_str["UNTIL"][0] = until_dt.astimezone(timezone.utc)

                dtstart_utc = dtstart.astimezone(timezone.utc)
                rule = rrulestr(rrule_str.to_ical().decode(), dtstart=dtstart_utc)

                start_of_today_utc = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                future_limit_utc = start_of_today_utc + timedelta(days=365)

                for occ_utc in rule.between(
                    start_of_today_utc, future_limit_utc, inc=True
                ):
                    occ_local = occ_utc.astimezone(SHANGHAI_TZ)
                    events.append(
                        CourseEvent(
                            summary=summary,
                            description=description,
                            location=location,
                            start_time=occ_local,
                            end_time=occ_local + duration,
                        )
                    )
            else:
                if dtstart.date() >= today:
                    events.append(
                        CourseEvent(
                            summary=summary,
                            description=description,
                            location=location,
                            start_time=dtstart,
                            end_time=dtend,
                        )
                    )

        events.sort(key=lambda e: e.start_time)
        self._cache[file_path] = events
        return events

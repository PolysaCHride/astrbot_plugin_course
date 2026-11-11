"""Exercise the LLM entry points with real bindings, calendar files and a fixed clock."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_course_binding import MAIN, STORAGE


def lesson(name, start, end, *properties):
    return "\r\n".join([
        "BEGIN:VEVENT", f"UID:{name}", f"SUMMARY:{name}", f"DTSTART:{start}",
        f"DTEND:{end}", *properties, "END:VEVENT",
    ])


def calendar(*lessons):
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Course Test//EN",
        *lessons, "END:VCALENDAR", "",
    ])


class CourseChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with patch.object(STORAGE.StarTools, "get_data_dir", return_value=Path(temp.name)):
            self.storage = STORAGE.CourseStorage("course")
        self.plugin = MAIN.CoursePlugin.__new__(MAIN.CoursePlugin)
        self.plugin._storage = self.storage
        self.plugin._parser = MAIN.IcsParser()
        self.now = datetime(2026, 11, 11, 8, 0, tzinfo=MAIN.SHANGHAI_TZ)  # Wednesday
        self.event = self.sender("alice")
        self.bind(self.event, calendar(
            lesson("周一实验", "20261109T090000", "20261109T110000"),
            lesson("早课", "20261104T073000", "20261104T083000",
                   "RRULE:FREQ=WEEKLY;COUNT=5;BYDAY=WE", "EXDATE:20261118T073000",
                   "LOCATION:理一 201"),
            lesson("自习", "20261111T090000", "20261111T100000"),
            lesson("讨论课", "20261111T090000", "20261111T100000"),
            lesson("夜间实验", "20261111T234500", "20261112T004500"),
        ))

    @staticmethod
    def sender(user, platform="weixin_personal_swkf", session="GroupMessage:group"):
        return SimpleNamespace(get_sender_id=lambda: user, unified_msg_origin=f"{platform}:{session}")

    def bind(self, event, contents):
        user = event.get_sender_id()
        self.storage.get_ics_path(user).write_bytes(contents.encode("utf-8"))
        self.storage.upsert_binding(user_id=user, unified_msg_origin=event.unified_msg_origin, nickname=user)

    async def ask(self, period, event=None, now=None):
        with patch.object(MAIN, "datetime", wraps=datetime) as clock:
            clock.now.return_value = now or self.now
            return await self.plugin.get_my_course_schedule(event or self.event, period)

    async def test_hint_only_when_tool_is_available_and_not_duplicated(self):
        req = SimpleNamespace(system_prompt="原人格", func_tool=None)
        await self.plugin.add_course_hint(self.event, req)
        self.assertEqual(req.system_prompt, "原人格")
        req.func_tool = Mock()
        req.func_tool.get_tool.return_value = None
        await self.plugin.add_course_hint(self.event, req)
        self.assertEqual(req.system_prompt, "原人格")
        req.func_tool.get_tool.return_value = object()
        await self.plugin.add_course_hint(self.event, req)
        await self.plugin.add_course_hint(self.event, req)
        req.func_tool.get_tool.assert_called_with(MAIN.TOOL_NAME)
        self.assertEqual(req.system_prompt, f"原人格\n{MAIN.CHAT_HINT}")

    async def test_local_weekday_recurrence_and_current_lesson_boundaries(self):
        data = json.loads(await self.ask("现在"))
        self.assertEqual(data["课程"], [{
            "课程": "早课", "开始": "2026-11-11 07:30", "结束": "2026-11-11 08:30", "地点": "理一 201",
        }])
        at_end = self.now.replace(hour=8, minute=30)
        self.assertEqual(json.loads(await self.ask("现在", now=at_end))["课程"], [])
        after_midnight = self.now.replace(day=12, hour=0, minute=30)
        self.assertEqual(json.loads(await self.ask("现在", now=after_midnight))["课程"][0]["课程"], "夜间实验")

    async def test_next_lesson_reports_ties_and_can_cross_midnight(self):
        data = json.loads(await self.ask("下一节"))
        self.assertEqual([row["课程"] for row in data["课程"]], ["自习", "讨论课"])
        after_last = self.now.replace(hour=23, minute=50)
        next_class = json.loads(await self.ask("下一节", now=after_last))["课程"]
        self.assertEqual(next_class[0]["开始"], "2026-11-25 07:30")

    async def test_full_week_and_specific_dates_include_past_and_exclude_cancelled_occurrence(self):
        data = json.loads(await self.ask("本周"))
        self.assertEqual((data["起始日期"], data["截止日期"]), ("2026-11-09", "2026-11-15"))
        self.assertEqual(data["课程"][0]["课程"], "周一实验")
        past = json.loads(await self.ask("2026-11-09"))
        self.assertEqual(past["总数"], 1)
        for period in ("下周三", "2026-11-18", "下周"):
            with self.subTest(period=period):
                self.assertEqual(json.loads(await self.ask(period))["总数"], 0)
        self.assertIn("无法识别", await self.ask("2026-11-31"))

    async def test_catalog_is_deduplicated(self):
        courses = json.loads(await self.ask("课程列表"))["课程"]
        self.assertEqual(courses.count("早课"), 1)
        self.assertNotIn("周一实验", courses)

    async def test_sender_isolation_and_binding_lifecycle(self):
        bob = self.sender("bob")
        self.assertIn("/绑定课表", await self.ask("今天", bob))
        self.bind(bob, calendar(lesson("化学", "20261111T130000", "20261111T140000")))
        self.assertEqual([e["课程"] for e in json.loads(await self.ask("今天", bob))["课程"]], ["化学"])
        private_bob = self.sender("bob", session="FriendMessage:bob")
        self.assertEqual(await self.ask("今天", bob), await self.ask("今天", private_bob))
        other_platform = self.sender("bob", platform="another-bot")
        self.assertIn("/绑定课表", await self.ask("今天", other_platform))
        self.bind(bob, calendar())
        self.assertEqual(json.loads(await self.ask("今天", bob))["总数"], 0)
        self.storage.delete_binding("bob")
        self.assertIn("/绑定课表", await self.ask("今天", bob))

    async def test_broken_calendar_is_distinct_from_free_day(self):
        path = self.storage.get_ics_path("alice")
        path.unlink()
        self.assertIn("无法读取", await self.ask("今天"))
        path.write_text("not a calendar", encoding="utf-8")
        self.assertIn("无法读取", await self.ask("今天"))

    async def test_dense_timetable_makes_truncation_explicit(self):
        self.bind(self.event, calendar(*(
            lesson(f"课程{i}", "20261111T090000", "20261111T100000") for i in range(55)
        )))
        data = json.loads(await self.ask("今天"))
        self.assertEqual((data["总数"], len(data["课程"]), data["省略条数"]), (55, 50, 5))

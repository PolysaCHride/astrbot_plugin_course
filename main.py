from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Set

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.io import download_file
from astrbot.core.utils.session_waiter import SessionController, session_waiter

from .course_types import CourseEvent
from .ics_parser import IcsParser, SHANGHAI_TZ
from .render_templates import DAY_TMPL, WEEK_TMPL
from .schedule_engine import day_events, upcoming_within_15m, week_start
from .storage import CourseStorage


@register(
    "astrbot_plugin_course",
    "NimYA",
    "绑定个人课表，查看今日/明日/本周/下周课表，并支持开课前发送课程提醒，以及每日定时发送课表。",
    "1.5.1",
)
class CoursePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._context = context

        self._storage = CourseStorage(self.name)
        self._parser = IcsParser()

        self._reminded: Dict[str, Set[str]] = {}
        self._stop_event = asyncio.Event()
        self._reminder_task: Optional[asyncio.Task[None]] = None

    async def initialize(self):
        self._stop_event.clear()
        self._reminder_task = asyncio.create_task(self._reminder_loop())

        bindings = self._storage.load_bindings()
        for user_id, binding in bindings.items():
            if binding.enable_daily_push and binding.daily_push_time:
                await self._register_user_cron(user_id, binding.daily_push_time)

    async def terminate(self):
        self._stop_event.set()
        if self._reminder_task:
            self._reminder_task.cancel()
            try:
                await self._reminder_task
            except asyncio.CancelledError:
                pass

    @filter.command("绑定课表")
    async def bind(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        nickname = str(event.get_sender_name())

        yield event.plain_result(
            "请在 120 秒内发送 .ics 文件。\n"
            "发送\"退出\"可取消。"
        )

        @session_waiter(timeout=120, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消绑定。"))
                controller.stop()
                return

            ics_path = self._storage.get_ics_path(user_id)

            file_url = await _try_get_file_url(evt)
            if file_url:
                await evt.send(evt.plain_result("正在下载课表..."))
                try:
                    await download_file(file_url, str(ics_path))
                    self._parser.clear_cache(str(ics_path))
                    self._storage.upsert_binding(
                        user_id=user_id,
                        unified_msg_origin=evt.unified_msg_origin,
                        nickname=nickname,
                    )
                    await evt.send(evt.plain_result("绑定成功。"))
                    controller.stop()
                except Exception as e:
                    logger.error(f"[course] download ics failed: {e}")
                    await evt.send(evt.plain_result("文件下载失败，请重试。"))
                    controller.stop()
                return

            controller.keep(timeout=120, reset_timeout=True)

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("绑定超时。")
        finally:
            event.stop_event()

    @filter.command("删除课表")
    async def delete(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())

        await self._unregister_user_cron(user_id)

        ok = self._storage.delete_binding(user_id)
        self._reminded.pop(user_id, None)
        if ok:
            yield event.plain_result("已删除课表。")
        else:
            yield event.plain_result("你还没有绑定课表。")

    @filter.command("设置每日推送")
    async def set_daily_push(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        yield event.plain_result(
            "请回复以下格式设置每日推送：\n"
            "开启 HH:MM （例如：开启 07:00）\n"
            '或回复"关闭"禁用每日推送\n'
            '120秒内有效，发送"退出"可取消。'
        )

        @session_waiter(timeout=120, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消设置。"))
                controller.stop()
                return

            if text == "关闭":
                bindings = self._storage.load_bindings()
                if user_id in bindings:
                    bindings[user_id].enable_daily_push = False
                    self._storage.save_bindings(bindings)
                await self._unregister_user_cron(user_id)
                await evt.send(evt.plain_result("已关闭每日推送。"))
                controller.stop()
                return

            parts = text.split()
            if len(parts) == 2 and parts[0] == "开启":
                time_str = parts[1]
                if not _is_valid_time_format(time_str):
                    controller.keep(timeout=120, reset_timeout=True)
                    return

                bindings = self._storage.load_bindings()
                if user_id in bindings:
                    bindings[user_id].enable_daily_push = True
                    bindings[user_id].daily_push_time = time_str
                    self._storage.save_bindings(bindings)

                await self._unregister_user_cron(user_id)
                await self._register_user_cron(user_id, time_str)

                await evt.send(
                    evt.plain_result(f"已开启每日推送，推送时间：{time_str}")
                )
                controller.stop()
                return

            controller.keep(timeout=120, reset_timeout=True)

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("设置超时。")
        finally:
            event.stop_event()

    @filter.command("设置提醒时间")
    async def set_reminder_time(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        yield event.plain_result(
            "请回复提前提醒的分钟数（例如：15 表示提前15分钟）\n"
            '120秒内有效，发送"退出"可取消。'
        )

        @session_waiter(timeout=120, record_history_chains=False)
        async def waiter(controller: SessionController, evt: AstrMessageEvent):
            text = (evt.message_str or "").strip()
            if text == "退出":
                await evt.send(evt.plain_result("已取消设置。"))
                controller.stop()
                return

            try:
                minutes = int(text)
                if minutes < 1 or minutes > 120:
                    controller.keep(timeout=120, reset_timeout=True)
                    return

                bindings = self._storage.load_bindings()
                if user_id in bindings:
                    bindings[user_id].reminder_advance_minutes = minutes
                    self._storage.save_bindings(bindings)
                await evt.send(evt.plain_result(f"已设置提前 {minutes} 分钟提醒"))
                controller.stop()
            except ValueError:
                controller.keep(timeout=120, reset_timeout=True)

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("设置超时。")
        finally:
            event.stop_event()

    @filter.command("查看设置")
    async def view_settings(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        push_status = "已开启" if binding.enable_daily_push else "已关闭"
        settings_text = (
            f"当前设置：\n"
            f"每日推送：{push_status}\n"
            f"推送时间：{binding.daily_push_time}\n"
            f"提前提醒：{binding.reminder_advance_minutes} 分钟"
        )
        yield event.plain_result(settings_text)

    @filter.command("今日课表")
    async def today(self, event: AstrMessageEvent):
        async for r in self._send_day_schedule(event, day_offset=0):
            yield r

    @filter.command("明日课表")
    async def tomorrow(self, event: AstrMessageEvent):
        async for r in self._send_day_schedule(event, day_offset=1):
            yield r

    @filter.command("本周课表")
    async def week(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        ics_path = (self._storage._base_dir / binding.ics_file).resolve()
        events = self._parser.parse_ics_file(str(ics_path))

        now = datetime.now(SHANGHAI_TZ)
        today_date = now.date()
        start = week_start(today_date)
        days = []
        labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i in range(7):
            d = start + timedelta(days=i)
            day_list = day_events(events, d)
            days.append(
                {
                    "label": labels[i],
                    "date": d.strftime("%m-%d"),
                    "is_today": d == today_date,
                    "courses": [_event_view(e) for e in day_list],
                }
            )

        title = f"本周课表"
        subtitle = f"{binding.nickname} | {start.strftime('%Y-%m-%d')} ~ {(start + timedelta(days=6)).strftime('%Y-%m-%d')}"
        url = await self.html_render(
            WEEK_TMPL,
            {
                "title": title,
                "subtitle": subtitle,
                "days": days,
                "page_width": 1280,
            },
            options={"quality": 100},
        )
        yield event.image_result(url)

    @filter.command("下周课表")
    async def next_week(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        ics_path = (self._storage._base_dir / binding.ics_file).resolve()
        events = self._parser.parse_ics_file(str(ics_path))

        now = datetime.now(SHANGHAI_TZ)
        today_date = now.date()
        start = week_start(today_date) + timedelta(days=7)
        days = []
        labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i in range(7):
            d = start + timedelta(days=i)
            day_list = day_events(events, d)
            days.append(
                {
                    "label": labels[i],
                    "date": d.strftime("%m-%d"),
                    "is_today": False,
                    "courses": [_event_view(e) for e in day_list],
                }
            )

        title = f"下周课表"
        subtitle = f"{binding.nickname} | {start.strftime('%Y-%m-%d')} ~ {(start + timedelta(days=6)).strftime('%Y-%m-%d')}"
        url = await self.html_render(
            WEEK_TMPL,
            {
                "title": title,
                "subtitle": subtitle,
                "days": days,
                "page_width": 1280,
            },
            options={"quality": 100},
        )
        yield event.image_result(url)

    async def _send_day_schedule(self, event: AstrMessageEvent, *, day_offset: int):
        user_id = str(event.get_sender_id())
        binding = self._storage.get_binding(user_id)
        if not binding:
            yield event.plain_result("你还没有绑定课表。请先使用 /绑定课表")
            return

        ics_path = (self._storage._base_dir / binding.ics_file).resolve()
        events = self._parser.parse_ics_file(str(ics_path))

        now = datetime.now(SHANGHAI_TZ)
        target = now.date() + timedelta(days=day_offset)
        day_list = day_events(events, target)

        title = "今日课表" if day_offset == 0 else "明日课表"
        subtitle = f"{binding.nickname} | {target.strftime('%Y-%m-%d')}"
        courses = [_event_view(e) for e in day_list]
        url = await self.html_render(
            DAY_TMPL,
            {
                "title": title,
                "subtitle": subtitle,
                "courses": courses,
                "page_width": 500,
            },
            options={"quality": 100},
        )
        yield event.image_result(url)

    async def _register_user_cron(self, user_id: str, time_str: str) -> None:
        """为用户注册每日推送的 cron 任务"""
        try:
            hour, minute = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            logger.warning(f"[course] invalid time format for user {user_id}: {time_str}")
            return

        cron_expr = f"{minute} {hour} * * *"
        job_id = f"course_daily_push_{user_id}"

        binding = self._storage.get_binding(user_id)
        if not binding:
            return

        payload = {
            "user_id": user_id,
            "unified_msg_origin": binding.unified_msg_origin,
            "nickname": binding.nickname,
            "ics_file": binding.ics_file,
        }

        try:
            await self._context.cron_manager.add_basic_job(
                name=f"每日课表推送_{user_id}",
                cron_expression=cron_expr,
                handler=self._daily_push_handler,
                description="每日课表推送",
                timezone="Asia/Shanghai",
                payload=payload,
                enabled=True,
                persistent=True,
            )
            logger.info(f"[course] registered cron job for user {user_id} at {time_str}")
        except Exception as e:
            logger.error(f"[course] failed to register cron job for user {user_id}: {e}")

    async def _unregister_user_cron(self, user_id: str) -> None:
        """取消用户的每日推送 cron 任务"""
        job_id = f"course_daily_push_{user_id}"
        try:
            await self._context.cron_manager.delete_job(job_id)
            logger.info(f"[course] unregistered cron job for user {user_id}")
        except Exception as e:
            logger.debug(f"[course] failed to unregister cron job for user {user_id}: {e}")

    async def _daily_push_handler(self, **payload) -> None:
        """Cron 任务触发的每日推送处理函数"""
        user_id = payload.get("user_id")
        if not user_id:
            logger.warning("[course] daily push handler missing user_id")
            return

        binding = self._storage.get_binding(user_id)
        if not binding:
            logger.info(f"[course] user {user_id} binding not found, skipping daily push")
            return

        if not binding.enable_daily_push:
            logger.info(f"[course] user {user_id} daily push disabled, skipping")
            return

        try:
            ics_path = (self._storage._base_dir / binding.ics_file).resolve()
            events = self._parser.parse_ics_file(str(ics_path))
            now = datetime.now(SHANGHAI_TZ)
            today = now.date()
            day_list = day_events(events, today)

            title = "今日课表"
            subtitle = f"{binding.nickname} | {today.strftime('%Y-%m-%d')}"
            courses = [_event_view(e) for e in day_list]
            url = await self.html_render(
                DAY_TMPL,
                {
                    "title": title,
                    "subtitle": subtitle,
                    "courses": courses,
                    "page_width": 500,
                },
                options={"quality": 100},
            )

            session = MessageSession.from_str(binding.unified_msg_origin)
            chain = MessageChain([Image.fromURL(url)])
            await self._context.send_message(session, chain)
            logger.info(f"[course] daily push sent to user {user_id}")
        except Exception as e:
            logger.error(f"[course] daily push failed for user {user_id}: {e}")

    async def _reminder_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick_reminder()
            except Exception as e:
                logger.error(f"[course] reminder tick failed: {e}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def _tick_reminder(self) -> None:
        bindings = self._storage.load_bindings()
        if not bindings:
            return

        now = datetime.now(SHANGHAI_TZ)
        for user_id, binding in bindings.items():
            ics_path = (self._storage._base_dir / binding.ics_file).resolve()
            events = self._parser.parse_ics_file(str(ics_path))
            hits = upcoming_within_15m(
                now=now,
                user_id=user_id,
                events=events,
                advance_minutes=binding.reminder_advance_minutes,
            )
            if not hits:
                continue

            reminded = self._reminded.setdefault(user_id, set())
            for hit in hits:
                key = hit.event.reminder_key()
                if key in reminded:
                    continue
                reminded.add(key)
                msg = _reminder_text(hit.event, binding.reminder_advance_minutes)
                chain = MessageChain().message(msg)
                session = MessageSession.from_str(binding.unified_msg_origin)
                await self._context.send_message(session, chain)


def _event_view(e: CourseEvent) -> Dict[str, str]:
    return {
        "summary": e.summary,
        "location": e.location or "",
        "time_range": f"{e.start_time.strftime('%H:%M')} - {e.end_time.strftime('%H:%M')}",
    }


def _reminder_text(e: CourseEvent, advance_minutes: int) -> str:
    loc = e.location.strip() if e.location else ""
    if loc:
        return f"开课提醒：{advance_minutes} 分钟后上课《{e.summary}》，地点：{loc}"
    return f"开课提醒：{advance_minutes} 分钟后上课《{e.summary}》"


async def _try_get_file_url(event: AstrMessageEvent) -> Optional[str]:
    try:
        messages = event.get_messages()
        for m in messages:
            if hasattr(m, "type") and getattr(m, "type") == "File":
                get_file = getattr(m, "get_file", None)
                if not callable(get_file):
                    continue
                file_path_obj = get_file(allow_return_url=True)
                if not asyncio.iscoroutine(file_path_obj):
                    continue
                file_path = await file_path_obj
                if isinstance(file_path, str) and file_path.startswith("http"):
                    return file_path
        return None
    except Exception:
        return None


def _is_valid_time_format(time_str: str) -> bool:
    import re

    return bool(re.match(r"^([0-1][0-9]|2[0-3]):[0-5][0-9]$", time_str))

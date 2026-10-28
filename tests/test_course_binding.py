"""Exercise attachment import and binding with real ICS parsing and filesystem IO.

Only AstrBot's event/registration/network boundaries are stubbed. Run with
``python -m unittest discover -s tests -v`` after installing requirements.txt.
"""

import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).parents[1]
ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Course Test//EN\r\n"
    "BEGIN:VEVENT\r\nUID:course-1\r\nDTSTART:20991028T090000\r\n"
    "DTEND:20991028T100000\r\nSUMMARY:高等数学\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
).encode("utf-8")


class FileStub:
    """Mirror the documented File.get_file return contract at the adapter boundary."""

    def __init__(self, source="", error=None):
        self.get_file = AsyncMock(return_value=source, side_effect=error)


def _load_plugin():
    names = (
        "astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.message_components",
        "astrbot.api.star", "astrbot.core", "astrbot.core.platform",
        "astrbot.core.platform.message_session", "astrbot.core.utils",
        "astrbot.core.utils.io", "astrbot.core.utils.session_waiter",
    )
    modules = {name: types.ModuleType(name) for name in names}
    modules["astrbot.api"].logger = Mock()
    modules["astrbot.api.event"].AstrMessageEvent = Mock
    modules["astrbot.api.event"].MessageChain = Mock
    modules["astrbot.api.event"].filter = types.SimpleNamespace(
        command=lambda *args, **kwargs: lambda function: function
    )
    modules["astrbot.api.message_components"].File = FileStub
    modules["astrbot.api.message_components"].Image = Mock
    modules["astrbot.api.star"].Star = type("Star", (), {})
    modules["astrbot.api.star"].Context = Mock
    modules["astrbot.api.star"].StarTools = Mock()
    modules["astrbot.api.star"].register = lambda *args: lambda cls: cls
    modules["astrbot.core.platform.message_session"].MessageSession = Mock
    modules["astrbot.core.utils.io"].download_file = AsyncMock()
    modules["astrbot.core.utils.session_waiter"].SessionController = Mock
    modules["astrbot.core.utils.session_waiter"].session_waiter = Mock()
    package_name = "_course_binding_test_plugin"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    modules[package_name] = package
    with patch.dict(sys.modules, modules):
        main = importlib.import_module(f"{package_name}.main")
        importer = importlib.import_module(f"{package_name}.file_import")
        storage = importlib.import_module(f"{package_name}.storage")
    return main, importer, storage


MAIN, IMPORTER, STORAGE = _load_plugin()


class FileImportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.destination = self.directory / "saved.ics"
        self.destination.write_bytes(b"previous schedule")
        self.download = AsyncMock()
        patcher = patch.object(IMPORTER, "download_file", self.download)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_old_schedule_intact(self):
        self.assertEqual(self.destination.read_bytes(), b"previous schedule")
        self.assertEqual(list(self.directory.glob(".course-*")), [])

    async def test_weixin_local_file_is_copied_and_adapter_cache_is_preserved(self):
        source = self.directory / "微信课表 附件.ics"
        source.write_bytes(ICS)
        attachment = FileStub(str(source))
        await IMPORTER.import_schedule_file(attachment, self.destination)
        self.assertEqual(self.destination.read_bytes(), ICS)
        self.assertEqual(source.read_bytes(), ICS)
        attachment.get_file.assert_awaited_once_with(allow_return_url=True)
        self.download.assert_not_awaited()
        self.assertEqual(list(self.directory.glob(".course-*")), [])

    async def test_qq_http_and_https_downloads_remain_supported(self):
        async def download(url, target):
            Path(target).write_bytes(ICS)

        self.download.side_effect = download
        for scheme in ("http", "https"):
            with self.subTest(scheme=scheme):
                url = f"{scheme}://example.invalid/schedule.ics"
                await IMPORTER.import_schedule_file(FileStub(url), self.destination)
                self.assertEqual(self.destination.read_bytes(), ICS)
                self.assertEqual(self.download.await_args.args[0], url)
                self.assertEqual(list(self.directory.glob(".course-*")), [])

    async def test_same_source_and_destination_does_not_truncate_schedule(self):
        self.destination.write_bytes(ICS)
        await IMPORTER.import_schedule_file(
            FileStub(str(self.destination)), self.destination
        )
        self.assertEqual(self.destination.read_bytes(), ICS)

    async def test_empty_file_reference_reports_failure(self):
        with self.assertRaises(OSError):
            await IMPORTER.import_schedule_file(FileStub(), self.destination)
        self.assert_old_schedule_intact()

    async def test_get_file_error_is_not_swallowed(self):
        with self.assertRaisesRegex(OSError, "adapter read failed"):
            await IMPORTER.import_schedule_file(
                FileStub(error=OSError("adapter read failed")), self.destination
            )
        self.assert_old_schedule_intact()

    async def test_missing_local_file_preserves_old_schedule(self):
        with self.assertRaises(FileNotFoundError):
            await IMPORTER.import_schedule_file(
                FileStub(str(self.directory / "missing.ics")), self.destination
            )
        self.assert_old_schedule_intact()

    async def test_invalid_content_preserves_old_schedule(self):
        for content in (b"", b"not an ICS file", b"<html>expired link</html>",
                        b"BEGIN:VEVENT\r\nSUMMARY:orphan\r\nEND:VEVENT\r\n"):
            with self.subTest(content=content):
                source = self.directory / "invalid.ics"
                source.write_bytes(content)
                with self.assertRaises(IMPORTER.InvalidScheduleFile):
                    await IMPORTER.import_schedule_file(
                        FileStub(str(source)), self.destination
                    )
                self.assert_old_schedule_intact()

    async def test_partial_download_failure_removes_staging_file(self):
        async def download(url, target):
            Path(target).write_bytes(b"partial download")
            raise OSError("connection lost")

        self.download.side_effect = download
        with self.assertRaisesRegex(OSError, "connection lost"):
            await IMPORTER.import_schedule_file(
                FileStub("https://example.invalid/course.ics"), self.destination
            )
        self.assert_old_schedule_intact()

    async def test_cancelled_download_removes_staging_file(self):
        started = asyncio.Event()

        async def download(url, target):
            Path(target).write_bytes(b"partial download")
            started.set()
            await asyncio.Future()

        self.download.side_effect = download
        task = asyncio.create_task(IMPORTER.import_schedule_file(
            FileStub("https://example.invalid/course.ics"), self.destination
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_old_schedule_intact()


class BindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        with patch.object(STORAGE.StarTools, "get_data_dir", return_value=self.directory):
            storage = STORAGE.CourseStorage("astrbot_plugin_course")
        self.plugin = MAIN.CoursePlugin.__new__(MAIN.CoursePlugin)
        self.plugin._storage = storage
        self.plugin._parser = MAIN.IcsParser()
        self.user_id = "test-user@im.wechat"
        self.origin = "weixin_personal_swkf:FriendMessage:test-user@im.wechat"
        self.command_event = self.make_event(text="/绑定课表")
        self.controller = Mock()
        self.destination = storage.get_ics_path(self.user_id)

    def make_event(self, messages=(), text=""):
        event = Mock(message_str=text, unified_msg_origin=self.origin)
        event.get_sender_id.return_value = self.user_id
        event.get_sender_name.return_value = "微信用户"
        event.get_messages.return_value = list(messages)
        event.plain_result.side_effect = lambda text: text
        event.send = AsyncMock()
        return event

    async def run_binding(self, replies=(), timeout=False):
        def waiter(**kwargs):
            self.assertEqual(kwargs["timeout"], 120)

            def decorate(handler):
                async def run(event):
                    if timeout:
                        raise TimeoutError
                    for reply in replies:
                        await handler(self.controller, reply)
                return run
            return decorate

        with patch.object(MAIN, "session_waiter", waiter):
            results = [result async for result in self.plugin.bind(self.command_event)]
        self.command_event.stop_event.assert_called_once()
        return results

    async def test_weixin_upload_binds_actual_file_and_preserves_instance_origin(self):
        source = self.directory / "downloaded.ics"
        source.write_bytes(ICS)
        self.plugin._parser._cache[str(self.destination)] = ["stale"]
        upload = self.make_event([FileStub(str(source))])
        results = await self.run_binding([upload])
        self.assertEqual(len(results), 1)
        self.assertEqual(upload.send.await_args.args[0], "绑定成功。")
        binding = self.plugin._storage.get_binding(self.user_id)
        self.assertEqual(binding.unified_msg_origin, self.origin)
        self.assertEqual(binding.nickname, "微信用户")
        self.assertEqual(self.destination.read_bytes(), ICS)
        self.assertEqual(source.read_bytes(), ICS)
        events = self.plugin._parser.parse_ics_file(str(self.destination))
        self.assertEqual(events[0].summary, "高等数学")
        self.controller.keep.assert_called_with(timeout=120, reset_timeout=True)
        self.controller.stop.assert_called_once()

    async def test_invalid_rebind_preserves_schedule_binding_and_cache(self):
        self.destination.write_bytes(ICS)
        self.plugin._storage.upsert_binding(
            user_id=self.user_id, unified_msg_origin=self.origin, nickname="原昵称"
        )
        self.plugin._parser._cache[str(self.destination)] = ["cached"]
        previous_binding = self.plugin._storage.get_binding(self.user_id)
        source = self.directory / "document.docx"
        source.write_bytes(b"not a calendar")
        upload = self.make_event([FileStub(str(source))])
        await self.run_binding([upload])
        self.assertIn("不是有效的 .ics", upload.send.await_args.args[0])
        self.assertEqual(self.destination.read_bytes(), ICS)
        self.assertEqual(self.plugin._storage.get_binding(self.user_id), previous_binding)
        self.assertEqual(self.plugin._parser._cache[str(self.destination)], ["cached"])
        self.controller.stop.assert_called_once()

    async def test_attachment_read_failure_replies_instead_of_binding_timeout(self):
        upload = self.make_event([FileStub(error=OSError("download failed"))])
        results = await self.run_binding([upload])
        self.assertNotIn("绑定超时。", results)
        self.assertIn("读取或保存失败", upload.send.await_args.args[0])
        self.assertIsNone(self.plugin._storage.get_binding(self.user_id))
        self.controller.stop.assert_called_once()

    async def test_file_read_timeout_is_bounded_and_reported(self):
        upload = self.make_event([FileStub("unused")])

        async def timeout(awaitable, timeout):
            self.assertEqual(timeout, 60)
            awaitable.close()
            raise asyncio.TimeoutError

        with patch.object(MAIN.asyncio, "wait_for", timeout):
            results = await self.run_binding([upload])
        self.assertNotIn("绑定超时。", results)
        self.assertIn("课表文件读取超时", upload.send.await_args.args[0])
        self.assertIsNone(self.plugin._storage.get_binding(self.user_id))
        self.controller.stop.assert_called_once()

    async def test_text_link_prompts_for_attachment_then_can_cancel(self):
        text = self.make_event(text="https://example.invalid/share")
        cancel = self.make_event(text="退出")
        await self.run_binding([text, cancel])
        self.assertIn("未检测到课表文件", text.send.await_args.args[0])
        self.assertEqual(cancel.send.await_args.args[0], "已取消绑定。")
        self.controller.keep.assert_called_once_with(timeout=120, reset_timeout=True)
        self.controller.stop.assert_called_once()
        self.assertIsNone(self.plugin._storage.get_binding(self.user_id))

    async def test_no_upload_still_times_out(self):
        results = await self.run_binding(timeout=True)
        self.assertEqual(results[-1], "绑定超时。")
        self.assertIsNone(self.plugin._storage.get_binding(self.user_id))


if __name__ == "__main__":
    unittest.main()

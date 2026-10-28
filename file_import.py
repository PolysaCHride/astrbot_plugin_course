from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from astrbot.api.message_components import File
from astrbot.core.utils.io import download_file
from icalendar import Calendar


class InvalidScheduleFile(ValueError):
    """The attachment is not an iCalendar calendar."""


async def import_schedule_file(attachment: File, destination: Path) -> None:
    """Persist a URL or adapter-local attachment without damaging an old schedule."""
    # Weixin downloads and decrypts inbound files before emitting a File component.
    # AstrBot normalizes local paths (including file:// URIs) in get_file().
    source = await attachment.get_file(allow_return_url=True)
    if not source:
        raise OSError("The attachment has no readable file or download URL")

    # Stage beside the destination so replacement is atomic on the same filesystem.
    # Close the handle before copying/downloading, including on Windows.
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=".course-", suffix=".ics", delete=False
    ) as handle:
        staged = Path(handle.name)
    try:
        if source.startswith(("http://", "https://")):
            await download_file(source, str(staged))
        else:
            # Copy rather than move: the adapter owns its temporary attachment.
            shutil.copyfile(source, staged)

        try:
            calendar = Calendar.from_ical(staged.read_bytes())
            if calendar.name != "VCALENDAR":
                raise ValueError("Expected a VCALENDAR component")
        except ValueError as exc:
            raise InvalidScheduleFile("The attachment is not a valid ICS file") from exc

        staged.replace(destination)
    finally:
        staged.unlink(missing_ok=True)

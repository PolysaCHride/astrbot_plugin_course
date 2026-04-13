from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .course_types import UserBinding


class CourseStorage:
    def __init__(self, plugin_name: str):
        self._plugin_name = plugin_name
        self._base_dir = Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
        self._ics_dir = self._base_dir / "ics"
        self._bindings_file = self._base_dir / "bindings.json"

        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._ics_dir.mkdir(parents=True, exist_ok=True)

    def get_ics_path(self, user_id: str) -> Path:
        safe_name = "".join(ch for ch in user_id if ch.isalnum() or ch in ("-", "_"))
        if not safe_name:
            safe_name = "user"
        return self._ics_dir / f"{safe_name}.ics"

    def load_bindings(self) -> Dict[str, UserBinding]:
        if not self._bindings_file.exists():
            return {}
        try:
            raw = json.loads(self._bindings_file.read_text(encoding="utf-8"))
            bindings: Dict[str, UserBinding] = {}
            for user_id, item in raw.get("bindings", {}).items():
                if not isinstance(item, dict):
                    continue
                bindings[user_id] = UserBinding(
                    user_id=user_id,
                    unified_msg_origin=str(item.get("unified_msg_origin", "")),
                    nickname=str(item.get("nickname", "")),
                    ics_file=str(item.get("ics_file", "")),
                    updated_at_ts=float(item.get("updated_at_ts", 0.0)),
                    enable_daily_push=bool(item.get("enable_daily_push", False)),
                    daily_push_time=str(item.get("daily_push_time", "07:00")),
                    reminder_advance_minutes=int(
                        item.get("reminder_advance_minutes", 15)
                    ),
                )
            return bindings
        except Exception as e:
            logger.error(f"[course] Failed to load bindings.json: {e}")
            return {}

    def save_bindings(self, bindings: Dict[str, UserBinding]) -> None:
        payload = {
            "version": 1,
            "updated_at_ts": time.time(),
            "bindings": {uid: asdict(b) for uid, b in bindings.items()},
        }
        try:
            self._bindings_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[course] Failed to save bindings.json: {e}")

    def delete_binding(self, user_id: str) -> bool:
        bindings = self.load_bindings()
        binding = bindings.pop(user_id, None)
        if not binding:
            return False
        self.save_bindings(bindings)
        try:
            ics_path = self._base_dir / binding.ics_file
            if ics_path.exists():
                ics_path.unlink()
        except Exception as e:
            logger.warning(f"[course] Failed to delete ics file: {e}")
        return True

    def upsert_binding(
        self, *, user_id: str, unified_msg_origin: str, nickname: str
    ) -> UserBinding:
        bindings = self.load_bindings()
        ics_path = self.get_ics_path(user_id)
        rel_ics = str(ics_path.relative_to(self._base_dir)).replace("\\", "/")
        binding = UserBinding(
            user_id=user_id,
            unified_msg_origin=unified_msg_origin,
            nickname=nickname,
            ics_file=rel_ics,
            updated_at_ts=time.time(),
        )
        bindings[user_id] = binding
        self.save_bindings(bindings)
        return binding

    def get_binding(self, user_id: str) -> Optional[UserBinding]:
        return self.load_bindings().get(user_id)

"""Progress board widget extracted for packaging."""

from __future__ import annotations

import collections.abc as collections_abc
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from x_make_common_x.progress_snapshot import load_progress_snapshot

try:  # pragma: no cover - runtime import guard for UI toolkit
    from PySide6 import QtCore as _QtCore
    from PySide6 import QtGui as _QtGui
    from PySide6 import QtWidgets as _QtWidgets
except ModuleNotFoundError as exc:  # pragma: no cover - surfaced to caller
    message = "PySide6 is required to display the progress board."
    raise RuntimeError(message) from exc

QtCore = cast("Any", _QtCore)
QtGui = cast("Any", _QtGui)
QtWidgets = cast("Any", _QtWidgets)

Qt = QtCore.Qt
QTimer = QtCore.QTimer
Signal = QtCore.Signal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from threading import Event
else:
    Sequence = collections_abc.Sequence
    Event = Any

_DONE_STATUSES = {"completed", "attention", "blocked"}
_POLL_INTERVAL_MS = 500
_AUTO_CLOSE_DELAY_MS = 750


class _ChecklistItem(Protocol):
    def setText(self, text: str) -> None: ...

    def setCheckState(self, state: object) -> None: ...


class _CloseEvent(Protocol):
    """Marker protocol for Qt close events."""


class ProgressBoardWidget(QtWidgets.QWidget):  # type: ignore[name-defined]
    """Checklist panel mirroring orchestrator stage progress."""

    board_completed = Signal()

    def __init__(
        self,
        *,
        snapshot_path: Path,
        stage_definitions: Sequence[tuple[str, str]],
        worker_done_event: Event,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._snapshot_path = Path(snapshot_path)
        self._stage_definitions = [
            (str(stage_id), str(title)) for stage_id, title in stage_definitions
        ]
        self._worker_done_event = worker_done_event
        self._items: dict[str, _ChecklistItem] = {}
        self._completion_triggered = False
        self._repo_index_cache: dict[str, dict[str, object]] = {}
        self._selected_stage_id: str | None = None

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh_snapshot)
        self._timer.start()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QLabel("Initializing orchestration tooling...")
        header.setWordWrap(True)
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._status_label = header
        layout.addWidget(header)

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(splitter, stretch=1)

        stage_container = QtWidgets.QWidget(splitter)
        stage_layout = QtWidgets.QVBoxLayout(stage_container)
        stage_layout.setContentsMargins(0, 0, 0, 0)

        checklist = QtWidgets.QListWidget(stage_container)
        checklist.setAlternatingRowColors(True)
        checklist.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        checklist.itemSelectionChanged.connect(self._handle_stage_selection)
        stage_layout.addWidget(checklist)
        self._checklist = checklist

        splitter.addWidget(stage_container)

        detail_container = QtWidgets.QWidget(splitter)
        detail_layout = QtWidgets.QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        detail_label = QtWidgets.QLabel("Repository progress")
        alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        detail_label.setAlignment(alignment)
        detail_layout.addWidget(detail_label)

        detail_table = QtWidgets.QTableWidget(detail_container)
        detail_table.setColumnCount(4)
        detail_table.setHorizontalHeaderLabels(
            ["Repository", "Status", "Updated", "Messages"]
        )
        detail_table.horizontalHeader().setStretchLastSection(True)
        detail_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        detail_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        detail_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        detail_layout.addWidget(detail_table)
        self._detail_table = detail_table

        splitter.addWidget(detail_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        for stage_id, title in self._stage_definitions:
            item = QtWidgets.QListWidgetItem(f"{title} - pending")
            item.setData(Qt.ItemDataRole.UserRole, stage_id)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(Qt.CheckState.Unchecked)
            checklist.addItem(item)
            self._items[stage_id] = item

        self.setMinimumSize(640, 480)
        if self._checklist.count():
            first = self._checklist.item(0)
            if first is not None:
                self._checklist.setCurrentItem(first)
                self._selected_stage_id = str(first.data(Qt.ItemDataRole.UserRole))

    def _refresh_snapshot(self) -> None:
        snapshot = load_progress_snapshot(self._snapshot_path)
        if snapshot is None:
            if not self._completion_triggered:
                self._status_label.setText("Waiting for progress snapshot feed...")
            return

        self._update_from_snapshot(snapshot)
        if self._worker_done_event.is_set() and not self._completion_triggered:
            self._status_label.setText("Tooling finished. Command center unlocking...")
            self._handle_completion()

    def _update_from_snapshot(self, snapshot: object) -> None:
        raw_stages = getattr(snapshot, "stages", {}) or {}
        stages: dict[str, object] = {}
        for maybe_id, stage in raw_stages.items():
            stage_id = str(getattr(stage, "stage_id", maybe_id))
            stages[stage_id] = stage

        for stage_id, stage in stages.items():
            if stage_id in self._items:
                continue
            title = str(getattr(stage, "title", stage_id))
            item = QtWidgets.QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, stage_id)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._checklist.addItem(item)
            self._items[stage_id] = item
            self._stage_definitions.append((stage_id, title))

        all_done = True
        for stage_id, title in self._stage_definitions:
            item = self._items.get(stage_id)
            if item is None:
                continue
            stage = stages.get(stage_id)
            status = getattr(stage, "status", "pending")
            messages = getattr(stage, "messages", ())
            if not self._apply_stage_state(item, title, status, messages):
                all_done = False

        self._refresh_stage_repo_details(stages)
        self._update_detail_view(self._current_stage_id())

        if stages and not self._completion_triggered:
            if all_done:
                self._status_label.setText(
                    "All stages reported. Waiting for tooling shutdown..."
                )
            else:
                self._status_label.setText("Tracking orchestration stages...")

    def _apply_stage_state(
        self,
        item: _ChecklistItem,
        title: str,
        status: str,
        messages: Sequence[str],
    ) -> bool:
        status_text = str(status or "pending")
        message_suffix = self._message_suffix(messages)
        item.setText(f"{title} - {status_text}{message_suffix}")

        normalized_status = status_text.lower()
        item.setCheckState(self._check_state_for_status(normalized_status))
        return normalized_status in _DONE_STATUSES

    def _handle_stage_selection(self) -> None:
        stage_id = self._current_stage_id()
        self._selected_stage_id = stage_id
        self._update_detail_view(stage_id)

    def _current_stage_id(self) -> str | None:
        selected = self._checklist.selectedItems()
        if not selected:
            return None
        return str(selected[0].data(Qt.ItemDataRole.UserRole))

    def _refresh_stage_repo_details(self, stages: dict[str, object]) -> None:
        observed_ids: set[str] = set()
        for stage_id, stage in stages.items():
            observed_ids.add(stage_id)
            metadata = getattr(stage, "metadata", {}) or {}
            cache_entry = self._load_repo_index_payload(stage_id, metadata)
            if cache_entry is None:
                self._repo_index_cache.pop(stage_id, None)
                continue
            self._repo_index_cache[stage_id] = cache_entry

        self._prune_stale_repo_cache(observed_ids)

    def _update_detail_view(self, stage_id: str | None) -> None:
        table = self._detail_table
        if stage_id is None:
            table.setRowCount(0)
            return

        cache_entry = self._repo_index_cache.get(stage_id)
        if not cache_entry:
            table.setRowCount(0)
            return

        entries = cache_entry.get("entries", [])
        if not isinstance(entries, list):
            table.setRowCount(0)
            return

        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            display = str(entry.get("display_name") or entry.get("repo_id") or "<repo>")
            status = str(entry.get("status") or "pending")
            updated_at = str(entry.get("updated_at") or "")
            messages = entry.get("messages")
            if isinstance(messages, list):
                message_text = " | ".join(
                    str(msg) for msg in messages if str(msg).strip()
                )
            else:
                message_text = str(messages or "")

            table.setItem(row, 0, QtWidgets.QTableWidgetItem(display))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(status))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(updated_at))
            message_item = QtWidgets.QTableWidgetItem(message_text)
            detail_path = entry.get("detail_path")
            if detail_path:
                message_item.setData(Qt.ItemDataRole.ToolTipRole, str(detail_path))
            table.setItem(row, 3, message_item)

        table.resizeRowsToContents()

    def _handle_completion(self) -> None:
        if self._completion_triggered:
            return
        self._completion_triggered = True
        self._timer.stop()
        self.board_completed.emit()

    def closeEvent(self, event: _CloseEvent) -> None:  # noqa: N802 - Qt signature
        self._timer.stop()
        super().closeEvent(event)

    @staticmethod
    def _message_suffix(messages: Sequence[str]) -> str:
        for message in reversed(tuple(messages)):
            text = str(message).strip()
            if text:
                return f" ({text})"
        return ""

    @staticmethod
    def _check_state_for_status(status: str) -> object:
        normalized = status.lower().strip()
        if normalized in _DONE_STATUSES:
            return Qt.CheckState.Checked
        if normalized == "running":
            return Qt.CheckState.PartiallyChecked
        if normalized == "pending":
            return Qt.CheckState.Unchecked
        return Qt.CheckState.PartiallyChecked

    @staticmethod
    def _normalized_messages(messages_raw: object) -> list[str]:
        if isinstance(messages_raw, list):
            return [str(msg).strip() for msg in messages_raw if str(msg).strip()]
        if isinstance(messages_raw, str):
            text = messages_raw.strip()
            if text:
                return [text]
        return []

    def _normalize_repo_entry(
        self,
        entry: object,
        entries_dir: Path,
    ) -> dict[str, object] | None:
        if not isinstance(entry, dict):
            return None
        repo_id = str(entry.get("repo_id") or "")
        display = str(entry.get("display_name") or repo_id or "<repo>")
        status = str(entry.get("status") or "pending")
        updated_at = str(entry.get("updated_at") or "")
        message_preview = self._normalized_messages(entry.get("message_preview"))
        detail_path_obj = entry.get("detail_path")
        detail_path = None
        if isinstance(detail_path_obj, str) and detail_path_obj:
            detail_path = str((entries_dir / detail_path_obj).resolve())
        return {
            "repo_id": repo_id,
            "display_name": display,
            "status": status,
            "updated_at": updated_at,
            "messages": message_preview,
            "detail_path": detail_path,
        }

    def _normalize_repo_entries(
        self,
        entries_payload: object,
        entries_dir: Path,
    ) -> list[dict[str, object]]:
        normalized_entries: list[dict[str, object]] = []
        if isinstance(entries_payload, list):
            for entry in entries_payload:
                normalized_entry = self._normalize_repo_entry(entry, entries_dir)
                if normalized_entry is not None:
                    normalized_entries.append(normalized_entry)
        return normalized_entries

    @staticmethod
    def _safe_stat(path: Path) -> object | None:
        try:
            return path.stat()
        except OSError:
            return None

    @staticmethod
    def _read_json_payload(path: Path) -> dict[str, object] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _load_repo_index_payload(
        self,
        stage_id: str,
        metadata: object,
    ) -> dict[str, object] | None:
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        index_path_obj = metadata_dict.get("repo_progress_index_path")
        if not index_path_obj:
            return None
        index_path = Path(str(index_path_obj))
        stat = self._safe_stat(index_path)
        if stat is None:
            return None
        cached = self._repo_index_cache.get(stage_id)
        if cached and cached.get("mtime") == getattr(stat, "st_mtime", None):
            return cached
        payload = self._read_json_payload(index_path)
        if payload is None:
            return None
        entries_dir = Path(str(payload.get("entries_dir") or index_path.parent))
        entries = self._normalize_repo_entries(payload.get("entries"), entries_dir)
        return {
            "path": index_path,
            "mtime": getattr(stat, "st_mtime", None),
            "entries": entries,
        }

    def _prune_stale_repo_cache(self, observed_ids: set[str]) -> None:
        stale_keys = [
            stage_id
            for stage_id in list(self._repo_index_cache)
            if stage_id not in observed_ids
        ]
        for stage_id in stale_keys:
            self._repo_index_cache.pop(stage_id, None)


def run_progress_board(
    *,
    snapshot_path: Path,
    stage_definitions: Sequence[tuple[str, str]],
    worker_done_event: Event,
) -> None:
    """Display the progress board until the orchestrator worker finishes."""

    app = QtWidgets.QApplication.instance()
    created_app = False
    if app is None:
        app = QtWidgets.QApplication(sys.argv or ["x_make_progress_board_x"])
        created_app = True

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("x_make_progress_board_x - Progress Board")

    board = ProgressBoardWidget(
        snapshot_path=snapshot_path,
        stage_definitions=stage_definitions,
        worker_done_event=worker_done_event,
    )
    window.setCentralWidget(board)
    window.showMaximized()

    def _finish() -> None:
        QTimer.singleShot(_AUTO_CLOSE_DELAY_MS, window.close)

    board.board_completed.connect(_finish)

    app.exec()

    if created_app:
        app.deleteLater()
        QtWidgets.QApplication.processEvents()

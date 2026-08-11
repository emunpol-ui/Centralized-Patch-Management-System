"""
Persistent client-side storage for deployment status reports (DEPLOY-004).

The CPMS Client Agent must retain a deployment status report when it cannot
be delivered and retry it during a later communication cycle (FR-012).

This module deliberately uses a small JSON file rather than introducing a
second database, message broker, or background worker. It is local runtime
state owned by the Client Agent, not CPMS server state.

Writes are atomic: the JSON is written to a temporary file in the same
directory and then replaced into place. A corrupted queue is never silently
discarded; loading it raises ``StatusReportStoreError`` so the caller can
leave the existing file untouched and report the problem.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional


class StatusReportStoreError(Exception):
    """Raised when the persisted status-report queue cannot be read or written."""


@dataclass(frozen=True)
class PendingStatusReport:
    """One deployment status report waiting for successful transmission."""

    id: str
    target_id: str
    status: str
    exit_code: Optional[int]
    error_message: Optional[str]


class StatusReportStore:
    """
    Persist and retrieve status reports that could not be transmitted.

    The queue preserves insertion order. A later successful report for the
    same target makes older queued reports unnecessary because the server has
    already accepted a later state; those older entries are removed by
    ``acknowledge``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> List[PendingStatusReport]:
        """Load all pending reports in transmission order."""
        if not self.path.exists():
            return []

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StatusReportStoreError(
                f"Unable to read pending deployment status reports from {self.path}: {exc}"
            ) from exc

        if not isinstance(raw, list):
            raise StatusReportStoreError(
                f"Pending deployment status report store {self.path} must contain a JSON array."
            )

        reports: List[PendingStatusReport] = []
        for item in raw:
            if not isinstance(item, dict):
                raise StatusReportStoreError(
                    f"Pending deployment status report store {self.path} contains an invalid entry."
                )
            try:
                reports.append(
                    PendingStatusReport(
                        id=str(item["id"]),
                        target_id=str(item["target_id"]),
                        status=str(item["status"]),
                        exit_code=item.get("exit_code"),
                        error_message=item.get("error_message"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise StatusReportStoreError(
                    f"Pending deployment status report store {self.path} contains an invalid entry."
                ) from exc

        return reports

    def enqueue(
        self,
        *,
        target_id: str,
        status: str,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> PendingStatusReport:
        """
        Append a report unless an identical report is already pending.

        Identical duplicate suppression prevents a transient failure followed
        by another failure from creating an unbounded local queue.
        """
        reports = self.load()
        for report in reports:
            if (
                report.target_id == target_id
                and report.status == status
                and report.exit_code == exit_code
                and report.error_message == error_message
            ):
                return report

        report = PendingStatusReport(
            id=str(uuid.uuid4()),
            target_id=target_id,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
        )
        reports.append(report)
        self._save(reports)
        return report

    def acknowledge(self, report: PendingStatusReport) -> None:
        """
        Remove a successfully transmitted report and any older queued reports
        for the same target.

        If a later state was accepted by the server, older states for that
        target are no longer actionable. This also handles the case where a
        server committed an earlier report but the HTTP response was lost:
        the next later report may succeed, allowing the stale queued entry to
        be safely discarded.
        """
        reports = self.load()
        remaining: List[PendingStatusReport] = []
        found = False

        for queued in reports:
            if queued.id == report.id:
                found = True
                continue

            if queued.target_id == report.target_id and not found:
                # Older entries for this target precede the acknowledged
                # report and are superseded by the successful later state.
                continue

            remaining.append(queued)

        if found:
            self._save(remaining)

    def remove(self, report: PendingStatusReport) -> None:
        """Remove exactly one queued report without applying supersession."""
        reports = self.load()
        remaining = [queued for queued in reports if queued.id != report.id]
        if len(remaining) != len(reports):
            self._save(remaining)

    def _save(self, reports: List[PendingStatusReport]) -> None:
        """Atomically replace the persisted queue."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: List[dict[str, Any]] = [asdict(report) for report in reports]

        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f"{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(payload, temporary_file, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, self.path)
            temporary_path = None
        except OSError as exc:
            raise StatusReportStoreError(
                f"Unable to persist pending deployment status reports to {self.path}: {exc}"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


__all__ = [
    "PendingStatusReport",
    "StatusReportStore",
    "StatusReportStoreError",
]

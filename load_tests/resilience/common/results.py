from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ResultStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


@dataclass(slots=True)
class ResilienceCaseResult:
    name: str
    status: ResultStatus
    duration_ms: float
    message: str | None = None
    details: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResilienceRunResult:
    run_id: str
    started_at: str = field(
        default_factory=lambda: (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )
    cases: list[ResilienceCaseResult] = field(
        default_factory=list
    )

    def add(
        self,
        case: ResilienceCaseResult,
    ) -> None:
        self.cases.append(
            case
        )

    @property
    def passed(self) -> int:
        return sum(
            case.status == "passed"
            for case in self.cases
        )

    @property
    def failed(self) -> int:
        return sum(
            case.status == "failed"
            for case in self.cases
        )

    @property
    def skipped(self) -> int:
        return sum(
            case.status == "skipped"
            for case in self.cases
        )

    @property
    def total(self) -> int:
        return len(
            self.cases
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
            },
            "cases": [
                case.to_dict()
                for case in self.cases
            ],
        }

    def save(
        self,
        path: str | Path,
    ) -> Path:
        output = Path(path)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output.write_text(
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return output
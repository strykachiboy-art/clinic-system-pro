from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from typing import Callable, Generic, TypeVar

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


T = TypeVar("T")


@dataclass(frozen=True)
class ConcurrencyWorkerResult(Generic[T]):
    worker_index: int
    backend_pid: int | None
    value: T | None
    error: BaseException | None


class PostgresConcurrencyHarness:
    def __init__(
        self,
        database_url: str,
        *,
        workers: int = 2,
        barrier_timeout_seconds: float = 15.0,
    ) -> None:
        if not database_url.startswith("postgresql"):
            raise ValueError(
                "Concurrency harness requires a PostgreSQL URL"
            )

        if workers < 2:
            raise ValueError(
                "Concurrency harness requires at least two workers"
            )

        self.workers = workers
        self.barrier_timeout_seconds = barrier_timeout_seconds
        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def close(self) -> None:
        self.engine.dispose()

    def run(
        self,
        operation: Callable[[Session, int], T],
    ) -> list[ConcurrencyWorkerResult[T]]:
        barrier = Barrier(self.workers)

        def worker(worker_index: int) -> ConcurrencyWorkerResult[T]:
            backend_pid: int | None = None

            try:
                with self.session_factory.begin() as session:
                    backend_pid = int(
                        session.execute(
                            text("SELECT pg_backend_pid()")
                        ).scalar_one()
                    )

                    barrier.wait(
                        timeout=self.barrier_timeout_seconds
                    )

                    value = operation(
                        session,
                        worker_index,
                    )

                    return ConcurrencyWorkerResult(
                        worker_index=worker_index,
                        backend_pid=backend_pid,
                        value=value,
                        error=None,
                    )

            except BaseException as exc:
                try:
                    barrier.abort()
                except Exception:
                    pass

                return ConcurrencyWorkerResult(
                    worker_index=worker_index,
                    backend_pid=backend_pid,
                    value=None,
                    error=exc,
                )

        with ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:
            results = list(
                executor.map(
                    worker,
                    range(self.workers),
                )
            )

        return results

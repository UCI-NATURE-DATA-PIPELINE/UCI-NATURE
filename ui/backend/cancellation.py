from __future__ import annotations

import threading
from typing import Callable, Optional


class OperationCancelled(RuntimeError):
    """Raised when a long-running backend operation is asked to stop."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise OperationCancelled("Operation cancelled by user")


def raise_if_cancelled(cancel_check: Optional[Callable[[], bool]] = None) -> None:
    if cancel_check and cancel_check():
        raise OperationCancelled("Operation cancelled by user")

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass
class MLRunResult:
    output_csv: Path
    provider_name: str
    meta: Dict[str, Any]


class MLProvider(ABC):

    name: str = "base"

    @abstractmethod
    def run(
        self,
        manifest_csv: Path,
        output_csv: Path,
        **opts: Any,
    ) -> MLRunResult:
        raise NotImplementedError


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, MLProvider] = {}

    def register(self, provider: MLProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> MLProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown provider '{name}'. Available: {sorted(self._providers.keys())}")
        return self._providers[name]

    def names(self) -> Iterable[str]:
        return self._providers.keys()
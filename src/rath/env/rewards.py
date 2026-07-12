"""Reward callback contracts for online environments."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from rath.env.actions import ToolAction
from rath.env.observations import jsonable_value
from rath.session import Session

__all__ = ["RewardFn", "RewardResult"]


@dataclass(frozen=True, slots=True)
class RewardResult:
    reward: float = 0.0
    done: bool = False
    info: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        reward = float(self.reward)
        if not math.isfinite(reward):
            raise ValueError("reward must be finite")
        if not isinstance(self.info, Mapping):
            raise TypeError("info must be a mapping")
        copied = deepcopy(dict(self.info))
        jsonable_value(copied, path="reward.info")
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "done", bool(self.done))
        object.__setattr__(self, "info", MappingProxyType(copied))


RewardFn = Callable[[Session, ToolAction, Any], RewardResult]

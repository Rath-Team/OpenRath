from __future__ import annotations

import importlib.util
import pickle
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from rath.env import (
    EnvObservation,
    ToolAction,
    TrajectoryEpisode,
    TrajectoryEpisodeEnd,
    TrajectoryEpisodeStart,
    TrajectoryStep,
)
from rath.training import (
    EpisodeRollout,
    RolloutBatch,
    RolloutEpisode,
    TrainingAdapterError,
    to_verl_data_proto,
)


def _batch() -> RolloutBatch:
    episode_id = "episode"
    observation = EnvObservation(
        episode_id,
        (),
        None,
        "local",
        {"parent_session_ids": []},
        None,
    )
    trajectory = TrajectoryEpisode(
        TrajectoryEpisodeStart(episode_id, observation),
        (),
        TrajectoryEpisodeEnd(
            episode_id=episode_id,
            step_count=0,
            transition_reward=0.0,
            terminal_reward=2.0,
            total_reward=2.0,
            terminated=False,
            truncated=False,
            status="stopped",
            final_observation=observation,
        ),
    )
    summary = RolloutEpisode(
        episode_id=episode_id,
        task_id="task",
        reward=2.0,
        terminated=False,
        truncated=False,
        steps=0,
        status="stopped",
    )
    return RolloutBatch((EpisodeRollout(summary, trajectory),), {"source": "test"})


def test_importing_training_keeps_optional_modules_unloaded() -> None:
    code = (
        "import sys, rath.training; "
        "assert 'verl' not in sys.modules; "
        "assert 'torch' not in sys.modules; "
        "assert 'numpy' not in sys.modules; "
        "assert 'tensordict' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_missing_dependency_error_has_exact_install_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__("importlib").import_module

    def _import(name: str) -> Any:
        if name in {"numpy", "verl", "verl.protocol"}:
            raise ModuleNotFoundError(name)
        return real_import(name)

    monkeypatch.setattr("rath.training.adapters.verl.importlib.import_module", _import)
    with pytest.raises(TrainingAdapterError) as caught:
        to_verl_data_proto(_batch())
    assert "pip install 'openrath[verl]'" in str(caught.value)


class _FakeArray(list[Any]):
    @property
    def shape(self) -> tuple[int]:
        return (len(self),)

    def tolist(self) -> list[Any]:
        return list(self)


def _install_fake_modules(
    monkeypatch: pytest.MonkeyPatch, *, data_proto: Any = None
) -> Any:
    numpy = types.ModuleType("numpy")
    numpy.empty = lambda size, dtype=None: _FakeArray([None] * size)  # type: ignore[attr-defined]
    verl = types.ModuleType("verl")
    verl.__version__ = "0.8.0"  # type: ignore[attr-defined]
    protocol = types.ModuleType("verl.protocol")

    class _DataProto:
        @classmethod
        def from_dict(cls, **kwargs: Any) -> dict[str, Any]:
            return kwargs

    protocol.DataProto = _DataProto if data_proto is None else data_proto  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "verl", verl)
    monkeypatch.setitem(sys.modules, "verl.protocol", protocol)
    return protocol.DataProto  # type: ignore[attr-defined]


def test_fake_supported_api_receives_aligned_object_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_modules(monkeypatch)
    payload = to_verl_data_proto(
        _batch(),
        tensors={"tokens": "tensor"},
        non_tensors={"custom": ["value"]},
        meta_info={"run": "unit"},
    )
    assert payload["tensors"] == {"tokens": "tensor"}
    non_tensors = payload["non_tensors"]
    assert non_tensors["episode_ids"].tolist() == ["episode"]
    assert non_tensors["rewards"].tolist() == [2.0]
    assert non_tensors["custom"].tolist() == ["value"]
    assert payload["meta_info"] == {
        "source": "test",
        "run": "unit",
        "openrath_schema_version": 1,
        "openrath_num_episodes": 1,
        "openrath_num_steps": 0,
    }


def test_adapter_rejects_length_and_canonical_key_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_modules(monkeypatch)
    with pytest.raises(TrainingAdapterError, match="length"):
        to_verl_data_proto(_batch(), non_tensors={"custom": []})
    with pytest.raises(TrainingAdapterError, match="canonical"):
        to_verl_data_proto(_batch(), non_tensors={"episode_ids": ["override"]})
    with pytest.raises(TrainingAdapterError, match="canonical"):
        to_verl_data_proto(_batch(), meta_info={"openrath_num_episodes": 99})


@pytest.mark.parametrize("data_proto", [None, object()])
def test_incompatible_verl_api_is_focused(
    data_proto: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    if data_proto is None:
        numpy = types.ModuleType("numpy")
        verl = types.ModuleType("verl")
        verl.__version__ = "0.8.0"  # type: ignore[attr-defined]
        protocol = types.ModuleType("verl.protocol")
        monkeypatch.setitem(sys.modules, "numpy", numpy)
        monkeypatch.setitem(sys.modules, "verl", verl)
        monkeypatch.setitem(sys.modules, "verl.protocol", protocol)
    else:
        _install_fake_modules(monkeypatch, data_proto=data_proto)
    with pytest.raises(TrainingAdapterError, match="incompatible verl 0.8.0"):
        to_verl_data_proto(_batch())


def test_real_verl_data_proto_when_extra_is_installed() -> None:
    if importlib.util.find_spec("verl") is None:
        pytest.skip("openrath[verl] is not installed in the core test environment")
    result = to_verl_data_proto(_batch())
    assert type(result).__name__ == "DataProto"


def _batch_with_step() -> RolloutBatch:
    episode_id = "episode"
    observation = EnvObservation(
        episode_id, (), None, "local", {"parent_session_ids": []}, None
    )
    step = TrajectoryStep(
        episode_id=episode_id,
        step_index=0,
        action=ToolAction("write_workspace_file", {"path": "a.py"}),
        transcript_delta=(),
        tool_result={"bytes_written": 3},
        reward=1.0,
        terminated=False,
        truncated=False,
    )
    trajectory = TrajectoryEpisode(
        TrajectoryEpisodeStart(episode_id, observation),
        (step,),
        TrajectoryEpisodeEnd(
            episode_id=episode_id,
            step_count=1,
            transition_reward=1.0,
            terminal_reward=0.0,
            total_reward=1.0,
            terminated=False,
            truncated=False,
            status="stopped",
            final_observation=observation,
        ),
    )
    summary = RolloutEpisode(
        episode_id=episode_id,
        task_id="task",
        reward=1.0,
        terminated=False,
        truncated=False,
        steps=1,
        status="stopped",
    )
    return RolloutBatch((EpisodeRollout(summary, trajectory),))


def test_non_tensor_payload_is_picklable(monkeypatch: pytest.MonkeyPatch) -> None:
    # A DataProto crosses a process boundary (Ray workers, save_to_disk), so no
    # field may hold the MappingProxyType that TrajectoryStep stores internally.
    _install_fake_modules(monkeypatch)
    payload = to_verl_data_proto(_batch_with_step())
    tool_results = payload["non_tensors"]["tool_results"].tolist()
    assert tool_results == [[{"bytes_written": 3}]]
    for values in payload["non_tensors"].values():
        pickle.dumps(values.tolist())

"""
Unit tests for the scenario control server — fake Popen, no real process/SUMO.

    python -m pytest tests/test_control_server.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from control_server import PRESETS, SimRunner, build_command, scenario_list  # noqa: E402


class FakeProc:
    def __init__(self, cmd, cwd=None):
        self.cmd = cmd
        self.cwd = cwd
        self.pid = 4321
        self._alive = True
        self.terminated = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self._alive = False


def _runner():
    created = []

    def fake_popen(cmd, cwd=None):
        p = FakeProc(cmd, cwd)
        created.append(p)
        return p

    return SimRunner(popen=fake_popen), created


def test_scenario_list_shape():
    items = scenario_list()
    assert {i["id"] for i in items} == set(PRESETS)
    assert all(i["label"] and i["description"] for i in items)


def test_build_command_known_and_unknown():
    cmd = build_command("crash_arterial", python="python3", script_dir="/x")
    assert cmd[0] == "python3"
    assert cmd[1].endswith("run_traci.py")
    assert "--scenario-id" in cmd and "crash_arterial" in cmd
    assert "--close-edge" in cmd
    with pytest.raises(KeyError):
        build_command("does_not_exist")


def test_start_status_stop_lifecycle():
    runner, created = _runner()
    assert runner.running() is False

    r = runner.start("baseline_am")
    assert r["ok"] is True and r["scenario"] == "baseline_am"
    assert runner.running() is True
    st = runner.status()
    assert st["running"] is True and st["scenario"] == "baseline_am" and st["pid"] == 4321
    # spawned with cwd = 2D_simulation (parent of scripts/)
    assert created[0].cwd.endswith("2D_simulation")

    r2 = runner.stop()
    assert r2["stopped"] is True
    assert runner.running() is False
    assert runner.status()["running"] is False


def test_start_refused_when_already_running():
    runner, _ = _runner()
    runner.start("baseline_am")
    r = runner.start("crash_arterial")
    assert r["ok"] is False and "already running" in r["error"]


def test_start_unknown_scenario_rejected():
    runner, created = _runner()
    r = runner.start("nope")
    assert r["ok"] is False and not created          # nothing spawned


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

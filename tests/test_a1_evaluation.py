"""Development must never execute held-out gold plans."""

from experiments.a1 import avaliar as evaluation


def test_priority_is_actually_lowered_in_child_process():
    import os
    import subprocess
    import sys

    if os.name != "nt":
        return
    code = (
        "from experiments.a1.runtime import lower_priority; lower_priority(); "
        "import ctypes; k=ctypes.WinDLL('kernel32'); "
        "k.GetCurrentProcess.restype=ctypes.c_void_p; "
        "k.GetPriorityClass.argtypes=[ctypes.c_void_p]; "
        "print(k.GetPriorityClass(k.GetCurrentProcess()))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert int(result.stdout) == 0x4000


def test_dev_preflight_does_not_execute_held_out_gold(monkeypatch):
    checked = []

    def check_gold(sandbox, items, name):
        assert name in {"TRAIN", "DEV"}, "held-out gold executed during development"
        checked.append(name)
        return []

    def holdout_check(sandbox):
        raise AssertionError("holdout inspected during development")

    monkeypatch.setattr(evaluation, "check_gold", check_gold)
    monkeypatch.setattr(evaluation, "holdout_check", holdout_check)
    report = evaluation.preflight(None, dev_only=True)
    assert checked == ["TRAIN", "DEV"]
    assert report == {"gold_errors": []}

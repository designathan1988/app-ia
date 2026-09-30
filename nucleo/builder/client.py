"""Python client for the headless builder-6 process (bridge/builder/run.mjs).

The builder is the transition model of the planner: the AI never reimplements
the editor. It asks the editor what a command does, whether it would run, and why
it would be refused.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
from typing import Any

BRIDGE = pathlib.Path(__file__).resolve().parents[2] / "bridge" / "builder" / "run.mjs"
DEFAULT_BUILDER = os.environ.get("BUILDER_ROOT", r"C:\Codex-Shared\deepseek\builder-6")


class BuilderError(RuntimeError):
    pass


class Builder:
    def __init__(self, root: str = DEFAULT_BUILDER, node: str = "node") -> None:
        self.proc = subprocess.Popen(
            [node, str(BRIDGE), root],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        first = self._read()
        if not first.get("ready"):
            raise BuilderError(f"ponte não iniciou: {first}")

    def _read(self) -> dict:
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise BuilderError(f"ponte encerrou: {err[-2000:]}")
        return json.loads(line)

    def call(self, op: str, **payload: Any) -> dict:
        self.proc.stdin.write(json.dumps({"op": op, **payload}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        reply = self._read()
        if "error" in reply:
            raise BuilderError(reply["error"])
        return reply

    # -- convenience -------------------------------------------------------
    def reset(self, document: dict | None = None, selection: list | None = None) -> None:
        self.call("reset", document=document, selection=selection or [])

    def dispatch(self, command: str, **args: Any) -> dict:
        return self.call("dispatch", command=command, args=args)

    def state(self) -> dict:
        return self.call("state")

    def validate(self, document: dict | None = None) -> list:
        return self.call("validate", document=document)["problems"]

    def export(self, document: dict | None = None) -> list[dict]:
        return self.call("export", document=document)["files"]

    def manifest(self) -> dict:
        return self.call("manifest")

    def close(self) -> None:
        try:
            self.call("close")
        except Exception:
            pass
        self.proc.wait(timeout=10)

    def __enter__(self) -> "Builder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from walk(child)

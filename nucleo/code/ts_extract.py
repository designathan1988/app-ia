"""Run the TypeScript fact extractor (bridge/code/ts_facts.mjs) on a project and read its facts."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

from ..builder.client import DEFAULT_BUILDER

ROOT = pathlib.Path(__file__).resolve().parents[2]


def extract(project: str = DEFAULT_BUILDER, tsconfig: str = "tsconfig.app.json", filt: str = "") -> list[dict]:
    env = {**os.environ}
    env.setdefault("NUCLEO_TS", DEFAULT_BUILDER)  # a TypeScript 6 install, for projects on TypeScript 7
    out = subprocess.run(["node", str(ROOT / "bridge" / "code" / "ts_facts.mjs"), project, tsconfig, filt],
                         capture_output=True, text=True, encoding="utf-8", check=True, env=env).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]

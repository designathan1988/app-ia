"""Local CI gate: the whole suite plus a large differential run. Exit code != 0 blocks the stage gate."""
import os
import subprocess
import sys

env = dict(os.environ)
env.setdefault("NUCLEO_DIFF_N", "3000")
cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"]
print("running:", " ".join(cmd), "| NUCLEO_DIFF_N =", env["NUCLEO_DIFF_N"])
sys.exit(subprocess.call(cmd, env=env))

"""Start the web interface from anywhere: python C:/Codex-Shared/nucleo/run_web.py [--porta=8790] [--codigo=...]"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

from nucleo.web_ui import main  # noqa: E402

sys.exit(main(sys.argv[1:]))

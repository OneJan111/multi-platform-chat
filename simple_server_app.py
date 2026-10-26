"""Server-lifetime chat history variant of the simple monitor.

Run with:
    streamlit run simple_server_app.py
"""
import os
import runpy
from pathlib import Path

os.environ["SIMPLE_SERVER_HISTORY"] = "1"
runpy.run_path(str(Path(__file__).with_name("simple_app.py")), run_name="__main__")

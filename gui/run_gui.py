"""
Starter script for Handloom AI Fabric Defect Detection Web GUI.
Launches the FastAPI backend server and opens the Web Dashboard in the default web browser.
"""

import sys
import time
import webbrowser
from pathlib import Path

# Ensure root is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# pyrefly: ignore [missing-import]
import uvicorn
from gui.server import app

def main():
    print("=" * 70)
    print("  HANDLOOM AI FABRIC DEFECT DETECTION SYSTEM - WEB GUI STARTER")
    print("=" * 70)
    print("  Loading trained models (Custom CNN + ResNet-50 Ensemble)...")
    print("  Starting FastAPI server at: http://127.0.0.1:8000")
    print("=" * 70)

    # Open web browser automatically after 1.5 seconds
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Run Uvicorn Server
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    main()

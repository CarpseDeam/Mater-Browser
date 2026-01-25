"""Mater-Browser GUI - Launch this to use the autonomous job application dashboard."""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.gui.dashboard import DashboardApp

if __name__ == "__main__":
    app = DashboardApp()
    app.run()

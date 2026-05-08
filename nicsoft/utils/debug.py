"""
nicsoft/utils/debug.py — Flag debug partagé.

Activation : NICLINK_LOG=DEBUG python -m nicsoft.web
"""
import os

DEBUG_MODE = os.environ.get("NICLINK_LOG", "").upper() == "DEBUG"

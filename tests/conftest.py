"""Shared pytest fixtures and availability flags."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _check_dwsim_available() -> bool:
    try:
        import dwsim_tools
        status = dwsim_tools.dwsim_status()
        return bool(status.get("dwsim_found"))
    except Exception:
        return False


DWSIM_AVAILABLE = _check_dwsim_available()

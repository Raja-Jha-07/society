import ctypes
import sys
import tempfile
from pathlib import Path


def enable_high_dpi() -> None:
    """Request native Windows rendering before Tk initializes."""
    if sys.platform != "win32":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10+).
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1).
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


enable_high_dpi()

from src.utthan.database import Database
from src.utthan.reports import generate_due_list
from src.utthan.ui import run


def smoke_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database = Database(Path(temp))
        period = database.period(2026, 8)
        if len(database.list_members()) != 60 or period is None:
            raise RuntimeError("Opening balances were not initialized")
        report = generate_due_list(database, period["id"])
        if not report.exists() or report.stat().st_size == 0:
            raise RuntimeError("PDF report could not be generated")


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        smoke_test()
    else:
        run()

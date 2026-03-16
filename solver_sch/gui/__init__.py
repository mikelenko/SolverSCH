"""
SolverSCH Desktop GUI — PySide6-based circuit analysis interface.

Install optional dependencies first:
    pip install -e ".[gui]"
"""


def launch_gui(cir_file: str = "") -> None:
    """Start the PySide6 GUI application."""
    # ── Pre-import matplotlib BEFORE PySide6 ───────────────────────────────
    # PySide6 6.x installs a shibokensupport meta-path hook that fires on
    # every new import and crashes when inspecting six.moves virtual modules
    # (used by python-dateutil < 2.9, which matplotlib pulls in).
    # Solution: trigger the entire matplotlib/dateutil/six import chain FIRST,
    # so those modules are cached in sys.modules before PySide6's hook exists.
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure          # triggers dateutil/six chain
        from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: F401
    except ImportError:
        pass

    # ── Now it is safe to import PySide6 ───────────────────────────────────
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "[ERROR] PySide6 is not installed.\n"
            "Install GUI dependencies with:  pip install -e \".[gui]\""
        )
        return

    import sys
    from solver_sch.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SolverSCH")
    app.setOrganizationName("SolverSCH")

    window = MainWindow()
    window.show()

    if cir_file:
        window.load_file(cir_file)

    sys.exit(app.exec())

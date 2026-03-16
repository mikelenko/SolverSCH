"""
SimWorker — runs Simulator in a QThread so the GUI stays responsive.
"""

import time
from PySide6.QtCore import QThread, Signal


class SimWorker(QThread):
    """Background thread for circuit simulation."""

    # NOTE: 'finished' is a reserved QThread signal (no args).
    # We use 'result_ready' to avoid the name collision.
    result_ready = Signal(object, float)   # (result_object, elapsed_seconds)
    sim_error = Signal(str)

    def __init__(self, circuit, sim_type: str, params: dict, parent=None):
        """
        Args:
            circuit:   Circuit object to simulate.
            sim_type:  "dc" | "ac" | "transient"
            params:    Dict of kwargs forwarded to the analysis method.
        """
        super().__init__(parent)
        self._circuit = circuit
        self._sim_type = sim_type
        self._params = params

    def run(self):
        from solver_sch.simulator import Simulator

        try:
            # Force MNA backend — "auto" would try LTspice for nonlinear circuits
            sim = Simulator(self._circuit, validate_on_init=False, backend="mna")
            t0 = time.perf_counter()

            if self._sim_type == "dc":
                result = sim.dc()
            elif self._sim_type == "ac":
                result = sim.ac(**self._params)
            elif self._sim_type == "transient":
                result = sim.transient(**self._params)
            else:
                raise ValueError(f"Unknown sim_type: {self._sim_type!r}")

            elapsed = time.perf_counter() - t0
            self.result_ready.emit(result, elapsed)

        except Exception as exc:
            import traceback
            self.sim_error.emit(f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")

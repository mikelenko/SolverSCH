"""
MainWindow — top-level QMainWindow for SolverSCH Desktop GUI.

Layout: three-panel QSplitter (Netlist | Config | Results)
Menu: File > Open, File > Exit
Status bar: file path, component count, simulation status
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from solver_sch.gui.netlist_panel import NetlistPanel
from solver_sch.gui.config_panel import ConfigPanel
from solver_sch.gui.results_panel import ResultsPanel


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SolverSCH — Circuit Simulator")
        self.resize(1400, 800)

        self._circuit = None
        self._worker = None
        self._netlist_text = ""

        self._build_menu()
        self._build_central()
        self.statusBar().showMessage("Ready. Open a .cir file to start.")

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")

        act_open = QAction("&Open .cir…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(QApplication.quit)
        file_menu.addAction(act_exit)

        # Simulate menu
        sim_menu = mb.addMenu("&Simulate")
        act_run = QAction("&Run", self)
        act_run.setShortcut("F5")
        act_run.triggered.connect(self._on_run_shortcut)
        sim_menu.addAction(act_run)

        # Help menu
        help_menu = mb.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    # ── Central widget ────────────────────────────────────────────────────────

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        self._netlist_panel = NetlistPanel()
        self._netlist_panel.circuit_loaded.connect(self._on_circuit_loaded)

        self._config_panel = ConfigPanel()
        self._config_panel.run_requested.connect(self._on_run)

        self._results_panel = ResultsPanel()

        splitter.addWidget(self._netlist_panel)
        splitter.addWidget(self._config_panel)
        splitter.addWidget(self._results_panel)

        # Initial widths: 280 / 240 / remaining
        splitter.setSizes([280, 240, 900])

        layout.addWidget(splitter)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_file(self, filepath: str) -> None:
        """Load a .cir file (callable from launch_gui)."""
        self._netlist_panel.load_file(filepath)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SPICE Netlist", "",
            "SPICE files (*.cir *.net *.nsx *.sp);;All files (*)",
        )
        if path:
            self._netlist_panel.load_file(path)

    def _on_circuit_loaded(self, text: str, circuit) -> None:
        self._netlist_text = text
        self._circuit = circuit
        self._config_panel.load_circuit(circuit)
        n_comps = len(circuit.get_components())
        n_nodes = len(circuit.get_unique_nodes())
        self.statusBar().showMessage(
            f"Loaded: {circuit.name}  |  {n_comps} components, {n_nodes} nodes"
        )

    def _on_run(self, sim_type: str, params: dict) -> None:
        if self._circuit is None:
            QMessageBox.warning(self, "No Circuit", "Load a .cir file first.")
            return

        # Clean up previous worker if any
        if self._worker and self._worker.isRunning():
            return

        from solver_sch.gui.sim_worker import SimWorker

        self._config_panel.set_running(True)
        self.statusBar().showMessage(f"Running {sim_type.upper()} simulation…")

        self._worker = SimWorker(self._circuit, sim_type, params)
        self._worker.result_ready.connect(self._on_sim_finished)
        self._worker.sim_error.connect(self._on_sim_error)
        self._worker.start()

    def _on_run_shortcut(self):
        """F5 shortcut: trigger run with current config."""
        self._config_panel._on_run()

    def _on_sim_finished(self, result, elapsed: float) -> None:
        self._config_panel.set_running(False)
        sim_type = type(result).__name__

        selected = self._config_panel.get_selected_output_nodes()

        from solver_sch.results import DcAnalysisResult, AcAnalysisResult, TransientAnalysisResult

        if isinstance(result, DcAnalysisResult):
            self._results_panel.show_dc(result, selected or None)
            self.statusBar().showMessage(
                f"DC complete in {elapsed:.2f}s  |  "
                f"{len(result.node_voltages)} nodes"
            )
        elif isinstance(result, AcAnalysisResult):
            self._results_panel.show_ac(result, selected or None)
            self.statusBar().showMessage(
                f"AC complete in {elapsed:.2f}s  |  "
                f"{len(result.frequencies)} frequency points"
            )
        elif isinstance(result, TransientAnalysisResult):
            self._results_panel.show_transient(result, selected or None)
            self.statusBar().showMessage(
                f"Transient complete in {elapsed:.2f}s  |  "
                f"{len(result.timepoints)} timesteps"
            )

    def _on_sim_error(self, msg: str) -> None:
        self._config_panel.set_running(False)
        self.statusBar().showMessage("Simulation failed.")
        QMessageBox.critical(self, "Simulation Error", msg)

    def _on_about(self):
        QMessageBox.about(
            self,
            "About SolverSCH",
            "<b>SolverSCH</b><br>"
            "MNA Circuit Simulator with AI Design Review<br><br>"
            "Workflow: Load .cir → Configure → Simulate → View Results",
        )

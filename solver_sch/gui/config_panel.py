"""
ConfigPanel — middle panel of the SolverSCH GUI.

Allows the user to:
  - Choose simulation type (DC / AC / Transient)
  - Override source voltages
  - Mark input / output nodes
  - Configure analysis parameters
  - Launch simulation
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QDoubleSpinBox, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal


class ConfigPanel(QWidget):
    """Middle panel: simulation configuration and Run button."""

    run_requested = Signal(str, dict)   # (sim_type, params)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._circuit = None
        self._source_edits = {}   # source_name -> QLineEdit
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        # Wrap everything in a scroll area so it doesn't overflow
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # ── Simulation type ──────────────────────────────────────────────
        grp_type = QGroupBox("Analysis Type")
        fl = QFormLayout(grp_type)
        self._combo_type = QComboBox()
        self._combo_type.addItems(["DC", "AC", "Transient"])
        self._combo_type.currentTextChanged.connect(self._on_type_changed)
        fl.addRow("Type:", self._combo_type)
        layout.addWidget(grp_type)

        # ── AC params ───────────────────────────────────────────────────
        self._grp_ac = QGroupBox("AC Parameters")
        fl_ac = QFormLayout(self._grp_ac)
        self._ac_fstart = self._spin(1.0, 1e9, 10.0, suffix=" Hz")
        self._ac_fstop  = self._spin(1.0, 1e12, 100e3, suffix=" Hz")
        self._ac_ppd    = self._spin(1, 100, 20, decimals=0)
        fl_ac.addRow("f_start:", self._ac_fstart)
        fl_ac.addRow("f_stop:", self._ac_fstop)
        fl_ac.addRow("Points/decade:", self._ac_ppd)
        self._grp_ac.setVisible(False)
        layout.addWidget(self._grp_ac)

        # ── Transient params ─────────────────────────────────────────────
        self._grp_tran = QGroupBox("Transient Parameters")
        fl_tr = QFormLayout(self._grp_tran)
        self._tr_tstop = self._spin(1e-6, 100.0,  5e-3,  suffix=" s")
        self._tr_dt    = self._spin(1e-6, 1.0,    10e-6, suffix=" s")
        fl_tr.addRow("t_stop:", self._tr_tstop)
        fl_tr.addRow("dt:", self._tr_dt)
        self._grp_tran.setVisible(False)
        layout.addWidget(self._grp_tran)

        # ── Source overrides ─────────────────────────────────────────────
        self._grp_sources = QGroupBox("Source Voltages")
        self._sources_layout = QFormLayout(self._grp_sources)
        self._grp_sources.setVisible(False)
        layout.addWidget(self._grp_sources)

        # ── Port configuration ───────────────────────────────────────────
        grp_ports = QGroupBox("Port Configuration")
        pv = QVBoxLayout(grp_ports)
        pv.addWidget(QLabel("Output nodes (for plot):"))
        self._output_list = QListWidget()
        self._output_list.setMaximumHeight(110)
        pv.addWidget(self._output_list)
        layout.addWidget(grp_ports)

        # ── Run button ───────────────────────────────────────────────────
        layout.addStretch()
        self._btn_run = QPushButton("▶  Run Simulation")
        self._btn_run.setEnabled(False)
        self._btn_run.setMinimumHeight(36)
        self._btn_run.clicked.connect(self._on_run)
        outer.addWidget(self._btn_run)

    # ── Public API ──────────────────────────────────────────────────────────

    def load_circuit(self, circuit) -> None:
        """Populate source overrides and port list from a Circuit object."""
        self._circuit = circuit
        self._populate_sources(circuit)
        self._populate_ports(circuit)
        self._btn_run.setEnabled(True)

    def set_running(self, running: bool) -> None:
        """Disable/enable Run button during simulation."""
        self._btn_run.setEnabled(not running)
        self._btn_run.setText("⏳  Running…" if running else "▶  Run Simulation")

    def get_selected_output_nodes(self):
        """Return list of checked output node names."""
        nodes = []
        for i in range(self._output_list.count()):
            item = self._output_list.item(i)
            if item.checkState() == Qt.Checked:
                nodes.append(item.text())
        return nodes

    # ── Private helpers ─────────────────────────────────────────────────────

    def _spin(self, minimum, maximum, value, suffix="", decimals=6):
        sp = QDoubleSpinBox()
        sp.setRange(minimum, maximum)
        sp.setValue(value)
        sp.setDecimals(decimals if decimals != 0 else 0)
        sp.setStepType(QDoubleSpinBox.AdaptiveDecimalStepType)
        if suffix:
            sp.setSuffix(suffix)
        return sp

    def _on_type_changed(self, text):
        self._grp_ac.setVisible(text == "AC")
        self._grp_tran.setVisible(text == "Transient")

    def _populate_sources(self, circuit):
        # Clear old widgets
        while self._sources_layout.rowCount():
            self._sources_layout.removeRow(0)
        self._source_edits.clear()

        from solver_sch.model.circuit import VoltageSource, ACVoltageSource
        sources = [
            c for c in circuit.get_components()
            if isinstance(c, (VoltageSource, ACVoltageSource))
        ]
        if not sources:
            self._grp_sources.setVisible(False)
            return

        self._grp_sources.setVisible(True)
        for src in sources:
            val = getattr(src, "voltage", getattr(src, "dc_offset", 0.0))
            edit = QLineEdit(str(val))
            edit.setPlaceholderText("Voltage (V)")
            self._source_edits[src.name] = (src, edit)
            self._sources_layout.addRow(f"{src.name}:", edit)

    def _populate_ports(self, circuit):
        self._output_list.clear()
        ground = circuit.ground_name
        for node in sorted(circuit.get_unique_nodes()):
            if node == ground:
                continue
            item = QListWidgetItem(node)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self._output_list.addItem(item)

    def _apply_source_overrides(self):
        """Write edited voltage values back to circuit components.

        VoltageSource.voltage is a read-only property that returns self.value,
        so we always write to src.value directly.
        ACVoltageSource uses src.dc_offset for the DC level.
        """
        from solver_sch.model.circuit import ACVoltageSource
        for name, (src, edit) in self._source_edits.items():
            try:
                val = float(edit.text())
                if isinstance(src, ACVoltageSource):
                    src.dc_offset = val
                else:
                    src._value = val   # TwoTerminalPassive backing field
            except ValueError:
                pass

    def _on_run(self):
        if self._circuit is None:
            return
        self._apply_source_overrides()
        sim_type = self._combo_type.currentText().lower()
        params = {}
        if sim_type == "ac":
            params = {
                "f_start": self._ac_fstart.value(),
                "f_stop":  self._ac_fstop.value(),
                "points_per_decade": int(self._ac_ppd.value()),
            }
        elif sim_type == "transient":
            params = {
                "t_stop": self._tr_tstop.value(),
                "dt":     self._tr_dt.value(),
            }
        self.run_requested.emit(sim_type, params)

"""
ResultsPanel — right panel of the SolverSCH GUI.

Three tabs:
  DC  — QTableWidget (node voltages + source currents) + bar chart
  AC  — QTableWidget (freq/node/mag/phase) + Bode plot
  Tran — QTableWidget (time + selected node voltages) + waveform plot

Each tab has a vertical QSplitter: table on top, plot on bottom.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QSplitter,
    QListWidget, QListWidgetItem, QLabel,
)
from PySide6.QtCore import Qt

from solver_sch.gui.plot_widget import PlotCanvas


class ResultsPanel(QWidget):
    """Right panel: tabbed DC / AC / Transient results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._dc_tab   = self._build_dc_tab()
        self._ac_tab   = self._build_ac_tab()
        self._tran_tab = self._build_tran_tab()

        self._tabs.addTab(self._dc_tab,   "DC")
        self._tabs.addTab(self._ac_tab,   "AC")
        self._tabs.addTab(self._tran_tab, "Transient")

    # ── Tab builders ────────────────────────────────────────────────────────

    def _build_dc_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(2, 2, 2, 2)

        splitter = QSplitter(Qt.Vertical)

        # Tables side by side
        tables_w = QWidget()
        tables_l = QHBoxLayout(tables_w)
        tables_l.setContentsMargins(0, 0, 0, 0)

        self._dc_volt_table = self._make_table(["Node", "Voltage (V)"])
        self._dc_curr_table = self._make_table(["Source", "Current (A)"])
        tables_l.addWidget(self._dc_volt_table)
        tables_l.addWidget(self._dc_curr_table)
        splitter.addWidget(tables_w)

        self._dc_plot = PlotCanvas()
        splitter.addWidget(self._dc_plot)
        splitter.setSizes([180, 300])

        layout.addWidget(splitter)
        return w

    def _build_ac_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(2, 2, 2, 2)

        splitter = QSplitter(Qt.Vertical)

        top_w = QWidget()
        top_l = QHBoxLayout(top_w)
        top_l.setContentsMargins(0, 0, 0, 0)

        # Node selector
        sel_w = QWidget()
        sel_l = QVBoxLayout(sel_w)
        sel_l.setContentsMargins(0, 0, 0, 0)
        sel_l.addWidget(QLabel("Show nodes:"))
        self._ac_node_list = QListWidget()
        self._ac_node_list.setMaximumWidth(130)
        self._ac_node_list.itemChanged.connect(self._on_ac_node_changed)
        sel_l.addWidget(self._ac_node_list)
        top_l.addWidget(sel_w)

        self._ac_table = self._make_table(["Freq (Hz)", "Node", "Mag (dB)", "Phase (°)"])
        top_l.addWidget(self._ac_table)
        splitter.addWidget(top_w)

        self._ac_plot = PlotCanvas()
        splitter.addWidget(self._ac_plot)
        splitter.setSizes([180, 300])

        layout.addWidget(splitter)
        return w

    def _build_tran_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(2, 2, 2, 2)

        splitter = QSplitter(Qt.Vertical)

        top_w = QWidget()
        top_l = QHBoxLayout(top_w)
        top_l.setContentsMargins(0, 0, 0, 0)

        sel_w = QWidget()
        sel_l = QVBoxLayout(sel_w)
        sel_l.setContentsMargins(0, 0, 0, 0)
        sel_l.addWidget(QLabel("Show nodes:"))
        self._tran_node_list = QListWidget()
        self._tran_node_list.setMaximumWidth(130)
        self._tran_node_list.itemChanged.connect(self._on_tran_node_changed)
        sel_l.addWidget(self._tran_node_list)
        top_l.addWidget(sel_w)

        self._tran_table = self._make_table(["Time (ms)", "Node", "Voltage (V)"])
        top_l.addWidget(self._tran_table)
        splitter.addWidget(top_w)

        self._tran_plot = PlotCanvas()
        splitter.addWidget(self._tran_plot)
        splitter.setSizes([180, 300])

        layout.addWidget(splitter)
        return w

    # ── Public API ──────────────────────────────────────────────────────────

    def show_dc(self, dc_result, pre_selected_nodes=None):
        """Populate DC tab and switch to it."""
        self._tabs.setCurrentWidget(self._dc_tab)

        # Voltage table
        vt = self._dc_volt_table
        vt.setRowCount(0)
        for node, v in dc_result.node_voltages.items():
            row = vt.rowCount()
            vt.insertRow(row)
            vt.setItem(row, 0, self._cell(node))
            vt.setItem(row, 1, self._cell(f"{v:.6g}"))

        # Current table
        ct = self._dc_curr_table
        ct.setRowCount(0)
        for src, i in dc_result.source_currents.items():
            row = ct.rowCount()
            ct.insertRow(row)
            ct.setItem(row, 0, self._cell(src))
            ct.setItem(row, 1, self._cell(f"{i:.6g}"))

        self._dc_plot.plot_dc_bar(dc_result)

    def show_ac(self, ac_result, pre_selected_nodes=None):
        """Populate AC tab and switch to it."""
        self._ac_result = ac_result
        self._tabs.setCurrentWidget(self._ac_tab)

        # Populate node selector
        self._ac_node_list.blockSignals(True)
        self._ac_node_list.clear()
        for node in sorted(ac_result.nodes.keys()):
            item = QListWidgetItem(node)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = pre_selected_nodes and node in pre_selected_nodes
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self._ac_node_list.addItem(item)
        self._ac_node_list.blockSignals(False)

        # Populate table (first 200 rows to avoid lag)
        t = self._ac_table
        t.setRowCount(0)
        MAX_ROWS = 200
        count = 0
        for node, r in ac_result.nodes.items():
            for i, freq in enumerate(ac_result.frequencies):
                if count >= MAX_ROWS:
                    break
                row = t.rowCount()
                t.insertRow(row)
                t.setItem(row, 0, self._cell(f"{freq:.4g}"))
                t.setItem(row, 1, self._cell(node))
                t.setItem(row, 2, self._cell(f"{r.magnitude_db[i]:.3f}"))
                t.setItem(row, 3, self._cell(f"{r.phase_deg[i]:.2f}"))
                count += 1

        self._redraw_ac_plot()

    def show_transient(self, tr_result, pre_selected_nodes=None):
        """Populate Transient tab and switch to it."""
        self._tran_result = tr_result
        self._tabs.setCurrentWidget(self._tran_tab)

        if not tr_result.timepoints:
            return

        all_nodes = sorted(tr_result.timepoints[0].node_voltages.keys())

        # Populate node selector
        self._tran_node_list.blockSignals(True)
        self._tran_node_list.clear()
        for node in all_nodes:
            item = QListWidgetItem(node)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = pre_selected_nodes and node in pre_selected_nodes
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self._tran_node_list.addItem(item)
        self._tran_node_list.blockSignals(False)

        # Populate table (max 500 rows)
        t = self._tran_table
        t.setRowCount(0)
        MAX_ROWS = 500
        for tp in tr_result.timepoints[:MAX_ROWS]:
            for node in all_nodes:
                row = t.rowCount()
                t.insertRow(row)
                t.setItem(row, 0, self._cell(f"{tp.time*1e3:.4f}"))
                t.setItem(row, 1, self._cell(node))
                t.setItem(row, 2, self._cell(f"{tp.node_voltages.get(node, 0):.6g}"))

        self._redraw_tran_plot()

    # ── Private helpers ─────────────────────────────────────────────────────

    def _make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setStretchLastSection(True)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setAlternatingRowColors(True)
        return t

    def _cell(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _checked_nodes(self, list_widget) -> list:
        result = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result

    def _on_ac_node_changed(self, _item):
        self._redraw_ac_plot()

    def _on_tran_node_changed(self, _item):
        self._redraw_tran_plot()

    def _redraw_ac_plot(self):
        if not hasattr(self, "_ac_result"):
            return
        nodes = self._checked_nodes(self._ac_node_list)
        self._ac_plot.plot_ac(self._ac_result, nodes or None)

    def _redraw_tran_plot(self):
        if not hasattr(self, "_tran_result"):
            return
        nodes = self._checked_nodes(self._tran_node_list)
        self._tran_plot.plot_transient(self._tran_result, nodes or None)

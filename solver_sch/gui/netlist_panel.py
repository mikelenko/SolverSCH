"""
NetlistPanel — left panel of the SolverSCH GUI.

Shows:
  - "Load .cir" button → QFileDialog
  - QPlainTextEdit with raw netlist text (read-only)
  - QTreeWidget with parsed circuit info (nodes, components, validation)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QPlainTextEdit, QTreeWidget, QTreeWidgetItem,
    QLabel, QSplitter,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class NetlistPanel(QWidget):
    """Left panel: load netlist file and display circuit information."""

    # Emitted when a new netlist is successfully parsed
    # Args: (netlist_text: str, circuit: Circuit)
    circuit_loaded = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── Top bar: Load button ──
        top = QHBoxLayout()
        self._btn_load = QPushButton("Load .cir…")
        self._btn_load.clicked.connect(self._on_load)
        top.addWidget(self._btn_load)
        top.addStretch()
        layout.addLayout(top)

        # ── Splitter: info tree (top) + netlist text (bottom) ──
        splitter = QSplitter(Qt.Vertical)

        # Circuit info tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Circuit Info")
        self._tree.setIndentation(14)
        splitter.addWidget(self._tree)

        # Raw netlist text
        text_container = QWidget()
        tc_layout = QVBoxLayout(text_container)
        tc_layout.setContentsMargins(0, 0, 0, 0)
        tc_layout.addWidget(QLabel("Netlist text:"))
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = self._text.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        self._text.setFont(font)
        tc_layout.addWidget(self._text)
        splitter.addWidget(text_container)

        splitter.setSizes([250, 150])
        layout.addWidget(splitter)

    # ── Public API ──────────────────────────────────────────────────────────

    def load_file(self, filepath: str) -> None:
        """Load and parse a .cir file, populate the panel."""
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            self._show_error(f"Cannot open file: {e}")
            return

        self._text.setPlainText(text)
        self._parse_and_display(text, filepath)

    def set_netlist_text(self, text: str) -> None:
        """Parse and display netlist from a string (no file I/O)."""
        self._text.setPlainText(text)
        self._parse_and_display(text, "inline")

    # ── Private helpers ─────────────────────────────────────────────────────

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SPICE Netlist",
            "",
            "SPICE files (*.cir *.net *.nsx *.sp);;All files (*)",
        )
        if path:
            self.load_file(path)

    def _parse_and_display(self, text: str, source: str) -> None:
        from solver_sch.parser.netlist_parser import NetlistParser
        from solver_sch.simulator import Simulator
        import os

        try:
            circuit = NetlistParser.parse_netlist(
                text, circuit_name=os.path.basename(source)
            )
        except Exception as e:
            self._show_error(f"Parse error: {e}")
            return

        self._populate_tree(circuit, Simulator(circuit, validate_on_init=False).validate())
        self.circuit_loaded.emit(text, circuit)

    def _populate_tree(self, circuit, validation) -> None:
        self._tree.clear()

        # ── Validation status ──
        val_item = QTreeWidgetItem(["Validation"])
        self._tree.addTopLevelItem(val_item)
        if validation.valid:
            status = QTreeWidgetItem(["✓ Valid"])
            status.setForeground(0, QColor("#2e7d32"))
        else:
            status = QTreeWidgetItem([f"✗ {len(validation.errors)} error(s)"])
            status.setForeground(0, QColor("#c62828"))
        val_item.addChild(status)
        for err in validation.errors:
            child = QTreeWidgetItem([f"[ERROR] {err.message}"])
            child.setForeground(0, QColor("#c62828"))
            val_item.addChild(child)
        for w in validation.warnings:
            child = QTreeWidgetItem([f"[WARN] {w.message}"])
            child.setForeground(0, QColor("#e65100"))
            val_item.addChild(child)

        # ── Components ──
        comps = circuit.get_components()
        comp_item = QTreeWidgetItem([f"Components ({len(comps)})"])
        self._tree.addTopLevelItem(comp_item)
        for c in comps:
            nodes_str = ", ".join(c.nodes())
            label = f"{type(c).__name__} {c.name}  [{nodes_str}]"
            comp_item.addChild(QTreeWidgetItem([label]))

        # ── Nodes ──
        nodes = sorted(circuit.get_unique_nodes())
        node_item = QTreeWidgetItem([f"Nodes ({len(nodes)})"])
        self._tree.addTopLevelItem(node_item)
        for n in nodes:
            node_item.addChild(QTreeWidgetItem([n]))

        val_item.setExpanded(True)
        comp_item.setExpanded(True)

    def _show_error(self, msg: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error", msg)

"""
PlotCanvas — matplotlib Agg backend rendered into a PySide6 QScrollArea.

Uses the non-interactive Agg backend (pure rasterizer, no Qt binding),
then converts the PNG output to a QPixmap. This sidesteps the PySide6 6.x /
shibokensupport crash caused by python-dateutil importing six.moves when
matplotlib's Qt backend is loaded.

Provides:
  plot_dc_bar(dc_result)
  plot_ac(ac_result, selected_nodes)
  plot_transient(tr_result, selected_nodes)
  clear()
"""

import warnings
import matplotlib
matplotlib.use("Agg")   # must be set before any other matplotlib import

from io import BytesIO
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QPushButton,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


class PlotCanvas(QWidget):
    """Renders matplotlib figures as static PNG images inside a QScrollArea."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._fig = Figure(figsize=(8, 5), tight_layout=True)
        self._canvas_agg = FigureCanvasAgg(self._fig)

        # ── Layout ──────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._img_label)
        layout.addWidget(self._scroll)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        self._btn_save = QPushButton("Save PNG…")
        self._btn_save.clicked.connect(self._save_plot)
        btn_bar.addWidget(self._btn_save)
        layout.addLayout(btn_bar)

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self):
        """Draw the figure and push it to the QLabel as a QPixmap."""
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "Attempt to set non-positive")
            self._canvas_agg.draw()
        buf = BytesIO()
        self._fig.savefig(buf, format="png", dpi=96)
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        self._img_label.setPixmap(pixmap)
        self._img_label.resize(pixmap.size())

    def clear(self):
        self._fig.clear()
        self._img_label.clear()

    def _save_plot(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)"
        )
        if path:
            self._fig.savefig(path, dpi=150)

    # ── Plot methods ──────────────────────────────────────────────────────────

    def plot_dc_bar(self, dc_result):
        """Bar chart of DC node voltages."""
        self._fig.clear()
        ax = self._fig.add_subplot(111)

        nodes = list(dc_result.node_voltages.keys())
        volts = [dc_result.node_voltages[n] for n in nodes]

        bars = ax.bar(range(len(nodes)), volts, color="#1976d2")
        ax.set_xticks(range(len(nodes)))
        ax.set_xticklabels(nodes, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Voltage (V)")
        ax.set_title("DC Node Voltages")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.bar_label(bars, fmt="%.3g", fontsize=7)

        self._render()

    def plot_ac(self, ac_result, selected_nodes=None):
        """Bode plot: magnitude (dB) + phase (deg) vs frequency."""
        self._fig.clear()
        nodes_to_plot = selected_nodes or list(ac_result.nodes.keys())
        if not nodes_to_plot:
            self._img_label.clear()
            return

        freqs = ac_result.frequencies
        ax_mag = self._fig.add_subplot(211)
        ax_phs = self._fig.add_subplot(212, sharex=ax_mag)

        for node in nodes_to_plot:
            if node not in ac_result.nodes:
                continue
            r = ac_result.nodes[node]
            ax_mag.semilogx(freqs, r.magnitude_db, label=node)
            ax_phs.semilogx(freqs, r.phase_deg, label=node)

        ax_mag.set_ylabel("Magnitude (dB)")
        ax_mag.set_title("AC Frequency Response (Bode)")
        ax_mag.legend(fontsize=7)
        ax_mag.grid(True, which="both", alpha=0.4)

        ax_phs.set_xlabel("Frequency (Hz)")
        ax_phs.set_ylabel("Phase (°)")
        ax_phs.legend(fontsize=7)
        ax_phs.grid(True, which="both", alpha=0.4)

        self._render()

    def plot_transient(self, tr_result, selected_nodes=None):
        """Time-domain waveforms."""
        self._fig.clear()
        if not tr_result.timepoints:
            self._img_label.clear()
            return

        all_nodes = list(tr_result.timepoints[0].node_voltages.keys())
        nodes_to_plot = selected_nodes or all_nodes
        if not nodes_to_plot:
            self._img_label.clear()
            return

        ax = self._fig.add_subplot(111)
        for node in nodes_to_plot:
            data = tr_result.voltages_at(node)
            t_ms = [t * 1e3 for t in data["time"]]
            ax.plot(t_ms, data["voltage"], label=node)

        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title("Transient Analysis")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.4)

        self._render()

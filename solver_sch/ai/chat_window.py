"""
chat_window.py — PySide6 desktop chat for SolverSCH agent.

Shows:
  • Your message (green bubble)
  • Agent thinking   (collapsible grey block)
  • Tool calls       (yellow panel: name + args)
  • Tool results     (blue panel: JSON preview)
  • Agent response   (white bubble)

Run:
    python -m solver_sch.ai.chat_window

Requires:
    pip install anthropic PySide6
    export ANTHROPIC_API_KEY=sk-ant-...
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from typing import Any

import anthropic
from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QFont, QColor, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from solver_sch.ai.chat import _tool_simulate_circuit, TOOLS_SCHEMA, _build_system_prompt


# ── Anthropic tool schema ─────────────────────────────────────────────────────

_ANTHROPIC_TOOLS = [
    {
        "name": t["name"],
        "description": t["description"],
        "input_schema": {
            "type": "object",
            "properties": {
                k: {"type": v["type"], "description": v["description"]}
                for k, v in t["parameters"].items()
            },
            "required": t["required"],
        },
    }
    for t in TOOLS_SCHEMA
]

_MAX_TOOL_ROUNDS = 8


# ── Worker thread (runs the Anthropic agentic loop) ───────────────────────────

class AgentWorker(QObject):
    """Runs in a QThread; emits fine-grained events back to the UI thread."""

    # text events
    thinking_start  = Signal()
    thinking_delta  = Signal(str)
    thinking_end    = Signal()
    text_start      = Signal()
    text_delta      = Signal(str)
    text_end        = Signal()

    # tool events
    tool_call       = Signal(str, str)   # (tool_name, args_json)
    tool_result     = Signal(str, str)   # (tool_name, result_preview)

    # lifecycle
    turn_done       = Signal(list)       # updated history
    error           = Signal(str)

    def __init__(self, user_text: str, history: list, parent=None):
        super().__init__(parent)
        self._user_text = user_text
        self._history   = list(history)
        self._client    = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )

    def run(self):
        import anyio
        try:
            anyio.run(self._arun)
        except Exception as exc:
            self.error.emit(str(exc))

    async def _arun(self):
        client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        messages = list(self._history)
        messages.append({"role": "user", "content": self._user_text})
        system = _build_system_prompt()

        for _round in range(_MAX_TOOL_ROUNDS):
            tool_uses: list[dict] = []

            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=8192,
                thinking={"type": "adaptive"},
                system=system,
                tools=_ANTHROPIC_TOOLS,
                messages=messages,
            ) as stream:
                current_type: str | None = None

                async for event in stream:
                    et = event.type

                    if et == "content_block_start":
                        blk = event.content_block
                        current_type = blk.type
                        if blk.type == "thinking":
                            self.thinking_start.emit()
                        elif blk.type == "text":
                            self.text_start.emit()
                        elif blk.type == "tool_use":
                            tool_uses.append({
                                "id": blk.id,
                                "name": blk.name,
                                "input_raw": "",
                            })

                    elif et == "content_block_delta":
                        d = event.delta
                        if d.type == "thinking_delta":
                            self.thinking_delta.emit(d.thinking)
                        elif d.type == "text_delta":
                            self.text_delta.emit(d.text)
                        elif d.type == "input_json_delta" and tool_uses:
                            tool_uses[-1]["input_raw"] += d.partial_json

                    elif et == "content_block_stop":
                        if current_type == "thinking":
                            self.thinking_end.emit()
                        elif current_type == "text":
                            self.text_end.emit()
                        elif current_type == "tool_use" and tool_uses:
                            raw = tool_uses[-1].get("input_raw", "")
                            try:
                                tool_uses[-1]["input"] = json.loads(raw) if raw else {}
                            except json.JSONDecodeError:
                                tool_uses[-1]["input"] = {}
                            args_pretty = json.dumps(
                                tool_uses[-1]["input"], indent=2
                            )
                            self.tool_call.emit(tool_uses[-1]["name"], args_pretty)

                final = await stream.get_final_message()

            messages.append({"role": "assistant", "content": final.content})

            if final.stop_reason != "tool_use" or not tool_uses:
                break

            # execute tools
            tool_results = []
            for tu in tool_uses:
                name  = tu["name"]
                args  = tu.get("input", {})
                try:
                    if name == "simulate_circuit":
                        result_str = _tool_simulate_circuit(**args)
                    else:
                        result_str = json.dumps({"error": f"Unknown tool '{name}'"})
                except Exception as exc:
                    result_str = json.dumps({"error": str(exc)})

                preview = result_str[:800]
                self.tool_result.emit(name, preview)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})

        self.turn_done.emit(messages)


# ── Reusable bubble / panel widgets ──────────────────────────────────────────

def _label(text: str, color: str, bold=False) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
    if bold:
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
    return lbl


class BubbleWidget(QFrame):
    """A coloured bubble that holds plain text (streaming-friendly)."""

    def __init__(self, role_label: str, bg: str, text_color: str = "#e8e8e8"):
        super().__init__()
        self.setStyleSheet(
            f"background:{bg}; border-radius:8px; padding:0px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        hdr = QLabel(role_label)
        hdr.setStyleSheet(f"color:{text_color}; font-size:10px; font-weight:bold;")
        layout.addWidget(hdr)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setStyleSheet(
            f"background:transparent; border:none; color:{text_color}; font-size:13px;"
        )
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._body)

        self._text = ""

    def append(self, chunk: str):
        self._text += chunk
        self._body.setPlainText(self._text)
        self._body.setFixedHeight(
            int(self._body.document().size().height()) + 4
        )

    def set_text(self, text: str):
        self._text = text
        self._body.setPlainText(text)
        self._body.setFixedHeight(
            int(self._body.document().size().height()) + 4
        )


class CollapsibleThinking(QFrame):
    """Thinking block — shows a toggle button + scrollable text."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:#2a2a3e; border-radius:8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        hdr = QHBoxLayout()
        lbl = QLabel("🧠  Agent Thinking")
        lbl.setStyleSheet("color:#a0a0c0; font-size:10px; font-weight:bold;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._toggle = QPushButton("▼ show")
        self._toggle.setFixedWidth(64)
        self._toggle.setStyleSheet(
            "color:#7070a0; background:transparent; border:none; font-size:10px;"
        )
        self._toggle.clicked.connect(self._on_toggle)
        hdr.addWidget(self._toggle)
        layout.addLayout(hdr)

        self._body = QPlainTextEdit()
        self._body.setReadOnly(True)
        self._body.setFixedHeight(120)
        self._body.setStyleSheet(
            "background:#1e1e2e; color:#8888aa; font-size:11px; border-radius:4px;"
        )
        self._body.hide()
        layout.addWidget(self._body)

        self._visible = False
        self._text = ""

    def _on_toggle(self):
        self._visible = not self._visible
        self._body.setVisible(self._visible)
        self._toggle.setText("▲ hide" if self._visible else "▼ show")

    def append(self, chunk: str):
        self._text += chunk
        self._body.setPlainText(self._text)
        cursor = self._body.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._body.setTextCursor(cursor)


class ToolPanel(QFrame):
    """Shows a tool call (name + args) and its result."""

    def __init__(self, name: str, args: str):
        super().__init__()
        self.setStyleSheet("background:#3a2e10; border-radius:8px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        hdr = QLabel(f"🔧  Tool: <b>{name}</b>")
        hdr.setStyleSheet("color:#f0c060; font-size:11px;")
        layout.addWidget(hdr)

        args_box = QPlainTextEdit(args)
        args_box.setReadOnly(True)
        args_box.setFixedHeight(80)
        args_box.setStyleSheet(
            "background:#221e0a; color:#d4b060; font-size:10px; border-radius:4px;"
        )
        layout.addWidget(args_box)

        self._result_lbl = QLabel("⏳  Running…")
        self._result_lbl.setStyleSheet("color:#909090; font-size:10px;")
        layout.addWidget(self._result_lbl)

        self._result_box = QPlainTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setFixedHeight(90)
        self._result_box.setStyleSheet(
            "background:#0a1a22; color:#60c0d4; font-size:10px; border-radius:4px;"
        )
        self._result_box.hide()
        layout.addWidget(self._result_box)

    def set_result(self, result: str):
        self._result_lbl.setText("✅  Result (preview):")
        self._result_lbl.setStyleSheet("color:#60c0d4; font-size:10px;")
        self._result_box.setPlainText(result)
        self._result_box.show()


# ── Main window ───────────────────────────────────────────────────────────────

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SolverSCH — Agent Chat")
        self.resize(820, 700)
        self._history: list = []
        self._thread: QThread | None = None
        self._worker: AgentWorker | None = None

        # active streaming widgets
        self._active_thinking: CollapsibleThinking | None = None
        self._active_bubble:   BubbleWidget | None = None
        self._active_tools:    dict[str, ToolPanel] = {}  # name → panel

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("background:#1a1a2e;")

        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # scroll area for chat
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:none; background:#1a1a2e;")
        vbox.addWidget(self._scroll, stretch=1)

        self._chat_widget = QWidget()
        self._chat_widget.setStyleSheet("background:#1a1a2e;")
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setContentsMargins(12, 12, 12, 12)
        self._chat_layout.setSpacing(10)
        self._chat_layout.addStretch()
        self._scroll.setWidget(self._chat_widget)

        # input row
        bar = QWidget()
        bar.setStyleSheet("background:#0f0f1e; border-top:1px solid #333;")
        bar.setFixedHeight(70)
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(12, 8, 12, 8)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Ask about a circuit… (Enter to send, Shift+Enter for newline)")
        self._input.setFixedHeight(50)
        self._input.setStyleSheet(
            "background:#1e1e2e; color:#e0e0e0; border-radius:6px; padding:6px; font-size:13px;"
        )
        self._input.installEventFilter(self)
        hbox.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedSize(70, 40)
        self._send_btn.setStyleSheet(
            "background:#5050c0; color:white; border-radius:6px; font-size:13px;"
        )
        self._send_btn.clicked.connect(self._on_send)
        hbox.addWidget(self._send_btn)

        vbox.addWidget(bar)

    # ── Event filter (Enter to send) ──────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            ke: QKeyEvent = event
            if ke.key() in (Qt.Key_Return, Qt.Key_Enter):
                if not (ke.modifiers() & Qt.ShiftModifier):
                    self._on_send()
                    return True
        return super().eventFilter(obj, event)

    # ── Helpers to add widgets to chat ────────────────────────────────────────

    def _add_widget(self, w: QWidget):
        # insert before the trailing stretch
        idx = self._chat_layout.count() - 1
        self._chat_layout.insertWidget(idx, w)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Send ──────────────────────────────────────────────────────────────────

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if not text or self._thread is not None:
            return
        self._input.clear()
        self._send_btn.setEnabled(False)

        # show user bubble
        bubble = BubbleWidget("You", "#1e3a2e", "#a0d8a0")
        bubble.set_text(text)
        self._add_widget(bubble)

        # spin up worker
        self._active_thinking = None
        self._active_bubble   = None
        self._active_tools    = {}

        self._thread = QThread(self)
        self._worker = AgentWorker(text, self._history)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)

        self._worker.thinking_start.connect(self._on_thinking_start)
        self._worker.thinking_delta.connect(self._on_thinking_delta)
        self._worker.thinking_end.connect(self._on_thinking_end)
        self._worker.text_start.connect(self._on_text_start)
        self._worker.text_delta.connect(self._on_text_delta)
        self._worker.text_end.connect(self._on_text_end)
        self._worker.tool_call.connect(self._on_tool_call)
        self._worker.tool_result.connect(self._on_tool_result)
        self._worker.turn_done.connect(self._on_done)
        self._worker.error.connect(self._on_error)

        self._thread.start()

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_thinking_start(self):
        self._active_thinking = CollapsibleThinking()
        self._add_widget(self._active_thinking)

    def _on_thinking_delta(self, chunk: str):
        if self._active_thinking:
            self._active_thinking.append(chunk)
            self._scroll_to_bottom()

    def _on_thinking_end(self):
        self._active_thinking = None

    def _on_text_start(self):
        self._active_bubble = BubbleWidget("Agent", "#1e1e3e", "#d0d0f0")
        self._add_widget(self._active_bubble)

    def _on_text_delta(self, chunk: str):
        if self._active_bubble:
            self._active_bubble.append(chunk)
            self._scroll_to_bottom()

    def _on_text_end(self):
        self._active_bubble = None

    def _on_tool_call(self, name: str, args: str):
        panel = ToolPanel(name, args)
        self._active_tools[name] = panel
        self._add_widget(panel)

    def _on_tool_result(self, name: str, result: str):
        panel = self._active_tools.get(name)
        if panel:
            panel.set_result(result)
        self._scroll_to_bottom()

    def _on_done(self, updated_history: list):
        self._history = updated_history
        self._cleanup_thread()

    def _on_error(self, msg: str):
        err = BubbleWidget("Error", "#3e1e1e", "#f08080")
        err.set_text(msg)
        self._add_widget(err)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
        self._send_btn.setEnabled(True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ChatWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

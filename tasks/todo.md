# Tasks

## Altium to SPICE Exporter
- [x] Analiza formatu pliku `.NET` (Altium Netlist)
- [x] Analiza BOM `.xls`
- [x] Utworzenie modelu danych `altium_model.py`
- [x] Implementacja parsera `altium_parser.py`
  - [x] Parser sekcji komponentÃ³w `[...]`
  - [x] Parser sekcji sieci `(...)`
  - [x] Parser wartoÅci z pola comment (100k, 10p, 1k5, 0R, etc.)
  - [x] Parsowanie BOM z xlrd
  - [x] Konwersja do `Circuit`
  - [x] Eksport do tekstu SPICE
- [x] Integracja z CLI (`altium-to-spice` command)
- [x] Testy jednostkowe `test_altium_parser.py`
- [x] Weryfikacja na rzeczywistym pliku 058-SBS-07 Comparator
- [x] Aktualizacja `tasks/lessons.md`

## AI Circuit Analysis
- [x] Wczytanie wyizolowanego obwodu Comparator_A_1.cir
- [x] Analiza topologii (dzielniki napiêæ, filtry RC)
- [x] Wnioski na temat uk³adu kondycjonowania sygna³u

## PySide6 Desktop GUI

### Phase 1: Skeleton Window + Netlist Loading
- [x] pyproject.toml: add `gui = ["PySide6>=6.5", "matplotlib>=3.7"]` optional deps
- [x] solver_sch/gui/__init__.py: launch_gui() entry point
- [x] solver_sch/gui/main_window.py: MainWindow with 3-panel QSplitter + menu + status bar
- [x] solver_sch/gui/netlist_panel.py: Load .cir, QPlainTextEdit, QTreeWidget circuit info
- [x] solver_sch/cli.py: add `gui` subcommand

### Phase 2: Config Panel + Sim Worker + DC Results
- [x] solver_sch/gui/sim_worker.py: QThread with finished/error signals
- [x] solver_sch/gui/config_panel.py: sim type, source voltages, port config, Run button
- [x] solver_sch/gui/results_panel.py: QTabWidget + DC table

### Phase 3: Plots (AC Bode + Transient waveforms)
- [x] solver_sch/gui/plot_widget.py: PlotCanvas(FigureCanvasQTAgg) — lazy import fix for PySide6 6.x
- [x] results_panel.py: extended with AC + Transient tabs + node checkboxes

### Verification
- [x] pytest tests/ -q — 70/70 passing

## AC/Transient Solver Fixes + Cross-Validation

### Bug Fixes
- [x] AC: Add BJT/MOSFET/Diode small-signal linearization to `stamp_ac()` (was treating nonlinear components as open circuits → -400 dB)
- [x] Transient: Initialize from DC operating point instead of zeros (coupling caps were uncharged → wrong initial conditions)
- [x] Simulator: Auto-run DC before AC/transient to provide operating point
- [x] Exporter: Include W/L parameters in MOSFET export to LTspice

### Cross-Validation Tests (`tests/test_mna_vs_ltspice.py`)
- [x] RC Low-Pass Filter (DC + AC) — linear baseline
- [x] Series RLC Bandpass (AC) — inductor + resonance
- [x] Diode Half-Wave Rectifier (DC + Transient) — nonlinear diode
- [x] BJT Common-Emitter Amp (DC + AC) — BJT linearization
- [x] NMOS Common-Source Amp (DC + AC) — MOSFET linearization
- [x] OpAmp Inverting Amplifier (DC) — VCVS accuracy

### Verification
- [x] pytest tests/ -q — 76/76 passing

## PNP BJT Support

### Implementation (MOSFET polarity pattern)
- [x] `components.py`: `_BJTBase` + `BJT_N`(_polarity=+1) + `BJT_P`(_polarity=-1), `BJT = BJT_N` alias
- [x] `circuit.py`: re-exports `BJT_N`, `BJT_P`, `PNP`, `_BJTBase`
- [x] `nl_stampers.py`: unified `stamp_bjt_nl()` with `comp._polarity` for voltage/current direction
- [x] `stamper.py`: AC linearization uses `_polarity`, registry has `BJT_N`/`BJT_P`
- [x] `netlist_parser.py`: detects PNP from `.model` card type or model name
- [x] `altium_parser.py`: uses `BJT_P` for PNP components
- [x] `exporter.py`: `isinstance(c, BJT_N)` for model name, `BJT_P` in formatters
- [x] `svg_exporter.py`, `altium_exporter.py`: updated `isinstance` checks

### Cross-Validation Tests
- [x] `test_signoff_cir_parsed` — parse signoff.cir, cross-validate MNA vs LTspice
- [x] `test_pnp_emitter_follower_dc_ac` — PNP emitter follower DC + AC vs LTspice

### Verification
- [x] pytest tests/ -q — 78/78 passing

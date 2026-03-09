# Reorganizacja Struktury Katalogów - Execution Plan

- [x] 1. **Utworzenie i Konfiguracja .gitignore**:
  - Utwórz plik `.gitignore` w głównym katalogu (lub zaktualizuj go jeśli istnieje).
  - Dodaj ignorowane reguły: `__pycache__/`, `*.pyc`, `*.log`, `*.raw`, `*.html`, `*-backups/`, `*.zip`, `.env`.
- [x] 2. **Usunięcie Plików Tymczasowych i Cache**:
  - Wyszukaj i usuń wszystkie foldery `__pycache__` z całego projektu.
  - Usuń cały folder `filter_kicad/filter_kicad-backups/` oraz `.zip` pliki KiPada.
- [x] 3. **Organizacja Głównego Katalogu (Root)**:
  - Utwórz katalog `scripts/`.
  - Przenieś do `scripts/` skrypty: `design_amp_filter.py`, `generate_filter_sch.pas`, `manual_ltspice_test.py`, `verify_opamp_filter.py`, `verify_opamp_filter_sklib.py`.
  - Utwórz katalog `results/`.
  - Przenieś do `results/` pliki wyjściowe i logi: `ac_result.html`, `dc_result.html`, `design_amp_filter.log`, `signoff.cir`, `signoff.log`, `signoff.op.raw`, `signoff.raw`, `skidl_REPL.log`, `verify_opamp_filter.log`.
  - Przenieś luźne pliki tekstowe (`*.erc`, `*.txt`) do `results/`.
- [x] 4. **Weryfikacja Modułowych Skryptów Testowych**:
  - Przenieś pozostałe skrypty np. `test_signoff.py`, `test_vin_range.py`, `test_viz.py` do właściwych katalogów (najpewniej `tests/`).
- [x] 5. **Uruchomienie Skrytów Testowych**:
  - `python -m pytest tests/` by- [x] Konfigurowalny `logging` zamiast `print()` w kluczowych modułachów (np. ścieżek importu w skryptach pythonowych odwołujących się z `root`).

---

# Plotly Visualizer - Execution Plan

- [x] 1. **Dependencies Update**:
  - Add `plotly` to the `dependencies` list in `pyproject.toml` (make sure `matplotlib` is fully absent).
  - Run `pip install --user plotly` in the terminal to apply the dependencies locally due to permission constraints.
- [x] 2. **Create New Browser Display Layer (`src/solver_sch/utils/visualizer.py`)**:
  - Implement `plot_ac(freqs, magnitudes)` exporting `ac_result.html` with a neon cyan line (`#00FFFF`), a logarithmic X-axis, and `plotly_dark`.
  - Implement `plot_transient(times, voltages)` exporting `transient_result.html` with a neon green line (`#39FF14`) and `plotly_dark`.
  - Implement `plot_monte_carlo(results, mu, sigma)` exporting `monte_carlo_result.html` with a deep purple histogram (`#800080`) and `plotly_dark`.
- [ ] 3. **Integrate Visualizer into AI CLI (`src/solver_sch/ai/auto_designer.py`)**:
  - Extensibility: parse `[VISUALIZE]` from `target_goal` to set `self.show_visualization`.
  - In `run_optimization_loop`, conditionally trigger `plot_ac(..., ...)` on AC success.
  - In `_run_monte_carlo`, conditionally trigger `plot_monte_carlo(...)` right after yield calculation.
- [x] 4. **Execute Inverter Transient Analysis**:
  - Implement `inverter.cir` following strict rule parameters.
  - Write `run_inverter.py` script to parse netlist, simulate with `MNASolver`, and trigger `plot_transient()`.
- [x] 5. **Execute SRAM Cell Transient Analysis**:
  - Implement `sram_cell.cir` designing a cross-coupled bistable flip-flop.
  - Write `run_sram.py` to trigger simulation and Plotly visualizations.
- [x] 6. **Implement Passive Physics Core: Inductor ('L')**:
  - Update `Circuit` and `NetlistParser` to map 'L' values.
  - Stamp Inductor dynamically in `stamper.py` as an auxiliary branch exactly like a Voltage Source.
  - Update AC Stamping (`1/(j*w*L)` on auxiliary offset) and Transient Backward Euler Stamping.
- [x] 7. **The Resonance Test (`tests/test_rlc.py`)**:
  - Write an automated AC test for a series RLC with $V=1V$, $R=10\Omega$, $L=1mH$, $C=1\mu F$.
  - Assert theoretical resonance at $f_0 \approx 5032.9$ Hz.
  - Fix any failures until regression passes.
- [x] 8. **Damped RLC Demonstration**:
  - Create `rlc_damped.cir` showcasing an underdamped decay logic.
  - Execute via Plotly visualization.
- [x] 9. **Implement CMOS Logic (Level 1 Shichman-Hodges)**:
  - Define `MOSFET_N` and `MOSFET_P`.
  - Update Netlist (`M` mapping with `W`, `L` extraction).
  - Analytically stamp Non-Linear Jacobian ($g_m$, $g_{ds}$) in `stamper.py`.
  - Validate with `test_cmos_logic.py` (0V/5V static points).
- [x] 10. **Implement Hierarchical Subcircuit Parsing**:
  - Update `netlist_parser.py` to extract `.SUBCKT` blocks.
  - Implement a recursive `flatten_hierarchy` routine to expand `X` instances.
  - Prefix internal nodes and component names with instance paths to prevent collisions.
  - Create and run `test_hierarchy.py` with a cascaded voltage divider.

---

# SPICE-like Component Models Architecture Plan

- [x] 1. **Utworzenie i Konfiguracja `ModelCard`**:
  - Implementacja klasy `ModelCard` w `circuit.py` do przechowywania parametrów typu NPN, D, NMOS.
  - Rejestr modeli w obiekcie `Circuit`.
- [x] 2. **Rozszerzenie Modeli Diody i BJT**:
  - Dioda: obsługa `Rs`, `Cjo`, `Vj`, `M`, `tt`, `BV`, `IBV` poza starymi parametrami Ebers-Moll.
  - BJT: wsparcie rozszerzonych parametrów Gummel-Poon (m.in. `VAF`, `VAR`, `IKF`).
- [x] 3. **Rozszerzenie Modeli MOSFET**:
  - Obsługa parametrów level 1/2/3 i bazowej nazwy modelu ze standardu SPICE.
- [x] 4. **Aktualizacja backendu LTspice `LTspiceRunner`**:
  - Generowanie dyrektyw `.model` w kodzie SPICE.
  - Powiązanie symboli (np. `D1`, `Q1`) z nazwami zdefiniowanych wcześniej modeli.
- [x] 5. **Weryfikacja**:
  - Test jednostkowy dla wczytywania i nadpisywania zachowań modułowych przez `.model`.
  - Sprawdzenie krzyżowe z symulacją SPICE (LTspice cross-validate).


---
# Cleanup unused files and Git imported repos
- [x] Delete 	asks/circuitron repository
- [x] Delete 	asks/klepcbgen repository
- [x] Delete 	asks/pcb_circuit_generator repository
- [x] Delete unused lib directory containing js tools
- [x] Clean logs

---
# Refaktoryzacja SolverSCH (~5500 LOC) — Plan Modularny

- [x] **Faza 0** — Chirurgiczny Cleanup (duplikaty importów, bare excepts, deprecated `simulate_ac()`, logger naming, `CurrentSource` w `__init__.py`, `pyproject.toml`)
- [x] **Faza 1** — Ekstrakcja Stałych (`solver_sch/constants.py`: THERMAL_VOLTAGE, GMIN, NR_MAX_ITER_*, NR_TOLERANCE, DIODE_VD_LIMIT); podłączenie konsumentów; ekstrakcja `SOLVER_ENVIRONMENT_RULES` do `system_prompts.py`
- [x] **Faza 2** — Normalizacja Nazewnictwa (`@property` zamiast zdublowanych atrybutów w BJT, MOSFET_N/P, OpAmp, Comparator)
- [x] **Faza 3** — Podział Plików (split `circuit.py` → `components.py` + `circuit.py`; ekstrakcja nl_stampers → `builder/nl_stampers.py`)
- [x] **Faza 4** — Error Handling & Type Hints (bare except w `netlist_parser.py`, type annotations w `AutonomousDesigner`)
- [x] **Faza 5** — Konsolidacja MOSFET DRY (`_MOSFETBase` z `_polarity`; unified `stamp_mosfet_nl`)

Wynik końcowy: 45/45 testów zielonych po każdej fazie.

---
# SignalAnalyzer — Pre-processor dla DesignReviewAgent

- [x] Utworzenie `solver_sch/utils/signal_analyzer.py` (`extract_ac_metrics`, `extract_transient_metrics`)
- [x] Aktualizacja `SENIOR_REVIEWER_PROMPT` — dodanie sekcji "5. DYNAMICS & STABILITY"
- [x] 45/45 testów zielonych

# SolverSCH — Complete Functional Tree

> **Context**: User requested a full scan of the codebase to understand project structure and capabilities.

---

## PROJECT OVERVIEW

**SolverSCH** is an **Autonomous EDA (Electronic Design Automation) toolkit** that combines:
- A physics-accurate MNA (Modified Nodal Analysis) circuit solver
- AI/LLM-driven autonomous design & review agents
- SPICE + Altium format parsers and exporters
- A PySide6 desktop GUI
- Cross-validation against commercial LTspice simulator

---

## FUNCTIONAL TREE

```
SolverSCH
│
├── 1. DOMAIN MODEL  (solver_sch/model/)
│   ├── components.py — Electronic component abstractions
│   │   ├── ModelCard          — SPICE .model parameter container
│   │   ├── Component (ABC)    — Base: name, nodes(), value
│   │   ├── TwoTerminalPassive — Base for R, C, L, V, I, D
│   │   │   ├── Resistor        — Linear R
│   │   │   ├── Capacitor       — Linear C (transient state)
│   │   │   ├── Inductor        — Ideal L (i_prev state for Backward Euler)
│   │   │   ├── VoltageSource   — Independent DC V
│   │   │   ├── ACVoltageSource — Sine AC source (amplitude, freq, dc_offset, ac_mag, ac_phase)
│   │   │   ├── CurrentSource   — Independent DC I
│   │   │   └── Diode           — Shockley model (Is, n, Vt, Vz for Zener)
│   │   ├── ThreeTerminalActive — Base for BJT, MOSFET, OpAmp, Comparator
│   │   │   ├── _BJTBase        — Ebers-Moll shared (Is, Bf, Br, _polarity)
│   │   │   │   ├── BJT_N (NPN, _polarity=+1)
│   │   │   │   └── BJT_P (PNP, _polarity=-1)
│   │   │   ├── _MOSFETBase     — Shichman-Hodges Level 1 (W, L, Vth, Kp, λ, _polarity)
│   │   │   │   ├── MOSFET_N (NMOS, _polarity=+1)
│   │   │   │   └── MOSFET_P (PMOS, _polarity=-1)
│   │   │   ├── OpAmp           — Ideal VCVS (gain)
│   │   │   └── Comparator      — Nonlinear tanh-based comparator (v_high, v_low, k)
│   │   └── LM5085Gate          — Behavioral PGATE driver (5-node, sigmoid model)
│   │
│   ├── circuit.py — Netlist container
│   │   └── Circuit
│   │       ├── add_component() / get_components()
│   │       ├── add_model() / get_models()
│   │       ├── get_unique_nodes()
│   │       ├── validate() → ValidationResult
│   │       ├── apply_models()  — merge .model cards into component params
│   │       ├── describe() → dict (LLM-readable)
│   │       └── draw(filepath) → SVG schematic
│   │
│   └── altium_model.py — Altium design dataclasses
│       ├── AltiumComponent    — designator, footprint, comment
│       ├── AltiumPin          — designator-pin reference
│       ├── AltiumNet          — net name + list of pins
│       ├── BomEntry           — BOM row (part, MPN, manufacturer, supplier)
│       └── AltiumProject      — full design (components, nets, BOM)
│
├── 2. MNA BUILDER  (solver_sch/builder/)
│   ├── stamper.py — MNAStamper: Circuit → sparse matrix A·x = z
│   │   ├── _map_nodes()           — assign node/source indices
│   │   ├── stamp_linear()         — R, V, I, OpAmp, Comparator, LM5085Gate
│   │   ├── stamp_nonlinear(x_prev)— Diode, BJT, MOSFET via NL registry → COO Jacobian
│   │   ├── stamp_ac(freq_hz)      — small-signal complex matrix (linearized at DC point)
│   │   │   ├── _stamp_ac_diode()
│   │   │   ├── _stamp_ac_bjt()
│   │   │   └── _stamp_ac_mosfet()
│   │   ├── stamp_transient_basis() — C/dt and L/dt structural entries (Backward Euler)
│   │   ├── stamp_transient_sources()— L/C history contributions per timestep
│   │   ├── stamp_dynamic_sources() — time-varying ACVoltageSource
│   │   ├── update_states()         — sync inductor i_prev
│   │   └── set_dc_solution()       — store DC point for AC linearization
│   │
│   └── nl_stampers.py — Newton-Raphson companion models
│       ├── stamp_diode_nl()        — Shockley + Zener breakdown + voltage limiting
│       ├── stamp_bjt_nl()          — Ebers-Moll unified NPN/PNP (polarity)
│       ├── stamp_mosfet_nl()       — Shichman-Hodges NMOS/PMOS (polarity)
│       ├── stamp_comparator_nl()   — tanh comparator Jacobian
│       ├── stamp_lm5085_gate_nl()  — sigmoid PGATE driver Jacobian
│       └── _apply_fet_matrix_stamp()— shared NMOS/PMOS gm+gds+GMIN pattern
│
├── 3. NUMERICAL SOLVER  (solver_sch/solver/)
│   └── sparse_solver.py — SparseSolver
│       ├── MNAResult               — {node_voltages, source_currents, x_converged}
│       ├── _inject_gmin()          — static: diagonal GMIN for stability
│       ├── _build_mna_result()     — map solution vector → structured result
│       ├── _nr_converge()          — Newton-Raphson loop (max 100 iter, tol 1e-6)
│       ├── solve()                 — DC operating point (NR + GMIN)
│       ├── simulate_transient()    — Backward Euler time stepping
│       ├── simulate_ac_sweep()     — Log-spaced AC frequency sweep
│       └── simulate_ac_discrete()  — AC at discrete frequency list
│
├── 4. SIMULATOR API  (solver_sch/simulator.py)
│   └── Simulator  — High-level facade (LLM-friendly)
│       ├── dc()                    → DcAnalysisResult
│       ├── ac(f_start, f_stop, ppd) → AcAnalysisResult
│       ├── transient(t_stop, dt)   → TransientAnalysisResult
│       ├── validate()              → ValidationResult
│       ├── info()                  → dict (circuit description)
│       ├── report()                → .xlsx report
│       ├── review() [async]        → markdown AI review
│       └── compare_with_ltspice()  → comparison dict
│
├── 5. RESULT TYPES  (solver_sch/results.py)
│   ├── DcAnalysisResult           — {node_voltages, source_currents}
│   ├── AcAnalysisResult           — {frequencies, nodes: NodeAcResult[mag_db, phase_deg]}
│   ├── TransientAnalysisResult    — {timepoints: TransientTimepoint[]}
│   ├── ValidationResult           — {valid, errors, warnings}
│   └── All results → .to_dict() / .to_json()
│
├── 6. PARSERS  (solver_sch/parser/)
│   ├── netlist_parser.py — SPICE text → Circuit
│   │   └── NetlistParser
│   │       ├── _parse_value()      — "4.7k" → 4700.0, "10uF" → 1e-5
│   │       ├── _clean_line()       — strip comments
│   │       ├── _flatten_hierarchy()— recursive .SUBCKT instantiation
│   │       └── parse_netlist()     — main entry point → Circuit
│   │
│   └── altium_parser.py — Altium .NET → Circuit
│       └── AltiumParser
│           ├── parse_netlist_file() / parse_netlist_content()
│           ├── parse_bom() [.xls] / parse_bom_xlsx() [.xlsx]
│           ├── extract_value()     — "100k 1% 0402" → 100000.0
│           ├── is_analog_component()— filter out digital ICs
│           ├── isolate_subcircuit()— BFS subcircuit extraction by net boundary
│           └── convert_to_circuit()— AltiumProject → Circuit
│
├── 7. AI / AGENTS  (solver_sch/ai/)
│   ├── auto_designer.py — Autonomous design loop
│   │   └── AutonomousDesigner
│   │       ├── run_optimization_loop(max_iter) — LLM → netlist → MNA → feedback → repeat
│   │       ├── _extract_netlist()  — regex extract SPICE block from LLM response
│   │       ├── _run_monte_carlo()  — N simulations with component tolerance
│   │       └── _perturb_netlist()  — 5% Gaussian R/C variation
│   │
│   ├── agent.py — Two-phase discovery + reporting loop
│   │   └── run_review() [async]
│   │       ├── Phase 1: Discovery  — tool calling loop (max 3 iter, dedup, stops on "READY")
│   │       └── Phase 2: Reporting  — structured markdown report (no tools)
│   │
│   ├── design_reviewer.py — DesignReviewAgent facade
│   │   └── DesignReviewAgent
│   │       ├── review_design_async()— → run_review()
│   │       ├── _format_prompt()    — BOM + netlist + datasheet + sim → markdown prompt
│   │       ├── _load_component_cards()— load .card.json per BOM component
│   │       └── _safe_json()        — numpy/complex JSON serializer
│   │
│   ├── tools.py — LLM tool implementations
│   │   ├── ToolRegistry            — register / get_schemas / async call
│   │   ├── tool_recalculate_divider()  — R1/R2 for voltage divider
│   │   ├── tool_recalculate_opamp_gain()— Rfb for inverting gain
│   │   ├── tool_analyze_diagram() [async] — Gemini Vision: image + question → text
│   │   ├── tool_query_datasheet() [async] — BM25Plus search over PDF/index
│   │   ├── tool_simulate_dc_sweep()— MNA-based DC sweep of comparator channel
│   │   ├── _load_datasheet_index() — cache PDF parsing → .index.json
│   │   └── _search_bm25()         — BM25Plus ranking over text chunks
│   │
│   ├── chat.py — Interactive CLI chat loop
│   │   ├── run_chat()              — REPL with tool calling (max 8 tool rounds)
│   │   ├── _tool_simulate_circuit()— execute DC/AC/transient from LLM request
│   │   └── _execute_tool()        — dispatch tool by name
│   │
│   ├── llm_providers.py — Provider factory
│   │   ├── LLMProvider (ABC)       — generate() / chat()
│   │   ├── GeminiProvider          — Google Gemini API (rate-limit retry)
│   │   ├── OpenAIProvider          — OpenAI ChatCompletion
│   │   ├── AnthropicProvider       — Claude API
│   │   ├── OllamaProvider          — Local Ollama HTTP
│   │   ├── StubProvider            — Offline hardcoded responses
│   │   └── get_provider()          — factory function by name
│   │
│   ├── llm_backends.py — Unified async LLMClient
│   │   └── LLMClient
│   │       ├── call_async()        — dispatch to backend
│   │       ├── _call_ollama_async()— POST /api/chat
│   │       └── _call_gemini_async()— Gemini SDK tool schema conversion
│   │
│   └── system_prompts.py — Prompt registry
│       ├── SOLVER_ENVIRONMENT_RULES — Design rule constraints
│       ├── REVIEW_RULES            — 7 rule categories (power, signal, protection, etc.)
│       ├── SENIOR_REVIEWER_PROMPT  — Pre-built default system prompt
│       └── build_reviewer_prompt() — Assemble prompt from rule registry
│
├── 8. EXPORTERS & UTILITIES  (solver_sch/utils/)
│   ├── exporter.py — Circuit → SPICE .cir
│   │   └── LTspiceExporter.export()
│   │       └── _fmt_*() formatters (R, C, L, V, I, OpAmp, Diode, BJT, MOSFET, Comparator, LM5085)
│   │
│   ├── altium_exporter.py — Circuit → Altium DelphiScript .pas
│   │   └── AltiumScriptExporter.export()
│   │
│   ├── svg_exporter.py — Circuit → SVG schematic
│   │   └── SVGExporter.generate()
│   │       ├── _generate_cell_for_comp() — dispatch component → netlistsvg cell
│   │       ├── Invoke netlistsvg subprocess (ELK layout engine)
│   │       ├── _autofit_viewbox()  — post-process SVG dimensions
│   │       └── _brute_force_svg_align()— post-process for alignment
│   │
│   ├── ltspice_comparator.py — Numerical comparison SolverSCH vs LTspice
│   │   └── LTspiceComparator
│   │       ├── compare_dc()        → ComparisonResult (node-by-node, PASS/WARN/FAIL)
│   │       ├── compare_ac()        → ComparisonResult (freq-by-freq, 1dB/5° tolerance)
│   │       └── compare_transient() → ComparisonResult
│   │
│   ├── ltspice_runner.py — LTspice batch execution + .raw parsing
│   │   └── LTspiceRunner
│   │       ├── run_dc()            → (node_voltages, source_currents)
│   │       ├── run_ac()            → (frequencies, complex_magnitudes)
│   │       └── run_transient()     → (times, node_voltages)
│   │
│   ├── signal_analyzer.py — Waveform metrics
│   │   ├── extract_ac_metrics()   → {peak_gain_db, bw_3db_hz, phase_margin_deg}
│   │   └── extract_transient_metrics() → {v_steady, v_max, peak_overshoot_pct}
│   │
│   ├── excel_report.py — Multi-sheet .xlsx report
│   │   └── ExcelReportGenerator.generate()
│   │       ├── _write_summary()    — Circuit overview sheet
│   │       ├── _write_dc()         — DC operating point table
│   │       ├── _write_ac()         — Bode plot (magnitude + phase)
│   │       ├── _write_transient()  — Waveform chart
│   │       └── _write_ltspice_comparison()— PASS/WARN/FAIL comparison sheet
│   │
│   ├── kicad_exporter.py — Circuit → KiCad netlist via SKiDL
│   │   └── SkidlExporter.export()
│   │
│   ├── kicad_auto_layout.py — Auto placement + routing
│   │   ├── AutoPlacer.place()      — BFS level-based grid placement
│   │   └── AutoRouter.route()      — Manhattan routing with collision avoidance
│   │
│   └── verifier.py — LTspice sign-off
│       └── LTspiceVerifier
│           ├── verify()            — export → run LTspice → parse .raw
│           └── verify_dc()         → (bool passed, message)
│
├── 9. GUI  (solver_sch/gui/)
│   ├── __init__.py → launch_gui()
│   ├── main_window.py — MainWindow (1400×800, 3-panel splitter)
│   │   ├── NetlistPanel (left, 280px)
│   │   ├── ConfigPanel  (center, 240px)
│   │   └── ResultsPanel (right, 900px)
│   │
│   ├── netlist_panel.py — Netlist editor + circuit tree
│   │   ├── Load .cir → parse → validate → populate tree
│   │   └── Signal: circuit_loaded(str, Circuit)
│   │
│   ├── config_panel.py — Simulation configurator
│   │   ├── Analysis type: DC / AC / Transient
│   │   ├── AC params: f_start, f_stop, points/decade
│   │   ├── Transient params: t_stop, dt
│   │   ├── Source voltage overrides
│   │   ├── Output node selector
│   │   └── Signal: run_requested(str, dict)
│   │
│   ├── results_panel.py — Results viewer (3 tabs)
│   │   ├── DC tab: node voltage table + bar chart
│   │   ├── AC tab: Bode plot (magnitude + phase) + node selector
│   │   └── Transient tab: waveform plot + node selector
│   │
│   ├── sim_worker.py — Background QThread simulation runner
│   │   ├── Signal: result_ready(object, float)
│   │   └── Signal: sim_error(str)
│   │
│   └── plot_widget.py — PlotCanvas (matplotlib Agg → QPixmap)
│       ├── plot_dc_bar()       — node voltage bar chart
│       ├── plot_ac()           — Bode plot (semilog, magnitude + phase)
│       └── plot_transient()    — time-domain waveforms
│
├── 10. CLI  (solver_sch/cli.py)
│   └── solversch [subcommand]
│       ├── ai              — Interactive autonomous design loop (AutonomousDesigner)
│       ├── review          — AI design review of SPICE netlist (async, Gemini)
│       ├── analyze         — Agent-driven analysis with tool calling
│       ├── gui [file]      — Launch PySide6 desktop application
│       ├── chat            — Multi-turn LLM chat with simulate_circuit tool
│       └── altium-to-spice — Altium .NET → SPICE .cir converter
│
└── 11. SUPPORT  (solver_sch/)
    ├── constants.py — Physics & solver constants
    │   ├── THERMAL_VOLTAGE = 0.02585 V
    │   ├── GMIN = 1e-12 S
    │   ├── DIODE_VD_LIMIT = 0.8 V
    │   ├── BJT_VBE_LIMIT = 0.8 V
    │   ├── NR_MAX_ITER_DC = 100
    │   └── NR_TOLERANCE = 1e-6
    │
    └── registry.py — Component/analysis metadata for LLMs
        ├── COMPONENT_REGISTRY      — introspected component schemas
        ├── available_components()  → JSON string
        ├── available_analyses()    → JSON string
        └── component_help(name)    → JSON string
```

---

## DATA FLOW (End-to-End)

```
[SPICE text / Altium .NET]
         │
         ▼
    NetlistParser / AltiumParser
         │
         ▼  Circuit (components + nodes)
         │
         ▼
    MNAStamper ──── stamp_linear() ──────────────────────────────┐
         │          stamp_nonlinear(x_prev) ← nl_stampers.py     │
         │          stamp_ac(freq)                               │
         │          stamp_transient_*()                          │
         │                                                       │
         ▼  (lil_matrix A, ndarray z, callbacks)                 │
    SparseSolver                                                  │
         │   DC → NR loop → spsolve()                           │
         │   AC → complex matrix per freq                       │
         │   Transient → Backward Euler per timestep            │
         │                                                       │
         ▼  MNAResult → wrapped in                              │
    DcAnalysisResult / AcAnalysisResult / TransientAnalysisResult│
         │                                                       │
         ├─→ Simulator.report() → ExcelReportGenerator (.xlsx)  │
         ├─→ Simulator.review() → DesignReviewAgent (markdown)  │
         ├─→ LTspiceComparator.compare_*() (PASS/WARN/FAIL)     │
         └─→ GUI ResultsPanel (tables + plots)                  │
                                                                 │
    (also)                                                        │
    LTspiceExporter → .cir file → LTspiceRunner → .raw → parse ─┘
```

---

## TEST SUITE OVERVIEW (37 test files, 78+ tests)

| Category | Test Files | Coverage |
|---|---|---|
| Linear components | test_ac.py, test_rlc.py, test_dynamics.py | RC, RLC, AC sweep, coupling caps |
| Nonlinear devices | test_diode.py, test_bjt_inverter.py, test_mosfet.py, test_mosfet_triode.py, test_zener.py | Diode, NPN, PNP, NMOS, PMOS |
| Logic circuits | test_cmos_logic.py, test_comparator.py | CMOS inverter, tanh comparator |
| Transient | test_transient.py, test_rectifier.py | RC charging, half-wave rectifier |
| Cross-validation | test_mna_vs_ltspice.py, test_cross_validation.py, test_spice_models_crossval.py, test_ltspice_components.py | MNA vs LTspice DC/AC/transient |
| Parsers | test_parser.py, test_altium_parser.py, test_model_cards.py | SPICE + Altium parsing |
| Complex circuits | test_signoff.py, test_boss_fight.py, test_600v_detector.py, test_lm5085_analysis.py, test_comparator_a1_analysis.py | End-to-end integration |
| AI/Agents | test_auto_designer_pareto.py, test_auto_designer_monte_carlo.py, test_review_pipeline.py, test_review_e2e_hard.py | Design loop, review agent |
| RAG/Search | test_datasheet_rag.py, test_hierarchical_rag.py | Datasheet lookup |
| Vision | test_multimodal_vision.py | Gemini image analysis |
| Hierarchy | test_hierarchy.py, test_isolate_subcircuit.py, test_pipeline.py | Subcircuit extraction |

---

## KEY ARCHITECTURAL PATTERNS

| Pattern | Where | Purpose |
|---|---|---|
| **Voltage limiting** | nl_stampers.py | Prevent exp() overflow in NR (diode ≤0.8V, BJT Vbe ≤0.8V) |
| **GMIN injection** | sparse_solver.py, nl_stampers.py | Prevent singular matrices from floating nodes (1e-12 S to diagonal) |
| **Callback injection** | simulator.py → sparse_solver | Decouple physics (stamper) from math (solver) |
| **Polarity flag** | _BJTBase, _MOSFETBase | Unified NPN/PNP and NMOS/PMOS with single stamper |
| **LIL→CSR conversion** | stamper.py → sparse_solver | O(1) mutation during construction, O(N) CSR for spsolve |
| **Backward Euler** | sparse_solver (transient) | Unconditionally stable implicit integration |
| **BM25Plus** | tools.py | Correct IDF for small corpora (avoids BM25Okapi zero-score bug) |
| **BFS subcircuit isolation** | altium_parser.py | Extract single functional block from flat netlist by net boundary |
| **Tool deduplication** | agent.py | Prevent LLM tool calling loops (set-based duplicate detection) |

"""
test_llm_live.py -> Testuje nowe API SolverSCH w boju z prawdziwym LLM.

Pipeline:
1. LLM (Gemini/OpenAI) dostaje listę dostępnych komponentów i analiz
2. LLM buduje obwód (RC filtr) jako kod Python
3. Simulator uruchamia DC + AC + Transient
4. Wyniki w JSON wracają do LLM
5. LLM interpretuje wyniki i pisze raport
6. Generujemy plik Excel

Uruchomienie:
    python scripts/test_llm_live.py --provider gemini
    python scripts/test_llm_live.py --provider openai
    python scripts/test_llm_live.py --provider stub   # offline, bez klucza
"""

import sys, os, json, argparse, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("test_llm_live")

from solver_sch import (
    Circuit, Resistor, Capacitor, ACVoltageSource, Simulator,
    available_components, available_analyses, component_help,
)
from solver_sch.ai.llm_providers import get_provider


# ─────────────────────────────────────────────────────────────────
# Step 1: Prepare the tool context for the LLM
# ─────────────────────────────────────────────────────────────────

TOOL_CONTEXT = f"""
You have access to SolverSCH — a Python circuit simulator. Here is the complete component catalogue:

{available_components()}

Available simulation methods:
{available_analyses()}

To use it:
    from solver_sch import Circuit, Resistor, Capacitor, ACVoltageSource, Simulator

    circuit = Circuit("My Circuit")
    circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000))
    circuit.add_component(Resistor("R1", "in", "out", 10000))
    circuit.add_component(Capacitor("C1", "out", "0", 1e-7))

    sim = Simulator(circuit)
    dc_result  = sim.dc()   # -> DcAnalysisResult (.to_json())
    ac_result  = sim.ac(f_start=10, f_stop=1e6)
    tr_result  = sim.transient(t_stop=5e-3, dt=10e-6)
"""


def run_test(provider_name: str, api_key: str | None = None, task: str = "") -> None:
    log.info("=== SolverSCH LLM Live Test ===")
    log.info("Provider: %s", provider_name)
    log.info("Task: %s", task)

    if not task:
        task = (
            "Design an RLC bandpass filter centered at 5 kHz with Q ≈ 5. "
            "Use standard E12 component values. Must have 'in' and 'out' nodes."
        )

    # ── Provider setup ──────────────────────────────────────────
    kwargs = {}
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
        os.environ["OPENAI_API_KEY"] = api_key

    llm = get_provider(provider_name, **kwargs)
    log.info("LLM Provider ready: %s", type(llm).__name__)

    # ─────────────────────────────────────────────────────────────
    # PHASE 1: Ask LLM to design a circuit
    # ─────────────────────────────────────────────────────────────

    design_prompt = f"""
You are an electronics engineer using SolverSCH simulator.

{TOOL_CONTEXT}

TASK: {task}

MANDATORY RULES (violation will cause silent -400 dB results):
1. You MUST add an ACVoltageSource on the signal input node. This is DIFFERENT from VoltageSource (which is DC-only).
   ACVoltageSource provides both the AC small-signal stimulus AND the time-domain sine wave.
   Example: ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000)
2. DC supply voltage (e.g. Vcc) should use VoltageSource. Input signal uses ACVoltageSource.
3. Use only standard E12 component values.
4. The code must end with: result_circuit = circuit
5. Do not import anything — all classes are already available.
6. Do not run the simulation — only build and return the circuit.

Available classes: Circuit, ACVoltageSource, VoltageSource, Resistor, Capacitor, Inductor, Diode, BJT, OpAmp

Output ONLY this format, nothing else:
```python
circuit = Circuit("My Circuit Name")
circuit.add_component(VoltageSource("Vcc", "vcc", "0", 5.0))          # DC supply
circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000))  # SIGNAL INPUT (mandatory!)
circuit.add_component(...)
...
result_circuit = circuit
```
"""

    log.info("[PHASE 1] Asking LLM to design circuit...")
    design_response = llm.generate(
        design_prompt,
        system_instruction="You are an expert analog electronics engineer. Output ONLY the requested Python code block, no explanations, no prose."
    )

    print("\n" + "="*60)
    print("LLM DESIGN RESPONSE:")
    print("="*60)
    print(design_response)

    # ── Extract and execute the code ────────────────────────────
    import re
    match = re.search(r"```python\n(.*?)\n```", design_response, re.DOTALL | re.IGNORECASE)
    if not match:
        # Try without language specifier
        match = re.search(r"```\n(.*?)\n```", design_response, re.DOTALL)

    if not match:
        log.warning("LLM did not return a code block. Using fallback RC filter.")
        circuit_code = """
circuit = Circuit("RC LP Filter 1kHz (fallback)")
circuit.add_component(ACVoltageSource("Vin", "in", "0", amplitude=1.0, frequency=1000))
circuit.add_component(Resistor("R1", "in", "out", 15000))
circuit.add_component(Capacitor("C1", "out", "0", 1e-8))
result_circuit = circuit
"""
    else:
        circuit_code = match.group(1)

    log.info("[PHASE 1] Executing LLM circuit code...")
    from solver_sch.registry import get_component_classes
    exec_ns = get_component_classes()
    exec_ns["Circuit"] = Circuit
    exec(circuit_code, exec_ns)
    circuit = exec_ns.get("result_circuit")

    if circuit is None:
        raise RuntimeError("LLM code did not set 'result_circuit'. Cannot continue.")

    # ── Validate ─────────────────────────────────────────────────
    validation = circuit.validate()
    print(f"\n[VALIDATE] valid={validation.valid}")
    if validation.errors:
        for e in validation.errors:
            print(f"  ERROR: {e.message}")
    if validation.warnings:
        for w in validation.warnings:
            print(f"  WARN:  {w.message}")

    # ─────────────────────────────────────────────────────────────
    # PHASE 2: Run simulations with the Simulator facade
    # ─────────────────────────────────────────────────────────────
    log.info("[PHASE 2] Running simulations via Simulator facade...")
    sim = Simulator(circuit, validate_on_init=False)

    # DC
    dc = sim.dc()
    dc_json = dc.to_json()
    print("\n[DC RESULT JSON]:")
    print(dc_json)

    # AC
    ac = sim.ac(f_start=10, f_stop=100e3, points_per_decade=20)
    at_1k = ac.at_frequency(1000)
    print(f"\n[AC] At 1kHz: {json.dumps(at_1k, indent=2)}")

    # Find -3dB frequency
    out_node = next(iter(ac.nodes))  # first non-ground node, usually 'out'
    ac_data = ac.nodes[out_node]
    import numpy as np
    ref_db = max(ac_data.magnitude_db)
    crossings = [(ac.frequencies[i], ac_data.magnitude_db[i])
                 for i in range(len(ac.frequencies))
                 if ac_data.magnitude_db[i] <= ref_db - 3.0]
    f3db = crossings[0][0] if crossings else None
    if f3db:
        print(f"\n[AC] -3dB crossover on '{out_node}': {f3db:.1f} Hz")
    else:
        print("\n[AC] -3dB point not found in sweep range")


    # Transient
    tr = sim.transient(t_stop=3e-3, dt=5e-6)
    print(f"\n[TRANSIENT] {len(tr.timepoints)} timesteps computed")

    # ─────────────────────────────────────────────────────────────
    # PHASE 2b: LTspice Cross-Validation
    # ─────────────────────────────────────────────────────────────
    log.info("[PHASE 2b] Running LTspice Cross-Validation...")
    try:
        ac_params = {"f_start": 10, "f_stop": 100e3, "points_per_decade": 20}
        ltspice_results = sim.compare_with_ltspice(
            analyses=["dc", "ac", "transient"],
            tolerance_pct=1.0,
            ac_params=ac_params,
            transient_params={"t_stop": 3e-3, "dt": 5e-6}
        )
        print("\n[LTSPICE COMPARISON RESULT]:")
        for analysis_name, comp_result in ltspice_results.items():
            print(f"  {comp_result.summary()}")
    except Exception as e:
        log.warning(f"LTspice Validation failed or skipped: {e}")
        ltspice_results = None

    # ─────────────────────────────────────────────────────────────
    # PHASE 3: Give results back to LLM for interpretation
    # ─────────────────────────────────────────────────────────────
    
    ltspice_context = ""
    if ltspice_results:
        ltspice_context = "LTspice Cross-Validation Results:\n"
        for analysis_name, comp_result in ltspice_results.items():
            ltspice_context += f"- {comp_result.summary()}\n"
            if not comp_result.passed:
                ltspice_context += "  (Some nodes failed matching with LTspice within tolerance)\n"
    
    analysis_prompt = f"""
You designed a circuit. Here are the simulation results from SolverSCH.

Circuit info: {json.dumps(sim.info(), indent=2)}

DC Operating Point:
{dc_json}

AC Analysis — values at 1 kHz:
{json.dumps(at_1k, indent=2)}

-3dB frequency (measured): {f"{f3db:.1f} Hz" if f3db else "not found in sweep range"}

{ltspice_context}

Based on the simulation results:
1. Did the circuit meet the target requirements?
2. What are the key performance metrics of your design?
3. If LTspice comparison failed, what might be the cause? (e.g. ideal vs non-ideal models)

Write a brief engineering summary (3-5 sentences).
"""

    log.info("[PHASE 3] Asking LLM to interpret results...")
    interpretation = llm.generate(analysis_prompt)

    print("\n" + "="*60)
    print("LLM RESULT INTERPRETATION:")
    print("="*60)
    print(interpretation)

    # ─────────────────────────────────────────────────────────────
    # PHASE 4: Generate Excel report
    # ─────────────────────────────────────────────────────────────
    log.info("[PHASE 4] Generating Excel report...")
    report_path = os.path.join(os.path.dirname(__file__), "..", "LLM_Test_Report.xlsx")
    report_path = os.path.abspath(report_path)
    sim.report(
        report_path, 
        analyses=["summary", "dc", "ac", "bom"], 
        auto_open=False,
        ac_params={"f_start": 10, "f_stop": 100e3, "ppd": 20},
        ltspice_results=ltspice_results
    )
    print(f"\n[REPORT] Saved to: {report_path}")

    print("\n" + "="*60)
    print("=== TEST COMPLETE ===")
    print("="*60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test SolverSCH Simulator with a live LLM API"
    )
    parser.add_argument(
        "--provider", default="ollama",
        choices=["gemini", "openai", "anthropic", "ollama", "stub"],
        help="LLM provider to use (default: gemini)"
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key (alternatively set GEMINI_API_KEY / OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--task", default=(
            "Design an inverting summing amplifier combining two input voltages 'Vin1' and 'Vin2' into an 'out' voltage. "
            "Use an ideal OpAmp. Set the gain for both inputs to -1 using 10k resistors. "
            "The inputs should be ACVoltageSources. Make Vin1 1kHz 1V and Vin2 2kHz 0.5V."
        ),
        help="Circuit design task description for the LLM"
    )
    args = parser.parse_args()

    run_test(provider_name=args.provider, api_key=args.api_key, task=args.task)

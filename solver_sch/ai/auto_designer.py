"""
Autonomous AI Designer
Top-level Agent Loop integrating the Headless EDA simulator.
Evaluates AI-generated Netlists through closed-loop physical feedback.
"""
import os
import re
import random
import numpy as np
from typing import List, Dict

from google import genai
from google.genai import types

from solver_sch.parser.netlist_parser import NetlistParser
from solver_sch.builder.stamper import MNAStamper
from solver_sch.solver.sparse_solver import SparseSolver
from solver_sch.utils.verifier import LTspiceVerifier

import time
from google.genai import errors

def ask_llm(prompt_history: List[Dict[str, str]]) -> str:
    """
    Executes a real generative inference using the Google Gemini API.
    Calls `gemini-2.5-flash` for high-performance deterministic hardware engineering.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("CRITICAL ERROR: GEMINI_API_KEY environment variable is not set. Please set it to run the Autonomous Designer.")
        
    client = genai.Client(api_key=api_key)
    
    # Extract only the content values since our list uses generic dict maps.
    full_prompt = "\n\n".join([msg.get("content", "") for msg in prompt_history])
    
    while True:
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are an expert analog electronics engineer. You design circuits based on user requirements. You MUST output ONLY valid SPICE netlists wrapped in ```spice``` markdown blocks. Do not add explanations. Use standard E12 resistor values.",
                    temperature=0.1 # Low temperature for deterministic engineering
                )
            )
            return response.text
        except errors.ClientError as e:
            if e.code == 429:
                print("\n[API QUOTA REACHED] Naruszono limit zapytań Gemini Free Tier (Błąd 429).")
                print("Usypianie agenta na 45 sekund w celu zresetowania limitu chmury...")
                time.sleep(45)
                print("[RESUMING] Ponawianie uderzenia do chmury obliczeniowej...")
            else:
                # Re-raise other unexpected ClientErrors
                raise e

class AutonomousDesigner:
    """An AI Agent that iterates over circuit designs using a real MNA physical environment."""
    
    def __init__(self, target_goal: str):
        self.target_goal = target_goal
        
        match_dc = re.search(r"\[DC TARGET: ([\d\.]+)V\]", self.target_goal, re.IGNORECASE)
        match_ac = re.search(r"\[AC TARGET: ([\d\.]+)Hz ([\-\d\.]+)dB\]", self.target_goal, re.IGNORECASE)
        match_current = re.search(r"\[MAX CURRENT: ([\d\.]+)mA\]", self.target_goal, re.IGNORECASE)
        match_mc = re.search(r"\[MONTE CARLO: (\d+)\]", self.target_goal, re.IGNORECASE)
        match_schematic = re.search(r"\[SCHEMATIC\]", self.target_goal, re.IGNORECASE)
        self.show_schematic = bool(match_schematic)
        
        self.target_max_current_ma = None
        if match_current:
            self.target_max_current_ma = float(match_current.group(1))
            
        self.monte_carlo_runs = 0
        if match_mc:
            self.monte_carlo_runs = int(match_mc.group(1))
        
        if match_dc:
            self.sim_mode = 'DC'
            self.target_dc_voltage = float(match_dc.group(1))
        elif match_ac:
            self.sim_mode = 'AC'
            self.target_ac_freq = float(match_ac.group(1))
            self.target_ac_mag = float(match_ac.group(2))
        else:
            self.sim_mode = 'AC'
            self.target_ac_freq = 159.15
            self.target_ac_mag = -3.0
            
        # System prompt restricting the LLM output exclusively to actionable Hardware definitions
        self.system_prompt = (
            "You are an expert analog electronics engineer. You design circuits based on user requirements. "
            "You MUST output ONLY valid SPICE netlists wrapped in ```spice``` markdown blocks. "
            "Do not add explanations or standard text, just the raw SPICE syntax block."
        )
        
        # In-memory session history
        self.conversation_history: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        
    def _extract_netlist(self, ai_response: str) -> str:
        """Uses Regex to aggressively extract the raw netlist from an LLM response."""
        # Match anything inside ```spice \n ... \n```
        match = re.search(r"```spice\n(.*?)\n```", ai_response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Fallback if markdown block is missing
        return ai_response.strip()

    def run_optimization_loop(self, max_iterations: int = 5):
        """
        Executes the iterative design-evaluate-adjust feedback loop natively.
        Targeting an RC 159Hz (-3dB) filter logic.
        """
        print(f"=== Autonomous Designer Session STARTED ===")
        print(f"Goal: {self.target_goal}")
        
        # 1. Initiating the Goal
        self.conversation_history.append({"role": "user", "content": self.target_goal})
        
        for iteration in range(1, max_iterations + 1):
            print(f"\n[{self.sim_mode} Evaluation Mode Activacted]")
            print(f"[Iteration {iteration}/{max_iterations}] Calling LLM...")
            
            # Step 1: Infer LLM Generation
            ai_text = ask_llm(self.conversation_history)
            self.conversation_history.append({"role": "assistant", "content": ai_text})
            
            # Step 2: Extract strictly formatted Netlist
            netlist_str = self._extract_netlist(ai_text)
            print("Extracted Netlist:\n" + "-"*40 + f"\n{netlist_str}\n" + "-"*40)
            
            try:
                # Step 3: Parsing string to Circuit domain
                circuit = NetlistParser.parse_netlist(netlist_str, circuit_name=f"AI_Iter_{iteration}")
                
                # Step 4: Compiling to numerical physics space
                stamper = MNAStamper(circuit)
                stamper.stamp_linear()
                
                solver = SparseSolver(
                    A_matrix=stamper.A_lil,
                    z_vector=stamper.z_vec,
                    node_to_idx=stamper.node_to_idx,
                    vsrc_to_idx=stamper.vsrc_to_idx,
                    n_independent_nodes=stamper.n
                )
                
                if self.sim_mode == 'AC':
                    # Step 5: Evaluation Sweep covering target freq
                    f_start = max(1.0, self.target_ac_freq / 10.0)
                    f_stop = self.target_ac_freq * 10.0
                    freqs, mags_db, phases_deg = solver.simulate_ac(
                        f_start=f_start, 
                        f_stop=f_stop, 
                        points_per_decade=50, 
                        stamper_ref=stamper
                    )
                    
                    # Step 6: Finding output at exactly target cutoff range
                    idx_target = (np.abs(freqs - self.target_ac_freq)).argmin()
                    mag_at_target = mags_db.get("out", np.zeros(len(freqs)))[idx_target]
                    
                    print(f"[Verification] Mag at {freqs[idx_target]:.2f}Hz = {mag_at_target:.3f} dB")
                    
                    # Step 7 (Feedback): Perfect Condition
                    # Math limits: Target -3.0 dB ~ Tol +/- 0.5dB
                    if abs(mag_at_target - self.target_ac_mag) <= 0.5:
                        print("--> SUCCESS: AI designed the circuit perfectly!")
                        if self.monte_carlo_runs > 0:
                            self._run_monte_carlo(netlist_str, 'AC')
                        break
                        
                    # Step 8 (Correction): Deviation Trigger Callback
                    else:
                        feedback = (
                            f"Simulation failed. At {self.target_ac_freq}Hz, the magnitude was {mag_at_target:.2f} dB. "
                            f"Target is {self.target_ac_mag} dB. Please adjust R or C values and provide the updated netlist."
                        )
                        print(f"--> FAILED: Providing feedback to LLM: {feedback}")
                        self.conversation_history.append({"role": "user", "content": feedback})
                
                elif self.sim_mode == 'DC':
                    mna_result = solver.solve()
                    v_out = mna_result.node_voltages.get('out', 0.0)
                    i_v1 = mna_result.voltage_source_currents.get('V1', 0.0)
                    i_v1_ma = abs(i_v1) * 1000.0
                    
                    print(f"[Verification] DC Voltage at node 'out' = {v_out:.3f} V")
                    if self.target_max_current_ma is not None:
                        print(f"[Verification] Current through V1 = {i_v1_ma:.3f} mA")
                    
                    # Dual-Feedback checking
                    v_pass = abs(v_out - self.target_dc_voltage) <= 0.1
                    i_pass = True
                    if self.target_max_current_ma is not None:
                        i_pass = i_v1_ma <= self.target_max_current_ma
                        
                    if v_pass and i_pass:
                        print("--> SUCCESS: AI designed the circuit perfectly in SolverSCH!")
                        
                        # Próba przemysłowej weryfikacji (Sign-off)
                        passed, msg = LTspiceVerifier.verify_dc(circuit, self.target_dc_voltage)
                        
                        if passed:
                            print(f"[VERIFIED] {msg}")
                        else:
                            print(f"[CRITICAL WARNING] {msg}")

                        if self.monte_carlo_runs > 0:
                            self._run_monte_carlo(netlist_str, 'DC')
                        break
                    else:
                        if self.target_max_current_ma is not None:
                            v_stat = "PASS" if v_pass else f"FAIL: Target {self.target_dc_voltage}V"
                            i_stat = "PASS" if i_pass else f"FAIL: Exceeds {self.target_max_current_ma}mA limit"
                            feedback = f"Simulation failed. V(out) = {v_out:.3f}V ({v_stat}). Current through V1 = {i_v1_ma:.3f}mA ({i_stat}). "
                            if not i_pass:
                                feedback += "You must INCREASE the overall impedance of the circuit while maintaining the resistor ratios to lower the current. "
                            feedback += "Provide updated netlist."
                        else:
                            feedback = (
                                f"Simulation failed. DC voltage at node 'out' was {v_out:.2f} V. "
                                f"Target is {self.target_dc_voltage} V. Please adjust resistor values and provide the updated netlist."
                            )
                        
                        print(f"--> FAILED: Providing feedback to LLM: {feedback}")
                        self.conversation_history.append({"role": "user", "content": feedback})
                    
            except Exception as e:
                # Execution crashed structurally
                error_feedback = f"Your netlist resulted in a simulator crash: {str(e)}. Fix the syntax."
                print(f"--> CRASH: {error_feedback}")
                self.conversation_history.append({"role": "user", "content": error_feedback})
                
        else:
            print(f"\n=== Session FAILED: Max iterations ({max_iterations}) reached. ===")

    def _run_monte_carlo(self, base_netlist: str, mode: str):
        """Runs N Monte Carlo simulations perturbing R and C with 5% Gaussian tolerance."""
        print(f"\n=== MONTE CARLO ANALYSIS ({self.monte_carlo_runs} Runs) ===")
        print("Perturbing Component Tolerances (R, C) using Standard Gaussian Distribution (5%)...")
        results = []
        pass_count = 0
        
        for i in range(self.monte_carlo_runs):
            perturbed_netlist = self._perturb_netlist(base_netlist)
            try:
                circuit = NetlistParser.parse_netlist(perturbed_netlist, circuit_name=f"MC_Iter_{i}")
                stamper = MNAStamper(circuit)
                stamper.stamp_linear()
                solver = SparseSolver(
                    A_matrix=stamper.A_lil, z_vector=stamper.z_vec,
                    node_to_idx=stamper.node_to_idx, vsrc_to_idx=stamper.vsrc_to_idx,
                    n_independent_nodes=stamper.n
                )
                
                if mode == 'DC':
                    mna_result = solver.solve()
                    v_out = mna_result.node_voltages.get('out', 0.0)
                    results.append(v_out)
                    if abs(v_out - self.target_dc_voltage) <= 0.1:
                        if self.target_max_current_ma is not None:
                            i_v1_ma = abs(mna_result.voltage_source_currents.get('V1', 0.0)) * 1000.0
                            if i_v1_ma <= self.target_max_current_ma:
                                pass_count += 1
                        else:
                            pass_count += 1
                            
                elif mode == 'AC':
                    f_start, f_stop = self.target_ac_freq / 2.0, self.target_ac_freq * 2.0
                    freqs, mags_db, _ = solver.simulate_ac(f_start, f_stop, 10, stamper)
                    idx_target = (np.abs(freqs - self.target_ac_freq)).argmin()
                    mag_at_target = mags_db.get("out", np.zeros(len(freqs)))[idx_target]
                    results.append(mag_at_target)
                    if abs(mag_at_target - self.target_ac_mag) <= 0.5:
                        pass_count += 1
                        
            except Exception:
                pass # Failed matrix convergence counts as a fail.
                
        if not results:
            print("Monte Carlo Analysis FAILED entirely structurally.")
            return
            
        mean_val = np.mean(results)
        std_dev = np.std(results)
        yield_pct = (pass_count / self.monte_carlo_runs) * 100.0
        
        target_unit = "V" if mode == 'DC' else "dB"
        print(f"Mean Output: {mean_val:.2f}{target_unit} | Std Dev: {std_dev:.2f}{target_unit}")
        print(f"Manufacturing Yield: {yield_pct:.1f}% (Surviving within target bounds)")

    def _perturb_netlist(self, netlist: str) -> str:
        """Perturbs explicitly R and C components in SPICE raw structure directly."""
        lines = netlist.strip().split('\n')
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('*'):
                new_lines.append(line)
                continue
            
            parts = line.split()
            designator = parts[0].upper()
            
            # Look specifically for R and C components. Value is at the end.
            if len(parts) >= 4 and (designator.startswith('R') or designator.startswith('C')):
                val_str = parts[3]
                try:
                    nominal_val = NetlistParser._parse_value(val_str)
                    # 5% tolerance equals 3 sigma range.
                    sigma = (nominal_val * 0.05) / 3.0
                    perturbed_val = random.gauss(nominal_val, sigma)
                    
                    # Ensure physics boundaries (R, C > 0)
                    perturbed_val = max(1e-12, perturbed_val)
                    parts[3] = str(perturbed_val)
                    new_lines.append(" ".join(parts))
                except ValueError:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        return "\n".join(new_lines)

if __name__ == '__main__':
    # Interactive CLI Loop
    żelazne_zasady = (
            " KRYTYCZNE ZASADY ŚRODOWISKA WERYFIKACYJNEGO (SUROWY DIALEKT MNA):\n"
            "1. Puste Płótno: Masz absolutną swobodę topologiczną. Kaskaduj komponenty i dodawaj węzły, jeśli trzeba.\n"
            "2. Sztywne Punkty Pomiarowe: Sygnał wejściowy ZAWSZE wchodzi na węzeł 'in'. Sygnał wyjściowy ZAWSZE mierzymy na węźle 'out'. Masa to '0'.\n"
            "3. BEZWZGLĘDNE ZASILANIE WEJŚCIA: ZAWSZE dodawaj wejściowe źródło testowe! Aby przetestować okno 9-36V, MUSISZ napisać 'V1 in 0 15' (gdzie 15 to przykładowe napięcie wewnątrz okna). Zasilanie logiki to np. 'V2 vcc 0 5'. Używaj CZYSTYCH liczb, bez słów 'DC' czy 'V'!\n"
            "4. Modele i Hierarchia: ZABRONIONE jest używanie dyrektyw .SUBCKT oraz .model.\n"
            "5. Składnia BJT: Bipolarne definiuj ściśle jako 'Q<nazwa> <kolektor> <baza> <emiter>'.\n"
            "6. Komparator z Limitami: Używaj 'U<nazwa> <wy> <we+> <we-> <high> <low>'. Przykład: 'U1 out in ref 5.0 0.0'.\n"
            "Myśl architektonicznie!"
        )
    
    print("=== Osobisty Projektant AI (The SolverSCH Environment) ===")
    print("Zasilany przez Gemini 2.5 Flash. Wpisz 'exit', 'quit' lub 'q' aby wyjść.\n")
    
    while True:
        try:
            goal_input = input("\n[CEL PROJEKTU] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nWyjście awaryjne. Zamykanie...")
            break
            
        if not goal_input:
            continue
            
        if goal_input.lower() in ('exit', 'quit', 'q'):
            print("Zamykanie środowiska projektowego. Do widzenia!")
            break
            
        # Inject the mandatory hardware topologies into user prompt
        full_prompt = goal_input + żelazne_zasady
        
        # Initialize the automated Agent Loop
        designer_agent = AutonomousDesigner(target_goal=full_prompt)
        
        # Run pipeline
        designer_agent.run_optimization_loop(max_iterations=5)
        
        print("-" * 50)

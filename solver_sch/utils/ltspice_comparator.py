import json
from dataclasses import dataclass, asdict
import math
from typing import List, Dict, Tuple

@dataclass
class NodeComparison:
    node: str
    solver_value: float
    ltspice_value: float
    error_abs: float
    error_pct: float
    status: str  # "PASS" | "WARN" | "FAIL"
    info: str = "" # np. "Magnitude", "Phase", "Peak"

@dataclass
class ComparisonResult:
    analysis: str  # "dc" | "ac" | "transient"
    nodes: List[NodeComparison]
    max_error_pct: float
    passed: bool
    tolerance_pct: float
    
    def to_dict(self) -> dict:
        return asdict(self)
        
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
        
    def summary(self) -> str:
        passed_count = sum(1 for n in self.nodes if n.status == "PASS")
        total = len(self.nodes)
        status = "PASSED" if self.passed else "FAILED"
        return f"[{status}] {self.analysis.upper()} Match: {passed_count}/{total} passed (Max error: {self.max_error_pct:.2f}%)"

class LTspiceComparator:
    """Wykonuje porównanie wyników z SolverSCH i LTspice."""

    @staticmethod
    def _evaluate(solver_val: float, ltspice_val: float, tolerance_pct: float, abs_floor: float = 1e-6) -> Tuple[float, float, str]:
        diff_abs = abs(solver_val - ltspice_val)
        
        # Unikamy dzielenia przez 0
        target = abs(ltspice_val)
        if target < abs_floor:
            # Zakładamy że jeśli obie są blisko 0 to jest OK
            if abs(solver_val) < abs_floor:
                return diff_abs, 0.0, "PASS"
            # Jeśli LTspice wskazuje blisko zera, a Solver inną wartość
            # Błąd procoentowy liczony względem floor lub solvera
            target = max(abs(solver_val), abs_floor)
            
        diff_pct = (diff_abs / target) * 100.0
        
        status = "PASS"
        if diff_pct > tolerance_pct:
            status = "FAIL"
        elif diff_pct > tolerance_pct / 2:
            status = "WARN"
            
        return diff_abs, diff_pct, status

    @classmethod
    def compare_dc(cls, solver_dc, ltspice_dc: Dict[str, float], tolerance_pct: float = 0.1) -> ComparisonResult:
        nodes_comp = []
        max_err = 0.0
        
        solver_v = solver_dc.node_voltages
        for node, v_solver in solver_v.items():
            if node == '0':
                continue
            
            # W LTspice węzły są czasami case-insensitive, ale szukamy dokładnych
            # Z solvera węzły mogą być stringami
            v_ltspice = ltspice_dc.get(str(node))
            if v_ltspice is None:
                # Spróbuj lowercase / upercase
                for ltnode, val in ltspice_dc.items():
                    if ltnode.lower() == str(node).lower():
                        v_ltspice = val
                        break
                        
            if v_ltspice is not None:
                err_abs, err_pct, status = cls._evaluate(v_solver, v_ltspice, tolerance_pct)
                max_err = max(max_err, err_pct)
                nodes_comp.append(NodeComparison(str(node), v_solver, v_ltspice, err_abs, err_pct, status, "Voltage"))
            else:
                 nodes_comp.append(NodeComparison(str(node), v_solver, float('nan'), float('nan'), float('nan'), "FAIL", "Missing in LTspice"))
                 
        passed = all(n.status in ("PASS", "WARN") for n in nodes_comp)
        return ComparisonResult("dc", nodes_comp, max_err, passed, tolerance_pct)

    @classmethod
    def compare_ac(cls, solver_ac, ltspice_freqs: List[float], ltspice_ac: Dict[str, List[complex]], tolerance_pct: float = 1.0) -> ComparisonResult:
         nodes_comp = []
         max_err = 0.0
         
         # Dla AC porównamy konkretne częstotliwości z wyników solvera
         # (które powinny być identyczne z AC LTspice jeśli ac_points, start, stop się zgadzają)
         # Zabezpieczamy się na wypadek rozjechania frequency points - weźmiemy 3 kluczowe punkty (poczatek, środek, koniec)
         
         if not solver_ac.frequencies or not ltspice_freqs:
             return ComparisonResult("ac", [], 100.0, False, tolerance_pct)
             
         indices_to_check = [0, len(solver_ac.frequencies) // 2, len(solver_ac.frequencies) - 1]
         
         for node, solver_data in solver_ac.nodes.items():
            
            lt_trace = ltspice_ac.get(str(node))
            if lt_trace is None:
                for ltnode, val in ltspice_ac.items():
                    if ltnode.lower() == str(node).lower():
                        lt_trace = val
                        break
            
            if lt_trace is None:
                nodes_comp.append(NodeComparison(str(node), float('nan'), float('nan'), float('nan'), float('nan'), "FAIL", "Missing in LTspice"))
                continue
                
            for idx in indices_to_check:
                f_target = solver_ac.frequencies[idx]
                sol_mag = solver_data.magnitude[idx]
                
                # Znajdź najbliższą f w LTspice
                min_diff = float('inf')
                best_lt_idx = 0
                for i, freq in enumerate(ltspice_freqs):
                    if abs(freq - f_target) < min_diff:
                        min_diff = abs(freq - f_target)
                        best_lt_idx = i
                
                lt_val = lt_trace[best_lt_idx]
                lt_mag = abs(lt_val)
                
                err_abs, err_pct, status = cls._evaluate(sol_mag, lt_mag, tolerance_pct)
                max_err = max(max_err, err_pct)
                
                nodes_comp.append(NodeComparison(f"{node} @ {f_target:.1f}Hz", sol_mag, lt_mag, err_abs, err_pct, status, "Magnitude [V]"))

         passed = all(n.status in ("PASS", "WARN") for n in nodes_comp)
         return ComparisonResult("ac", nodes_comp, max_err, passed, tolerance_pct)

    @classmethod
    def compare_transient(
        cls, 
        solver_tran, 
        ltspice_times: List[float], 
        ltspice_tran: Dict[str, List[float]], 
        tolerance_pct: float = 2.0
    ) -> ComparisonResult:
        nodes_comp = []
        max_err = 0.0
        
        if not solver_tran or not ltspice_times:
             return ComparisonResult("transient", [], 100.0, False, tolerance_pct)
             
        # solver_tran is a list of TransientTimepoint objects
        # We will check start, middle, and end points
        indices_to_check = [1, len(solver_tran) // 2, len(solver_tran) - 1]
        
        # Get nodes from the first result
        first_tp = solver_tran[0]
        nodes = first_tp.node_voltages.keys()
        
        for node in nodes:
            if node == '0':
                continue
                
            lt_trace = ltspice_tran.get(str(node))
            if lt_trace is None:
                for ltnode, val in ltspice_tran.items():
                    if ltnode.lower() == str(node).lower():
                        lt_trace = val
                        break
                        
            if lt_trace is None:
                nodes_comp.append(NodeComparison(str(node), float('nan'), float('nan'), float('nan'), float('nan'), "FAIL", "Missing in LTspice"))
                continue
                
            for idx in indices_to_check:
                tp = solver_tran[idx]
                t_target = tp.time
                sol_val = tp.node_voltages.get(node, 0.0)
                
                # Linear interpolation for LTspice value at t_target
                t1, t2, v1, v2 = 0.0, 0.0, 0.0, 0.0
                lt_val = 0.0
                for i, t_lt in enumerate(ltspice_times):
                    if t_lt >= t_target:
                        t2 = t_lt
                        v2 = lt_trace[i]
                        if i > 0:
                            t1 = ltspice_times[i-1]
                            v1 = lt_trace[i-1]
                        else:
                            t1 = t_lt
                            v1 = v2
                        break
                else:
                    # If target is past the end of LTspice times
                    t1 = ltspice_times[-1]
                    t2 = t1
                    v1 = lt_trace[-1]
                    v2 = v1
                    
                if t1 == t2:
                    lt_val = v2
                else:
                    lt_val = v1 + (v2 - v1) * (t_target - t1) / (t2 - t1)
                
                err_abs, err_pct, status = cls._evaluate(sol_val, lt_val, tolerance_pct, abs_floor=1e-3)
                max_err = max(max_err, err_pct)
                
                nodes_comp.append(NodeComparison(f"{node} @ {t_target*1000:.2f}ms", sol_val, lt_val, err_abs, err_pct, status, "Voltage [V]"))

        passed = all(n.status in ("PASS", "WARN") for n in nodes_comp)
        return ComparisonResult("transient", nodes_comp, max_err, passed, tolerance_pct)

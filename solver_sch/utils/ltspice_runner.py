import os
import subprocess
import logging
from typing import Dict, List, Tuple
from PyLTSpice import RawRead
from solver_sch.model.circuit import Circuit
from solver_sch.utils.exporter import LTspiceExporter

log = logging.getLogger(__name__)

class LTspiceRunner:
    """Uruchamia eksportowany obwód w LTspice i czyta wyniki bazowe .raw."""
    
    # Automated path discovery for ADI LTspice (Standard for Windows Users)
    LTSPICE_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\ADI\LTspice\LTspice.exe")

    @classmethod
    def _run_ltspice(cls, cir_path: str) -> str:
        if not os.path.exists(cls.LTSPICE_PATH):
            raise FileNotFoundError(f"LTspice executable not found at {cls.LTSPICE_PATH}")

        raw_path = cir_path.replace('.cir', '.raw')
        # Remove old raw file if exists
        if os.path.exists(raw_path):
            os.remove(raw_path)

        log.info(f"[LTspiceRunner] Uruchamianie LTspice dla: {cir_path}")
        # -b: Batch mode, -Run: Start simulation immediately
        subprocess.run([cls.LTSPICE_PATH, "-b", "-Run", os.path.abspath(cir_path)], check=True)
            
        if not os.path.exists(raw_path):
            raise FileNotFoundError(f"LTspice failed to generate .raw output at {raw_path}")
            
        return raw_path

    @classmethod
    def run_dc(cls, circuit: Circuit, workdir: str = ".") -> Dict[str, float]:
        """Uruchamia analizę DC i zwraca wyniki dla węzłów."""
        cir_path = os.path.join(workdir, f"signoff_{circuit.name.replace(' ', '_')}_dc.cir")
        LTspiceExporter.export(circuit, cir_path, analysis="op")
        
        raw_path = cls._run_ltspice(cir_path)
        raw = RawRead(raw_path)
        
        voltages = {}
        currents = {}
        for trace_name in raw.get_trace_names():
            trace = raw.get_trace(trace_name)
            if not trace:
                continue
                
            val = float(trace.get_wave()[0])
            
            if trace_name.startswith("V(") and trace_name.endswith(")"):
                node = trace_name[2:-1]
                voltages[node] = val
            elif trace_name.startswith("I(") and trace_name.endswith(")"):
                # E.g. I(V1) or I(R1)
                comp = trace_name[2:-1]
                currents[comp] = val
                    
        return voltages, currents

    @classmethod
    def run_ac(cls, circuit: Circuit, f_start: float = 10, f_stop: float = 100e3, points: int = 20, workdir: str = ".") -> Tuple[List[float], Dict[str, List[complex]]]:
        """Uruchamia analizę AC i zwraca częstotliwości oraz zespolone napięcia węzłów."""
        cir_path = os.path.join(workdir, f"signoff_{circuit.name.replace(' ', '_')}_ac.cir")
        LTspiceExporter.export(circuit, cir_path, analysis="ac", ac_start=f_start, ac_stop=f_stop, ac_points=points)
        
        raw_path = cls._run_ltspice(cir_path)
        raw = RawRead(raw_path)
        
        freq_trace = raw.get_trace("frequency")
        if freq_trace is None:
            raise ValueError("Brak osi częstotliwości (frequency) w wynikach AC z LTspice.")
        
        freqs = list(freq_trace.get_wave())
        
        results = {}
        for trace_name in raw.get_trace_names():
            if trace_name.startswith("V(") and trace_name.endswith(")"):
                node = trace_name[2:-1]
                trace = raw.get_trace(trace_name)
                if trace is not None:
                    results[node] = list(trace.get_wave())
                    
        return freqs, results

    @classmethod
    def run_transient(cls, circuit: Circuit, t_stop: float, t_step: float, workdir: str = ".") -> Tuple[List[float], Dict[str, List[float]]]:
        """Uruchamia analizę czasową i zwraca czas oraz napięcia węzłów."""
        cir_path = os.path.join(workdir, f"signoff_{circuit.name.replace(' ', '_')}_tran.cir")
        LTspiceExporter.export(circuit, cir_path, analysis="tran", tran_stop=t_stop, tran_step=t_step)
        
        raw_path = cls._run_ltspice(cir_path)
        raw = RawRead(raw_path)
        
        time_trace = raw.get_trace("time")
        if time_trace is None:
            raise ValueError("Brak osi czasu (time) w wynikach Transient z LTspice.")
            
        times = list(time_trace.get_wave())
        
        results = {}
        for trace_name in raw.get_trace_names():
            if trace_name.startswith("V(") and trace_name.endswith(")"):
                node = trace_name[2:-1]
                trace = raw.get_trace(trace_name)
                if trace is not None:
                    results[node] = list(trace.get_wave())
                    
        return times, results

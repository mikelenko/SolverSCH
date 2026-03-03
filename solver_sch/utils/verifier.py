import subprocess
import os
from PyLTSpice import RawRead
from solver_sch.utils.exporter import LTspiceExporter

class LTspiceVerifier:
    """Uruchamia LTspice w trybie batch i weryfikuje wyniki."""
    # Automated path discovery for ADI LTspice (Standard for Windows Users)
    LTSPICE_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\ADI\LTspice\LTspice.exe")

    @classmethod
    def verify(cls, circuit, analysis_cmd: str):
        """Eksportuje układ wg zadanego polecenia i uruchamia LTspice."""
        LTspiceExporter.export(circuit, "signoff.cir", analysis_cmd)
        
        if not os.path.exists(cls.LTSPICE_PATH):
            raise FileNotFoundError(f"LTspice executable not found at {cls.LTSPICE_PATH}")

        print(f"[LTspiceVerifier] Found LTspice at: {cls.LTSPICE_PATH}")
        # -b: Batch mode, -Run: Start simulation immediately
        subprocess.run([cls.LTSPICE_PATH, "-b", "-Run", os.path.abspath("signoff.cir")], check=True)
            
        if not os.path.exists("signoff.raw"):
            raise FileNotFoundError("LTspice failed to generate .raw output.")
            
        return "signoff.raw"
        
    @classmethod
    def parse_raw(cls, raw_file_path: str):
        """Odczytuje obiekt RawRead LTspice."""
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"RAW file not found at {raw_file_path}")
        return RawRead(raw_file_path)

    @classmethod
    def verify_dc(cls, circuit, target_v, tolerance=0.05):
        """Eksportuje układ, uruchamia LTspice i porównuje napięcie na węźle 'out'."""
        LTspiceExporter.export(circuit, "signoff.cir")
        
        if not os.path.exists(cls.LTSPICE_PATH):
            return False, f"Sign-off Error: LTspice executable not found at {cls.LTSPICE_PATH}"

        try:
            print(f"[LTspiceVerifier] Found LTspice at: {cls.LTSPICE_PATH}")
            # -b: Batch mode, -Run: Start simulation immediately
            subprocess.run([cls.LTSPICE_PATH, "-b", "-Run", os.path.abspath("signoff.cir")], check=True)
            
            if not os.path.exists("signoff.raw"):
                return False, "Sign-off Error: LTspice failed to generate .raw output."

            raw = RawRead("signoff.raw")
            # Próba odczytu V(out) - standardowy punkt pomiarowy projektanta
            trace = raw.get_trace("V(out)")
            if trace is None:
                return False, "Sign-off Error: Node 'out' not found in LTspice results."
                
            v_out = trace.get_wave()[-1]
            
            # Weryfikacja błędu bezwzględnego względem celu
            diff = abs(v_out - target_v)
            if diff <= (abs(target_v) * tolerance + 1e-6):
                return True, f"SIGN-OFF PASSED: LTspice={v_out:.3f}V (Error: {diff:.3f}V)"
            return False, f"SIGN-OFF WARNING: LTspice={v_out:.3f}V (Target: {target_v}V, Diff: {diff:.3f}V)"
            
        except subprocess.CalledProcessError as e:
            return False, f"Sign-off Error: LTspice process failed (Code {e.returncode})"
        except Exception as e:
            return False, f"Sign-off Error: {str(e)}"

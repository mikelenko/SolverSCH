"""
components.py -> Electronic Component Domain Models.

All passive and active component types for use in Circuit netlists.
NO arrays, NO matrices, NO numerical solvers, NO numpy, NO scipy dependencies.
"""

from abc import ABC, abstractmethod
import math
from typing import Any, Dict, Optional, Tuple

from solver_sch.constants import THERMAL_VOLTAGE


class ModelCard:
    """A collection of physical simulation parameters for a specific component type.

    Mimics SPICE .MODEL cards. E.g., .MODEL 1N4148 D(Is=2.52n Rs=0.568 N=1.752 ...)
    """
    def __init__(self, name: str, model_type: str, parameters: Dict[str, Any]):
        self.name = name
        self.model_type = model_type  # e.g., 'D', 'NPN', 'PNP', 'NMOS', 'PMOS'
        self.parameters = parameters

    def __repr__(self) -> str:
        params_str = ' '.join(f"{k}={v}" for k, v in self.parameters.items())
        return f".model {self.name} {self.model_type}({params_str})"


class Component(ABC):
    """Abstract Base Class for an electronic circuit element."""

    def __init__(self, name: str) -> None:
        self.name: str = name

    @abstractmethod
    def nodes(self) -> Tuple[str, ...]:
        """Return the terminals to which this component is connected."""
        pass

    @property
    def value(self) -> float:
        """Default value for generic reporting/descriptions."""
        return 0.0


class TwoTerminalPassive(Component):
    """Base class for components with exactly two terminals and a primary numerical value."""

    def __init__(self, name: str, node1: str, node2: str, value: float) -> None:
        super().__init__(name)
        self.node1: str = node1
        self.node2: str = node2
        self._value: float = value

    def nodes(self) -> Tuple[str, str]:
        return self.node1, self.node2

    @property
    def value(self) -> float:
        return self._value


class ThreeTerminalActive(Component):
    """Base class for active components with three primary terminals (e.g. BJT, MOSFET)."""

    def __init__(self, name: str, term1: str, term2: str, term3: str) -> None:
        super().__init__(name)
        self.term1: str = term1
        self.term2: str = term2
        self.term3: str = term3

    def nodes(self) -> Tuple[str, str, str]:
        return self.term1, self.term2, self.term3


class Resistor(TwoTerminalPassive):
    """A linear resistor element (Passive)."""

    @property
    def resistance(self) -> float:
        return self.value


class VoltageSource(TwoTerminalPassive):
    """An independent ideal voltage source (Active)."""

    @property
    def voltage(self) -> float:
        return self.value


class CurrentSource(TwoTerminalPassive):
    """An independent ideal current source (Active).

    Current flows from node1 to node2 inside the source.
    """

    @property
    def current(self) -> float:
        return self.value


class ACVoltageSource(TwoTerminalPassive):
    """An independent ideal AC voltage source.

    Supports Time-Domain Sine sweeps and Small-Signal AC Frequency Domain magnitude/phase setups.
    """

    def __init__(self, name: str, node1: str, node2: str, amplitude: float, frequency: float, dc_offset: float = 0.0, ac_mag: float = 1.0, ac_phase: float = 0.0) -> None:
        # Base value is set to dc_offset for reporting
        super().__init__(name, node1, node2, dc_offset)
        # Time-domain parameters
        self.amplitude = amplitude
        self.frequency = frequency
        self.dc_offset = dc_offset
        # Small-Signal frequency domain parameters
        self.ac_mag = ac_mag
        self.ac_phase = ac_phase

    def get_voltage(self, t: float) -> float:
        """Returns the instantaneous voltage at time t using standard sine wave formula plus DC offset."""
        return self.dc_offset + self.amplitude * math.sin(2.0 * math.pi * self.frequency * t)

    @property
    def voltage(self) -> float:
        """Returns the DC offset for DC Operating Point stamping or initial transient state."""
        return self.dc_offset


class Diode(TwoTerminalPassive):
    """A non-linear PN junction diode.

    Using standard Shockley Diode equation parameters.
    """

    def __init__(
        self,
        name: str,
        anode: str,
        cathode: str,
        Is: float = 1e-14,
        n: float = 1.0,
        Vt: float = THERMAL_VOLTAGE,
        Vz: Optional[float] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        # Pass 0.0 as value - diodes are non-linear
        super().__init__(name, anode, cathode, 0.0)
        self.Is = Is
        self.n = n
        self.Vt = Vt
        self.Vz = Vz
        self.model = model
        self.spice_params = kwargs

    @property
    def anode(self) -> str:
        return self.node1

    @property
    def cathode(self) -> str:
        return self.node2


class Capacitor(TwoTerminalPassive):
    """A linear ideal capacitor element."""

    @property
    def capacitance(self) -> float:
        return self.value


class Inductor(TwoTerminalPassive):
    """An ideal inductor component for magnetic energy storage."""

    def __init__(self, name: str, node1: str, node2: str, inductance: float) -> None:
        super().__init__(name, node1, node2, inductance)
        self.inductance = inductance
        # Internal state history
        self.i_prev: float = 0.0

    @property
    def voltage(self) -> float:
        return 0.0  # Non-applicable, operates on transient Geq/Ieq


class _BJTBase(ThreeTerminalActive):
    """Shared base for Ebers-Moll BJT models (NPN and PNP).

    Subclasses set `_polarity`: +1 for NPN, -1 for PNP.
    Terminals: Collector, Base, Emitter.
    """
    _polarity: int

    def __init__(
        self,
        name: str,
        collector: str,
        base: str,
        emitter: str,
        Is: float = 1e-14,
        Bf: float = 100.0,
        Br: float = 1.0,
        Vt: float = THERMAL_VOLTAGE,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        super().__init__(name, collector, base, emitter)

        # Physics Parameters Ebers-Moll Base
        self.Is = Is
        self.Bf = Bf
        self.Br = Br
        self.Vt = Vt
        self.model = model
        self.spice_params = kwargs

    @property
    def collector(self) -> str: return self.term1

    @property
    def base(self) -> str: return self.term2

    @property
    def emitter(self) -> str: return self.term3

    @property
    def bjt_type(self) -> str:
        return "NPN" if self._polarity == 1 else "PNP"

    @property
    def voltage(self) -> float:
        return 0.0


class BJT_N(_BJTBase):
    """Ebers-Moll NPN BJT. Current flows into collector."""
    _polarity = 1

    def __init__(self, name: str, collector: str, base: str, emitter: str,
                 Is: float = 1e-14, Bf: float = 100.0, Br: float = 1.0,
                 Vt: float = THERMAL_VOLTAGE, model: Optional[str] = None,
                 **kwargs: Any) -> None:
        super().__init__(name, collector, base, emitter, Is, Bf, Br, Vt, model, **kwargs)


class BJT_P(_BJTBase):
    """Ebers-Moll PNP BJT. Current flows out of collector."""
    _polarity = -1

    def __init__(self, name: str, collector: str, base: str, emitter: str,
                 Is: float = 1e-14, Bf: float = 100.0, Br: float = 1.0,
                 Vt: float = THERMAL_VOLTAGE, model: Optional[str] = None,
                 **kwargs: Any) -> None:
        super().__init__(name, collector, base, emitter, Is, Bf, Br, Vt, model, **kwargs)


# Backward-compatible alias
BJT = BJT_N


class _MOSFETBase(ThreeTerminalActive):
    """Shared base for Shichman-Hodges Level 1 MOSFET models (NMOS and PMOS).

    Subclasses set `_polarity`: +1 for NMOS, -1 for PMOS.
    """
    _polarity: int

    def __init__(self, name: str, drain: str, gate: str, source: str,
                 w: float = 1e-6, l: float = 1e-6,
                 v_th: float = 0.7, k_p: float = 250e-6, lambda_: float = 0.01,
                 model: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, drain, gate, source)
        self.w = w
        self.l = l
        self.v_th = v_th
        self.k_p = k_p
        self.lambda_ = lambda_
        self.model = model
        self.spice_params = kwargs
        self.beta = self.k_p * (self.w / self.l)

    @property
    def drain(self) -> str: return self.term1

    @property
    def gate(self) -> str: return self.term2

    @property
    def source(self) -> str: return self.term3

    @property
    def voltage(self) -> float:
        return 0.0


class MOSFET_N(_MOSFETBase):
    """Shichman-Hodges Level 1 NMOS Model. Current flows drain → source."""
    _polarity = 1

    def __init__(self, name: str, drain: str, gate: str, source: str,
                 w: float = 1e-6, l: float = 1e-6,
                 v_th: float = 0.7, k_p: float = 250e-6, lambda_: float = 0.01,
                 model: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, drain, gate, source, w, l, v_th, k_p, lambda_, model, **kwargs)


class MOSFET_P(_MOSFETBase):
    """Shichman-Hodges Level 1 PMOS Model. Current flows source → drain."""
    _polarity = -1

    def __init__(self, name: str, drain: str, gate: str, source: str,
                 w: float = 1e-6, l: float = 1e-6,
                 v_th: float = -0.7, k_p: float = 250e-6, lambda_: float = 0.01,
                 model: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(name, drain, gate, source, w, l, v_th, k_p, lambda_, model, **kwargs)


class OpAmp(ThreeTerminalActive):
    """An ideal Operational Amplifier acting as a linear VCVS (Voltage-Controlled Voltage Source).

    Terminals: Non-inverting (+), Inverting (-), Output.
    """

    def __init__(self, name: str, in_p: str, in_n: str, out: str, gain: float = 1e5) -> None:
        super().__init__(name, in_p, in_n, out)
        self.gain = gain

    @property
    def in_p(self) -> str: return self.term1

    @property
    def in_n(self) -> str: return self.term2

    @property
    def out(self) -> str: return self.term3

    @property
    def voltage(self) -> float:
        return 0.0


class Comparator(ThreeTerminalActive):
    """An ideal non-linear Comparator component.

    Terminals: Non-inverting (+), Inverting (-), Output.
    """

    def __init__(self, name: str, node_p: str, node_n: str, node_out: str, v_high: float = 5.0, v_low: float = 0.0, k: float = 1000.0) -> None:
        super().__init__(name, node_p, node_n, node_out)
        self.v_high = v_high
        self.v_low = v_low
        self.k = k

    @property
    def node_p(self) -> str: return self.term1

    @property
    def node_n(self) -> str: return self.term2

    @property
    def node_out(self) -> str: return self.term3

    @property
    def voltage(self) -> float:
        return 0.0


class LM5085Gate(Component):
    """Behavioral DC model of the LM5085 PGATE driver + internal VCC regulator.

    Models two functions of the LM5085 COT buck controller:
      1. PGATE output: V_pgate = V_vin - Vdrive * sigmoid(k * (VREF - V_fb))
         - When V_fb < VREF=1.25V: sigmoid→1, PGATE = V_vin - Vdrive  (PFET ON)
         - When V_fb > VREF:       sigmoid→0, PGATE ≈ V_vin             (PFET OFF)
      2. VCC internal supply: modeled externally as VoltageSource(vcc, gnd, VCC_VOLTAGE)

    The PGATE stamping uses a tanh-based smooth approximation suitable for Newton-Raphson.

    Nodes:
      vin   - input supply (VIN pin 8)
      fb    - feedback node (ADJ/FB pin 2), compared to VREF
      pgate - gate driver output (PGATE pin 6)
      gnd   - ground reference
    """
    VREF: float = 1.25      # Internal FB reference voltage [V]
    VCC_VOLTAGE: float = 7.0  # Internal bias supply voltage [V]

    def __init__(
        self,
        name: str,
        vin: str,
        fb: str,
        pgate: str,
        vcc: str,
        gnd: str = "0",
        vdrive: float = 5.0,
        k: float = 500.0,
    ) -> None:
        super().__init__(name)
        self.vin = vin
        self.fb = fb
        self.pgate = pgate
        self.vcc = vcc
        self.gnd = gnd
        self.vdrive = vdrive  # Gate drive swing [V]: PGATE = VIN - vdrive when ON
        self.k = k            # Sigmoid steepness

    def nodes(self) -> Tuple[str, ...]:
        return (self.vin, self.fb, self.pgate, self.vcc, self.gnd)


# Class Aliases for EDA Test Integrity
NMOS = MOSFET_N
PMOS = MOSFET_P
NPN = BJT_N
PNP = BJT_P

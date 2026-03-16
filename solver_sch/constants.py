"""
constants.py -> Centralized physical and solver constants for SolverSCH.
"""

# Thermal voltage at 300K (room temperature): kT/q
THERMAL_VOLTAGE: float = 0.02585  # Volts

# SPICE-standard minimum conductance to ground for matrix stability
GMIN: float = 1e-12  # Siemens

# Newton-Raphson solver iteration limits and convergence tolerance
NR_MAX_ITER_DC: int = 100
NR_MAX_ITER_TRANSIENT: int = 50
NR_TOLERANCE: float = 1e-6

# Voltage limiting for exponential models (prevents Shockley equation overflow)
DIODE_VD_LIMIT: float = 0.8   # Volts — diode Vd clamp
BJT_VBE_LIMIT: float = 0.8    # Volts — BJT Vbe/Vbc clamp
MOSFET_VOV_CLAMP: float = 20.0  # Volts — MOSFET overdrive clamp
SIGMOID_CLAMP_RANGE: float = 50.0  # dimensionless — tanh argument clamp

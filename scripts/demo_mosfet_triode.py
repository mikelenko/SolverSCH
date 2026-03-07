import os
from solver_sch.model.circuit import Circuit, Resistor, VoltageSource, MOSFET_N, ModelCard
from solver_sch.simulator import Simulator

def main():
    print("--- MOSFET Triode Region Demonstration ---")
    
    # 1. Obwód i Model
    circuit = Circuit("MOSFET Triode Demo")
    
    # Model NMOS zgodny ze standardem SPICE Level 1
    # VTO: Napięcie progowe (Threshold Voltage)
    # KP: Transkonduktancja na jednostkę W/L (Transconductance parameter)
    nmos_model = ModelCard("BS170", "NMOS", {"VTO": "2.0", "KP": "0.1", "LAMBDA": "0.01"})
    circuit.add_model(nmos_model)
    
    # 2. Parametry pracy (cel: Zakres triodowy)
    # Warunek triodowy: Vgs > Vth ORAZ Vds < Vgs - Vth
    # Vth = 2.0V
    # Dla Vgs = 5V: Vgs - Vth = 3V
    # Musimy wymusić Vds < 3V. Zastosujemy opornik drenu, na którym odłoży się większość napięcia zasilania.
    
    V_DD = 10.0   # Zasilanie
    V_GG = 5.0    # Napięcie bramki (Vgs)
    R_D = 1000.0   # Opornik w drenie (1kΩ)
    
    circuit.add_component(VoltageSource("VDD", "vd", "0", V_DD))
    circuit.add_component(VoltageSource("VGG", "vg", "0", V_GG))
    
    # Opornik ograniczający między VDD a drenem tranzystora
    circuit.add_component(Resistor("RD", "vd", "drain", R_D))
    
    # MOSFET ze zdefiniowanym z zewnątrz modelem BS170
    circuit.add_component(MOSFET_N("M1", "drain", "vg", "0", model="BS170"))
    
    # 3. Symulacja przez Backend LTspice
    sim = Simulator(circuit, backend="ltspice")
    result = sim.dc()
    
    # 4. Analiza wyników
    v_ds = result.node_voltages.get("drain", 0.0)
    v_th = 2.0  # z modelu
    
    print(f"\nWyniki:")
    print(f"Vgs = {V_GG} V")
    print(f"Napięcie na drenie (Vds) = {v_ds:.3f} V")
    
    overdrive = V_GG - v_th
    print(f"Overdrive Voltage (Vgs - Vth) = {overdrive} V")
    
    if v_ds < overdrive:
        print("\n=> SUKCES! Tranzystor pracuje w zakresie triodowym (liniowym).")
        print("   (Vds < Vgs - Vth)")
    else:
        print("\n=> UWAGA: Tranzystor pracuje w zakresie nasycenia (saturation).")
        print("   (Vds >= Vgs - Vth)")
        
    print("\nSzczegóły węzłów:")
    for node, voltage in result.node_voltages.items():
        print(f" - {node}: {voltage:.3f} V")

if __name__ == "__main__":
    main()

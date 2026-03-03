from solver_sch.model.circuit import (
    Resistor, Capacitor, Inductor, VoltageSource, ACVoltageSource,
    Diode, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator
)

class LTspiceExporter:
    """Konwertuje obiekt Circuit na format .cir dla LTspice."""
    @staticmethod
    def export(circuit, filename, analysis_cmd=".tran 10n"):
        lines = [f"* LTspice Export: {circuit.name}"]
        for comp in circuit.get_components():
            if isinstance(comp, Resistor):
                lines.append(f"R{comp.name} {comp.node1} {comp.node2} {comp.value}")
            elif isinstance(comp, Capacitor):
                lines.append(f"C{comp.name} {comp.node1} {comp.node2} {comp.value}")
            elif isinstance(comp, Inductor):
                lines.append(f"L{comp.name} {comp.node1} {comp.node2} {comp.value}")
            elif isinstance(comp, VoltageSource):
                lines.append(f"V{comp.name} {comp.node1} {comp.node2} {comp.value}")
            elif isinstance(comp, ACVoltageSource):
                lines.append(f"V{comp.name} {comp.node1} {comp.node2} SINE({comp.dc_offset} {comp.amplitude} {comp.frequency}) AC {comp.ac_mag} {comp.ac_phase}")
            elif isinstance(comp, OpAmp):
                # Mapujemy jako Voltage Controlled Voltage Source (VCVS) ze wspolczynnikiem gain
                lines.append(f"E{comp.name} {comp.out} 0 {comp.in_p} {comp.in_n} {comp.gain}")
            elif isinstance(comp, BJT):
                lines.append(f"Q{comp.name} {comp.collector} {comp.base} {comp.emitter} NPN_MODEL")
            elif isinstance(comp, Comparator):
                # Mapowanie U na behawioralne źródło napięcia w LTspice
                # Zgodnie z modelem w circuit.py: node_p, node_n, node_out
                lines.append(f"B{comp.name} {comp.node_out} 0 V=if(V({comp.node_p})>V({comp.node_n}), {comp.v_high}, {comp.v_low})")
        
        # Modele uproszczone dla sign-off
        lines.append(".model NPN_MODEL NPN(Bf=100)")
        lines.append(analysis_cmd)
        lines.append(".save all")
        lines.append(".end")
        with open(filename, 'w') as f:
            f.write("\n".join(lines))

import os
import math
from typing import Dict, Tuple, Set
import logging
from solver_sch.model.circuit import (
    Resistor, Capacitor, Inductor, VoltageSource, ACVoltageSource,
    Diode, BJT, MOSFET_N, MOSFET_P, OpAmp, Comparator, Circuit
)

logger = logging.getLogger("solver_sch.utils.altium_exporter")

class AltiumScriptExporter:
    """Generates an Altium Designer DelphiScript (.pas) to recreate the schematic."""

    @staticmethod
    def export(circuit: Circuit, filename: str):
        """Generates the DelphiScript file with automated placement and wiring."""
        lines = [
            "Procedure CreateSolverSCH;",
            "Var",
            "    SchSheet  : ISch_Document;",
            "    Component : ISch_Component;",
            "    Wire      : ISch_Wire;",
            "    Point1, Point2 : TPoint;",
            "Begin",
            "    SchSheet := SchServer.GetActiveSchematicDocument;",
            "    If SchSheet = Nil Then Begin",
            "        ShowMessage('SolverSCH: Open a Schematic Document first!');",
            "        Exit;",
            "    End;",
            "",
            "    // Start Undo/Redo registration",
            "    SchServer.ProcessControl.PreProcess(SchSheet, eStore_All);",
            ""
        ]

        # 1. Component Placement & Pin Tracking
        # node_pins: Dict[node_name, List[Tuple[x, y]]]
        node_pins: Dict[str, list] = {}
        
        GRID = 1200 # Mils for clear separation
        current_x = 1000
        current_y = 5000
        
        components = circuit.get_components()
        for comp in components:
            lib_ref, part_lib = AltiumScriptExporter._map_to_altium(comp)
            
            lines.append(f"    // Placing {comp.name}")
            lines.append(f"    Component := SchServer.SchObjectFactory(eSchComponent, eDisplay_Normal);")
            lines.append(f"    Component.LibReference := '{lib_ref}';")
            lines.append(f"    Component.SourceLibName := '{part_lib}';")
            lines.append(f"    Component.Designator.Text := '{comp.name}';")
            lines.append(f"    Component.Location := Point(MilsToCoord({current_x}), MilsToCoord({current_y}));")
            lines.append(f"    SchSheet.AddSchObject(Component);")
            lines.append(f"    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);")
            
            # Record Pin Locations for Wiring (Standard pin offsets in Misc Devices)
            # This is a heuristic mapping for standard Altium symbols
            offsets = AltiumScriptExporter._get_pin_offsets(comp)
            for node_name, (dx, dy) in offsets.items():
                px, py = current_x + dx, current_y + dy
                if node_name not in node_pins: node_pins[node_name] = []
                node_pins[node_name].append((px, py))
            
            current_x += GRID
            if current_x > 6000:
                current_x = 1000
                current_y -= GRID
            lines.append("")

        # 2. Automated Wiring
        lines.append("    // Automated Wiring between Nets")
        for net_name, pins in node_pins.items():
            if len(pins) < 2: continue
            lines.append(f"    // Net: {net_name}")
            # Connect all pins to the first pin in the net (star topology for simplicity)
            x1, y1 = pins[0]
            for i in range(1, len(pins)):
                x2, y2 = pins[i]
                lines.append(f"    Wire := SchServer.SchObjectFactory(eWire, eDisplay_Normal);")
                lines.append(f"    Wire.Location1 := Point(MilsToCoord({x1}), MilsToCoord({y1}));")
                lines.append(f"    Wire.Location2 := Point(MilsToCoord({x2}), MilsToCoord({y2}));")
                lines.append(f"    SchSheet.AddSchObject(Wire);")
                lines.append(f"    SchServer.RobotManager.SendMessage(SchSheet.I_ObjectAddress, IDC_ANNOTATE_ALL, NIL);")
        
        lines.extend([
            "",
            "    // Finalize and Refresh",
            "    SchServer.ProcessControl.PostProcess(SchSheet, eStore_All);",
            "    SchSheet.GraphicallyInvalidate; ",
            "    ShowMessage('SolverSCH: Schematic Generated with ' + IntToStr(SchSheet.SchComponentCount) + ' components and auto-wiring!');",
            "End;"
        ])

        with open(filename, "w") as f:
            f.write("\n".join(lines))
        
        logger.info("[ALTIUM EXPORT] v2 DelphiScript saved to %s", filename)

    @staticmethod
    def _get_pin_offsets(comp) -> Dict[str, Tuple[int, int]]:
        """Standard pin offsets (normalized in Mils) for Miscellaneous Devices.IntLib symbols."""
        if isinstance(comp, (Resistor, Capacitor, Inductor)):
            return {comp.node1: (-100, 0), comp.node2: (100, 0)}
        if isinstance(comp, (VoltageSource, ACVoltageSource)):
            return {comp.node1: (0, 100), comp.node2: (0, -100)}
        if isinstance(comp, OpAmp):
            return {comp.in_p: (-200, 100), comp.in_n: (-200, -100), comp.out: (200, 0)}
        if isinstance(comp, Comparator):
            return {comp.node_p: (-200, 100), comp.node_n: (-200, -100), comp.node_out: (200, 0)}
        if isinstance(comp, BJT):
            return {comp.collector: (0, 200), comp.base: (-200, 0), comp.emitter: (0, -200)}
        return {}

    @staticmethod
    def _map_to_altium(comp) -> Tuple[str, str]:
        """Maps internal components to Altium 'Miscellaneous Devices.IntLib'."""
        lib = "Miscellaneous Devices.IntLib"
        if isinstance(comp, Resistor): return "Res1", lib
        if isinstance(comp, Capacitor): return "Cap", lib
        if isinstance(comp, Inductor): return "Inductor", lib
        if isinstance(comp, (VoltageSource, ACVoltageSource)): return "Source V", lib
        if isinstance(comp, Diode): return "Diode", lib
        if isinstance(comp, BJT): return "NPN", lib # Assuming NPN for now
        if isinstance(comp, (OpAmp, Comparator)): return "OpAmp", lib
        return "Component", lib

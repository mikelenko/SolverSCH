"""
Netlist Parser: A syntax Lexer translating SPICE-compatible strings into Circuit objects.
Strict isolation: Does not interact with solvers or compilers.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from solver_sch.model.circuit import (
    Circuit,
    Resistor,
    Capacitor,
    Inductor,
    VoltageSource,
    ACVoltageSource,
    CurrentSource,
    Diode,
    BJT,
    MOSFET_N,
    MOSFET_P,
    OpAmp,
    Comparator
)
import logging

logger = logging.getLogger("solver_sch.parser.netlist_parser")


@dataclass
class SubcircuitDef:
    name: str
    ports: List[str]
    lines: List[str] = field(default_factory=list)


class NetlistParser:
    """Parses SPICE text layouts into internal Circuit component maps."""
    
    # Standard SPICE Engineering Notation Map
    PREFIXES = {
        'f': 1e-15,  # femto
        'p': 1e-12,  # pico
        'n': 1e-9,   # nano
        'u': 1e-6,   # micro
        'm': 1e-3,   # milli
        'k': 1e3,    # kilo
        'meg': 1e6,  # mega
        'g': 1e9,    # giga
        't': 1e12    # tera
    }
    
    @classmethod
    def _parse_value(cls, val_str: str) -> float:
        """Converts strings like '4.7k', '10uF', '1Meg' into standard floats."""
        val_str = val_str.lower().strip()
        # Regex to strip off leading number components (+/-/e/E) from the trailing unit 
        match = re.match(r"^([+-]?(?:[0-9]*\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?)([a-zA-Z]*)$", val_str)
        
        if not match:
            raise ValueError(f"Cannot parse numerical value from string: '{val_str}'")
            
        number_part = float(match.group(1))
        unit_str = match.group(2)
        
        # Iteratively try to match unit to SPICE prefix (from longest to shortest for 'meg' vs 'm')
        for prefix in sorted(cls.PREFIXES.keys(), key=len, reverse=True):
            if unit_str.startswith(prefix):
                return number_part * cls.PREFIXES[prefix]
                
        return number_part

    @classmethod
    def _clean_line(cls, line: str) -> Optional[str]:
        """Strips whitespaces and handles SPICE inline/block comments."""
        line = line.strip()
        if not line or line.startswith('*'):
            return None # Ignore empty strings and full comment lines
            
        # Inline comment truncation (';' or '//')
        for char in [';', '//']:
            idx = line.find(char)
            if idx != -1:
                line = line[:idx].strip()
                
        if not line:
            return None
            
        return line

    @classmethod
    def _flatten_hierarchy(cls, inst_name: str, connected_nodes: List[str], 
                           subckt_def: SubcircuitDef, subckts_map: Dict[str, SubcircuitDef]) -> List[str]:
        """Recursively flattens an 'X' component instantiation macro into base SPICE blocks."""
        flat_lines = []
        
        if len(connected_nodes) != len(subckt_def.ports):
            raise ValueError(f"Port mismatch for instance {inst_name} of {subckt_def.name}: expected {len(subckt_def.ports)} ports, got {len(connected_nodes)}")
            
        port_map = dict(zip(subckt_def.ports, connected_nodes))
        
        # Designators and the number of node tokens they have
        node_counts = {
            'R': 2, 'C': 2, 'L': 2, 'V': 2, 'I': 2, 'D': 2,
            'Q': 3, 'M': 3, 'E': 4, 'U': 3
        }
        
        for line in subckt_def.lines:
            parts = line.split()
            if not parts:
                continue
                
            designator = parts[0][0].upper()
            
            # Recursive Subcircuit Invocation
            if designator == 'X':
                nested_inst_name = f"{inst_name}.{parts[0]}"
                nested_subckt_name = parts[-1].upper()
                nested_connected_nodes = parts[1:-1]
                
                remapped_nested_nodes = []
                for node in nested_connected_nodes:
                    if node == '0' or node.upper() == 'GND':
                        remapped_nested_nodes.append(node)
                    elif node in port_map:
                        remapped_nested_nodes.append(port_map[node])
                    else:
                        remapped_nested_nodes.append(f"{inst_name}.{node}")
                        
                if nested_subckt_name not in subckts_map:
                    raise ValueError(f"Unknown subcircuit {nested_subckt_name} referenced by {nested_inst_name}")
                    
                flat_lines.extend(cls._flatten_hierarchy(nested_inst_name, remapped_nested_nodes, subckts_map[nested_subckt_name], subckts_map))
                continue
                
            # Base Component Remapping
            comp_name = f"{inst_name}.{parts[0]}"
            new_parts = [comp_name]
            
            num_nodes = node_counts.get(designator, 0)
            
            for i, part in enumerate(parts[1:]):
                if i < num_nodes:
                    # Node Token
                    if part == '0' or part.upper() == 'GND':
                        new_parts.append('0')
                    elif part in port_map:
                        new_parts.append(port_map[part])
                    else:
                        new_parts.append(f"{inst_name}.{part}")
                else:
                    # Parameter/Value Token
                    new_parts.append(part)
                    
            flat_lines.append(" ".join(new_parts))
            
        return flat_lines

    @classmethod
    def parse_netlist(cls, text: str, circuit_name: str = "Imported Circuit", ground_name: str = "0") -> Circuit:
        """Translates multi-line Netlist strings into a populated Circuit abstraction layer."""
        circuit = Circuit(name=circuit_name, ground_name=ground_name)
        
        lines = text.split('\n')
        clean_lines = []
        for raw_line in lines:
            line = cls._clean_line(raw_line)
            if line:
                clean_lines.append(line)
                
        # Phase 1: Subcircuit Extraction
        subckts_map: Dict[str, SubcircuitDef] = {}
        main_lines = []
        
        current_subckt = None
        for line in clean_lines:
            parts = line.split()
            upper_cmd = parts[0].upper()
            
            if upper_cmd == '.SUBCKT':
                if len(parts) < 2: continue
                subckt_name = parts[1].upper()
                subckt_ports = parts[2:]
                current_subckt = SubcircuitDef(subckt_name, subckt_ports)
                subckts_map[subckt_name] = current_subckt
            elif upper_cmd == '.ENDS':
                current_subckt = None
            else:
                if current_subckt is not None:
                    current_subckt.lines.append(line)
                else:
                    main_lines.append(line)
                    
        # Phase 2: Hierarchical Flattening
        flat_lines = []
        for line in main_lines:
            parts = line.split()
            if parts[0].upper().startswith('X'):
                inst_name = parts[0]
                subckt_name = parts[-1].upper()
                connected_nodes = parts[1:-1]
                
                if subckt_name not in subckts_map:
                    logger.warning("Unknown subcircuit '%s' for instance %s", subckt_name, inst_name)
                    continue
                    
                flat_lines.extend(cls._flatten_hierarchy(inst_name, connected_nodes, subckts_map[subckt_name], subckts_map))
            else:
                flat_lines.append(line)
                
        # Phase 3: Physical Block Instantiation
        for line in flat_lines:
            parts = line.split()
            if not parts:
                continue
                
            name = parts[0]
            if name.startswith('.'):
                continue
            # Extract true physical designator even if hierarchically prefixed (e.g. 'X1.X2.R1' -> 'R')
            base_name = name.split('.')[-1]
            designator = base_name[0].upper()
            
            try:
                # 1. Passive Components
                if designator == 'R' and len(parts) >= 4:
                    circuit.add_component(Resistor(name, parts[1], parts[2], cls._parse_value(parts[3])))
                elif designator == 'C' and len(parts) >= 4:
                    circuit.add_component(Capacitor(name, parts[1], parts[2], cls._parse_value(parts[3])))
                elif designator == 'L' and len(parts) >= 4:
                    circuit.add_component(Inductor(name, parts[1], parts[2], cls._parse_value(parts[3])))
                
                # 2. Voltage Sources (DC and AC "SIN" syntax)
                elif designator == 'V' and len(parts) >= 4:
                    node1, node2 = parts[1], parts[2]
                    parts_upper = [p.upper() for p in parts]
                    
                    if 'AC' in parts_upper or 'SIN' in parts_upper or 'SINE' in parts_upper:
                        # Handle AC/SIN/SINE
                        amp_idx = 4
                        for token in ['AC', 'SIN', 'SINE']:
                            if token in parts_upper:
                                token_idx = parts_upper.index(token)
                                # Next token might be the value, or it might be (val ...)
                                if len(parts) > token_idx + 1:
                                    val_str = parts[token_idx+1]
                                    # Strip parentheses if SINE(0 0.1 1000)
                                    val_str = val_str.replace('(', ' ').replace(')', ' ').split()[0]
                                    try:
                                        amp = cls._parse_value(val_str)
                                        freq = cls._parse_value(parts[token_idx+2]) if len(parts) > token_idx+2 else 1000.0
                                    except:
                                        amp = 1.0 # Default
                                        freq = 1000.0
                                    circuit.add_component(ACVoltageSource(name, node1, node2, amp, freq))
                                    break
                    elif 'DC' in parts_upper:
                        dc_idx = parts_upper.index('DC')
                        val = cls._parse_value(parts[dc_idx+1]) if len(parts) > dc_idx+1 else 0.0
                        circuit.add_component(VoltageSource(name, node1, node2, val))
                    else:
                        circuit.add_component(VoltageSource(name, node1, node2, cls._parse_value(parts[3])))
                
                # 2b. Current Sources
                elif designator == 'I' and len(parts) >= 4:
                    circuit.add_component(CurrentSource(name, parts[1], parts[2], cls._parse_value(parts[3])))
                
                # 3. Semiconductor Logic 
                elif designator == 'D' and len(parts) >= 3:
                    m_name = parts[3] if len(parts) > 3 else None
                    circuit.add_component(Diode(name, parts[1], parts[2], model=m_name))
                
                elif designator == 'Q' and len(parts) >= 4:
                    circuit.add_component(BJT(name, parts[1], parts[2], parts[3]))
                
                elif designator == 'M' and len(parts) >= 5:
                    m_type = parts[4].upper()
                    w_val = 1e-6
                    l_val = 1e-6
                    
                    for p in parts[5:]:
                        if p.upper().startswith('W='):
                            w_val = cls._parse_value(p[2:])
                        elif p.upper().startswith('L='):
                            l_val = cls._parse_value(p[2:])
                            
                    if m_type == 'NMOS':
                        circuit.add_component(MOSFET_N(name, parts[1], parts[2], parts[3], w=w_val, l=l_val))
                    elif m_type == 'PMOS':
                        circuit.add_component(MOSFET_P(name, parts[1], parts[2], parts[3], w=w_val, l=l_val))
                    else:
                        logger.warning("Unknown MOSFET type '%s' for %s. Defaulting to NMOS.", m_type, name)
                        circuit.add_component(MOSFET_N(name, parts[1], parts[2], parts[3], w=w_val, l=l_val))
                    
                # 4. Op-Amp Macromodel (E designator in SPICE)
                # Matches n+ n- nc+ nc- gain
                elif designator == 'E' and len(parts) >= 5:
                    gain = cls._parse_value(parts[5]) if len(parts) > 5 else 1e5
                    circuit.add_component(OpAmp(name, in_p=parts[3], in_n=parts[4], out=parts[1], gain=gain))
                    
                # 5. Comparator Model
                elif designator == 'U' and len(parts) >= 4:
                    v_high = cls._parse_value(parts[4]) if len(parts) > 4 else 5.0
                    v_low = cls._parse_value(parts[5]) if len(parts) > 5 else 0.0
                    circuit.add_component(Comparator(name, parts[1], parts[2], parts[3], v_high, v_low))
            
            except Exception as e:
                logger.warning("Could not load line -> '%s' | Exception: %s", line, str(e))
                
        return circuit

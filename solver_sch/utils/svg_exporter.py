import json
import os
import platform
import re
import subprocess
import tempfile
from collections import deque
from typing import Any, Dict, List, Set, Deque

from solver_sch.model.circuit import (
    Resistor, Capacitor, Inductor, VoltageSource, ACVoltageSource, 
    Diode, BJT, MOSFET_N, MOSFET_P, OpAmp
)

SKIN_PATH = os.path.join(os.path.dirname(__file__), 'resources', 'solver_sch_skin.svg')

# Engineering notation suffixes
_ENG_SUFFIXES = [
    (1e12, 'T'), (1e9, 'G'), (1e6, 'M'), (1e3, 'k'),
    (1e0, ''),
    (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p'), (1e-15, 'f')
]

# Unit mapping per component type
_UNITS = {
    'r_h': 'Ω', 'r_v': 'Ω',
    'c_h': 'F', 'c_v': 'F',
    'l_h': 'H', 'l_v': 'H',
    'v': 'V', 'i': 'A',
}

def _eng_format(value: float, unit: str = '') -> str:
    """Format a float into engineering notation with unit suffix."""
    if value == 0: return f"0{unit}"
    abs_val = abs(value)
    for threshold, suffix in _ENG_SUFFIXES:
        if abs_val >= threshold:
            scaled = value / threshold
            if scaled == int(scaled): return f"{int(scaled)}{suffix}{unit}"
            else: return f"{scaled:.2g}{suffix}{unit}"
    return f"{value:.2g}{unit}"

class SVGExporter:
    """Exports Circuit topologies to SVG schematics via netlistsvg.
    
    Enforces a strict vertical potential gradient and centralized anchor hierarchy.
    Correctly partitions horizontal zones (Supply -> Base -> Anchor -> Collector).
    """
    
    POWER_NETS = {'gnd', 'GND', '0', 'vcc', 'VCC', 'vdd', 'VDD', 'vee', 'VEE', 'vss', 'VSS'}
    
    def __init__(self, circuit) -> None:
        self.circuit = circuit
        self.node_to_id: Dict[str, int] = {}
        self.next_node_id: int = 1
        self.cells: Dict[str, Any] = {}
        self._power_count: int = 0
        
    def _is_power(self, node_name: str) -> bool:
        return str(node_name).upper() in {n.upper() for n in self.POWER_NETS}

    def _get_node_id(self, node_name: str) -> int:
        n_clean = str(node_name)
        if n_clean not in self.node_to_id:
            self.node_to_id[n_clean] = self.next_node_id
            self.next_node_id += 1
        return self.node_to_id[n_clean]
    
    def _get_power_node_id(self, node_name: str, comp_name: str) -> int:
        if self._is_power(node_name):
            unique_key = f"_pwr_{node_name}_{comp_name}"
            if unique_key not in self.node_to_id:
                self.node_to_id[unique_key] = self.next_node_id
                self.next_node_id += 1
                self._power_count += 1
                sym_name = f"_{node_name}_{self._power_count}"
                is_gnd = str(node_name).upper() in {'GND', '0', 'VSS', 'VEE'}
                self.cells[sym_name] = {
                    'type': 'gnd' if is_gnd else 'vcc',
                    'port_directions': {'A': 'input' if is_gnd else 'output'},
                    'connections': {'A': [self.node_to_id[unique_key]]},
                    'attributes': {
                        'name': node_name,
                        'org.eclipse.elk.layered.layering.layerConstraint': 'LAST_SEPARATE' if is_gnd else 'FIRST_SEPARATE',
                        'org.eclipse.elk.layerConstraint': 'LAST_SEPARATE' if is_gnd else 'FIRST_SEPARATE'
                    }
                }
            return self.node_to_id[unique_key]
        return self._get_node_id(node_name)
        
    def _add_2port(self, comp_type: str, name: str, node_p: str, node_n: str, val: str, pin_p: str, pin_n: str) -> None:
        display_val = val
        try:
            num = float(val)
            unit = _UNITS.get(comp_type, '')
            display_val = _eng_format(num, unit)
        except (ValueError, TypeError): pass
            
        self.cells[name] = {
            'type': comp_type,
            'port_directions': {pin_p: 'output', pin_n: 'output'},
            'connections': {
                pin_p: [self._get_power_node_id(node_p, name)],
                pin_n: [self._get_power_node_id(node_n, name)]
            },
            'attributes': {'ref': name, 'value': display_val}
        }
        
    def _add_3port(self, comp_type: str, name: str, pin1: tuple, pin2: tuple, pin3: tuple, val: str) -> None:
        self.cells[name] = {
            'type': comp_type,
            'port_directions': {pin1[0]: pin1[2], pin2[0]: pin2[2], pin3[0]: pin3[2]},
            'connections': {
                pin1[0]: [self._get_power_node_id(pin1[1], name)],
                pin2[0]: [self._get_power_node_id(pin2[1], name)],
                pin3[0]: [self._get_power_node_id(pin3[1], name)]
            },
            'attributes': {'ref': name, 'value': str(val)}
        }

    def _autofit_viewbox(self, svg_path: str) -> None:
        if not os.path.exists(svg_path): return
        with open(svg_path, 'r', encoding='utf-8') as f: content = f.read()
        translates = re.findall(r'translate\(([\d.-]+)\s*,?\s*([\d.-]+)\)', content)
        if not translates: return
        max_x = max(float(t[0]) for t in translates) + 200
        max_y = max(float(t[1]) for t in translates) + 200
        content = re.sub(r'<svg([^>]*)width="[^"]*"', f'<svg\\1width="{int(max_x)}"', content)
        content = re.sub(r'height="[^"]*"', f'height="{int(max_y)}" viewBox="0 0 {int(max_x)} {int(max_y)}"', content, count=1)
        with open(svg_path, 'w', encoding='utf-8') as f: f.write(content)

    def _generate_cell_for_comp(self, comp: Any) -> None:
        if isinstance(comp, (Resistor, Capacitor, Inductor)):
            suffix = '_v' if (self._is_power(comp.node1) or self._is_power(comp.node2)) else '_h'
            if isinstance(comp, Resistor): self._add_2port('r' + suffix, comp.name, comp.node1, comp.node2, str(comp.resistance), 'A', 'B')
            elif isinstance(comp, Capacitor): self._add_2port('c' + suffix, comp.name, comp.node1, comp.node2, str(comp.capacitance), 'A', 'B')
            elif isinstance(comp, Inductor): self._add_2port('l' + suffix, comp.name, comp.node1, comp.node2, str(comp.inductance), 'A', 'B')
        elif isinstance(comp, (VoltageSource, ACVoltageSource)):
            val = getattr(comp, 'voltage', getattr(comp, 'ac_mag', 'V'))
            self._add_2port('v', comp.name, comp.node1, comp.node2, str(val), '+', '-')
        elif isinstance(comp, Diode):
            suffix = '_v' if (self._is_power(comp.node1) or self._is_power(comp.node2)) else '_h'
            self._add_2port('d' + suffix, comp.name, comp.node1, comp.node2, getattr(comp, 'model', 'D'), '+', '-')
        elif isinstance(comp, BJT):
            comp_type = 'q_npn' if 'NPN' in str(getattr(comp, 'type', 'NPN')).upper() else 'q_pnp'
            self._add_3port(comp_type, comp.name, ('C', comp.collector, 'output'), ('B', comp.base, 'input'), ('E', comp.emitter, 'output'), getattr(comp, 'model', 'Q'))
        elif isinstance(comp, (MOSFET_N, MOSFET_P)):
            comp_type = 'q_npn' if isinstance(comp, MOSFET_N) else 'q_pnp'
            self._add_3port(comp_type, comp.name, ('C', comp.drain, 'output'), ('B', comp.gate, 'input'), ('E', comp.source, 'output'), getattr(comp, 'model', 'M'))
        elif isinstance(comp, OpAmp):
            self.cells[comp.name] = {
                'type': 'op',
                'port_directions': {'+': 'input', '-': 'input', 'OUT': 'output'},
                'connections': {'+': [self._get_node_id(comp.in_p)], '-': [self._get_node_id(comp.in_n)], 'OUT': [self._get_node_id(comp.out)]},
                'attributes': {'ref': comp.name, 'value': 'OPAMP'} 
            }
        else:
            self.cells[comp.name] = {
                'type': 'generic',
                'port_directions': {'in': 'input', 'out': 'output'},
                'connections': {
                    'in': [self._get_node_id(comp.node1 if hasattr(comp, 'node1') else 0)],
                    'out': [self._get_node_id(comp.node2 if hasattr(comp, 'node2') else 0)]
                },
                'attributes': {'ref': comp.name, 'value': comp.__class__.__name__}
            }

    def generate(self, output_path: str) -> bool:
        """Main flow: logical layout followed by brute-force coordinate re-sync."""
        self.cells = {}; self.node_to_id = {}; self.next_node_id = 1
        for comp in self.circuit.get_components(): self._generate_cell_for_comp(comp)

        # 1. Topology Mapping
        net_to_cells = {}; cell_to_nets = {}
        for cname, cdata in self.cells.items():
            cell_to_nets[cname] = set()
            for ports in cdata['connections'].values():
                for nid in ports:
                    if nid not in net_to_cells: net_to_cells[nid] = set()
                    net_to_cells[nid].add(cname)
                    cell_to_nets[cname].add(nid)
        
        # 2. Anchor and Stage Identification
        anchor_types = {'q_npn', 'q_pnp', 'op', 'generic'}
        anchors = {cn for cn, d in self.cells.items() if d['type'] in anchor_types}
        supply_cells = {cn for cn, d in self.cells.items() if d['type'] == 'voltage_source'}
        
        self._supply_comps = set()
        for cn in supply_cells:
            self._supply_comps.add(f"cell_{cn}")
            for nid in cell_to_nets.get(cn, []):
                for connected_cn in net_to_cells.get(nid, []):
                    self._supply_comps.add(f"cell_{connected_cn}")
                    
        self._supply_nets = set()
        for nid, cns in net_to_cells.items():
            if all(f"cell_{cn}" in self._supply_comps for cn in cns):
                self._supply_nets.add(f"net_{nid}")
        
        # 3. Final Corrected Priority Mapping (Smaller = LEFT confirmed by amp_v24 failure)
        # Goal: Supply (1) -> Base (20) -> Anchor (40) -> Collector (60) -> Emitter (80)
        
        stage_map = {} 
        ident_gnd = {nid for cn, d in self.cells.items() if d['type'] == 'gnd' for nl in d['connections'].values() for nid in nl}
        
        for cn, cdata in self.cells.items():
            if cn in anchors: 
                stage_map[cn] = 40
                continue
            if cn in supply_cells: 
                stage_map[cn] = 1
                continue
            
            prio = 20 # Default to Base zone
            for nid in cell_to_nets[cn]:
                if nid in ident_gnd: continue
                # Look for anchor terminal connection
                found = False
                for anc in anchors:
                    anc_data = self.cells[anc]
                    for pin, nids in anc_data['connections'].items():
                        if nid in nids:
                            if pin in {'B', '+', '-'}: prio = 20; found = True
                            elif pin in {'C', 'OUT'}: prio = 60; found = True
                            elif pin == 'E': prio = 80; found = True
                            break
                    if found: break
                if found: break
            stage_map[cn] = prio

        # 4. Vertical Layering (Potential Levels)
        v_layers = {}; queue = deque()
        for cname, cdata in self.cells.items():
            if cdata['type'] == 'vcc': v_layers[cname] = 0; queue.append((cname, 0))
        
        v_nets = set()
        while queue:
            curr_c, curr_l = queue.popleft()
            for nid in cell_to_nets[curr_c]:
                if nid in v_nets: continue
                v_nets.add(nid)
                for nx_c in net_to_cells.get(nid, []):
                    if nx_c not in v_layers and self.cells[nx_c]['type'] != 'gnd':
                        v_layers[nx_c] = curr_l + 1; queue.append((nx_c, curr_l + 1))

        max_vl = max(v_layers.values()) if v_layers else 1
        for cn in self.cells:
            if cn not in v_layers and self.cells[cn]['type'] != 'gnd': v_layers[cn] = max_vl + 1
        
        gnd_layer = (max(v_layers.values()) if v_layers else 1) + 1
        for cn in self.cells:
            if self.cells[cn]['type'] == 'gnd': v_layers[cn] = gnd_layer

        # 5. Apply Constraints
        comp_gnd_row = gnd_layer - 1
        self._gnd_terminal_comps = set()

        for cn, cdata in self.cells.items():
            at = cdata['attributes']
            prio = stage_map.get(cn, 20)
            
            # Record GND passives for post-processor before we override v_layers for power symbols
            is_gnd_term = any(nid in ident_gnd for nid in cell_to_nets[cn])
            if cdata['type'] not in {'gnd', 'vcc'} and is_gnd_term:
                v_layers[cn] = comp_gnd_row
                self._gnd_terminal_comps.add(cn)

            if cdata['type'] in {'vcc', 'gnd'}:
                nid = list(cdata['connections'].values())[0][0]
                connected = [c for c in net_to_cells.get(nid, []) if c != cn]
                if connected: prio = stage_map.get(connected[0], 20)
                else: prio = 1 if cdata['type'] == 'vcc' else 80
            
            at['org.eclipse.elk.priority'] = prio
            at['org.eclipse.elk.layered.priority'] = prio
            at['org.eclipse.elk.layerIndex'] = v_layers[cn]
            at['org.eclipse.elk.layered.layering.layerIndex'] = v_layers[cn]

        # Enforce JSON insertion order for ELK forceNodeModelOrder (Smaller = Left)
        sorted_cells = {k: self.cells[k] for k in sorted(self.cells.keys(), key=lambda x: self.cells[x]['attributes'].get('org.eclipse.elk.priority', 50))}

        # SVG Export
        sch_json = {'modules': {self.circuit.name.replace(' ', '_'): {'ports': {}, 'cells': sorted_cells}}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(sch_json, tmp); tmp_p = tmp.name
            
        cmd = 'netlistsvg.cmd' if platform.system() == 'Windows' else 'netlistsvg'
        try:
            subprocess.run([cmd, tmp_p, '--skin', SKIN_PATH, '-o', output_path], capture_output=True, text=True, check=True)
            self._autofit_viewbox(output_path)
            self._brute_force_svg_align(output_path)
            return True
        except Exception as e: raise RuntimeError(f"Rendering failed: {str(e)}")
        finally:
            if os.path.exists(tmp_p): os.remove(tmp_p)

    def _brute_force_svg_align(self, svg_path: str) -> None:
        """Staff Engineer Level: Rewrites SVG with absolute precision and port-offset awareness."""
        if not os.path.exists(svg_path): return
        with open(svg_path, 'r', encoding='utf-8') as f: content = f.read()
        def fmt(v): return f"{v:.6f}".rstrip('0').rstrip('.') or "0"

        # 1. Supply Offset Logic (Force to far left)
        supply_ids = getattr(self, '_supply_comps', set())
        supply_nets = getattr(self, '_supply_nets', set())
        
        shift_s = 0; shift_o = 0
        if supply_ids:
            # ONLY match the opening <g> tag to prevent catastrophic backtracking!
            group_matches = list(re.finditer(r'<g([^>]+id="([^"]+)"[^>]*)>', content))
            supply_x = []; other_x = []
            for m in group_matches:
                attrs = m.group(1)
                bid = m.group(2)
                mt = re.search(r'transform="translate\(([\d.-]+),\s*([\d.-]+)\)"', attrs)
                if mt:
                    x_val = float(mt.group(1))
                    if bid in supply_ids: supply_x.append(x_val)
                    else: other_x.append(x_val)
                    
            if supply_x and other_x:
                min_s = min(supply_x); max_s = max(supply_x)
                min_o = min(other_x)
                if min_s > min_o or min_s > 100:
                    shift_s = 40 - min_s
                    width_s = max_s - min_s
                    shift_o = (40 + width_s + 100) - min_o

        if shift_s != 0 or shift_o != 0:
            def shift_wires_x(match):
                element = match.group(0)
                cls_match = re.search(r'class="([^"]+)"', element)
                if not cls_match: return element
                classes = cls_match.group(1).split()
                is_supply = any(c in supply_nets or c in supply_ids for c in classes)
                x_shift = shift_s if is_supply else shift_o
                if abs(x_shift) < 0.1: return element
                
                if element.startswith('<line'):
                    for i in ['1', '2']:
                        element = re.sub(rf'x{i}="([\d.-]+)"', lambda m: f'x{i}="{fmt(float(m.group(1)) + x_shift)}"', element)
                elif element.startswith('<path'):
                    def coord_repl(cm):
                        cmd, px, py = cm.group(1), float(cm.group(2)), float(cm.group(3))
                        return f'{cmd} {fmt(px + x_shift)} {fmt(py)}'
                    element = re.sub(r'([ML])\s*([\d.-]+)\s*,\s*([\d.-]+)', coord_repl, element)
                    element = re.sub(r'([ML])\s*([\d.-]+)\s+([\d.-]+)', coord_repl, element)
                return element
            
            content = re.sub(r'<line [^>]+>', shift_wires_x, content)
            content = re.sub(r'<path [^>]+>', shift_wires_x, content)

        # Re-parse opening tags for terminal/GND fixing
        group_matches = list(re.finditer(r'<g([^>]+id="([^"]+)"[^>]*)>', content))
        if not group_matches: return
        id_to_data = {}
        for m in group_matches:
            attrs = m.group(1)
            bid = m.group(2)
            mt = re.search(r'transform="translate\(([\d.-]+),\s*([\d.-]+)\)"', attrs)
            if mt: id_to_data[bid] = {'attrs': attrs, 'ax': float(mt.group(1)), 'ay': float(mt.group(2))}

        gnd_ids = [bid for bid, dat in id_to_data.items() if 's:type="gnd"' in dat['attrs']]
        target_gnd_y = max(id_to_data[bid]['ay'] for bid in gnd_ids) if gnd_ids else 800
        term_ids = {f"cell_{cn}" for cn in getattr(self, '_gnd_terminal_comps', set())}
        term_ids = [bid for bid in term_ids if bid in id_to_data]
        target_term_y = max(id_to_data[bid]['ay'] for bid in term_ids) if term_ids else (target_gnd_y - 120)

        def fix_wires(old_ax_x, old_port_y, new_port_y, content_str):
            def line_repl(lm):
                la = lm.group(1)
                for i in [1, 2]:
                    mx, my = re.search(f'x{i}="([\\d.-]+)"', la), re.search(f'y{i}="([\\d.-]+)"', la)
                    if mx and my:
                        vx, vy = float(mx.group(1)), float(my.group(1))
                        if abs(vx - old_ax_x) < 5 and abs(vy - old_port_y) < 5: la = re.sub(f'y{i}="[\\d.-]+"', f'y{i}="{fmt(new_port_y)}"', la)
                return f'<line {la}'
            content_str = re.sub(r'<line ([^>]+)', line_repl, content_str)
            def path_repl(pm):
                pre, d = pm.group(1), pm.group(2)
                def coord_repl(cm):
                    cd, px, py = cm.group(1), float(cm.group(2)), float(cm.group(3))
                    if abs(px - old_ax_x) < 5 and abs(py - old_port_y) < 5: return f'{cd} {fmt(px)} {fmt(new_port_y)}'
                    return cm.group(0)
                d_fixed = re.sub(r'([ML])\s*([\d.-]+)\s*,\s*([\d.-]+)', coord_repl, d)
                d_fixed = re.sub(r'([ML])\s*([\d.-]+)\s+([\d.-]+)', coord_repl, d_fixed)
                return f'{pre}d="{d_fixed}"'
            content_str = re.sub(r'(<path [^>]*?)d="([^"]+)"', path_repl, content_str)
            return content_str

        new_content = content
        for bid, dat in id_to_data.items():
            is_gnd = bid in gnd_ids; is_term = bid in term_ids
            x_shift = shift_s if bid in supply_ids else shift_o
            dat['ax'] += x_shift
            
            target_y = target_gnd_y if is_gnd else (target_term_y if is_term else dat['ay'])
            if abs(dat['ay'] - target_y) < 0.1 and abs(x_shift) < 0.1: continue
            
            def tag_repl(tm):
                tag_body = tm.group(1)
                new_tag_body = re.sub(r'transform="translate\([\d.-]+,\s*([\d.-]+)\)"', f'transform="translate({fmt(dat["ax"])},{fmt(target_y)})"', tag_body)
                return f'<g{new_tag_body}>'
            new_content = re.sub(rf'<g([^>]*\bid="{re.escape(bid)}"[^>]*)>', tag_repl, new_content)
            
            # Use fixed standard port offsets for checking terminal connections rather than parsing full group block
            # because we no longer capture the block body in our regex
            # We already fixed horizontal wire alignment, so we only adjust vertical Y stretching here for known GND terminals.
            if is_term or is_gnd:
                # E.g. GND uses y=-15 offset relative to target_y to connect its top port
                dy_s = -15 if is_gnd else 50 # term uses 50 for bottom port of a resistor
                new_content = fix_wires(dat['ax'], dat['ay'] + dy_s, target_y + dy_s, new_content)
        with open(svg_path, 'w', encoding='utf-8') as f: f.write(new_content)

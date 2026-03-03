import math

class AutoPlacer:
    def __init__(self, circuit):
        self.circuit = circuit
        self.components = list(circuit.get_components())
        self.pos = {}
        self.GRID = 2.54
        self.START_X = 50.8
        self.START_Y = 50.8
        self.DX = 30.48
        self.DY = 25.4
        
    def place(self):
        node_to_comps = {}
        for c in self.components:
            nodes = []
            if hasattr(c, 'node1'): nodes.extend([c.node1, c.node2])
            elif hasattr(c, 'in_p'): nodes.extend([c.in_p, c.in_n, c.out])
            
            for n in nodes:
                if n != "0": 
                    node_to_comps.setdefault(n, []).append(c)
                    
        sources = [c for c in self.components if c.__class__.__name__ in ('VoltageSource', 'ACVoltageSource')]
        
        placed = set()
        levels = {}
        for s in sources:
            levels[s] = 0
            
        queue = sources[:]
        visited_nodes = set()
        while queue:
            curr = queue.pop(0)
            placed.add(curr)
            lvl = int(levels[curr])
            
            nodes = []
            if hasattr(curr, 'node1'): nodes.extend([curr.node1, curr.node2])
            elif hasattr(curr, 'in_p'): nodes.extend([curr.in_p, curr.in_n, curr.out])
            
            for n in nodes:
                if n == "0" or n in visited_nodes: continue
                visited_nodes.add(n)
                for nxt_comp in node_to_comps.get(n, []):
                    if nxt_comp not in placed:
                        # OpAmp feedback grouping
                        is_feedback = False
                        if hasattr(nxt_comp, 'node1') and hasattr(curr, 'in_p'):
                            if (nxt_comp.node1 == curr.out and nxt_comp.node2 == curr.in_n) or (nxt_comp.node2 == curr.out and nxt_comp.node1 == curr.in_n):
                                is_feedback = True
                                
                        if is_feedback:
                            levels[nxt_comp] = lvl + 0.1
                        else:
                            levels[nxt_comp] = lvl + 1
                        queue.append(nxt_comp)
                        placed.add(nxt_comp)
                        
        for c in self.components:
            if c not in levels:
                levels[c] = 0
                
        # 1. Place all non-feedback components
        current_y = {}
        for c, lvl in sorted(levels.items(), key=lambda x: x[1]):
            if int(lvl) != lvl: continue # skip feedback for now
            
            base_lvl = int(lvl)
            if base_lvl not in current_y:
                current_y[base_lvl] = self.START_Y
                
            x = self.START_X + base_lvl * self.DX
            y = current_y[base_lvl]
            self.pos[c.name] = [x, y]
            current_y[base_lvl] += self.DY

        # 2. Place feedback components explicitly above OpAmps
        opamps = [c for c in self.components if c.__class__.__name__ in ('OpAmp',)]
        for op in opamps:
            if op.name not in self.pos: continue
            for c in self.components:
                if getattr(c, '__class__', None).__name__ in ('Resistor', 'Capacitor'):
                    if (c.node1 == op.out and c.node2 == op.in_n) or (c.node2 == op.out and c.node1 == op.in_n):
                        ox, oy = self.pos[op.name]
                        self.pos[c.name] = [(ox - 0.0), (oy - 20.32)] # 20mm above
                        
        # 3. Apply grid snap
        for k, v in list(self.pos.items()):
            self.pos[k] = (round(v[0] / self.GRID) * self.GRID, round(v[1] / self.GRID) * self.GRID)

        return self.pos

class AutoRouter:
    def __init__(self):
        self.wires = []
        
    def is_collision(self, x, y, bboxes):
        for bx1, by1, bx2, by2 in bboxes:
            if bx1-0.1 < x < bx2+0.1 and by1-0.1 < y < by2+0.1:
                return True
        return False

    def route(self, pin_nets, bboxes):
        nets = {}
        for node, px, py in pin_nets:
            nets.setdefault(node, []).append((px, py))
            
        for node, points in nets.items():
            if node == "0": continue # GND handles locally via #PWR
            if len(points) < 2: continue
            
            # Simple progressive routing
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i+1]
                
                # Check directly if they share X or Y
                if p1[0] == p2[0] or p1[1] == p2[1]:
                    self.wires.append((p1, p2))
                else:
                    # Try Manhattan X -> Y
                    # Round mid X to grid
                    cx1 = round(((p1[0] + p2[0]) / 2.0) / 2.54) * 2.54
                    
                    if self.is_collision(cx1, p1[1], bboxes) or self.is_collision(cx1, p2[1], bboxes):
                        cy1 = round(((p1[1] + p2[1]) / 2.0) / 2.54) * 2.54
                        if p1[1] != cy1: self.wires.append(((p1[0], p1[1]), (p1[0], cy1)))
                        if p1[0] != p2[0]: self.wires.append(((p1[0], cy1), (p2[0], cy1)))
                        if cy1 != p2[1]: self.wires.append(((p2[0], cy1), (p2[0], p2[1])))
                    else:
                        if p1[0] != cx1: self.wires.append(((p1[0], p1[1]), (cx1, p1[1])))
                        if p1[1] != p2[1]: self.wires.append(((cx1, p1[1]), (cx1, p2[1])))
                        if cx1 != p2[0]: self.wires.append(((cx1, p2[1]), (p2[0], p2[1])))
                        
                self.wires.append("JUNCTION:" + str(p1[0]) + "," + str(p1[1]))
                self.wires.append("JUNCTION:" + str(p2[0]) + "," + str(p2[1]))
                
        return self.wires

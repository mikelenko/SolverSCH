"""
altium_parser.py -> Parsuje pliki .NET (Altium) i wyciąga z nich obwód.

Zgodnie z zasadami projektu, omijamy układy scalone (poza OpAmpami) i skupiamy się na
części analogowej. Mapuje Altium -> solver_sch Circuit.
"""

import re
import logging
from typing import Dict, List, Optional, Set
import xlrd

from solver_sch.model.altium_model import AltiumComponent, AltiumNet, AltiumPin, BomEntry, AltiumProject
from solver_sch.model.circuit import (
    Circuit, Resistor, Capacitor, Inductor, Diode, OpAmp, Comparator, ModelCard,
    BJT_N, BJT_P, MOSFET_P, MOSFET_N, VoltageSource, LM5085Gate,
)

logger = logging.getLogger("solver_sch.parser.altium_parser")

class AltiumParser:
    """Konwerter plików Altium (.NET, BOM) na obiekty Circuit."""

    # SPICE Engineering Notation Map dla parsera ułamków (często występują w Altium)
    PREFIX_MULTIPLIERS = {
        'F': 1e-15, 'P': 1e-12, 'N': 1e-9, 'U': 1e-6,
        'M': 1e-3, 'K': 1e3, 'MEG': 1e6, 'G': 1e9, 'T': 1e12
    }

    @classmethod
    def parse_netlist_file(cls, filepath: str) -> AltiumProject:
        """Parsuje plik .NET z Altium Designera jako zbiór ciągów znaków."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
                
        return cls.parse_netlist_content(content)

    @classmethod
    def parse_netlist_content(cls, content: str) -> AltiumProject:
        """Parsuje tekstową zawartość pliku .NET."""
        project = AltiumProject()
        
        # 1. Parsowanie Komponentów: [Designator \n Footprint \n Comment]
        # np. [\nU1\nSOIC8\nLM358\n]
        comp_blocks = re.findall(r'\[([^\]]+)\]', content)
        for block in comp_blocks:
            lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
            if len(lines) >= 3:
                # W Altium, linie to zazwyczaj: [0] = Designator, [1] = Footprint, [2] = Comment
                designator = lines[0]
                footprint = lines[1]
                comment = lines[2]
                project.components[designator] = AltiumComponent(designator, footprint, comment)

        # 2. Parsowanie Sieci: (NetName \n Pin1 \n Pin2 ...)
        # np. (\nGND\nR1-1\nC2-2\n)
        net_blocks = re.findall(r'\(([^\)]+)\)', content)
        for block in net_blocks:
            lines = [line.strip() for line in block.strip().split('\n') if line.strip()]
            if len(lines) >= 1:
                net_name = lines[0]
                net = AltiumNet(name=net_name)
                for pin_str in lines[1:]:
                    net.pins.append(AltiumPin.from_string(pin_str))
                project.nets.append(net)

        return project

    @classmethod
    def parse_bom(cls, filepath: str) -> Dict[str, BomEntry]:
        """Parsuje plik BOM w formacie Excel (.xls).

        Wymaga zainstalowanej blilioteki `xlrd`. Zwraca {designator: BomEntry}.
        Przeszukuje plik do momentu znalezienia nagłówków.
        """
        bom_map: Dict[str, BomEntry] = {}
        try:
            wb = xlrd.open_workbook(filepath)
            sh = wb.sheet_by_index(0)
            
            # Wyszukiwanie rzędu z nagłówkami
            header_row = -1
            col_map = {}
            for row_idx in range(min(30, sh.nrows)):
                row_vals = [str(v).strip().lower() for v in sh.row_values(row_idx)]
                if 'designator' in row_vals and 'description' in row_vals:
                    header_row = row_idx
                    # Mapowanie najważniejszych kolumn
                    for i, val in enumerate(row_vals):
                        if val == 'part number': col_map['pn'] = i
                        elif val == 'footprint': col_map['footprint'] = i
                        elif val == 'designator': col_map['designator'] = i
                        elif val == 'manufacturer': col_map['mfr'] = i
                        elif val == 'manufacturer part number': col_map['mpn'] = i
                        elif val == 'description': col_map['desc'] = i
                    break
                    
            if header_row == -1 or 'designator' not in col_map:
                logger.warning(f"Nie znaleziono odpowiednich nagłówków BOM w {filepath}")
                return bom_map
                
            # Parsowanie wierszy BOM
            for row_idx in range(header_row + 1, sh.nrows):
                row = sh.row_values(row_idx)
                
                # Zatrzymanie się jeśli skończono czytać części BOM
                if not row[col_map['designator']]:
                    # Czasem są wiersze końcowe zawierające opisy typu "Approved By". Pomijamy puste.
                    continue
                    
                designators_str = str(row[col_map['designator']])
                designators = [d.strip() for d in designators_str.split(',') if d.strip()]
                
                pn = str(row[col_map.get('pn', -1)]) if 'pn' in col_map else ""
                footprint = str(row[col_map.get('footprint', -1)]) if 'footprint' in col_map else ""
                mfr = str(row[col_map.get('mfr', -1)]) if 'mfr' in col_map else ""
                mpn = str(row[col_map.get('mpn', -1)]) if 'mpn' in col_map else ""
                desc = str(row[col_map.get('desc', -1)]) if 'desc' in col_map else ""
                
                entry = BomEntry(part_number=pn, footprint=footprint, designators=designators,
                                 manufacturer=mfr, mpn=mpn, description=desc)
                                 
                for d in designators:
                    bom_map[d] = entry

        except ImportError:
            logger.error("Brak pakietu `xlrd`. Zastosuj `pip install xlrd` do wczytania BOM.")
        except Exception as e:
            logger.error(f"Błąd podczas parsowania BOM: {e}")
            
        return bom_map

    @classmethod
    def parse_bom_xlsx(cls, filepath: str, sheet_number: Optional[str] = None) -> Dict[str, str]:
        """Parsuje plik BOM w formacie .xlsx (openpyxl) z kolumną SheetNumber.

        Zwraca {designator: comment} dla komponentów pasujących do sheet_number.
        Jeśli sheet_number=None, zwraca wszystkie.
        """
        try:
            import openpyxl
        except ImportError:
            logger.error("Brak pakietu `openpyxl`. Zainstaluj: pip install openpyxl")
            return {}

        result: Dict[str, str] = {}
        try:
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            sh = wb.active
            rows = list(sh.iter_rows(values_only=True))
            if not rows:
                return result

            headers = [str(c).strip() if c is not None else "" for c in rows[0]]
            try:
                desig_idx = headers.index("Designator")
                sheet_idx = headers.index("SheetNumber")
            except ValueError as e:
                logger.error(f"Brak wymaganej kolumny w BOM xlsx: {e}")
                return result
            # Description zawiera czytelne wartości (np. "68µH ...", "100n/16V X7R") — użyj jej jako "comment"
            desc_idx = headers.index("Description") if "Description" in headers else -1
            comment_idx = headers.index("Comment") if "Comment" in headers else -1

            for row in rows[1:]:
                sheet_val = str(row[sheet_idx] or "").strip()
                desig_val = str(row[desig_idx] or "").strip()
                # Preferuj Description (zawiera wartość inżynierską) nad Comment (numer katalogowy)
                desc_val = str(row[desc_idx] or "").strip() if desc_idx >= 0 else ""
                comment_val = str(row[comment_idx] or "").strip() if comment_idx >= 0 else ""
                value_str = desc_val if desc_val else comment_val
                if not desig_val:
                    continue

                if sheet_number is not None:
                    sheets = [s.strip() for s in re.split(r"[,;]+", sheet_val)]
                    target = str(sheet_number)
                    if not any(
                        s == target or s.startswith(target + ".") or s.startswith(target + " ")
                        for s in sheets
                    ):
                        continue

                for d in re.split(r"[,\s]+", desig_val):
                    d = d.strip()
                    if d:
                        result[d] = value_str
        except Exception as e:
            logger.error(f"Błąd parsowania BOM xlsx: {e}")

        return result

    @classmethod
    def filter_by_designators(cls, project: AltiumProject, designators: Set[str]) -> AltiumProject:
        """Zwraca nowy AltiumProject zawierający tylko komponenty z podanego zbioru designatorów.

        Sieci są filtrowane — zostawiane są tylko piny komponentów z whitelist.
        """
        filtered = AltiumProject()

        for des in designators:
            if des in project.components:
                filtered.components[des] = project.components[des]

        for net in project.nets:
            filtered_pins = [p for p in net.pins if p.designator in designators]
            if filtered_pins:
                filtered.nets.append(AltiumNet(name=net.name, pins=filtered_pins))

        logger.info(
            f"filter_by_designators: {len(filtered.components)} komp., {len(filtered.nets)} sieci "
            f"(z {len(project.components)} / {len(project.nets)})."
        )
        return filtered

    @classmethod
    def extract_value(cls, text: str) -> Optional[float]:
        """Parsuje opisy z Altium (comment/description) w celu wyodrębnienia wartości numerycznej.
        
        Rozpoznaje formaty np: 
        '100k 1% 0402' -> 100000.0
        '1u/16V X7R' -> 1e-6
        '0R 0402' -> 0.001 (zabezpieczenie Gmin)
        '1k5 1% 0402' -> 1500.0
        '620R' -> 620.0
        """
        # Normalizacja unicode i specjalnych symboli
        text = text.replace('µ', 'u').replace('μ', 'u').replace('Ω', 'R').replace('ω', 'R')
        # "mOhms" / "mohm" → MILLIOHM marker
        text = re.sub(r'\bm[Oo][Hh][Mm]s?\b', 'MILLIOHM', text)
        # Jednostki indukcyjności: uH/µH → U, mH → M, nH → N (przed upper())
        text = re.sub(r'([0-9])\s*([uµ])H\b', r'\1U', text, flags=re.IGNORECASE)
        text = re.sub(r'([0-9])\s*mH\b', r'\1M', text, flags=re.IGNORECASE)
        text = re.sub(r'([0-9])\s*nH\b', r'\1N', text, flags=re.IGNORECASE)
        text = text.upper().strip()
        # "10 MILLIOHM" → 0.01 Ohm
        m_mohm = re.search(r'\b(\d+(?:\.\d+)?)\s*MILLIOHM', text)
        if m_mohm:
            return float(m_mohm.group(1)) * 1e-3

        # 1. Poszukiwanie ułamków brytyjskich np. 1K5, 4U7, 2R2, 0R
        # Pattern szuka cyfr, oznaczenia inżynierskiego, i reszty cyfr (np. "4U7", "1K5")
        match = re.search(r'\b(\d+)([RKMGTUNPF])(\d+)\b', text)
        if match:
            num1 = match.group(1)
            unit = match.group(2)
            num2 = match.group(3)
            
            base_val = float(f"{num1}.{num2}")
            
            if unit == 'R':
                return base_val
            multiplier = cls.PREFIX_MULTIPLIERS.get(unit, 1.0)
            return base_val * multiplier
            
        # 2. Szukanie 0R jako zabezpieczenia Gmin dla zwarcia w analogowych zworkach
        match = re.search(r'\b0R\b', text)
        if match:
            return 0.001 # 1mOhm zastępujący zwarcie (aby zapobiec dzieleniu przez zero)

        # 3. Klasyczne oznaczenia np "100K", "10U/16V", "620R", "10K 1%"
        # Dopasowuje cyfry, opcjonalny ułamek, a potem od razu (bez spacji) jednostkę.
        match = re.search(r'\b(\d+(?:\.\d+)?)([RKMGTUNPF])\b', text)
        if match:
             base_val = float(match.group(1))
             unit = match.group(2)
             
             if unit == 'R':
                 return base_val
             multiplier = cls.PREFIX_MULTIPLIERS.get(unit, 1.0)
             return base_val * multiplier
        
        # 3b. Klasyka ze spacją (lub bez), ale na końcu / lub %: np '10u/16V'
        match = re.search(r'\b(\d+(?:\.\d+)?)\s*([RKMGTUNPF])(?:[/%\b\s]|\Z)', text)
        if match:
             base_val = float(match.group(1))
             unit = match.group(2)
             
             if unit == 'R':
                 return base_val
             multiplier = cls.PREFIX_MULTIPLIERS.get(unit, 1.0)
             return base_val * multiplier
        
        # 4. Same liczby np. 100
        match = re.search(r'\b(\d+(?:\.\d+)?)\b', text)
        if match:
             return float(match.group(1))

        return None

    @classmethod
    def is_analog_component(cls, comp: AltiumComponent, net_map: Dict[str, str]) -> bool:
        """Filtruje komponenty czysto cyfrowe bez szansy odwzorowania w SPICE z tej aplikacji."""
        prefix = comp.prefix
        
        if prefix in ('R', 'C', 'L', 'D', 'Q', 'M'):
             return True
             
        # Obsługa specjalna układów U
        if prefix == 'U':
             # Szukamy wzmacniaczy operacyjnych lub komparatorów po opisie w Comment
             desc = comp.comment.upper()
             if "LMV321" in desc or "OPAMP" in desc or "COMPARATOR" in desc or "LP2901" in desc:
                 return True
             if "LM5085" in desc:
                 return True
             return False # Pomiń całą resztę (mikrokontrolery, FPGA, RTC)
             
        # Test pointy itp omijamy (mają zwykle puste prefixy albo TST_POINT)
        return False
        
    @classmethod
    def isolate_subcircuit(cls, project: AltiumProject, start_net_name: str, stop_nets: List[str]) -> AltiumProject:
        """Wyciąga pod-obwód za pomocą BFS startując od wybranej sieci i zatrzymując się na zasilaniach.
        
        Zwraca nowy AltiumProject ze zredukowaną listą komponentów i sieci.
        """
        # Szybkie wyszukiwanie sieci po nazwie
        net_by_name = {n.name: n for n in project.nets}
        
        # Ostrzeżenie jeśli sieć startowa nie istnieje (zwracamy pusty projekt)
        if start_net_name not in net_by_name:
            logger.warning(f"Sieć startowa '{start_net_name}' nie istnieje w projekcie.")
            return AltiumProject()
            
        visited_nets = set()
        visited_comps = set()
        queue = [start_net_name]
        
        # Stop condition uppercase for safe matching
        stop_nets_upper = {n.upper() for n in stop_nets}
        
        while queue:
            current_net_name = queue.pop(0)
            if current_net_name in visited_nets:
                continue
                
            visited_nets.add(current_net_name)
            current_net = net_by_name.get(current_net_name)
            if not current_net:
                continue
                
            # Zbieranie komponentów fizycznie podpiętych do tej sieci
            for pin in current_net.pins:
                comp_designator = pin.designator
                if comp_designator not in visited_comps:
                    visited_comps.add(comp_designator)
                    
                    # Sprawdzamy, czy komponent jest analogowy. Jeśli to wielki układ cyfrowy (jak FPGA U30),
                    # NIE przechodzimy przez niego na inne sieci (zapobiega to wyciągnięciu całej płyty).
                    comp = project.components.get(comp_designator)
                    comp_nets = project.get_nets_for_component(comp_designator)
                    
                    if comp and cls.is_analog_component(comp, comp_nets):
                        # Ograniczenie przechodzenia dla układów wielokanałowych (np. poczwórny komparator)
                        # aby zapobiec łączeniu niezależnych obwodów A, B, C, D w jeden potężny graf.
                        allowed_pins = None
                        prefix = comp.prefix
                        if prefix == 'U' and ("LP2901" in comp.comment.upper() or "COMPARATOR" in comp.comment.upper()):
                            groups = [{'4', '5', '2'}, {'6', '7', '1'}, {'8', '9', '14'}, {'10', '11', '13'}]
                            for g in groups:
                                if str(pin.pin) in g:
                                    allowed_pins = g
                                    break
                                    
                        # Znaleźliśmy nowy komponent przepuszczający. Dodajemy jego pozostałe sieci do BFS.
                        for p_idx, net_n in comp_nets.items():
                            if allowed_pins and str(p_idx) not in allowed_pins:
                                continue # Pomiń piny należące do innych kanałów w tym samym układzie scalonym
                                
                            if net_n and net_n not in visited_nets and str(net_n).upper() not in stop_nets_upper:
                                queue.append(str(net_n))
                            
        # Zbudowanie zredukowanego projektu (z zachowaniem oryginalnych referencji do obiektów - nie robimy deepcopy)
        isolated_proj = AltiumProject()
        
        for comp_name in visited_comps:
            if comp_name in project.components:
                isolated_proj.components[comp_name] = project.components[comp_name]
                
        # Dodajemy tylko te sieci, które do czegoś w izolowanym układzie są odniesione
        for net in project.nets:
            # Filtrujemy piny w sieci by zostawić tylko te z isolated_comps
            filtered_pins = [p for p in net.pins if p.designator in visited_comps]
            if filtered_pins:
                isolated_proj.nets.append(AltiumNet(name=net.name, pins=filtered_pins))
                
        logger.info(f"Odinzolowano {len(isolated_proj.components)} komponentów startując z '{start_net_name}'.")
        return isolated_proj

    @classmethod
    def _find_node_or_ground(cls, pin_nodes: Dict[str, str], pin: str) -> str:
        """Zwraca '0' dla masy z Altium, lub węzeł przypisany w pin_nodes."""
        node = pin_nodes.get(pin)
        if not node:
             return "UNCONNECTED"
        if node.upper() in ["GND", "0", "AGND", "DGND", "PGND", "GNDA"]:
             return "0"
        return node

    @classmethod
    def convert_to_circuit(cls, project: AltiumProject, circuit_name: str = "Altium Export") -> Circuit:
        """Zamienia model Altium (.NET) na solver_sch.model.Circuit."""
        circuit = Circuit(name=circuit_name)

        if any(c.prefix == 'D' for c in project.components.values()):
            circuit.add_model(ModelCard("D_ALTIUM", "D", {"Is": "1e-14", "n": "1"}))

        for designator, comp in project.components.items():
            pin_nodes = project.get_nets_for_component(designator)
            if not cls.is_analog_component(comp, pin_nodes):
                logger.debug(f"Pominięto (nie-analogowe): {designator} - {comp.comment}")
                continue

            prefix = comp.prefix
            node1 = cls._find_node_or_ground(pin_nodes, "1")
            node2 = cls._find_node_or_ground(pin_nodes, "2")

            if prefix in ('R', 'C', 'L'):
                if not cls._map_passive(comp, circuit, node1, node2):
                    continue
            elif prefix == 'D':
                cls._map_diode(comp, circuit, node1, node2)
            elif prefix in ('Q', 'M'):
                if not cls._map_transistor(comp, circuit, pin_nodes):
                    continue
            elif prefix == 'U':
                cls._map_ic(comp, circuit, pin_nodes)

        return circuit

    @classmethod
    def _map_passive(cls, comp: "AltiumComponent", circuit: Circuit, node1: str, node2: str) -> bool:
        """Maps R/C/L component. Returns False if value parsing fails."""
        val = cls.extract_value(comp.comment)
        if val is None:
            logger.warning(f"Nie powiodło się parsowanie wartości dla {comp.designator}: '{comp.comment}'. Ominięto.")
            return False
        prefix = comp.prefix
        designator = comp.designator
        if prefix == 'R':
            circuit.add_component(Resistor(designator, node1, node2, val))
        elif prefix == 'C':
            circuit.add_component(Capacitor(designator, node1, node2, val))
        elif prefix == 'L':
            circuit.add_component(Inductor(designator, node1, node2, val))
        return True

    @classmethod
    def _map_diode(cls, comp: "AltiumComponent", circuit: Circuit, node1: str, node2: str) -> None:
        """Maps D component. Pin1=Anode, Pin2=Cathode (standard SMD footprint)."""
        circuit.add_component(Diode(comp.designator, node1, node2, model="D_ALTIUM"))

    @classmethod
    def _map_transistor(cls, comp: "AltiumComponent", circuit: Circuit, pin_nodes: dict) -> bool:
        """Maps Q/M component as MOSFET or BJT. Returns False if pins incomplete."""
        designator = comp.designator
        desc_up = comp.comment.upper()
        foot_up = comp.footprint.upper()
        is_mosfet = any(kw in desc_up or kw in foot_up for kw in
                        ("SQS", "BSS", "FDS", "NMOS", "PMOS", "MOSFET", "FET",
                         "POWERPAK", "SOT23-3N", "SOT23F"))
        is_pch = any(kw in desc_up for kw in ("P-CHANNEL", "PCHANNEL", "SQS411", "SQP"))

        if is_mosfet:
            # PowerPAK (8-pin): Source=pins 1-3, Gate=pin4, Drain=pins 5-8
            src = cls._find_node_or_ground(pin_nodes, "1")
            gate = cls._find_node_or_ground(pin_nodes, "4")
            drn = cls._find_node_or_ground(pin_nodes, "5")
            if src == "UNCONNECTED":
                src = cls._find_node_or_ground(pin_nodes, "2")
            if drn == "UNCONNECTED":
                drn = cls._find_node_or_ground(pin_nodes, "6")
            if gate == "UNCONNECTED" or src == "UNCONNECTED" or drn == "UNCONNECTED":
                logger.warning(f"MOSFET {designator}: niepełne piny (S={src} G={gate} D={drn}), pomijam.")
                return False
            model_name = "SQS411_PMOS" if is_pch else "GENERIC_NMOS"
            if is_pch:
                circuit.add_component(MOSFET_P(designator, drain=drn, gate=gate, source=src, model=model_name))
            else:
                circuit.add_component(MOSFET_N(designator, drain=drn, gate=gate, source=src, model=model_name))
        else:
            # BJT — SOT-23-3: Pin1=Base, Pin2=Emitter, Pin3=Collector
            base = cls._find_node_or_ground(pin_nodes, "1")
            emitter = cls._find_node_or_ground(pin_nodes, "2")
            collector = cls._find_node_or_ground(pin_nodes, "3")
            is_pnp = any(kw in desc_up for kw in ("PNP", "MMBT3906", "BC857", "PMBT3906", "BC327"))
            bjt_cls = BJT_P if is_pnp else BJT_N
            bjt_type = "PNP" if is_pnp else "NPN"
            raw = desc_up.split('/')[0][:12]
            safe = re.sub(r'[^A-Z0-9_]', '_', raw).strip('_')
            circuit.add_component(bjt_cls(
                designator,
                collector=collector, base=base, emitter=emitter,
                model=f"{bjt_type}_{safe}",
            ))
        return True

    @classmethod
    def _map_ic(cls, comp: "AltiumComponent", circuit: Circuit, pin_nodes: dict) -> None:
        """Maps U-prefix ICs: LMV321 (OpAmp), LM5085 (Buck), LP2901 (Quad Comparator)."""
        designator = comp.designator
        comment_up = comp.comment.upper()

        if "LMV321" in comment_up:
            # SOT23-5: 1=IN+, 2=V-, 3=IN-, 4=OUT, 5=V+
            in_p = cls._find_node_or_ground(pin_nodes, "1")
            in_n = cls._find_node_or_ground(pin_nodes, "3")
            out = cls._find_node_or_ground(pin_nodes, "4")
            circuit.add_component(OpAmp(designator, in_p=in_p, in_n=in_n, out=out))

        elif "LM5085" in comment_up:
            # WSON-8: 1=TON/RT, 2=FB/ADJ, 3=COMP, 4=GND, 5=ISEN, 6=PGATE, 7=VCC, 8=VIN
            vin_node = cls._find_node_or_ground(pin_nodes, "8")
            fb_node = cls._find_node_or_ground(pin_nodes, "2")
            pgate_node = cls._find_node_or_ground(pin_nodes, "6")
            vcc_node = cls._find_node_or_ground(pin_nodes, "7")
            if any(n == "UNCONNECTED" for n in (vin_node, fb_node, pgate_node, vcc_node)):
                logger.warning(f"LM5085 {designator}: brak kluczowych pinów, pomijam.")
            else:
                circuit.add_component(LM5085Gate(
                    designator, vin=vin_node, fb=fb_node, pgate=pgate_node, vcc=vcc_node, gnd="0",
                ))

        elif "LP2901" in comment_up or "COMPARATOR" in comment_up:
            # 14-pin SOIC: 1=OUT2, 2=OUT1, 3=VCC, 4=IN1-, 5=IN1+, 6=IN2-, 7=IN2+
            #              8=IN3-, 9=IN3+, 10=IN4-, 11=IN4+, 12=GND, 13=OUT4, 14=OUT3
            for unit, (pin_n, pin_p, pin_out) in (
                ("_A", ("4",  "5",  "2")),
                ("_B", ("6",  "7",  "1")),
                ("_C", ("8",  "9",  "14")),
                ("_D", ("10", "11", "13")),
            ):
                in_n = cls._find_node_or_ground(pin_nodes, pin_n)
                in_p = cls._find_node_or_ground(pin_nodes, pin_p)
                out = cls._find_node_or_ground(pin_nodes, pin_out)
                if in_n != "UNCONNECTED" or in_p != "UNCONNECTED":
                    circuit.add_component(Comparator(f"{designator}{unit}", node_p=in_p, node_n=in_n, node_out=out))

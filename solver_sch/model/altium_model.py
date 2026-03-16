"""
altium_model.py -> Data model for Altium Designer exported netlist and BOM.

Strict Rules:
- Pure data containers only. NO parsing logic, NO I/O.
- NO numpy, NO scipy, NO external dependencies.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AltiumComponent:
    """A single component entry from the Altium .NET component section.

    Fields map directly to the [designator / footprint / comment] block.
    """
    designator: str       # e.g. "R1", "C7", "U7", "D25"
    footprint: str        # e.g. "RESC0402L", "CAPC0402L", "SOT95P310X110-5N"
    comment: str          # e.g. "100k 1% 0402", "LMV321IYLT"

    @property
    def prefix(self) -> str:
        """Extract the alphabetical prefix from the designator (e.g. 'R' from 'R184_2')."""
        for i, ch in enumerate(self.designator):
            if ch.isdigit():
                return self.designator[:i].upper()
        return self.designator.upper()


@dataclass
class AltiumPin:
    """A pin reference in the format 'designator-pin_number'."""
    designator: str
    pin: str

    @classmethod
    def from_string(cls, pin_str: str) -> "AltiumPin":
        """Parse 'R1-1', 'U30-A17', 'C7-1' into AltiumPin."""
        parts = pin_str.rsplit("-", 1)
        if len(parts) == 2:
            return cls(designator=parts[0], pin=parts[1])
        return cls(designator=pin_str, pin="1")


@dataclass
class AltiumNet:
    """A single net from the Altium .NET net section.

    Contains the net name and all pin connections.
    """
    name: str                     # e.g. "+3V3", "GND", "Supply OUT"
    pins: List[AltiumPin] = field(default_factory=list)

    def get_designators(self) -> List[str]:
        """Return unique designators connected to this net."""
        return list(set(p.designator for p in self.pins))


@dataclass
class BomEntry:
    """A single BOM row with manufacturer and sourcing data."""
    part_number: str
    footprint: str
    designators: List[str]
    manufacturer: str
    mpn: str
    description: str
    supplier: str = ""
    spn: str = ""
    quantity: int = 0


@dataclass
class AltiumProject:
    """Complete parsed representation of an Altium design.

    Holds components, nets, and optionally BOM enrichment data.
    """
    components: Dict[str, AltiumComponent] = field(default_factory=dict)  # key = designator
    nets: List[AltiumNet] = field(default_factory=list)
    bom: Dict[str, BomEntry] = field(default_factory=dict)  # key = designator

    def get_nets_for_component(self, designator: str) -> Dict[str, str]:
        """Return {pin_number: net_name} mapping for a given component."""
        result: Dict[str, str] = {}
        for net in self.nets:
            for pin in net.pins:
                if pin.designator == designator:
                    result[pin.pin] = net.name
        return result

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def net_count(self) -> int:
        return len(self.nets)

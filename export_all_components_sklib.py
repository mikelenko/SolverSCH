from collections import defaultdict
from skidl import Pin, Part, Alias, SchLib, SKIDL, TEMPLATE

from skidl.pin import pin_types

SKIDL_lib_version = '0.0.1'

export_all_components = SchLib(tool=SKIDL).add_parts(*[
        Part(**{ 'name':'R_Small', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'R_Small'}), 'ref_prefix':'R', 'fplist':[''], 'footprint':'Resistor_SMD:R_0805_2012Metric', 'keywords':'R resistor', 'description':'Resistor, small symbol', 'datasheet':'~', 'pins':[
            Pin(num='1',name='~',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='~',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'L_Small', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'L_Small'}), 'ref_prefix':'L', 'fplist':[''], 'footprint':'Inductor_SMD:L_0805_2012Metric', 'keywords':'inductor choke coil reactor magnetic', 'description':'Inductor, small symbol', 'datasheet':'~', 'pins':[
            Pin(num='1',name='~',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='~',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'C_Small', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'C_Small'}), 'ref_prefix':'C', 'fplist':[''], 'footprint':'Capacitor_SMD:C_0805_2012Metric', 'keywords':'capacitor cap', 'description':'Unpolarized capacitor, small symbol', 'datasheet':'~', 'pins':[
            Pin(num='1',name='~',func=pin_types.PASSIVE,unit=1),
            Pin(num='2',name='~',func=pin_types.PASSIVE,unit=1)], 'unit_defs':[] }),
        Part(**{ 'name':'LM358', 'dest':TEMPLATE, 'tool':SKIDL, 'aliases':Alias({'LM358'}), 'ref_prefix':'U', 'fplist':['', ''], 'footprint':'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 'keywords':'dual opamp', 'description':'Low-Power, Dual Operational Amplifiers, DIP-8/SOIC-8/TO-99-8', 'datasheet':'http://www.ti.com/lit/ds/symlink/lm2904-n.pdf', 'pins':[
            Pin(num='3',name='+',func=pin_types.INPUT,unit=1),
            Pin(num='2',name='-',func=pin_types.INPUT,unit=1),
            Pin(num='1',name='~',func=pin_types.OUTPUT,unit=1),
            Pin(num='5',name='+',func=pin_types.INPUT,unit=2),
            Pin(num='6',name='-',func=pin_types.INPUT,unit=2),
            Pin(num='7',name='~',func=pin_types.OUTPUT,unit=2),
            Pin(num='8',name='V+',func=pin_types.PWRIN,unit=3),
            Pin(num='4',name='V-',func=pin_types.PWRIN,unit=3)], 'unit_defs':[{'label': 'uA', 'num': 1, 'pin_nums': ['1', '3', '2']},{'label': 'uB', 'num': 2, 'pin_nums': ['5', '6', '7']},{'label': 'uC', 'num': 3, 'pin_nums': ['8', '4']}] })])
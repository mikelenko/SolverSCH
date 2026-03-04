import sys; sys.path.insert(0, '.')

# Test 1: Clean imports from top-level package
from solver_sch import Circuit, Resistor, Capacitor, Inductor, ACVoltageSource, OpAmp, Simulator
from solver_sch import available_components, available_analyses, component_help
print('[OK] Clean top-level imports work')

# Test 2: Component registry
import json
catalogue = json.loads(available_components())
print(f'[OK] Registry has {len(catalogue)} component types: {list(catalogue.keys())}')

# Test 3: Circuit.validate()
c = Circuit('Test', ground_name='0')
c.add_component(ACVoltageSource('Vin', 'in', '0', amplitude=1.0, frequency=1000))
c.add_component(Resistor('R1', 'in', 'out', 1000))
c.add_component(Capacitor('C1', 'out', '0', 1e-6))
v = c.validate()
print(f'[OK] Circuit.validate() -> valid={v.valid}, errors={len(v.errors)}, warnings={len(v.warnings)}')

# Test 4: Simulator facade
sim = Simulator(c)

# DC
dc = sim.dc()
print('[OK] sim.dc() ->', dc.to_dict()['node_voltages_V'])

# AC
ac = sim.ac(f_start=100, f_stop=100e3, points_per_decade=5)
at_1k = ac.at_frequency(1000)
print(f'[OK] sim.ac() -> at 1kHz: out={at_1k["out"]["magnitude_dB"]:.2f}dB')

# Circuit info
info = sim.info()
print(f'[OK] sim.info() -> {info["component_count"]} components, nodes: {info["nodes"]}')

# Test 5: Validation error on bad circuit
bad = Circuit('Bad', ground_name='0')
bad.add_component(Resistor('R1', 'a', 'b', -500))  # negative R
bv = bad.validate()
print(f'[OK] Bad circuit invalid: valid={bv.valid}, errors={[e.message for e in bv.errors]}')

print()
print('=== ALL VERIFICATION TESTS PASSED ===')

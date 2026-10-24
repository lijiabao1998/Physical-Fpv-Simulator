"""Reproduce pinned Python baselines. No research solve or empirical gate changes."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'python'))
from powertrain import Powertrain
from flight import FlightModel, FlightConfig

manifest = json.loads((ROOT / 'source-manifest.json').read_text())
for name, digest in manifest['files'].items():
    assert hashlib.sha256((ROOT / 'python' / name).read_bytes()).hexdigest() == digest, name

cases = []
for name, duration, duties, direct, velocity in [
    ('freefall', 1, [0]*4, None, [0,0,0]),
    ('hover', 1, None, [0.72*9.80665/4]*4, [0,0,0]),
    ('underpowered', 1, None, [0.8]*4, [0,0,0]),
    ('powered-drag', 1, [.44]*4, None, [1.2,-.4,0]),
    ('differential', .2, [.47,.45,.43,.46], None, [0,0,0]),
]:
    dt=1/240
    flight=FlightModel(FlightConfig(ground_enabled=False))
    flight.state.position_m=np.array([0.,0.,20.])
    flight.state.velocity_m_s=np.array(velocity,dtype=float)
    power=Powertrain()
    trace=[]
    for i in range(round(duration/dt)):
        if duties is not None:
            load=power.step(duties,dt,float(np.linalg.norm(flight.state.velocity_m_s)))
            thrust,torque=load.thrust_n,load.rotor_torque_nm
        else:
            load=power.evaluate([0]*4)
            thrust,torque=np.array(direct),np.zeros(4)
        flight.step(thrust,torque,dt)
        if (i+1)%12==0:
            trace.append({'time':(i+1)*dt,'position':flight.state.position_m.tolist(),
                          'velocity':flight.state.velocity_m_s.tolist(),
                          'q':flight.state.quaternion_wxyz.tolist(),
                          'rates':flight.state.angular_velocity_rad_s.tolist(),
                          'voltage':load.voltage_v,'thrust':np.asarray(thrust).tolist(),
                          'soc':float(power.telemetry()['soc'][0][0])})
    cases.append({'name':name,'duration':duration,'dt':dt,'duties':duties,'directThrust':direct,
                  'initialVelocity':velocity,'trace':trace})

out={'schema':'fpv-python-reference-v1','source_sha':manifest['source_commit'],
     'numpy_version':np.__version__,'synthetic':True,'hardware_validated':False,'cases':cases}
destination=ROOT.parent/'web'/'numerical-results'
destination.mkdir(parents=True,exist_ok=True)
(destination/'python-fixtures.json').write_text(json.dumps(out,indent=2)+'\n')
print(f'Wrote {len(cases)} pinned Python trajectories; source hashes verified, no hardware claim.')

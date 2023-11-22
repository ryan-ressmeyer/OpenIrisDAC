import nidaqmx
import nidaqmx.stream_writers
import nidaqmx.system
import numpy as np
from tqdm import tqdm
import time
system = nidaqmx.system.System.local()

devs = [device for device in system.devices]

assert len(devs), 'Could not find NI-DAQ device. Is it connected?'
dev = devs[0]
print(f'Using device: {dev}')

with nidaqmx.Task() as task:
    task.ao_channels.add_ao_voltage_chan(dev.name + "/ao0", name_to_assign_to_channel='', min_val=0.0, max_val=5.0)
    task.ao_channels.add_ao_voltage_chan(dev.name + "/ao1", name_to_assign_to_channel='', min_val=0.0, max_val=5.0)
    
    writer = nidaqmx.stream_writers.AnalogMultiChannelWriter(
        task.out_stream, auto_start=True)

    dt = .001 # 1ms update
    out_arr = np.zeros(2)
    for t in tqdm(np.arange(0,10,dt)):
        out_arr[0] = 7 * (np.cos(2*np.pi*t) + 1) / 2 # 1Hz
        out_arr[1] = 7 * (np.sin(4*np.pi*t) + 1) / 2 # 2Hz
        writer.write_one_sample(out_arr)
        time.sleep(dt)
    writer.write_one_sample(np.array([0, 0]))
    
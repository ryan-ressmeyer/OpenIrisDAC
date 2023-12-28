if __name__ == '__main__':
    import AIOUSB as ao
    import time
    import numpy as np
    from tqdm import tqdm

    def write_channel_voltage(index, channel:int, voltage:float, v_max=5):
        """
        Writes a voltage to a channel. The voltage is clamped to the range [-v_max, v_max].
        """
        v_out = voltage if voltage < v_max else v_max
        v_out = v_out if v_out > -v_max else -v_max
        with nidaqmx.Task() as task:
            task.ao_channels.add_ao_voltage_chan("Dev1/ao0")
            task.ao_channels.add_ao_voltage_chan("Dev1/ao1")
            task.write([1.1, 2.2, 3.3, 4.4, 5.5], auto_start=True)

    print('Running test')

    dt = .001 # 1ms update
    for t in tqdm(np.arange(0,10,dt)):
        x = 4 * np.cos(2*np.pi*t) # 1Hz
        y = 4 * np.sin(4*np.pi*t) # 2Hz
        write_channel_voltage(ao.diOnly, 0, x)
        write_channel_voltage(ao.diOnly, 1, y)
        time.sleep(dt)
    write_channel_voltage(ao.diOnly, 0, 0)
    write_channel_voltage(ao.diOnly, 1, 0)

    print('Finished!')
        
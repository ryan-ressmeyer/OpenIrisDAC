from ctypes import *
import os
from pathlib import Path

file_path = os.path.dirname(os.path.realpath(__file__))

apci_lib = CDLL(Path(file_path) / "APCI/apcilib/apcilib.so")

class DAC(object):
    """
    DAC class for interfacing with the APCI PCIe-DA16-6
    """
    def __init__(self):
        self.devicepath = "/dev/apci/pcie_da16_6_0"
        self.bar_register = 2
        self.f_apci = None
        self._ignore = c_uint8(0)

    def set_simultaneous_mode(self):
        """
        Puts the DAC in simultaneous mode. This means that all channels are updated at the same time. 
        Update is pushed from memory to DAC on update_outputs() call.
        """
        self._check_open()
        apci_lib.apci_read8(self.f_apci, 0, self.bar_register, 0x00, byref(self._ignore))
    
    def set_asynchronous_mode(self):
        """
        Puts the DAC in asynchronous mode. This means that each channel is updated individually.
        """
        self._check_open()
        apci_lib.apci_read8(self.f_apci, 0, self.bar_register, 0x0A, byref(self._ignore))

    def write_channel_voltage(self, channel:int, voltage:float, v_max=10):
        """
        Writes a voltage to a channel. The voltage is clamped to the range [-v_max, v_max].
        """
        self._check_open()

        v_out = voltage if voltage < v_max else v_max
        v_out = v_out if v_out > -v_max else -v_max

        short_out = c_uint16(int((v_out + v_max) / v_max / 2 * 65536))
        apci_lib.apci_write16(self.f_apci, 0, self.bar_register, channel*2, short_out)

    def update_outputs(self):
        """
        Pushes the voltage values from memory to the DAC.
        """
        self._check_open()
        apci_lib.apci_read8(self.f_apci, 0, self.bar_register, 0x08, byref(self._ignore))

    def _check_open(self):
        if self.f_apci is None:
            raise ValueError('Device not open. Use with statement to open device.')

    def __enter__(self):
        try:
            self.f_apci = os.open(self.devicepath, os.O_RDONLY)
        except:
            print('Failed to open device. Trying again new permissions.')
            os.system('sudo setfacl -m u:$USER:rw /dev/apci/*')
            self.f_apci = os.open(self.devicepath, os.O_RDONLY)      
        
        # Zero channels
        for i in range(6):
            self.write_channel_voltage(i, 0)
        self.update_outputs()

        # Clear restrict-output-voltage mode
        apci_lib.apci_read8(self.f_apci, 0, self.bar_register, 0x0F, byref(self._ignore))

        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        for i in range(6):
            self.write_channel_voltage(i, 0)
        self.update_outputs()

        os.close(self.f_apci)
        self.f_apci = None

if __name__ == "__main__":
    import time
    import numpy as np
    from tqdm import tqdm

    with DAC() as dac:
        print('Running test')
        dac.set_simultaneous_mode()
        dt = .001 # 1ms update
        for t in tqdm(np.arange(0,10,dt)):
            x = 4 * np.cos(2*np.pi*t) # 1Hz
            y = 4 * np.sin(4*np.pi*t) # 2Hz
            dac.write_channel_voltage(0, x)
            dac.write_channel_voltage(1, y)
            dac.update_outputs()
            time.sleep(dt)
        dac.write_channel_voltage(0, 0)
        dac.write_channel_voltage(1, 0)
        dac.update_outputs()

    print('Finished!')

from open_iris_client import OpenIrisClient
import PySimpleGUI as sg
import time
from pathlib import Path
from dataclasses import dataclass
import math
import nidaqmx
import nidaqmx.stream_writers
import nidaqmx.system
import numpy as np

@dataclass
class Point:
    x: float
    y: float
    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)
    
    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __mul__(self, other):
        if isinstance(other, Point):
            return Point(self.x * other.x, self.y * other.y)
        else:
            return Point(self.x * other, self.y * other)

    
    def clip(self, minimum, maxaximum):
        return Point(min(max(self.x, minimum), maxaximum), min(max(self.y, minimum), maxaximum))

    def rotate(self, angle:float):
        return Point(self.x * math.cos(angle) - self.y * math.sin(angle), self.x * math.sin(angle) + self.y * math.cos(angle))

@dataclass
class EyeData:
    pupil: Point
    cr: Point
    p4: Point
    cr_error: str
    p4_error: str
    def __init__(self, struct:dict = {}):
        if struct:
            self.pupil = Point(struct['Pupil']['X'], struct['Pupil']['Y'])
            if struct['CRs']:
                self.cr = Point(struct['CRs'][0]['X'], struct['CRs'][0]['Y'])
                self.cr_error = ''
            else:
                self.cr = Point(0,0)
                self.cr_error = 'No CRs'
            if len(struct['CRs']) >= 4:
                self.p4 = Point(struct['CRs'][3]['X'], struct['CRs'][3]['Y'])
                self.p4_error = ''
            else:
                self.p4 = Point(0,0)
                self.p4_error = 'NO P4'
        else:
            self.pupil = Point(0,0)
            self.cr = Point(0,0)
            self.p4 = Point(0,0)
            self.cr_error = 'No data'
            self.p4_error = 'No data'

@dataclass
class EyesData:
    left: EyeData
    right: EyeData
    error: str
    def __init__(self, struct:dict = {}):
        if struct:
            self.left = EyeData(struct['Left'])
            self.right = EyeData(struct['Right'])
            self.error = ''
        else:
            self.left = EyeData()
            self.right = EyeData()
            self.error = 'No data'

@dataclass
class CalibrationParameters:
    x_bias: float
    y_bias: float
    x_gain: float
    y_gain: float
    rotation: float
    
    def transform(self, pos:Point):
        return ((pos + Point(self.x_bias, self.y_bias)) * Point(self.x_gain, self.y_gain)).rotate(self.rotation * math.pi / 180)

class GUI:
    def __init__(self):
        self.left_cal = CalibrationParameters(-60,-180,-.013,-.013,0)
        self.right_cal = CalibrationParameters(80,-180,-.013,-.013,0)
        self.method = 'dpi'
        self.eye = 'Left'
        c1 = sg.Column([
            [sg.Text('X Bias')], 
            [sg.Slider((-300,300), default_value=self.cal.x_bias, s=(30, 20), resolution=1, k='x bias', enable_events=True)]
            ])
        c2 = sg.Column([
            [sg.Text('Y Bias')], 
            [sg.Slider((-300,300), default_value=self.cal.y_bias, s=(30, 20), resolution=1, k='y bias', enable_events=True)]
            ])
        c3 = sg.Column([
            [sg.Text('X Gain')], 
            [sg.Slider((0,500), default_value=int(abs(self.cal.x_gain)*1000), s=(30, 20), resolution=1, k='x gain', enable_events=True)], 
            [sg.Checkbox('flip x', k='flip x', enable_events=True, default=self.cal.x_gain < 0)]
            ])
        c4 = sg.Column([
            [sg.Text('Y Gain')], 
            [sg.Slider((0,500), default_value=int(abs(self.cal.y_gain)*1000), s=(30, 20), resolution=1, k='y gain', enable_events=True)], 
            [sg.Checkbox('flip y', k='flip y', enable_events=True, default=self.cal.y_gain < 0)]
            ])
        c5 = sg.Column([
            [sg.Text('Rotation')], 
            [sg.Slider((-180,180), default_value=self.cal.rotation, s=(30, 20), resolution=1, k='rotation', enable_events=True)]
            ])
        self.graph = sg.Graph(canvas_size=(400,400), graph_bottom_left=(-5,-5), graph_top_right=(5,5), background_color='grey', key='graph')
        graph_col = sg.Column([
            [sg.Text('', key='error', size=(20,1), text_color='red')],
            [self.graph],
            [
                sg.Text('Method: '), 
                sg.Radio('P1-P4', 'method', key='dpi', default=self.method=='dpi', enable_events=True), 
                sg.Radio('P1-Pupil', 'method', key='pcr', default=self.method=='pcr', enable_events=True)
            ],
            [
                sg.Text('Eye: '), 
                sg.Radio('Right', 'eye', key='Right', default=self.eye=='Right', enable_events=True),
                sg.Radio('Left', 'eye', key='Left', default=self.eye=='Left', enable_events=True), 
            ]
            ])
        self.layout = [
            [c1, c2, c3, c4, c5, graph_col]
        ]

    @property
    def cal(self):
        if self.eye == 'Left':
            return self.left_cal
        elif self.eye == 'Right':
            return self.right_cal
        else:
            raise Exception('Invalid eye')

    def get_eyedata(self, client:OpenIrisClient):
        data = client.receive_data()
        if data is not None:
            return EyesData(data)
        else:
            ed = EyesData({})
            ed.error = 'No data'
            return ed

    def update_graph(self, out:np.ndarray):
        self.graph.erase()
        # draw axes
        self.graph.draw_line((-5,0), (5,0))
        self.graph.draw_line((0,-5), (0,5))
        for xy in range(-5, 6):
            self.graph.draw_line((xy,-0.1), (xy,0.1))
            self.graph.draw_line((-0.1,xy), (0.1,xy))

        self.graph.draw_point((out[0], out[1]), size=.15, color='red')
        self.graph.draw_point((out[3], out[4]), size=.15, color='green')

    
    def update_sliders(self):
        self.window['x bias'].update(value = self.cal.x_bias)
        self.window['y bias'].update(value = self.cal.y_bias)
        self.window['x gain'].update(value = int(abs(self.cal.x_gain)*1000))
        self.window['y gain'].update(value = int(abs(self.cal.y_gain)*1000))
        self.window['flip x'].update(value = self.cal.x_gain < 0)
        self.window['flip y'].update(value = self.cal.y_gain < 0)
        self.window['rotation'].update(value = self.cal.rotation)
        self.window.refresh()
        time.sleep(0.01)

    def window_loop(self, open_iris_ip='localhost', verbose=False):
        system = nidaqmx.system.System.local()
        devs = [device for device in system.devices]
        assert len(devs), 'Could not find NI-DAQ device. Is it connected?'
        dev = devs[0]
        print(f'Using device: {dev}')

        with OpenIrisClient(server_address=open_iris_ip) as client, nidaqmx.Task() as ao_task:
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao0", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao1", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao2", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao3", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao4", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
            ao_task.ao_channels.add_ao_voltage_chan(dev.name + "/ao5", name_to_assign_to_channel='', min_val=-5.0, max_val=5.0)
    
            writer = nidaqmx.stream_writers.AnalogMultiChannelWriter(
                ao_task.out_stream, auto_start=True)

            out_arr = np.ones(6)*-5

            self.window = sg.Window('OpenIrisClient', self.layout)
            out = None
            while True:
                event, values = self.window.read(timeout=10) # 10ms ~= 100Hz
                if verbose:
                    print(event, values)

                if event == sg.WIN_CLOSED or event == 'Close':
                    break
                
                if event in ['Left', 'Right']:
                    # Update eye
                    if values['Left']:
                        self.eye = 'Left'
                    elif values['Right']:
                        self.eye = 'Right'
                    else:
                        self.eye = 'Left'
                    # self.send_cal_to_usb()
                    self.update_sliders()

                if event in ['dpi', 'pcr']:
                    # Update method
                    if values['dpi']:
                        self.method = 'dpi'
                    elif values['pcr']:
                        self.method = 'pcr'
                    else:
                        self.method = 'dpi'

                if event in ['x bias', 'y bias', 'x gain', 'y gain', 'flip x', 'flip y', 'rotation']:
                    # Update calibration
                    self.cal.x_bias = values["x bias"]
                    self.cal.y_bias = values["y bias"]
                    self.cal.x_gain = values["x gain"]/1000 * (-1 if values['flip x'] else 1)
                    self.cal.y_gain = values["y gain"]/1000 * (-1 if values['flip y'] else 1)
                    self.cal.rotation = values["rotation"]
                    # self.send_cal_to_usb() This would be ideal, but toFloat() is too slow in Arduino

                if event == sg.TIMEOUT_EVENT:

                    # Get eye data
                    ed = self.get_eyedata(client)
                    eye_data = ed.left if self.eye == 'Left' else ed.right
                    if ed.error:
                        self.window['error'].update(value = ed.error, text_color='red')
                    elif self.method == 'dpi':
                        if eye_data.cr_error or eye_data.p4_error:
                            self.window['error'].update(value = eye_data.cr_error + ' ' + eye_data.p4_error, text_color='red')
                        else:  
                            self.window['error'].update(value = 'Tracking', text_color='lawn green')
                            l_out = self.left_cal.transform(ed.left.cr - ed.left.p4)
                            r_out = self.right_cal.transform(ed.right.cr - ed.right.p4)
                            out_arr = np.array([l_out.x, l_out.y, 0, r_out.x, r_out.y,0])
                    elif self.method == 'pcr':
                        if eye_data.cr_error:
                            self.window['error'].update(value = eye_data.cr_error, text_color='red')
                        else:
                            self.window['error'].update(value = 'Tracking', text_color='lawn green')
                            l_out = self.left_cal.transform(ed.left.cr - ed.left.p4)
                            r_out = self.right_cal.transform(ed.right.cr - ed.right.p4)
                            out_arr = np.array([l_out.x, l_out.y, 0, r_out.x, r_out.y,0])
                    out_arr = np.clip(out_arr)
                    self.update_graph(out_arr)
                    writer.write_one_sample(out_arr)

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        # if self.usb_ser is not None:
        #     self.usb_ser.close()
        if self.window:
            self.window.close()
    

if __name__ == "__main__":
    with GUI() as gui:
        gui.window_loop(open_iris_ip='localhost', verbose=False)
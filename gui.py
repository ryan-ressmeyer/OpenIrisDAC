from open_iris_client import OpenIrisClient, Point, EyesData
import PySimpleGUI as sg
import time
from pathlib import Path
from dac import AnalogModule, AIOModule, discover_ao_modules
from dataclasses import dataclass
import math

@dataclass
class CalibrationParameters:
    x_bias: float
    y_bias: float
    x_gain: float
    y_gain: float
    rotation: float

    def transform(self, pos:Point):
        return ((pos + Point(self.x_bias, self.y_bias)) * Point(self.x_gain, self.y_gain)).rotate(self.rotation * math.pi / 180)
    
    def save(self, fname:Path):
        with open(fname, 'w') as f:
            f.write(f'{self.x_bias},{self.y_bias},{self.x_gain},{self.y_gain},{self.rotation}')
    
    def load(self, fname:Path):
        try:
            with open(fname, 'r') as f:
                self.x_bias, self.y_bias, self.x_gain, self.y_gain, self.rotation = [float(x) for x in f.read().split(',')]
        except Exception as e:
            print(e)
            print('Error loading calibration file.')

class AnalogOutput:
    def __init__(self, module:AnalogModule = None, channel:int=0):
        if module is None:
            module = AnalogModule()
        self.module = module
        self.channel = channel
        self.out = 0
    
    def write(self, voltage:float):
        self.module.write_channel(self.channel, voltage)
        self.out = voltage

    @property
    def v_out(self):
        return self.module.v_out[self.channel]

class AnalogOutputPair:
    def __init__(self, output1:AnalogOutput=None, output2:AnalogOutput=None):
        if output1 is None:
            output1 = AnalogOutput()
        if output2 is None:
            output2 = AnalogOutput()
        self.output1 = output1
        self.output2 = output2
        self.out = Point(0,0)
    
    def write(self, voltage:Point):
        self.output1.write(voltage.x)
        self.output2.write(voltage.y)
        self.out = voltage

    @property
    def v_out(self):
        return Point(self.output1.v_out, self.output2.v_out)


class GlobalState:
    def __init__(self, save_dir:Path = None) -> None:
        if save_dir is None:
            save_dir = Path(__file__).parent / 'state'
        self.save_dir = save_dir
        if not self.save_dir.exists():
            self.save_dir.mkdir()

        self.left_cal = CalibrationParameters(-60,180,-.013,.013,0)
        self.left_method = 'dpi'
        self.left_output = AnalogOutputPair()

        self.right_cal = CalibrationParameters(80,180,-.013,.013,0)
        self.right_method = 'dpi'
        self.right_output = AnalogOutputPair()

        self.pupil_cal = CalibrationParameters(0,0,0.01,0.01,0)
        self.pupil_output = AnalogOutputPair()

        self.last_eyes_data = EyesData()
        self.is_running = True

        self.load()

        self.discover_analog_modules()

    def discover_analog_modules(self):
        # TODO Move this to global state (also save serial numbers?)
        self.module_list = discover_ao_modules()
        print(f"Found {len(self.module_list)} Output Devices: {self.module_list}")
        
        self.output_dict = {}
        for module in self.module_list:
            for channel in range(module.n_channels):
                key = f'{module.name}-ch{channel}'
                while key in self.output_dict:
                    key = key[:len(module.name)] + '-2' + key[len(module.name):]
                self.output_dict[key] = AnalogOutput(module, channel)

        print(f"Found {len(self.output_dict)} Output Channels: {self.output_dict.keys()}")

    def save(self):
        if not self.save_dir.exists():
            dir.mkdir()
        # save calibrations
        self.left_cal.save(self.save_dir / 'left_cal.txt')
        self.right_cal.save(self.save_dir / 'right_cal.txt')
        self.pupil_cal.save(self.save_dir / 'pupil_cal.txt')
        # save methods
        with open(self.save_dir / 'methods.txt', 'w') as f:
            f.write(f'{self.left_method},{self.right_method}')
    
    def load(self):
        if not self.save_dir.exists():
            return
        # load calibrations
        try:
            self.left_cal.load(self.save_dir / 'left_cal.txt')
            self.right_cal.load(self.save_dir / 'right_cal.txt')
            self.pupil_cal.load(self.save_dir / 'pupil_cal.txt')
        except:
            print('Error loading calibration files.')
        # load methods
        try:
            with open(self.save_dir / 'methods.txt', 'r') as f:
                self.left_method, self.right_method = f.read().split(',')
            if self.left_method not in ['dpi', 'pcr']:
                self.left_method = 'dpi'
            if self.right_method not in ['dpi', 'pcr']:
                self.right_method = 'dpi'
        except:
            self.left_method = 'dpi'
            self.right_method = 'dpi'

class GUI:
    def __init__(self, state:GlobalState) -> None:
        self.state = state

        def make_column(title, key, size, resolution, default_value, minimum, maximum, append=[]):
            return sg.Column([
                [sg.Text(title)], 
                [sg.Slider((minimum,maximum), default_value=default_value, s=size, resolution=resolution, k=key, enable_events=True)],
                append
                ])
        
        self.gain_factor = 2000
        self.pupil_factor = 10000
        col_size = (30,20)
        lc1 = make_column('X Bias', 'left_x_bias', col_size, 1, self.state.left_cal.x_bias, -300, 300)
        lc2 = make_column('Y Bias', 'left_y_bias', col_size, 1, self.state.left_cal.y_bias, -300, 300)
        lc3 = make_column('X Gain', 'left_x_gain', col_size, 1, int(abs(self.state.left_cal.x_gain)*self.gain_factor), 0, 300,
                          [sg.Checkbox('Flip', key='left_flip_x', default=(self.state.left_cal.x_gain < 0), enable_events=True)])
        lc4 = make_column('Y Gain', 'left_y_gain', col_size, 1, int(abs(self.state.left_cal.y_gain)*self.gain_factor), 0, 300,
                          [sg.Checkbox('Flip', key='left_flip_y', default=(self.state.left_cal.y_gain < 0), enable_events=True)])
        lc5 = make_column('Rotation', 'left_rotation', col_size, 1, self.state.left_cal.rotation, -180, 180)
        l = sg.Column([
            [lc1, lc2, lc3, lc4, lc5], 
            [sg.Text('Method: '), 
             sg.Radio('DPI (P1-P4)', 'left_method', key='left_dpi', default=self.state.left_method=='dpi', enable_events=True), 
             sg.Radio('PCR (P1-Pupil)', 'left_method', key='left_pcr', default=self.state.left_method=='pcr', enable_events=True)
             ]
        ])
        lt = sg.Tab('Left Eye', [[l]])

        rc1 = make_column('X Bias', 'right_x_bias', col_size, 1, self.state.right_cal.x_bias, -300, 300)
        rc2 = make_column('Y Bias', 'right_y_bias', col_size, 1, self.state.right_cal.y_bias, -300, 300)
        rc3 = make_column('X Gain', 'right_x_gain', col_size, 1, int(abs(self.state.right_cal.x_gain)*self.gain_factor), 0, 300,
                          [sg.Checkbox('Flip', key='right_flip_x', default=(self.state.right_cal.x_gain < 0), enable_events=True)])
        rc4 = make_column('Y Gain', 'right_y_gain', col_size, 1, int(abs(self.state.right_cal.y_gain)*self.gain_factor), 0, 300, 
                          [sg.Checkbox('Flip', key='right_flip_y', default=(self.state.right_cal.y_gain < 0), enable_events=True)])
        rc5 = make_column('Rotation', 'right_rotation', col_size, 1, self.state.right_cal.rotation, -180, 180)
        r = sg.Column([
            [rc1, rc2, rc3, rc4, rc5], 
            [sg.Text('Method: '), 
             sg.Radio('DPI (P1-P4)', 'right_method', key='right_dpi', default=self.state.right_method=='dpi', enable_events=True), 
             sg.Radio('PCR (P1-Pupil)', 'right_method', key='right_pcr', default=self.state.right_method=='pcr', enable_events=True)
             ]
        ])
        rt = sg.Tab('Right Eye', [[r]])

        pc1 = make_column('Left Bias', 'left_pupil_bias', (30, 20), 100, self.state.pupil_cal.x_bias, -30000, 30000)
        pc2 = make_column('Right Bias', 'right_pupil_bias', (30, 20), 100, self.state.pupil_cal.y_bias, -30000, 30000)
        pc3 = make_column('Left Gain', 'left_pupil_gain', (30, 20), 1, int(abs(self.state.pupil_cal.x_gain)*self.pupil_factor), 0, 300)
        pc4 = make_column('Right Gain', 'right_pupil_gain', (30, 20), 1, int(abs(self.state.pupil_cal.y_gain)*self.pupil_factor), 0, 300)
        pt = sg.Tab('Pupil', [[pc1, pc2, pc3, pc4]])
        
        tabs = sg.TabGroup([[lt, rt, pt]], key='tabs')
        
        self.graph = sg.Graph(canvas_size=(400,400), graph_bottom_left=(-5,-5), graph_top_right=(5,5), background_color='grey', key='graph')
        

        self.output_list = list(self.state.output_dict.keys())
        self.output_list.insert(0, 'NONE')
        graph_col = sg.Column([
            [sg.Text('', key='error', size=(20,1), text_color='red')],
            [self.graph],
            [sg.Text('Channels: '),],
            [sg.Button(' ', disabled=True, button_color='DodgerBlue'), 
             sg.Text('Left X: '), sg.Combo(self.output_list, default_value=self.output_list[1] if len(self.output_list) >= 1 else 'None', 
                                           key='left_x_channel', enable_events=True),
             sg.Text(' Y: '), sg.Combo(self.output_list, default_value=self.output_list[2] if len(self.output_list) >= 2 else 'None', 
                                            key='left_y_channel', enable_events=True)],
            [sg.Button(' ', disabled=True, button_color='firebrick1'), 
             sg.Text('Right X: '), sg.Combo(self.output_list, default_value=self.output_list[3] if len(self.output_list) >= 3 else 'None', 
                                            key='right_x_channel', enable_events=True),
             sg.Text(' Y: '), sg.Combo(self.output_list, default_value=self.output_list[4] if len(self.output_list) >= 4 else 'None', 
                                            key='right_y_channel', enable_events=True)],
            [sg.Button(' ', disabled=True, button_color='DarkGoldenrod1'), 
             sg.Text('Pupil Left: '), sg.Combo(self.output_list, default_value=self.output_list[5] if len(self.output_list) >= 5 else 'None', 
                                            key='pupil_x_channel', enable_events=True),
             sg.Text(' Right: '), sg.Combo(self.output_list, default_value=self.output_list[6] if len(self.output_list) >= 6 else 'None', 
                                            key='pupil_y_channel', enable_events=True)],
            [sg.Button('Switch Left/Right', key='switch', enable_events=True)]
            ])
        self.layout = [
            [tabs, graph_col]
        ]

    def update_output_channels(self):
        left_x = self.state.output_dict[self.window['left_x_channel'].get()] if self.window['left_x_channel'].get() != 'NONE' else AnalogOutput()
        left_y = self.state.output_dict[self.window['left_y_channel'].get()] if self.window['left_y_channel'].get() != 'NONE' else AnalogOutput()
        left_pupil = self.state.output_dict[self.window['pupil_x_channel'].get()] if self.window['pupil_x_channel'].get() != 'NONE' else AnalogOutput()
        right_x = self.state.output_dict[self.window['right_x_channel'].get()] if self.window['right_x_channel'].get() != 'NONE' else AnalogOutput()
        right_y = self.state.output_dict[self.window['right_y_channel'].get()] if self.window['right_y_channel'].get() != 'NONE' else AnalogOutput()
        right_pupil = self.state.output_dict[self.window['pupil_y_channel'].get()] if self.window['pupil_y_channel'].get() != 'NONE' else AnalogOutput()
        self.state.left_output = AnalogOutputPair(left_x, left_y)
        self.state.right_output = AnalogOutputPair(right_x, right_y)
        self.state.pupil_output = AnalogOutputPair(left_pupil, right_pupil)
        
    def update_graph(self):
        self.graph.erase()
        # draw axes
        self.graph.draw_line((-5,0), (5,0))
        self.graph.draw_line((0,-5), (0,5))
        for xy in range(-5, 6):
            self.graph.draw_line((xy,-0.1), (xy,0.1))
            self.graph.draw_line((-0.1,xy), (0.1,xy))

        self.graph.draw_point((self.state.right_output.v_out.x, self.state.right_output.v_out.y), size=.15, color='firebrick1')
        self.graph.draw_point((self.state.left_output.v_out.x, self.state.left_output.v_out.y), size=.15, color='DodgerBlue')
        self.graph.draw_point((self.state.pupil_output.v_out.x, self.state.pupil_output.v_out.y), size=.15, color='DarkGoldenrod1')

    def window_loop(self, verbose=False):
        
        self.window = sg.Window('OpenIrisClient', self.layout)
        first = True
        while True:
            event, values = self.window.read(timeout=20) # 20ms = 50Hz
            if first:
                self.update_output_channels()
                first = False
            if verbose:
                print(event, values)

            # handle exit
            if event == sg.WIN_CLOSED or event == 'Close':
                self.state.is_running = False
                break
            
            # Update left method
            if event in ['left_dpi', 'left_pcr']:
                if values['left_dpi']:
                    self.state.left_method = 'dpi'
                elif values['left_pcr']:
                    self.state.left_method = 'pcr'
                else:
                    self.state.left_method = 'dpi'
            
            # Update right method
            if event in ['right_dpi', 'right_pcr']:
                if values['right_dpi']:
                    self.state.right_method = 'dpi'
                elif values['right_pcr']:
                    self.state.right_method = 'pcr'
                else:
                    self.state.right_method = 'dpi'

            # Update states
            if event == 'left_x_bias':
                self.state.left_cal.x_bias = values[event]
            if event == 'left_y_bias':
                self.state.left_cal.y_bias = values[event]
            if event == 'left_x_gain' or event == 'left_flip_x':
                self.state.left_cal.x_gain = values['left_x_gain']/self.gain_factor * (-1 if values['left_flip_x'] else 1)
            if event == 'left_y_gain' or event == 'left_flip_y':
                self.state.left_cal.y_gain = values['left_y_gain']/self.gain_factor * (-1 if values['left_flip_y'] else 1)
            if event == 'left_rotation':
                self.state.left_cal.rotation = values[event]
            if event == 'right_x_bias':
                self.state.right_cal.x_bias = values[event]
            if event == 'right_y_bias':
                self.state.right_cal.y_bias = values[event]
            if event == 'right_x_gain' or event == 'right_flip_x':
                self.state.right_cal.x_gain = values['right_x_gain']/self.gain_factor * (-1 if values['right_flip_x'] else 1)
            if event == 'right_y_gain' or event == 'right_flip_y':
                self.state.right_cal.y_gain = values['right_y_gain']/self.gain_factor * (-1 if values['right_flip_y'] else 1)
            if event == 'right_rotation':
                self.state.right_cal.rotation = values[event]
            if event == 'left_pupil_bias':
                self.state.pupil_cal.x_bias = values[event]
            if event == 'right_pupil_bias':
                self.state.pupil_cal.y_bias = values[event]
            if event == 'left_pupil_gain':
                self.state.pupil_cal.x_gain = values[event]/self.pupil_factor
            if event == 'right_pupil_gain':
                self.state.pupil_cal.y_gain = values[event]/self.pupil_factor

            # Update output channels
            if event in ['left_x_channel', 'left_y_channel', 'right_x_channel', 'right_y_channel', 'pupil_x_channel', 'pupil_y_channel']:
                self.update_output_channels()

            # Switch left and right
            if event == 'switch':
                temp = self.state.left_output
                self.state.left_output = self.state.right_output
                self.state.right_output = temp

                temp = self.window['right_x_channel'].get()
                self.window['right_x_channel'].update(value=self.window['left_x_channel'].get())
                self.window['left_x_channel'].update(value=temp)

                temp = self.window['right_y_channel'].get()
                self.window['right_y_channel'].update(value=self.window['left_y_channel'].get())
                self.window['left_y_channel'].update(value=temp)

            # update graph and errors on timeout (refresh)
            if event == sg.TIMEOUT_EVENT:
                self.update_graph()

                # Get eye data
                error = self.state.last_eyes_data.get_error(left_p4=self.state.left_method=='dpi', right_p4=self.state.right_method=='dpi')
                if error:
                    self.window['error'].update(value = error, text_color='red')
                else:
                    self.window['error'].update(value = 'Tracking', text_color='lawn green')
                

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self.window:
            self.window.close()
        
        self.state.is_running = False

        if exc_type:
            print(exc_type, exc_value, traceback)
            return False
        return True

    def run(self, verbose=False):
        with self as gui:
            while self.state.is_running:
                gui.window_loop(verbose)

class DataPipeline:
    def __init__(self, state:GlobalState, server_address='localhost', port=9003):
        self.state = state
        self.server_address = server_address
        self.port = port

    def run(self, debug=False):
        with OpenIrisClient(self.server_address, self.port) as client:
            while self.state.is_running:
                data = client.fetch_next_data(True)
                self.state.last_eyes_data = data

                left_output = data.left.cr - (data.left.pupil if self.state.left_method == 'pcr' else data.left.p4)
                left_output = self.state.left_cal.transform(left_output)
                self.state.left_output.write(left_output)
                
                right_output = data.right.cr - (data.right.pupil if self.state.right_method == 'pcr' else data.right.p4)
                right_output = self.state.right_cal.transform(right_output)
                self.state.right_output.write(right_output)

                pupil_output = Point(data.left.pupil_area, data.right.pupil_area)
                pupil_output = self.state.pupil_cal.transform(pupil_output)
                self.state.pupil_output.write(pupil_output)
                if debug:
                    print(data)
                    print(f'{left_output}, {right_output}, {pupil_output}')

                

if __name__ == "__main__":
    from threading import Thread

    # with GUI() as gui:
    #     gui.window_loop(open_iris_ip='localhost', verbose=False)
    gs = GlobalState()
    gui_thread = Thread(target=GUI(gs).window_loop, args=(False,))
    gui_thread.start()
    dp_thread = Thread(target=DataPipeline(gs).run, args=(False,))
    dp_thread.start()
    dp_thread.join()
    gui_thread.join()
    gs.save()
    print('Done')
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
            cals_dir = Path(__file__).parent / 'cals'
            if not cals_dir.exists():
                cals_dir.mkdir()
            save_dir = Path(__file__).parent / 'cals' / '.state'

        self.save_dir = save_dir
        if not self.save_dir.exists():
            self.save_dir.mkdir()

        self.left_cal = CalibrationParameters(-60,180,-.013,.013,0)
        self.left_method = 'dpi'
        self.left_output = AnalogOutputPair()

        self.right_cal = CalibrationParameters(80,180,-.013,.013,0)
        self.right_method = 'dpi'
        self.right_output = AnalogOutputPair()

        self.pupil_cal = CalibrationParameters(0,0,3e-5,3e-5,0)
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

    def save(self, path:Path = None):
        if path is None:
            path = self.save_dir

        if not path.exists():
            path.mkdir()
        # save calibrations
        self.left_cal.save(path / 'left_cal.txt')
        self.right_cal.save(path / 'right_cal.txt')
        self.pupil_cal.save(path / 'pupil_cal.txt')
        # save methods
        with open(path / 'methods.txt', 'w') as f:
            f.write(f'{self.left_method},{self.right_method}')
    
    def load(self, path:Path = None):
        if path is None:
            path = self.save_dir

        if not path.exists():
            print('No save directory found.')
            return
        # load calibrations
        try:
            self.left_cal.load(path / 'left_cal.txt')
            self.right_cal.load(path / 'right_cal.txt')
            self.pupil_cal.load(path / 'pupil_cal.txt')
        except:
            print('Error loading calibration files.')
        # load methods
        try:
            with open(path / 'methods.txt', 'r') as f:
                self.left_method, self.right_method = f.read().split(',')
            if self.left_method not in ['dpi', 'pcr']:
                self.left_method = 'dpi'
            if self.right_method not in ['dpi', 'pcr']:
                self.right_method = 'dpi'
        except:
            self.left_method = 'dpi'
            self.right_method = 'dpi'

from typing import Callable
class GUIField:
    def __init__(self, title:str, key:str, size:tuple, obj:object, field:str, gain_factor:float=1, increment:float=1, multiplicative:bool=False,
                slider_enabled:bool=False, slider_minimum:float=-100, slider_maximum:float=100, slider_resolution:float=1, 
                flip_enabled:bool=False):
        self.title = title
        self.key = key
        self.size = size
        self.object = obj
        self.field = field
        self.default_value = getattr(obj, field) / gain_factor
        self.setter = lambda x: setattr(obj, field, x)
        self.getter = lambda : getattr(obj, field)
        self.gain_factor = gain_factor
        self.increment = increment
        self.multiplicative = multiplicative
        self.slider_enabled = slider_enabled
        self.slider_minimum = slider_minimum
        self.slider_maximum = slider_maximum
        self.slider_resolution = slider_resolution
        self.flip_enabled = flip_enabled
        if self.flip_enabled:
            self.flip_default = self.default_value < 0
            self.default_value = abs(self.default_value)

    def get_layout(self):
        layout = []
        layout.append([sg.Text(self.title)] + ([sg.Checkbox('Flip', key=self.key+'_flip', default=self.flip_default, enable_events=True)] if self.flip_enabled else []))
        layout.append([
                        sg.Button('<', key=self.key+'_dec', enable_events=True, s=(2, self.size[1])), 
                        sg.InputText(default_text=self.default_value, s=(self.size[0], self.size[1]), key=self.key+'_input', enable_events=True),
                        sg.Button('>', key=self.key+'_inc', enable_events=True, s=(2, self.size[1]))
                    ])
        if self.slider_enabled:
            layout.append([sg.Slider((self.slider_minimum, self.slider_maximum), orientation='h', s=(self.size[0]-1, 15), disable_number_display=True,
                        default_value=self.default_value, resolution=self.slider_resolution, key=self.key+'_slider', enable_events=True)])
        layout.append([sg.HSeparator()])

        return sg.Column(layout)
    
    def sync_state(self, window):
        state = self.getter()
        if self.flip_enabled:
            sign = state < 0
            window[self.key+'_flip'].update(value=sign)
            state = abs(state)
        
        old_input = window[self.key+'_input'].get()
        new_input = str(state/self.gain_factor)
        if old_input != new_input:
            window[self.key+'_input'].update(value=f'{state/self.gain_factor:g}')
        if self.slider_enabled:
            old_slider = window[self.key+'_slider'].widget.get()
            new_slider = state/self.gain_factor
            if old_slider != new_slider:
                window[self.key+'_slider'].update(value=state/self.gain_factor)
        
    def update(self, window, event:str, values:dict):
        if self.key in event:
            flip = (1 - values[self.key+'_flip'] * 2) if self.flip_enabled else 1
            if event == self.key+'_input':
                try:
                    self.setter(float(values[event]) * self.gain_factor * flip)
                except:
                    pass
            if event == self.key+'_inc':
                if self.multiplicative:
                    self.setter(self.getter() * (1+self.increment))
                else:
                    self.setter(self.getter() + self.increment * self.gain_factor * flip)
            if event == self.key+'_dec':
                if self.multiplicative:
                    self.setter(self.getter() * (1-self.increment))
                else:
                    self.setter(self.getter() - self.increment * self.gain_factor * flip)
            if event == self.key+'_slider':
                self.setter(values[event] * self.gain_factor * flip)
            if event == self.key+'_flip':
                self.setter(self.getter() * -1)
            self.sync_state(window)

class GUI:
    def __init__(self, state:GlobalState) -> None:
        self.state = state

        menu_def = [['File', ['Save Config', 'Load Config', 'Exit']]]

        def make_column(title, key, size, resolution, default_value, minimum, maximum, append=[]):
            return sg.Column([
                [sg.Text(title)], 
                [sg.Slider((minimum,maximum), default_value=default_value, s=size, resolution=resolution, k=key, enable_events=True)],
                append
                ])
        
        field_size = (40,1)
        self.bias_factor = 5e0
        self.gain_factor = 1.3e-4
        b_min = -100
        b_max = 100
        b_res = .2
        g_min = 0
        g_max = 500
        g_res = .5
        self.lbx = GUIField(
            'X Bias', 'left_x_bias', field_size,
            self.state.left_cal, 'x_bias', gain_factor=self.bias_factor,
            increment=.5, multiplicative=False,
            slider_enabled=True, slider_minimum=b_min, slider_maximum=b_max, slider_resolution=b_res
            )
        self.lby = GUIField(
            'Y Bias', 'left_y_bias', field_size,
            self.state.left_cal, 'y_bias', gain_factor=self.bias_factor,
            increment=.5, multiplicative=False,
            slider_enabled=True, slider_minimum=b_min, slider_maximum=b_max, slider_resolution=b_res
            )
        self.lgx = GUIField(
            'X Gain', 'left_x_gain', field_size,
            self.state.left_cal, 'x_gain', gain_factor=self.gain_factor,
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )
        self.lgy = GUIField(
            'Y Gain', 'left_y_gain', field_size,
            self.state.left_cal, 'y_gain', gain_factor=self.gain_factor,
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )
        self.lr = GUIField(
            'Rotation', 'left_rotation', field_size,
            self.state.left_cal, 'rotation', gain_factor=1,
            increment=1, multiplicative=False,
            slider_enabled=True, slider_minimum=-180, slider_maximum=180, slider_resolution=1
            )
        lt = sg.Tab('Left Eye', [
            [self.lbx.get_layout()],
            [self.lby.get_layout()],
            [self.lgx.get_layout()],
            [self.lgy.get_layout()],
            [self.lr.get_layout()],
            [sg.VPush()],
            [sg.Text('Method: '),
                sg.Radio('DPI (P1-P4)', 'left_method', key='left_dpi', default=self.state.left_method=='dpi', enable_events=True), 
                sg.Radio('PCR (P1-Pupil)', 'left_method', key='left_pcr', default=self.state.left_method=='pcr', enable_events=True)
            ]])
        
        self.rbx = GUIField(
            'X Bias', 'right_x_bias', field_size,
            self.state.right_cal, 'x_bias', gain_factor=self.bias_factor,
            increment=1, multiplicative=False,
            slider_enabled=True, slider_minimum=b_min, slider_maximum=b_max, slider_resolution=b_res
            )
        self.rby = GUIField(
            'Y Bias', 'right_y_bias', field_size,
            self.state.right_cal, 'y_bias', gain_factor=self.bias_factor,
            increment=1, multiplicative=False,
            slider_enabled=True, slider_minimum=b_min, slider_maximum=b_max, slider_resolution=b_res
            )
        self.rgx = GUIField(
            'X Gain', 'right_x_gain', field_size,
            self.state.right_cal, 'x_gain', gain_factor=self.gain_factor,
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )
        self.rgy = GUIField(
            'Y Gain', 'right_y_gain', field_size,
            self.state.right_cal, 'y_gain', gain_factor=self.gain_factor,
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )
        self.rr = GUIField(
            'Rotation', 'right_rotation', field_size,
            self.state.right_cal, 'rotation', gain_factor=1,
            increment=1, multiplicative=False,
            slider_enabled=True, slider_minimum=-180, slider_maximum=180, slider_resolution=1
            )
        rt = sg.Tab('Right Eye', [
            [self.rbx.get_layout()],
            [self.rby.get_layout()],
            [self.rgx.get_layout()],
            [self.rgy.get_layout()],
            [self.rr.get_layout()],
            [sg.VPush()],
            [sg.Text('Method: '),
                sg.Radio('DPI (P1-P4)', 'right_method', key='right_dpi', default=self.state.right_method=='dpi', enable_events=True), 
                sg.Radio('PCR (P1-Pupil)', 'right_method', key='right_pcr', default=self.state.right_method=='pcr', enable_events=True)
            ]])
        
        
        self.pupil_bias_factor = 3e3
        self.pupil_gain_factor = 3e-7
        self.plb = GUIField(
            'Left Pupil Bias', 'left_pupil_bias', field_size, 
            self.state.pupil_cal, 'x_bias', gain_factor=self.pupil_bias_factor, 
            increment=1, multiplicative=False
            )
        self.prb = GUIField(
            'Right Pupil Bias', 'right_pupil_bias', field_size, 
            self.state.pupil_cal, 'y_bias', gain_factor=self.pupil_bias_factor,
            increment=1, multiplicative=False
            )
        self.plg = GUIField(
            'Left Pupil Gain', 'left_pupil_gain', field_size, 
            self.state.pupil_cal, 'x_gain', gain_factor=self.pupil_gain_factor, 
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )
        self.prg = GUIField(
            'Right Pupil Gain', 'right_pupil_gain', field_size, 
            self.state.pupil_cal, 'y_gain', gain_factor=self.pupil_gain_factor,
            increment=0.05, multiplicative=True, flip_enabled=True,
            slider_enabled=True, slider_minimum=g_min, slider_maximum=g_max, slider_resolution=g_res
            )

        pt = sg.Tab('Pupil', [
            [self.plb.get_layout()],
            [self.prb.get_layout()],
            [self.plg.get_layout()],
            [self.prg.get_layout()],
            [sg.VPush()],
            ])
        
        tabs = sg.TabGroup([[lt, rt, pt]], key='tabs', expand_y=True)
        
        self.graph = sg.Graph(canvas_size=(400,400), graph_bottom_left=(-5.1,-5.1), graph_top_right=(5.1,5.1), background_color='grey', key='graph')

        self.output_list = list(self.state.output_dict.keys())
        self.output_list.insert(0, 'None')
        graph_col = sg.Column([
            [sg.Text('', key='error', size=(20,1), text_color='red')],
            [self.graph],
            [sg.Text('Channels: '),],
            [sg.Button(' Zero ', key='left_zero', enable_events=True, button_color='DodgerBlue'), 
             sg.Text('Left X: '), sg.Combo(self.output_list, default_value=self.output_list[1] if len(self.output_list) > 1 else 'None', 
                                           key='left_x_channel', enable_events=True),
             sg.Text(' Y: '), sg.Combo(self.output_list, default_value=self.output_list[2] if len(self.output_list) > 2 else 'None', 
                                            key='left_y_channel', enable_events=True)],
            [sg.Button(' Zero ', key='right_zero', enable_events=True, button_color='firebrick1'), 
             sg.Text('Right X: '), sg.Combo(self.output_list, default_value=self.output_list[3] if len(self.output_list) > 3 else 'None', 
                                            key='right_x_channel', enable_events=True),
             sg.Text(' Y: '), sg.Combo(self.output_list, default_value=self.output_list[4] if len(self.output_list) > 4 else 'None', 
                                            key='right_y_channel', enable_events=True)],
            [sg.Button(' ', disabled=True, button_color='DarkGoldenrod1'), 
             sg.Text('Pupil Left: '), sg.Combo(self.output_list, default_value=self.output_list[5] if len(self.output_list) > 5 else 'None', 
                                            key='pupil_x_channel', enable_events=True),
             sg.Text(' Right: '), sg.Combo(self.output_list, default_value=self.output_list[6] if len(self.output_list) > 6 else 'None', 
                                            key='pupil_y_channel', enable_events=True)],
            [sg.Button('Switch Left/Right', key='switch', enable_events=True)]
            ])
        self.layout = [
            [sg.Menu(menu_def)],
            [tabs, graph_col]
        ]

    def update_sliders(self):
        self.lbx.sync_state(self.window)
        self.lby.sync_state(self.window)
        self.lgx.sync_state(self.window)
        self.lgy.sync_state(self.window)
        self.lr.sync_state(self.window)
        self.rbx.sync_state(self.window)
        self.rby.sync_state(self.window)
        self.rgx.sync_state(self.window)
        self.rgy.sync_state(self.window)
        self.rr.sync_state(self.window)
        self.plb.sync_state(self.window)
        self.prb.sync_state(self.window)
        self.plg.sync_state(self.window)
        self.prg.sync_state(self.window)

    def update_output_channels(self):
        left_x = self.state.output_dict[self.window['left_x_channel'].get()] if self.window['left_x_channel'].get() != 'None' else AnalogOutput()
        left_y = self.state.output_dict[self.window['left_y_channel'].get()] if self.window['left_y_channel'].get() != 'None' else AnalogOutput()
        left_pupil = self.state.output_dict[self.window['pupil_x_channel'].get()] if self.window['pupil_x_channel'].get() != 'None' else AnalogOutput()
        right_x = self.state.output_dict[self.window['right_x_channel'].get()] if self.window['right_x_channel'].get() != 'None' else AnalogOutput()
        right_y = self.state.output_dict[self.window['right_y_channel'].get()] if self.window['right_y_channel'].get() != 'None' else AnalogOutput()
        right_pupil = self.state.output_dict[self.window['pupil_y_channel'].get()] if self.window['pupil_y_channel'].get() != 'None' else AnalogOutput()
        self.state.left_output = AnalogOutputPair(left_x, left_y)
        self.state.right_output = AnalogOutputPair(right_x, right_y)
        self.state.pupil_output = AnalogOutputPair(left_pupil, right_pupil)
        
    def update_graph(self):
        self.graph.erase()
        # draw axes
        self.graph.draw_line((-5,0), (5,0))
        self.graph.draw_line((0,-5), (0,5))
        self.graph.draw_line((-5,-5), (-5,5))
        self.graph.draw_line((-5,5), (5,5))
        self.graph.draw_line((5,5),(5,-5))
        self.graph.draw_line((5,-5),(-5,-5))
        self.graph.draw_text('5V', (0.3,4.7), color='black')
        self.graph.draw_text('5V', (4.7,0.3), color='black')
        self.graph.draw_text('-5V', (-0.4,-4.7), color='black')
        self.graph.draw_text('-5V', (-4.6,-0.3), color='black')
        
        for xy in range(-5, 6):
            self.graph.draw_line((xy,-0.1), (xy,0.1))
            self.graph.draw_line((-0.1,xy), (0.1,xy))
        
        clip = lambda x: min(max(x, -5), 5)
        rx = clip(self.state.right_output.v_out.x)
        ry = clip(self.state.right_output.v_out.y)
        lx = clip(self.state.left_output.v_out.x) 
        ly = clip(self.state.left_output.v_out.y)
        px = clip(self.state.pupil_output.v_out.x) 
        py = clip(self.state.pupil_output.v_out.y)
        self.graph.draw_point((rx, ry), size=.15, color='firebrick1')
        self.graph.draw_point((lx, ly), size=.15, color='DodgerBlue')
        self.graph.draw_point((px, py), size=.15, color='DarkGoldenrod1')
        
        int0 = self.state.last_eyes_data.extra.ints[0] & 1
        int1 = self.state.last_eyes_data.extra.ints[1] & 1
        self.graph.draw_point((4.3, -4.7), size=.30, color='spring green' if int0 else 'red')
        self.graph.draw_point((4.7, -4.7), size=.30, color='spring green' if int1 else 'red')

    def window_loop(self, verbose=False):
        
        self.window = sg.Window('OpenIrisClient', self.layout)
        first = True
        while self.state.is_running:
            event, values = self.window.read(timeout=20) # 20ms = 50Hz
            # if event != '__TIMEOUT__':
            #     print(event, values)
            if first:
                self.update_output_channels()
                first = False
            if verbose and event != sg.TIMEOUT_EVENT:
                print(event, values)

            # handle exit
            if event == sg.WIN_CLOSED or event == 'Close' or event == 'Exit':
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
            self.rbx.update(self.window, event, values)
            self.rby.update(self.window, event, values)
            self.rgx.update(self.window, event, values)
            self.rgy.update(self.window, event, values)
            self.rr.update(self.window, event, values)
            self.lbx.update(self.window, event, values)
            self.lby.update(self.window, event, values)
            self.lgx.update(self.window, event, values)
            self.lgy.update(self.window, event, values)
            self.lr.update(self.window, event, values)
            self.plb.update(self.window, event, values)
            self.prb.update(self.window, event, values)
            self.plg.update(self.window, event, values)
            self.prg.update(self.window, event, values)

            # Update output channels
            if event in ['left_x_channel', 'left_y_channel', 'right_x_channel', 'right_y_channel', 'pupil_x_channel', 'pupil_y_channel']:
                self.update_output_channels()

            # Zero left
            if event == 'left_zero':
                last_left = self.state.last_eyes_data.left.cr - \
                    (self.state.last_eyes_data.left.pupil if self.state.left_method == 'pcr' else self.state.last_eyes_data.left.p4)
                print(last_left)
                self.state.left_cal.x_bias = -last_left.x
                self.state.left_cal.y_bias = -last_left.y
                print(self.state.left_cal.x_bias, self.state.left_cal.y_bias)
                print(self.state.left_cal.transform(last_left))
                self.lbx.sync_state(self.window)
                self.lby.sync_state(self.window)
            
            
            # Zero right
            if event == 'right_zero':
                last_right = self.state.last_eyes_data.right.cr - \
                    (self.state.last_eyes_data.right.pupil if self.state.right_method == 'pcr' else self.state.last_eyes_data.right.p4)
                self.state.right_cal.x_bias = -last_right.x
                self.state.right_cal.y_bias = -last_right.y
                self.rbx.sync_state(self.window)
                self.rby.sync_state(self.window)

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

            # Save config
            if event == 'Save Config':
                # Open a dialog to select a new file
                save_dir = sg.popup_get_folder('Select save directory', default_path=self.state.save_dir)
                self.state.save(Path(save_dir))

            # Load config
            if event == 'Load Config':
                # Open a folder picking dialog
                load_dir = sg.popup_get_folder('Select directory to load', default_path=self.state.save_dir)
                if load_dir:
                    self.state.load(Path(load_dir))
                    self.update_sliders()

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
            gui.window_loop(verbose)

class DataPipeline:
    def __init__(self, state:GlobalState, server_address='localhost', port=9003):
        self.state = state
        self.server_address = server_address
        self.port = port

    def run(self, debug=False):
        with OpenIrisClient(self.server_address, self.port) as client:
            while self.state.is_running:
                data = client.fetch_next_data(debug)
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
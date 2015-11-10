#!/usr/bin/env python
'''
LED command handling module

Copyright Goro Senzai 2015

'''

import time, os, struct
current_time_in_milisec = lambda: int(round(time.time() * 1000))
import pygame.midi
import pygame.event
from pymavlink import mavutil
from MAVProxy.modules.lib import mp_module

class LEDModule(mp_module.MPModule):
    def __init__(self, mpstate):
        super(LEDModule, self).__init__(mpstate, "led", "led command handling", public = True)
        self.color = [ 0x0 ] * 3
        self.last_color = [ 0 ] * 3
        self.override_counter = 0
        self.instance_id = 0xff
        #  self.pattern_id = 0 # off
        #  self.pattern_id = 2 # solid
        self.pattern_id = 6 # fadeout
        self.add_command('led', self.cmd_led, "LED Set Color", ['RGB color in hex', 'mode <solid|fadeout>'])
        self.add_command('ledoff', self.cmd_led_off, "Turn Off LED Override", [''])
        self.override_period = mavutil.periodic_event(1)
        self.note_count = 0
        self.brightness_factor = 1.5

        pygame.init()
        time.sleep(0.2)
        pygame.midi.init()

        self.input_id = pygame.midi.get_default_input_id()
        print 'input_id', self.input_id
        print pygame.midi.get_device_info(self.input_id)
        if self.input_id >= 0:
            self.midiin = pygame.midi.Input(self.input_id,0)

    def idle_task(self):
        # This is an incomplete listing:
        COMMANDS = {    0: "NOTE_OFF",
                        1: "NOTE_ON",
                        2: "KEY_AFTER_TOUCH",
                        3: "CONTROLLER_CHANGE",
                        4: "PROGRAM_CHANGE",
                        5: "CHANNEL_AFTER_TOUCH",
                        6: "PITCH_BEND" }

        # Incomplete listing: this is the key to CONTROLLER_CHANGE events data1
        CONTROLLER_CHANGES = {  1: "MOD WHEEL",
                                2: "BREATH",
                                4: "FOOT",
                                5: "PORTAMENTO",
                                6: "DATA",
                                7: "VOLUME",
                                10: "PAN" }

        if (self.midiin.poll()):
            midi_events = self.midiin.read(10)
            for midi in midi_events:
                ((status,data1,data2,data3),timestamp) = midi
                if status == 0xFF:
                    # pygame doesn't seem to get these, so I didn't decode
                    command =  "META"
                    channel = None
                else:
                    try:
                        command = COMMANDS[ (status & 0x70) >> 4]
                    except:
                        command = status & 0x70
                    channel = status & 0x0F

                if command == "NOTE_ON":
                    note_number = data1
                    velocity = data2
                    if data2 == 0:
                        # velocity == 0 -> NOTE_OFF
                        self.note_count -= 1
                        if self.pattern_id == 2:
                            # only send note off when pattern == solid
                            #  print("NOTE_OFF: %u" % note_number)
                            channels = [ 0x0 ] * 3
                            self.set_override(channels)
                    else:
                        self.note_count += 1
                        # igoner quiet notes
                        if velocity > 32:
                            channels = self.color
                            # Each channel defaults to velocity (0-127) * 2 = 0-254
                            channels = [ velocity * 2 ] * 3
                            # Psudo-randomly select channels to dim down
                            select1 = self.note_count % 3
                            select2 = note_number % 3
                            select3 = velocity % 3
                            # Higher notes have a small precedence over lower notes
                            channels[select1] = velocity / self.brightness_factor + note_number / self.brightness_factor
                            channels[select2] = velocity / self.brightness_factor + note_number / self.brightness_factor
                            channels[select3] = velocity / self.brightness_factor + note_number / self.brightness_factor
                            self.set_override(channels)

    def send_led_override(self):
        '''send LED color override packet'''
        self.master.mav.led_set_colour_send(self.target_system,
                                            self.target_component,
                                            self.instance_id,
                                            self.color[0],
                                            self.color[1],
                                            self.color[2],
                                            self.pattern_id)

    def cmd_led_off(self, args):
        '''handle Turning LED Override Off (Return LED to normal status indicator mode)'''
        self.pattern_id = 0 # off
        self.color = [ 0x0 ] * 3
        self.master.mav.led_set_colour_send(self.target_system,
                                            self.target_component,
                                            self.instance_id,
                                            self.color[0],
                                            self.color[1],
                                            self.color[2],
                                            0)

    def set_override(self, newchannels):
        '''this is a public method for use by drone API or other scripting'''
        self.color = newchannels
        self.override_counter = 10
        self.send_led_override()

    def cmd_led(self, args):
        '''handle LED color value override'''
        if len(args) < 1 or len(args) > 2:
            print("Usage: led RRGGBB (hex value) mode <solid|fadeout>")
            return

        value = int(args[0], 16)
        if value > 0xffffff or value < -1:
            raise ValueError("Color value must be a positive integer between 0x000000 and 0xffffff")

        channels = self.color
        channels[0] = (value & 0xFF0000) >> 16
        channels[1] = (value & 0x00FF00) >> 8 
        channels[2] = (value & 0x0000FF)
        print("setting colors: %u %u %u\n") % (channels[0],channels[1],channels[2])

        if (len(args) == 2 and (args[1] == "fadeout" or args[1] == "fade" or args[1] == "fo")):
            self.pattern_id = 6 # fadeout
        else:
            # solid & default behavior
            self.pattern_id = 2 # solid

        self.set_override(channels)

def init(mpstate):
    '''initialise module'''
    return LEDModule(mpstate)


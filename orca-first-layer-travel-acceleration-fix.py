#!/usr/bin/python
import argparse
import math
from enum import Enum
import re
import os
from typing import List


class Line:
    def __init__(self, xy1: tuple, xy2: tuple):
        self.x1 = xy1[0]
        self.y1 = xy1[1]
        self.x2 = xy2[0]
        self.y2 = xy2[1]
        self._length = None

    def length(self):
        if self._length is None:
            self._length = math.hypot(self.x2 - self.x1, self.y2 - self.y1)
        return self._length

    def __str__(self):
        return f'X1:{self.x1} Y1:{self.y1} X2:{self.x2} Y2:{self.y2}'


class Parameter:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return f"{self.name}{self.value}"

    def clone(self):
        return Parameter(self.name, self.value)


class State:
    def __init__(self, x=None, y=None, z=None, e=None, f=None,
                 extr_temp=None, bed_temp=None, fan=None, move_absolute=True,
                 extrude_absolute=True, is_outer_perimeter=False):
        self.X = x
        self.Y = y
        self.Z = z
        self.E = e
        self.F = f
        self.ExtruderTemperature = extr_temp
        self.BedTemperature = bed_temp
        self.Fan = fan
        self.move_is_absolute = move_absolute
        self.extrude_is_absolute = extrude_absolute
        self.is_outer_perimeter = is_outer_perimeter

    def clone(self):
        return State(self.X, self.Y, self.Z, self.E, self.F,
                     self.ExtruderTemperature, self.BedTemperature, self.Fan,
                     self.move_is_absolute, self.extrude_is_absolute, self.is_outer_perimeter)


class Gcode:
    def __init__(self, command: str = None, parameters: List[Parameter] = None,
                 move_is_absolute: bool = True, extrude_is_absolute: bool = True,
                 comment: str = None, previous_state: State = None):
        self.command = command
        if parameters is None:
            self.parameters = []
        else:
            self.parameters = parameters
        self.move_is_absolute = move_is_absolute
        self.extrude_is_absolute = extrude_is_absolute
        self.comment = comment
        self.previous_state = previous_state
        self.num_line = None

    @staticmethod
    def _format_number(number: int, precision: int) -> str:
        value = round(number, precision)
        value = format(value, '.' + str(precision) + 'f')
        value = value.rstrip('0').rstrip('.')
        if value.startswith('0.'):
            value = value[1:]
        elif value.startswith('-0.'):
            value = '-' + value[2:]
        return value

    def __str__(self):
        string = ""
        if self.command is not None:
            string += self.command
            for st in self.parameters:
                if st.value is None:
                    string += f' {st.name}'
                else:
                    if st.name == "X" or st.name == "Y" or st.name == "Z":
                        string += f' {st.name}{Gcode._format_number(st.value, 3)}'
                    elif st.name == "E":
                        # 1 micron is for sure enough accuracy for extrude move
                        string += f' {st.name}{Gcode._format_number(st.value, 3)}'
                        if self.is_xy_movement() is False:
                            comment = None
                            if st.value < 0:
                                comment = "retract"
                            elif st.value > 0:
                                comment = "un_retract"

                            if self.comment is None:
                                self.comment = comment
                            else:
                                self.comment += f" {comment}"
                    else:
                        string += f' {st.name}{st.value}'

        if self.comment is not None and len(self.comment) > 1:
            if string == "":
                string += f"; {self.comment}"
            else:
                string += f" ; {self.comment}"
        return string

    def clone(self):
        if self.previous_state is None:
            prev_state = State()
        else:
            prev_state = self.previous_state.clone()
        gcode = Gcode(self.command,
                      move_is_absolute=self.move_is_absolute, extrude_is_absolute=self.extrude_is_absolute,
                      comment=self.comment, previous_state=prev_state)
        for param in self.parameters:
            gcode.parameters.append(param.clone())

        if self.num_line is not None:
            gcode.num_line = self.num_line
        return gcode

    def state(self) -> State:
        if self.previous_state is None:
            _state = State()
            _state.X = 0
            _state.Y = 0
            _state.Z = 0
            _state.E = 0
        else:
            _state = self.previous_state.clone()

        _state.is_outer_perimeter = self.is_outer_perimeter()

        if self.command == "G1":
            for parameter in self.parameters:
                if parameter.name == "X":
                    if _state.move_is_absolute:
                        _state.X = parameter.value
                    else:
                        _state.X += parameter.value
                elif parameter.name == "Y":
                    if _state.move_is_absolute:
                        _state.Y = parameter.value
                    else:
                        _state.Y += parameter.value
                elif parameter.name == "Z":
                    if _state.move_is_absolute:
                        _state.Z = parameter.value
                    else:
                        _state.Z += parameter.value
                elif parameter.name == "E":
                    if _state.extrude_is_absolute:
                        _state.E = parameter.value
                    else:
                        _state.E += parameter.value
                elif parameter.name == "F":
                    _state.F = parameter.value
        elif self.command == "G28":
            restore_all = True
            for parameter in self.parameters:
                if parameter.name == "X":
                    _state.X = 0
                    restore_all = False
                elif parameter.name == "Y":
                    _state.Y = 0
                    restore_all = False
                elif parameter.name == "Z":
                    _state.Z = 0
                    restore_all = False
            if restore_all:
                _state.X = 0
                _state.Y = 0
                _state.Z = 0
                _state.E = 0
                _state.F = None
        elif self.command == "M104" or self.command == "M109":
            for parameter in self.parameters:
                if parameter.name == "S":
                    _state.ExtruderTemperature = parameter.value
        elif self.command == "M140" or self.command == "M190":
            for parameter in self.parameters:
                if parameter.name == "S":
                    _state.BedTemperature = parameter.value
        elif self.command == "M106":
            for parameter in self.parameters:
                if parameter.name == "S":
                    _state.Fan = parameter.value
        elif self.command == "G92":  # Set current position
            for parameter in self.parameters:
                if parameter.name == "X":
                    _state.X = parameter.value
                elif parameter.name == "Y":
                    _state.Y = parameter.value
                elif parameter.name == "Z":
                    _state.Z = parameter.value
                elif parameter.name == "E":
                    _state.E = parameter.value

        _state.move_is_absolute = self.move_is_absolute
        _state.extrude_is_absolute = self.extrude_is_absolute
        return _state

    def is_xy_movement(self):
        if self.command != "G1":
            return False
        found_x = next((gc for gc in self.parameters if gc.name ==
                        "X" and gc.value is not None), None)
        found_y = next((gc for gc in self.parameters if gc.name ==
                        "Y" and gc.value is not None), None)
        if found_x is not None or found_y is not None:
            return True
        return False

    def is_z_movement(self):
        if self.command != "G1":
            return False
        found_z = next((gc for gc in self.parameters if gc.name ==
                        "Z" and gc.value is not None), None)
        if found_z is not None:
            return True
        return False

    def is_any_movement(self):
        if self.is_xy_movement() or self.is_z_movement():
            return True
        return False

    def is_extruder_move(self):
        found_e = next((gc for gc in self.parameters if gc.name ==
                        "E" and gc.value is not None), None)
        if found_e is not None and self.command != "G92":
            return True
        return False

    def is_outer_perimeter(self):
        if self.command is not None:
            outer_wall_types = [";TYPE:Outer wall",
                                ";TYPE:WALL-OUTER", ";TYPE:External perimeter"]
            if self.command in outer_wall_types:
                return True
            elif self.command.startswith(";TYPE:"):
                return False

        if self.previous_state is None:
            return False

        return self.previous_state.is_outer_perimeter

    def move_length(self) -> float:
        state = self.state()
        x1 = self.previous_state.X
        y1 = self.previous_state.Y
        x2 = state.X
        y2 = state.Y
        if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
            return distance_between_points(x1, y1, x2, y2)
        return None

    def set_param(self, name, value):
        found = next((gc for gc in self.parameters if gc.name == name), None)
        if found is not None:
            found.value = value
        else:
            self.parameters.append(Parameter(name, value))

    def get_param(self, name):
        found = next((gc for gc in self.parameters if gc.name == name), None)
        if found is not None:
            return found.value


def validate_gcode_command_string(string):
    # The pattern matches a letter followed by a positive number or zero
    pattern = re.compile("^[A-Za-z][0-9]+$")
    # The match method returns None if the string does not match the pattern
    return pattern.match(string) is not None


def create_acceleration_command(flavor: str, accel: int):
    if flavor == "klipper":
        return f"SET_VELOCITY_LIMIT ACCEL={accel}"
    else:
        return f"M204 P{accel}"


def parse_gcode_line(gcode_line: str, prev_state: State) -> Gcode:
    gcode = Gcode()
    if prev_state is not None:
        gcode.previous_state = prev_state.clone()
        gcode.extrude_is_absolute = gcode.previous_state.extrude_is_absolute
        gcode.move_is_absolute = gcode.previous_state.move_is_absolute

    gcode_line = gcode_line.strip()
    if not gcode_line:
        return gcode
    # If contain only comment
    if gcode_line.startswith(";") or gcode_line.startswith("\n"):
        if gcode_line.endswith("\n"):
            gcode_line = gcode_line[:len(gcode_line) - 1]
        gcode.command = gcode_line.replace("\n", "", )
        return gcode

    parts = gcode_line.split(';', 1)
    if len(parts) > 1:
        gcode.comment = parts[1].replace("\n", "").replace(';', "").strip()

    # Split the line at semicolon to remove comments
    gcode_parts = parts[0].strip().split()

    # validate command is one letter and one positive number
    if validate_gcode_command_string(gcode_parts[0]) is False:
        gcode.command = parts[0]
        return gcode

    gcode.command = gcode_parts[0]

    # Iterate through the remaining parts and extract key-value pairs
    for part in gcode_parts[1:]:
        name = part[0]
        value = part[1:]
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError as e:
                # Just keep everything in name
                name = part
                value = None
        parameter = Parameter(name, value)
        gcode.parameters.append(parameter)

    return gcode


class Mode(Enum):
    REGULAR = 0
    PERIMETER = 1
    EXT_PERIMETER = 2
    OVERHANG_PERIMETER = 3
    BR_INFILL = 4
    SOLID_INFILL = 5
    TOP_SOLID_INFILL = 6


def distance_between_points(x1, y1, x2, y2):
    if x2 is None:
        x2 = x1
    if y2 is None:
        y2 = y1
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def delete_file_if_exists(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"The file {file_path} has been deleted.")
    else:
        print(f"The file {file_path} does not exist.")


def read_gcode_file(path: str) -> List[Gcode]:
    gcodes = []
    print("Read gcode file to memory")
    with open(path, "r", encoding='utf8') as readfile:
        lines = readfile.readlines()
        last_state = None
        num_line = 1
        for line in lines:
            gcode = parse_gcode_line(line, last_state)
            if gcode.command == "G90":  # enable absolute coordinates
                gcode.move_is_absolute = True
            elif gcode.command == "G91":  # enable relative coordinates
                gcode.move_is_absolute = False
            elif gcode.command == "M82":  # enable absolute distances for extrusion
                gcode.extrude_is_absolute = True
            elif gcode.command == "M83":  # enable relative distances for extrusion
                gcode.extrude_is_absolute = False
            last_state = gcode.state()
            gcode.num_line = num_line
            num_line += 1

            z_value = gcode.get_param("Z")
            if z_value is not None and z_value > gcode.previous_state.Z:
                gcode.comment = "Z lift"

            gcodes.append(gcode)
    readfile.close()
    return gcodes



def vector_from_points(p1, p2):
    return [p2[0] - p1[0], p2[1] - p1[1]]


def vector_add(v1, v2):
    return [v1[0] + v2[0], v1[1] + v2[1]]


def vector_mul(v, s):
    return [v[0] * s, v[1] * s]


def vector_mag(v):
    return (v[0] ** 2 + v[1] ** 2) ** 0.5


def vector_norm(v):
    m = vector_mag(v)
    return [v[0] / m, v[1] / m]


def convert_to_relative_extrude(gcodes: List[Gcode]):
    gcodes_new = []
    print("Convert gcode to relative extrude moves")

    first_move = next((gc for gc in gcodes if gc.command == "G1"), None)
    first_move_id = gcodes.index(first_move)
    enable_relative_extrude = Gcode(
        command="M83", comment="enable relative extrude mode")
    gcodes.insert(first_move_id, enable_relative_extrude)
    for gcode in gcodes:
        if gcode.command == "M82":  # pass enable absolute mode command
            continue

        gcode_new = gcode.clone()
        gcode_new.extrude_is_absolute = False

        if len(gcodes_new) > 1:
            gcode_new.previous_state = gcodes_new[-1].state()

        if gcode.is_extruder_move():
            if gcode.previous_state.extrude_is_absolute:
                relative_extrude_length = gcode.get_param(
                    "E") - gcode_new.previous_state.E
                gcode_new.set_param("E", relative_extrude_length)
            gcodes_new.append(gcode_new)
        else:
            gcodes_new.append(gcode_new)

    return gcodes_new


def main():
    parser = argparse.ArgumentParser(description='Seam hide post-process')
    parser.add_argument('path', help='the path to the file')
    parser.add_argument('--save_to_file', dest='save_to_file',
                        default=None, type=bool)

    args = parser.parse_args()

    save_to_file = args.save_to_file
    file_path = args.path
    
    travel_acceleration = None
    initial_layer_acceleration = None
    gcode_flavor = None

    with open(file_path, "r", encoding='utf8') as readfile:
        lines = readfile.readlines()
        config_section = False
        for line in lines:
            if line.startswith("; CONFIG_BLOCK_START"):
                config_section = True
            if config_section == False:
                continue
            
            if line.startswith("; travel_acceleration"):
                travel_acceleration = line.split("=")[1].strip()
                travel_acceleration = int(travel_acceleration)
            elif line.startswith("; initial_layer_acceleration"):
                initial_layer_acceleration = line.split("=")[1].strip()
                initial_layer_acceleration = int(initial_layer_acceleration)
            elif line.startswith("; gcode_flavor"):
                gcode_flavor = line.split("=")[1].strip() 


    if travel_acceleration is None or initial_layer_acceleration is None or gcode_flavor is None:
        raise Exception()

    print(f"Read to memory and modify")
    gcode_for_save = []
    layer = 0
    travel_mode = False
    last_state = None
    last_G1_gcode = None
    for line in lines:
        if layer < 2 and line.startswith(";LAYER_CHANGE"):
            layer += 1

        if layer < 2:
            if line.startswith("G1"):
                last_G1_gcode = parse_gcode_line(line, last_state)
                last_state = last_G1_gcode.state()
            else:
                gcode_for_save.append(line)
                continue
    
            if (travel_mode is False
                    and last_G1_gcode.is_extruder_move() is False
                    and last_G1_gcode.is_xy_movement() is True
                    and last_G1_gcode.move_length() > 1):
                travel_mode = True
                travel_accel_gcode = Gcode(
                    command=create_acceleration_command(gcode_flavor, travel_acceleration),
                    comment="travel accel")
                gcode_for_save.append(str(travel_accel_gcode) + "\n")
            elif (travel_mode is True 
                    and last_G1_gcode.is_extruder_move() is True):
                travel_mode = False
                print_accel_gcode = Gcode(
                    command=create_acceleration_command(gcode_flavor, initial_layer_acceleration),
                    comment="print accel")
                gcode_for_save.append(str(print_accel_gcode) + "\n")
            
            gcode_for_save.append(line)

        else:
            if travel_mode:
                travel_mode = False
                print_accel_gcode = Gcode(
                    command=create_acceleration_command(gcode_flavor, initial_layer_acceleration),
                    comment="print accel")
                gcode_for_save.append(str(print_accel_gcode) + "\n")
            gcode_for_save.append(line)


    print(f"Save to file")
    destFilePath = file_path
    if save_to_file is not None:
        save_to_file
        destFilePath = re.sub(r'\.gcode$', '', file_path) + \
                       '_post_processed.gcode'

    delete_file_if_exists(destFilePath)
    with open(destFilePath, "w", encoding='utf-8') as writefile:
            writefile.write("".join(gcode_for_save))
    writefile.close()


if __name__ == '__main__':
    main()

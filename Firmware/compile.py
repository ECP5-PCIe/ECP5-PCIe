#!/bin/python

import sys
import os
from subprocess import call
from shutil import copyfile, rmtree

path = ""
program = False
port = "/dev/ttyUSB1"

if len(sys.argv) <= 1:
    print("Usage: compile.py [-p|-program|program <port>] <filename>.cpp")

for arg in sys.argv:
    if arg.endswith(".cpp") or arg.endswith(".ino"):
        path = arg
    if arg == "program" or arg == "-p" or arg == "-program":
        program = True
    if program:
        port = arg

assert path != ""

if program:
    assert os.path.exists(port)

assert os.path.exists(path)

if not os.path.exists("build/arduino"):
    os.makedirs("build/arduino")
if not os.path.exists("build/arduino-cache"):
    os.makedirs("build/arduino-cache")
if not os.path.exists("build/tmp"):
    os.makedirs("build/tmp")

copyfile(path, "build/tmp/sketch.cpp")

args = [
    "/usr/share/arduino/arduino-builder",
    "-compile",
    "-logger=machine", 
    "-hardware","/usr/share/arduino/hardware",
    "-hardware","/home/user/.arduino15/packages",
    "-hardware","/home/user/Arduino/hardware",
    "-tools","/usr/share/arduino/tools-builder",
    "-tools","/home/user/.arduino15/packages",
    "-libraries","/home/user/Arduino/libraries",
    "-fqbn=arduino:avr:uno",
    "-ide-version=10812",
    "-build-path","build/arduino",
    "-warnings=default",
    "-build-cache","build/arduino-cache",
    "-prefs=build.warn_data_percentage=75",
    "-verbose",
    "build/tmp/sketch.cpp"
]

call(args)

if(program):
    #_, hexpath = os.path.split(path)
    pgmargs = [
        "avrdude",
        "-v",
        "-patmega328p",
        "-carduino",
        "-b115200",
        "-D",
        "-F",
        "-P" + port,
        "-Uflash:w:build/arduino/sketch.cpp.hex:i"
        #"-Uflash:w:build/arduino/" + hexpath + ".hex:i"
    ]
    call(pgmargs)

rmtree("build/arduino")
rmtree("build/arduino-cache")
rmtree("build/tmp")
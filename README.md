# OrcaSlicer first layer travel acceleration fix

This is a post-processor for G-code files.

It fixes a slow acceleration for travel moves at the first layer.
 
## How to use the script
requirements: python version 3+  
1. download the script file **orca-first-layer-travel-acceleration-fix.py** to any folder at your machine
2. add this string into **postprocessing script** section

**<-path to python folder->**\python.exe "**<-path to the script->**\orca-first-layer-travel-acceleration-fix.py" "**<-path to gcode file->**.gcode"

![Снимок](https://github.com/vgdh/OrcaSlicer-first-layer-travel-acceleration-fix/assets/15322782/3297b640-7491-45f7-b7b7-12d3a4288e81)

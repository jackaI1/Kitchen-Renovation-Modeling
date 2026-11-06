# Preliminary wall screen

`renovation.envelope` is an unfinished, one-dimensional teaching calculation. It sums layer thickness divided by conductivity for RSI, then interpolates temperature by thermal resistance and vapour pressure by inverse permeance. Layers are ordered inside to outside, and relative humidity is a fraction. The caller declares control functions and continuity; the program cannot verify joints or real construction. The warning about the position of a vapour retarder is a simple heating-season heuristic, not a code check.

The interface comparison is an uncorrected vapour-pressure screening profile, not a complete Glaser moisture accumulation and drying analysis. Surface films, thermal bridges, rain, air leakage, moisture storage and transient weather are omitted. Do not use it for construction decisions. ASHRAE notes that steady-state methods have serious limitations and recommends hygrothermal modelling: https://handbook.ashrae.org/Handbooks/F25/IP/F25_Ch25/F25_Ch25_ip.aspx

Run the hand-check tests with `python3 -m unittest discover -s tests`. Further examples, inputs, reporting and validation are needed before this is a finished feature.

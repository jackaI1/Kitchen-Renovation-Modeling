# Desktop and immersive viewing

The desktop view works with mouse, trackpad or touch. Drag to orbit; scroll or pinch to zoom. Choose a compartment in the list for keyboard access. The model is a cutaway, with a translucent hull so the compartments stay visible. Labels show both a value and a status; colour is not the only cue.

## Headset setup

1. Run `npm run build` and `HOST=0.0.0.0 npm start` on the development computer.
2. Put a trusted HTTPS reverse proxy in front of port 5173. Forward WebSocket upgrades for `/sensors` as well as normal HTTP requests. For a local certificate, trust the issuing certificate on the headset. Do not put credentials or private certificates in the repository.
3. Visit the HTTPS URL in the headset browser. Allow immersive access. A compatible WebXR `immersive-vr` device makes the entry button available; a rejected permission request leaves orbit view working and shows recovery text.
4. Enter immersive view. The vessel should sit about 1.8 m ahead at tabletop height, at 18% scale. Look around it and confirm all four labels update. Point a controller at a compartment and press select.
5. Exit through the browser/headset session control. Confirm the desktop camera and orbit controls return. Try another entry/exit cycle.

A phone with no immersive VR device is expected to show the fallback message. AR placement and hand tracking are not implemented. The automated Chromium tests include two entry/exit cycles through the IWER WebXR emulator, with live telemetry during the session. Emulation does not represent a physical headset test. I have not verified optics, controller ergonomics or frame rate on headset hardware.

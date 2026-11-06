# Model import pipeline

I keep the model small enough to inspect comfortably in a browser or as a tabletop in a headset. I preserve compartment names through every step because those names connect geometry to readings.

## 1. Store the source

`data/source/vessel.json` is the editable original, not the GLB. It records metres, hull cross-sections in increasing longitudinal X, and compartment centres and dimensions. Blender uses Z up; the exporter converts it to glTF Y up. The hull is intentionally open at the deck. Positive Blender Y is port; negative Y is starboard. No external models, customer records, textures, or credentials are needed.

The exact mesh names are `hull`, `tank_port`, `tank_starboard`, `tank_freshwater`, and `engine_room`. To adjust dimensions, edit the JSON. To introduce a new compartment, update the source validation names in `pipeline/source_validation.py`, `PARTS` in `src/telemetry.ts`, the simulator, and the tests together. This is a fixed manifest, not a general-purpose untrusted file uploader.

## 2. Process in Blender

Run `npm run model:build`. Blender 4.2+ in background mode runs `pipeline/export_vessel.py`. It validates the source before replacing its temporary scene, builds mesh objects, bakes rotation and scale, welds vertices within 0.1 mm, deletes loose vertices, recalculates face normals and triangulates. It does not join compartments or decimate away their identities. The source is already low-poly, so the current cleanup correctly leaves vertex counts unchanged. Materials have no textures, cameras, lights or animation to carry into the browser.

For a separate staging export:

```sh
blender --background --factory-startup --python-exit-code 1 --python pipeline/export_vessel.py -- \
  --source data/source/vessel.json --output /tmp/vessel-candidate.glb
npx tsx pipeline/validate-glb.ts /tmp/vessel-candidate.glb
```

The export includes `vessel.report.json` alongside the GLB with per-part vertex counts, triangle counts and total bytes. Blender version differences can change binary serialization, so CI validates regenerated output instead of requiring byte-for-byte equality.

## 3. Validate

`npm run test:python` checks missing/duplicate names, dimensions, non-finite coordinates, units and station order. `npm run model:validate` validates the actual exported GLB using the Khronos validator, then parses it with three.js and applies the viewer's mesh validation. A model must be under 2 MB, at most 20,000 triangles, contain all required named meshes, and have finite positions and triangle geometry. Khronos errors fail the command; review any warnings before accepting a new model.

The browser repeats the named-mesh and geometry checks before it attaches the model. Renaming a tank produces a readable model rejection rather than an apparently working, incorrectly mapped overlay. Unit tests also exercise broken meshes independently of the source file.

## 4. Import and review

After a staging export passes, copy its GLB and report into `public/models/`, then run `npm run check` and `npm run test:browser`. The `GLTFLoader` in `src/main.ts` loads `/models/vessel.glb`. Materials are replaced with the inspection palette; in-scene sprite labels sit above each compartment. This does not alter the stored GLB.

Check the model from multiple angles. Confirm port and starboard match the source, both metric selectors update the intended parts, both alarm scenarios colour the intended compartment, and disconnects mark all readings stale. Run a headset test when physical equipment is available. Commit source, exporter changes, GLB, and report together.

## Packet contract

Every second the server sends version 1, an increasing integer `sequence`, a Unix-millisecond `timestamp`, a scenario (`normal`, `flood`, `heat`), and four `readings`. Each reading has a `part` name, `level` in percent [0,100], and `temperature` in °C [-20,120]. If a connection stays open but stops delivering packets, values remain marked stale; reload to reconnect that stalled stream. A browser can send `{"scenario":"flood"}` to change only its own stream. Packets are limited to 1 KB on the server's receiving side; invalid control messages are ignored. Slow clients skip updates rather than accumulate an unbounded send queue.

To connect real sensors later, replace `server/simulation.ts` with an adapter that emits this contract. Keep timestamps, units, part names and stale-data handling. This project does not supply calibration, marine certification, real alarms, sensor hardware or historical storage.

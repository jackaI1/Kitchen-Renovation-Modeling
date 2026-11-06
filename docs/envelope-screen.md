# Wall heat and moisture study

I use this study to compare the layers behind a wall finish. Air control limits drafts and moist air leakage. Water control drains rain to the outside. Vapour control slows water diffusing through materials. Thermal control slows heat flow. One material can serve several functions, but its joints must also work.

`examples/walls.json` contains three synthetic Ontario-style assemblies: a wood frame wall with cavity insulation, the same wall with exterior mineral wool, and an insulated masonry wall. These are learning examples, not details from my house or approved Ontario wall designs. The thickness, conductivity and whole-layer permeance values are explicit study assumptions, not manufacturer-certified product data. The drained cavity and cladding are outside the specified exterior boundary. The climate is a chosen winter case (21 C indoors, -18 C outdoors, 35%/80% RH), not an official location's design weather.

Run `python -m renovation --output output` and open `output/envelope/envelope.json`. In Python, `analyze(layers, indoor_c, outdoor_c, indoor_rh, outdoor_rh)` preserves the original screen's interface. Layers go from indoors to outdoors; RH uses 0 to 1. The JSON wrapper requires the exact documented SI units. Permeance is ng/(Pa s m²) for the entire layer, not permeability per metre.

## Heat and diffusion equations

For each layer, R = thickness / conductivity in m² K/W, also called RSI. Total RSI is the sum, U = 1/RSI, and interface temperature is `Ti + (To-Ti) * cumulative_R / total_R`. No surface films are silently added. The examples neglect surface films and framing bridges, so these are material-path resistances, not effective whole-wall U-values.

Saturation pressure uses a Magnus approximation: `610.94 exp(a T/(b+T))` Pa, with `(a,b)=(17.625,243.04)` above freezing and `(22.587,273.86)` below. Temperatures are restricted to -45 through 60 C. Boundary vapour pressure is RH times saturation pressure. Diffusion resistance Z is `1/permeance` and dry interface pressure interpolates by cumulative Z.

If the dry profile exceeds saturation, the Glaser calculation fixes active condensation planes at saturation and makes the pressure profile linear in Z between them. The lower convex envelope removes any candidate plane that would require evaporation from an initially dry wall. Flux `g=(p_left-p_right)/Z` has units ng/(m² s). The difference between incoming and outgoing flux at a plane is its condensation potential; multiplying by `86400e-9` gives g/(m² day). The report retains both the dry pressure and corrected Glaser pressure. The sum of plane condensation equals boundary influx minus outflux.

For a hand check, two equal RSI=2 layers, each with permeance 100, place their interface at 0 C between 20 and -20 C. With RH=.8 at both boundaries, its pressure is constrained to 610.94 Pa. Incoming flux is `100*(.8*psat(20)-610.94)`, outgoing flux is `100*(610.94-.8*psat(-20))`; the test checks their difference and the unit conversion independently.

## Controls and limits

Every function needs at least one layer declared continuous. Missing functions are listed; a layer explicitly declared discontinuous produces a warning. A heating-case vapour layer outside all designated insulation and water control inside all insulation trigger placement review warnings. These are simple rules for review, not universal requirements: exterior insulation and climate can change suitable locations. Declared continuity cannot verify penetrations, flashing, workmanship or connection between assemblies.

This is a steady, dry-start, interface-plane Glaser dew-point check, not a full ISO 13788 annual moisture assessment. It omits moisture storage, annual drying, liquid transport, rain, solar drive, leakage, thermal bridges and latent heat feedback. It checks layer interfaces only; it cannot exclude condensation within a thick homogeneous layer. A positive result is a reason to investigate; a zero result does not establish a moisture-safe wall.

References: [ISO 13788 scope and omissions](https://www.iso.org/standard/51615.html); [US DOE/PNNL cold-weather condensation control](https://basc.pnnl.gov/resource-guides/condensation-control-walls-cold-weather). These explain the simplified diffusion method and the importance of continuous air control and appropriate vapour-retarder position; this implementation does not claim code compliance.

# HIP-RA User Guide

HIP-RA (Heat In Place - Resource Assessment) estimates the geothermal energy
resource of a reservoir using the volumetric heat-in-place method. Given
reservoir temperature, area, thickness and porosity, it calculates stored heat,
recoverable heat, and producible electricity.

The method follows Muffler & Cataldi (1978) and the reexamination by
Garg & Combs (2011).

HIP-RA-X is the successor version to HIP-RA. HIP-RA-X reports results broken
down by reservoir, rock and fluid.

## Input File

Input files are plain text with one parameter per line, in the form
`Parameter Name, value`:

```
Reservoir Temperature, 212.5
Rejection Temperature, 60.0
Reservoir Porosity, 10.0
Reservoir Area, 109930 acre
Reservoir Thickness, 0.25
Reservoir Life Cycle, 25
```

A unit may follow the value, as with `Reservoir Area` above. Values are
converted to the parameter's preferred units in the output — 109,930 acres is
reported as 444.87 km**2. If no unit is given, the preferred unit is assumed.

Temperatures in Fahrenheit must be written as `degF`; `F` is interpreted as
farads.

All parameters have defaults, so a minimal input file is valid. See the
[Parameters Reference](hip_ra_x_parameters.html) for the full list, defaults
and permitted ranges.

## Running from the command line

```
python src/hip_ra_x/hip_ra_x.py <path to input file>
```

Use an absolute path to the input file. Relative paths may not resolve against
your shell's working directory.

## Running from Python

```python
from pathlib import Path

from hip_ra import HipRaInputParameters
from hip_ra_x import HipRaXClient


def hip_ra_x():
    client = HipRaXClient()
    result = client.get_hip_ra_x_result(
        HipRaInputParameters(Path('hip-ra-x-area-acres.txt').absolute())
    )
    print(result.result)


if __name__ == '__main__':
    hip_ra_x()
```

Parameters may also be passed directly as a dictionary instead of a file:

```python
result = HipRaXClient().get_hip_ra_x_result(
    HipRaInputParameters(
        {
            'Reservoir Temperature': 250.0,
            'Rejection Temperature': 60.0,
            'Reservoir Porosity': 10.0,
            'Reservoir Area': 55.0,
            'Reservoir Thickness': 0.25,
            'Reservoir Life Cycle': 25,
        }
    )
)
```

Results are returned as a nested dictionary with two top-level keys,
`SUMMARY OF INPUTS` and `SUMMARY OF RESULTS`, each mapping parameter names to
their value and unit:

```python
result.result['SUMMARY OF RESULTS']['Producible Electricity (reservoir)']
# {'value': 795.7, 'unit': 'MW'}
```

`SUMMARY OF INPUTS` includes any defaults applied and the results of any unit
conversions, so it reflects the parameters actually used rather than only those
supplied.

Set `Print Output to Console` to `False` to suppress the console report.

## Example Output

Running the example input file above produces:

```
                               *********************
                               ***HIP CASE REPORT***
                               *********************

      ***SUMMARY OF INPUTS***
      Reservoir Temperature:       212.50 degC
      Rejection Temperature:        60.00 degC
      Reservoir Porosity:           10.00 %
      Reservoir Area:              444.87 km**2
      Reservoir Thickness:           0.25 kilometer
      Reservoir Life Cycle:         25.00 yr
      Rock Heat Capacity:        2.84e+12 kJ/km**3C
      Fluid Specific Heat Capacity:       4.27 kJ/kgC
      Density Of Reservoir Fluid:   8.93e+11 kg/km**3
      Density Of Reservoir Rock:   2.55e+12 kg/km**3
      Recoverable Fluid Factor:       0.50
      Recoverable Heat from Rock:       0.75

      ***SUMMARY OF RESULTS***
      Reservoir Depth:               6.58 kilometer
      Reservoir Pressure:           64.56 MPa
      Reservoir Volume (reservoir):     111.22 km**3
      Reservoir Volume (rock):     100.10 km**3
      Recoverable Volume (recoverable fluid):       5.56 km**3
      Stored Heat (reservoir):   3.56e+16 kJ
      Stored Heat (rock):        3.25e+16 kJ
      Stored Heat (fluid):       3.14e+15 kJ
      Mass of Reservoir (rock):   2.55e+14 kilogram
      Mass of Reservoir (fluid):   5.65e+13 kilogram
      Specific Enthalpy (reservoir):     282.10 kJ/kg
      Specific Enthalpy (rock):     169.84 kJ/kg
      Specific Enthalpy (fluid):     112.26 kJ/kg
      Recovery Factor (reservoir):      11.74 %
      Available Heat (reservoir):   6.34e+15 kJ
      Producible Heat (reservoir):   4.18e+15 kJ
      Producible Heat/Unit Area (reservoir):   9.40e+12 kJ/km**2
      Producible Heat/Unit Volume (reservoir):   3.76e+13 kJ/km**3
      Producible Electricity (reservoir):    3155.91 MW
      Producible Electricity/Unit Area (reservoir):       7.09 MW/km**2
      Producible Electricity/Unit Volume (reservoir):      28.38 MW/km**3
```

## Interpreting the Results

The report has two sections. **Summary of Inputs** echoes the parameters used,
including any defaults applied and any unit conversions performed. **Summary of
Results** gives the calculated resource estimate.

The calculation proceeds from reservoir geometry to recoverable energy:

- **Reservoir Volume** — area multiplied by thickness, split into rock and fluid
  fractions according to porosity.
- **Stored Heat** — total thermal energy in the reservoir relative to the
  rejection temperature, reported separately for rock and fluid.
- **Recovery Factor** — the proportion of stored heat that can be extracted at
  the wellhead.
- **Available Heat** and **Producible Heat** — the recoverable energy, and the
  portion convertible to useful output over the reservoir life cycle.
- **Producible Electricity** — the electrical capacity implied by the producible
  heat and the utilisation efficiency.

Per-unit-area and per-unit-volume figures allow comparison between prospects of
different size.

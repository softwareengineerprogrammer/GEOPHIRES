# SAM Economic Models: End Uses and Surface Applications

SAM Economic Models support a variety of geothermal end-use options and surface applications.

See the [Theoretical Basis for GEOPHIRES End-use options documentation](Theoretical-Basis-for-GEOPHIRES.html#enduse-options)
for details on the underlying physical simulation mechanics.

## Electricity

For pure electricity generation configurations, SAM Economic Models calculate standard project finance metrics,
including a nominal Levelized Cost of Electricity (LCOE).

## Examples:

1. [example_SAM-single-owner-PPA](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA)
1. [example_SAM-single-owner-PPA-2](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-2)
1. [example_SAM-single-owner-PPA-3](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-3)
1. [example_SAM-single-owner-PPA-4](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-4)
1. [example_SAM-single-owner-PPA-5](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-5)
1. [example_SAM-single-owner-PPA-6_carbon-revenue](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-6_carbon-revenue)

## Direct-Use Heat

Direct-use heat configurations evaluate pure thermal energy extraction, reporting financial viability via the nominal
Levelized Cost of Heat (LCOH) in $/MMBTU.

### Grid Electricity Consumption and Cash Flow Reporting

In GEOPHIRES, pure direct-use heat and cooling configurations
typically require parasitic pumping power purchased from the grid. The cost of this grid electricity is calculated
and fully accounted for within GEOPHIRES' baseline OPEX calculations prior to executing the SAM financial engine.

The specific cash flow line items for `Electricity from grid (kWh)` and `Electricity purchase ($)` are intentionally
removed from the final SAM cash flow profile report for these end-uses. {# TODO/WIP: 'to avoid potential confusion with the equivalent unused SAM mechanisms' #}

### Examples:

1. [example_SAM-single-owner-PPA-8_heat](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-8_heat)

## Cogeneration

Combined Heat and Power (CHP) end-uses simulate both electricity and direct-use heat generation.
The model outputs allocated metrics for both product streams, including `Electricity CAPEX ($/kWe)`, `Heat CAPEX ($/kWth)`, LCOE, and LCOH.

### CHP Cost Allocation Ratio

To separate the levelized costs of electricity and heat, GEOPHIRES utilizes the `CHP Electrical Plant Cost Allocation Ratio`.
When calculating the levelized metrics, the total present value of annual costs includes not only CAPEX, but also OPEX,
taxes, and debt service. By applying a CAPEX-derived allocation ratio to this total present value, the model
mathematically forces the assumption that thermal OPEX and financing burdens scale exactly proportionally to thermal CAPEX.
If the electrical power plant has a high O&M burden and the direct-use heat component has a relatively low O&M burden,
applying the CAPEX ratio to the total PV will artificially inflate the LCOH and artificially lower the LCOE.
Analysts should be aware of this proportional scaling approximation when evaluating granular CHP OPEX profiles.


### Examples:

1. [example_SAM-single-owner-PPA-7_chp](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7_chp)
1. [example_SAM-single-owner-PPA-7b_chp-cc](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7b_chp-cc)

## Absorption Chiller (Cooling)

Cooling applications via absorption chillers are supported, providing a nominal Levelized Cost of Cooling (LCOC) in
$/MMBTU. Like Direct-Use Heat, parasitic electricity requirements are factored into the baseline OPEX prior to
SAM execution.


### Examples:

1. [example_SAM-single-owner-PPA-9_cooling](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-9_cooling)

## Limitations

Heat Pump, District Heating, and Reservoir Thermal Energy Storage (SUTRA) surface applications are not currently supported for SAM Economic Models.

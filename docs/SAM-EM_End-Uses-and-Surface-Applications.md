# SAM Economic Models: End Uses and Surface Applications

[SAM Economic Models](SAM-Economic-Models.html) support a variety of geothermal end-use options and surface applications.

See the [Theoretical Basis for GEOPHIRES End-use options documentation](Theoretical-Basis-for-GEOPHIRES.html#enduse-options)
for details on the underlying physical simulation mechanics.

## Electricity

For pure electricity generation configurations, SAM Economic Models calculate standard project finance metrics,
including a nominal Levelized Cost of Electricity (LCOE).

### Examples:

1. [example_SAM-single-owner-PPA](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA): 50 MWe
1. [example_SAM-single-owner-PPA-6_carbon-revenue](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-6_carbon-revenue): Electricity with Carbon Credits

See [SAM Economic Models documentation](SAM-Economic-Models.html#examples) for additional electricity examples.

## Direct-Use Heat

Direct-use heat configurations evaluate pure thermal energy extraction, reporting financial viability via the nominal
Levelized Cost of Heat (LCOH) in $/MMBTU.
Heat revenue is modeled as capacity payment revenue and included as the `Heat revenue ($)` cash flow line item.

### Grid Electricity Consumption and Cash Flow Reporting

In GEOPHIRES, pure direct-use heat and cooling configurations
typically require parasitic pumping power purchased from the grid. The cost of this grid electricity is calculated
and fully accounted for within GEOPHIRES' baseline OPEX calculations prior to executing the SAM financial engine.

Because these costs are injected directly into the fixed O&M parameters passed to SAM, SAM's native grid-purchase
mechanisms are bypassed. Consequently, the specific cash flow line items for `Electricity from grid (kWh)`
and `Electricity purchase ($)` are intentionally removed from the final SAM cash flow profile report.
This prevents the display of default zero values, which could otherwise mislead analysts into assuming parasitic power
costs were omitted.

### Examples:

1. [example_SAM-single-owner-PPA-8_heat](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-8_heat): Direct-Use Heat

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

### Injection Temperature and CHP Topping Cycles

In GEOPHIRES, adjusting the `Injection Temperature` for a Cogeneration Topping Cycle will affect the amount of direct-use heat produced, but it will **not** affect electricity production.

This is the physically correct behavior. In a topping cycle, the geofluid flows sequentially: it first passes through the power plant (which extracts heat to generate electricity and rejects the fluid at a calculated thermodynamic exhaust temperature), and then passes through the direct-use application (which extracts the residual heat down to the user-defined `Injection Temperature`).

Because the power plant sits upstream, its electricity production is governed entirely by the production temperature and its own exhaust temperature. Lowering the `Injection Temperature` simply increases the temperature delta across the downstream direct-use application, yielding more heat without altering the upstream power cycle.

### Examples:

1. [example_SAM-single-owner-PPA-7_chp](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7_chp): Combined Heat and Power (CHP): Cogeneration Topping Cycle
1. [example_SAM-single-owner-PPA-7b_chp-cc](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7b_chp-cc): Combined Heat and Power (CHP): Carbon Credits
1. [example_SAM-single-owner-PPA-7c](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7c): Combined Heat and Power (CHP): Carbon Credits with fixed Surface Plant Capital Cost
1. [example_SAM-single-owner-PPA-7d_chp-bottoming](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7d_chp-bottoming): Combined Heat and Power (CHP): Cogeneration Bottoming Cycle
1. [example_SAM-single-owner-PPA-7e_chp-parallel](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-7d_chp-parallel): Combined Heat and Power (CHP): Cogeneration Parallel Cycle

## Absorption Chiller (Cooling)

Cooling applications via absorption chillers are supported, providing a nominal Levelized Cost of Cooling (LCOC) in
$/MMBTU. Cooling revenue is modeled as capacity payment revenue and included as the `Cooling revenue ($)` cash flow line item.
Like Direct-Use Heat, parasitic electricity requirements are factored into the baseline OPEX prior to
SAM execution.

### Examples:

1. [example_SAM-single-owner-PPA-9_cooling](https://gtp.scientificwebservices.com/geophires?geophires-example-id=example_SAM-single-owner-PPA-9_cooling): Cooling (Direct-Use Heat with Absorption Chiller Surface Application)

## Limitations

Heat Pump, District Heating, and Reservoir Thermal Energy Storage (SUTRA) surface applications are not currently supported for SAM Economic Models.

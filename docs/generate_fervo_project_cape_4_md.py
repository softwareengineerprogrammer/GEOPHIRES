#!python
"""
Script to generate Fervo_Project_Cape-4.md from its jinja template.
This ensures the markdown documentation stays in sync with actual GEOPHIRES results.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment
from jinja2 import FileSystemLoader
from pint.facets.plain import PlainQuantity

from geophires_x.GeoPHIRESUtils import sig_figs
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXResult
from geophires_x_client import ImmutableGeophiresInputParameters

# Add project root to path to import GEOPHIRES modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))


def get_input_parameter_values(input_params: GeophiresInputParameters, result: GeophiresXResult) -> dict[str, Any]:
    print('Extracting input parameter values...')

    r: dict[str, dict[str, Any]] = result.result

    return {
        'reservoir_volume_m3': f"{r['RESERVOIR PARAMETERS']['Reservoir volume']['value']:,}",
    }


def _q(d: dict[str, Any]) -> PlainQuantity:
    return PlainQuantity(d['value'], d['unit'])


def get_result_values(result: GeophiresXResult) -> dict[str, Any]:
    print('Extracting result values...')

    r: dict[str, dict[str, Any]] = result.result

    total_capex_q: PlainQuantity = _q(r['CAPITAL COSTS (M$)']['Total CAPEX'])
    min_net_generation_mwe = r['SURFACE EQUIPMENT SIMULATION RESULTS']['Minimum Net Electricity Generation']['value']
    max_net_generation_mwe = r['SURFACE EQUIPMENT SIMULATION RESULTS']['Maximum Net Electricity Generation']['value']

    total_fracture_surface_area_per_well_m2 = _total_fracture_surface_area_per_well_m2(result)

    return {
        'lcoe_usd_per_mwh': sig_figs(
            _q(r['SUMMARY OF RESULTS']['Electricity breakeven price']).to('USD / MWh').magnitude, 3
        ),
        'irr_pct': sig_figs(r['ECONOMIC PARAMETERS']['After-tax IRR']['value'], 3),
        'npv_musd': sig_figs(r['ECONOMIC PARAMETERS']['Project NPV']['value'], 3),
        'occ_gusd': sig_figs(_q(r['CAPITAL COSTS (M$)']['Overnight Capital Cost']).to('GUSD').magnitude, 3),
        'total_capex_gusd': sig_figs(total_capex_q.to('GUSD').magnitude, 3),
        'min_net_generation_mwe': round(sig_figs(min_net_generation_mwe, 3)),
        'max_net_generation_mwe': round(sig_figs(max_net_generation_mwe, 3)),
        'capex_usd_per_kw': round(
            sig_figs((total_capex_q / PlainQuantity(max_net_generation_mwe, 'MW')).to('USD / kW').magnitude, 2)
        ),
        'stim_costs_musd': round(sig_figs(_stim_costs_musd(result), 3)),
        'stim_costs_per_well_musd': sig_figs(_stim_costs_per_well_musd(result), 3),
        'total_fracture_surface_area_per_well_mm2': sig_figs(total_fracture_surface_area_per_well_m2 / 1e6, 2),
        'total_fracture_surface_area_per_well_mft2': round(
            sig_figs(
                PlainQuantity(total_fracture_surface_area_per_well_m2, 'm ** 2').to('foot ** 2').magnitude * 1e-6, 2
            )
        ),
        # TODO port all input and result values here instead of hardcoding them in the template
    }


def _stim_costs_musd(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result

    stim_costs_musd = _q(r['CAPITAL COSTS (M$)']['Stimulation costs']).to('MUSD').magnitude
    return stim_costs_musd


def _number_of_wells(result: GeophiresXResult) -> int:
    r: dict[str, dict[str, Any]] = result.result

    number_of_wells = (
        r['SUMMARY OF RESULTS']['Number of injection wells']['value']
        + r['SUMMARY OF RESULTS']['Number of production wells']['value']
    )

    return number_of_wells


def _stim_costs_per_well_musd(result: GeophiresXResult) -> float:
    stim_costs_per_well_musd = _stim_costs_musd(result) / _number_of_wells(result)
    return stim_costs_per_well_musd


def _total_fracture_surface_area_per_well_m2(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result
    res_params = r['RESERVOIR PARAMETERS']
    return (
        _q(res_params['Fracture area']).to('m ** 2').magnitude
        * res_params['Number of fractures']['value']
        / _number_of_wells(result)
    )


def main():
    """
    Generate Fervo_Project_Cape-4.md (markdown documentation) from the Jinja template.
    """

    input_params: GeophiresInputParameters = ImmutableGeophiresInputParameters(
        from_file_path=project_root / 'tests/examples/Fervo_Project_Cape-4.txt'
    )
    result = GeophiresXResult(project_root / 'tests/examples/Fervo_Project_Cape-4.out')

    template_values = get_input_parameter_values(input_params, result)
    template_values = {**template_values, **get_result_values(result)}

    # Set up Jinja environment
    docs_dir = project_root / 'docs'
    env = Environment(loader=FileSystemLoader(docs_dir), autoescape=True)
    template = env.get_template('Fervo_Project_Cape-4.md.jinja')

    # Render template
    print('Rendering template...')
    output = template.render(**template_values)

    # Write output
    output_file = docs_dir / 'Fervo_Project_Cape-4.md'
    output_file.write_text(output)

    print(f'✓ Generated {output_file}')
    print('\nKey results:')
    print(f"\tLCOE: {template_values['lcoe_usd_per_mwh']}")
    print(f"\tIRR: {template_values['irr_pct']}")
    # print(f"  Total CAPEX: {result_values['capex']}")  # TODO


if __name__ == '__main__':
    main()

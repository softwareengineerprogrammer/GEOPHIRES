#!python
"""
Script to generate Fervo_Project_Cape-5.md from its jinja template.
This ensures the markdown documentation stays in sync with actual GEOPHIRES results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from jinja2 import Environment
from jinja2 import FileSystemLoader
from pint.facets.plain import PlainQuantity

from geophires_docs import _FPC5_INPUT_FILE_PATH
from geophires_docs import _FPC5_RESULT_FILE_PATH
from geophires_docs import _PROJECT_ROOT
from geophires_x.GeoPHIRESUtils import is_int
from geophires_x.GeoPHIRESUtils import sig_figs
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXResult
from geophires_x_client import ImmutableGeophiresInputParameters

# Add project root to path to import GEOPHIRES and docs modules


def _get_input_parameters_dict(  # TODO consolidate with FervoProjectCape5TestCase._get_input_parameters
    _params: GeophiresInputParameters, include_parameter_comments: bool = False, include_line_comments: bool = False
) -> dict[str, Any]:
    comment_idx = 0
    ret: dict[str, Any] = {}
    for line in _params.as_text().split('\n'):
        parts = line.strip().split(', ')  # TODO generalize for array-type params
        field = parts[0].strip()
        if len(parts) >= 2 and not field.startswith('#'):
            fieldValue = parts[1].strip()
            if include_parameter_comments and len(parts) > 2:
                fieldValue += ', ' + (', '.join(parts[2:])).strip()
            ret[field] = fieldValue.strip()

        if include_line_comments and field.startswith('#'):
            ret[f'_COMMENT-{comment_idx}'] = line.strip()
            comment_idx += 1

        # TODO preserve newlines

    return ret


def _get_schema() -> dict[str, Any]:
    schema_file = _PROJECT_ROOT / 'src/geophires_x_schema_generator/geophires-request.json'
    with open(schema_file, encoding='utf-8') as f:
        return json.loads(f.read())


def _get_parameter_schema(param_name: str) -> dict[str, Any]:
    return _get_schema()['properties'][param_name]


def _get_parameter_schema_type(param_name: str) -> dict[str, Any]:
    return _get_parameter_schema(param_name)['type']


def _get_parameter_category(param_name: str) -> str:
    return _get_parameter_schema(param_name)['category']


def _get_parameter_units(param_name: str) -> str | None:
    unit = _get_schema()['properties'][param_name]['units']

    if unit == '':
        return 'dimensionless'

    return unit


def _get_unit_display(parameter_units_from_schema: str) -> str:
    if parameter_units_from_schema is None:
        return ''

    display_unit_prefix = (
        ' '
        if not (parameter_units_from_schema and any(it in parameter_units_from_schema for it in ['%', 'USD', 'MUSD']))
        else ''
    )
    display_unit = parameter_units_from_schema
    for replacement in [
        ('kilometer', 'km'),
        ('degC', '℃'),
        ('meter', 'm'),
        ('m**3', 'm³'),
        ('m**2', 'm²'),
        ('MUSD', 'M'),
        ('USD', ''),
    ]:
        display_unit = display_unit.replace(replacement[0], replacement[1])

    return f'{display_unit_prefix}{display_unit}'


def generate_fpc_reservoir_parameters_table_md(input_params: GeophiresInputParameters) -> str:
    params_to_exclude = [
        'Maximum Temperature',
        'Reservoir Porosity',
        'Reservoir Volume Option',
    ]

    return get_fpc_category_parameters_table_md(
        input_params,
        'Reservoir',
        params_to_exclude,
    )


def generate_fpc_well_bores_parameters_table_md(input_params: GeophiresInputParameters) -> str:
    return get_fpc_category_parameters_table_md(
        input_params,
        'Well Bores',
        parameters_to_exclude=['Number of Multilateral Sections'],
    )


def generate_fpc_surface_plant_parameters_table_md(input_params: GeophiresInputParameters) -> str:
    return get_fpc_category_parameters_table_md(
        input_params,
        'Surface Plant',
        parameters_to_exclude=['End-Use Option', 'Construction Years'],
    )


def generate_fpc_construction_parameters_table_md(input_params: GeophiresInputParameters) -> str:
    input_params_dict = _get_input_parameters_dict(
        input_params, include_parameter_comments=True, include_line_comments=True
    )
    schedule_param_name = 'Construction CAPEX Schedule'
    construction_input_params = {}
    for construction_param in ['Construction Years', schedule_param_name]:
        construction_input_params[construction_param] = input_params_dict[construction_param]

    # Comment hardcoded here for now because handling of array parameters with comments might be buggy in client or
    # web interface...
    schedule_param_comment = (
        'Array of fractions of overnight capital cost expenditure for each year, starting with '
        'lower costs during initial years for exploration and increasing to higher costs during '
        'later years as buildout progresses.'
    )
    construction_input_params[schedule_param_name] = (
        f'{construction_input_params[schedule_param_name]}' f', -- {schedule_param_comment}'
    )

    return get_fpc_category_parameters_table_md(
        ImmutableGeophiresInputParameters(params=construction_input_params), None
    )


def generate_fpc_economics_parameters_table_md(input_params: GeophiresInputParameters) -> str:
    return get_fpc_category_parameters_table_md(
        input_params,
        'Economics',
        parameters_to_exclude=[
            'Ending Electricity Sale Price',
            'Electricity Escalation Start Year',
            'Construction CAPEX Schedule',
            'Time steps per year',
            'Print Output to Console',
        ],
    )


def get_fpc_category_parameters_table_md(
    input_params: GeophiresInputParameters, category_name: str | None, parameters_to_exclude: list[str] | None = None
) -> str:
    if parameters_to_exclude is None:
        parameters_to_exclude = []

    input_params_dict = _get_input_parameters_dict(
        input_params, include_parameter_comments=True, include_line_comments=True
    )

    non_breaking_space = '\xa0'

    # noinspection MarkdownIncorrectTableFormatting
    table_md = f"""
| Parameter         | Input{non_breaking_space}Value    | Comment      |
|-------------------|-------------------------------------------|-------------|
"""

    table_entries = []
    for param_name, param_val_comment in input_params_dict.items():
        if param_name.startswith(('#', '_COMMENT-')):
            continue

        if param_name in parameters_to_exclude:
            continue

        category = _get_parameter_category(param_name)
        if category_name is None or category == category_name:
            param_val_comment_split = param_val_comment.split(
                # ',',
                ',' if _get_parameter_schema_type(param_name) != 'array' else ', ',
                maxsplit=1,
            )

            param_val = param_val_comment_split[0]

            param_comment = (
                param_val_comment_split[1].replace('-- ', '') if len(param_val_comment_split) > 1 else ' .. N/A '
            )
            param_unit = _get_parameter_units(param_name)
            if param_unit == 'dimensionless':
                param_unit_display = '%'
                param_val = sig_figs(
                    PlainQuantity(float(param_val), 'dimensionless').to('percent').magnitude,
                    10,  # trim floating point errors
                )
            elif ' ' in param_val:
                param_val_split = param_val.split(' ', maxsplit=1)
                param_val = param_val_split[0]
                param_unit_display = _get_unit_display(param_val_split[1])
            else:
                param_unit_display = _get_unit_display(param_unit)

            param_unit_display_prefix = '$' if param_unit and 'USD' in param_unit else ''

            if is_int(param_val):
                param_val = int(param_val)

            param_schema = _get_parameter_schema(param_name)
            if param_schema and 'enum_values' in param_schema:
                for enum_value in param_schema['enum_values']:
                    if enum_value['int_value'] == param_val:
                        enum_display = enum_value['value']
                        # param_val = f'{param_val} ({enum_display})'
                        param_val = enum_display
                        break

            param_name_display = param_name.replace(' ', non_breaking_space, 2)
            table_entries.append(
                [param_name_display, f'{param_unit_display_prefix}{param_val}{param_unit_display}', param_comment]
            )

    for table_entry in table_entries:
        table_md += f'| {table_entry[0]} | {table_entry[1]} | {table_entry[2]} |\n'

    return table_md.strip()


def _q(d: dict[str, Any]) -> PlainQuantity:
    return PlainQuantity(d['value'], d['unit'])


def get_fpc5_input_parameter_values(input_params: GeophiresInputParameters, result: GeophiresXResult) -> dict[str, Any]:
    print('Extracting input parameter values...')

    params = _get_input_parameters_dict(input_params)
    r: dict[str, dict[str, Any]] = result.result

    exploration_cost_musd = _q(r['CAPITAL COSTS (M$)']['Exploration costs']).to('MUSD').magnitude
    assert exploration_cost_musd == float(
        params['Exploration Capital Cost']
    ), 'Exploration cost mismatch between parameters and result'

    return {
        'exploration_cost_musd': round(sig_figs(exploration_cost_musd, 2)),
        'wacc_pct': sig_figs(r['ECONOMIC PARAMETERS']['WACC']['value'], 3),
        'reservoir_volume_m3': f"{r['RESERVOIR PARAMETERS']['Reservoir volume']['value']:,}",
    }


def get_result_values(result: GeophiresXResult) -> dict[str, Any]:
    print('Extracting result values...')

    r: dict[str, dict[str, Any]] = result.result

    total_capex_q: PlainQuantity = _q(r['CAPITAL COSTS (M$)']['Total CAPEX'])

    surf_equip_sim = r['SURFACE EQUIPMENT SIMULATION RESULTS']
    min_net_generation_mwe = surf_equip_sim['Minimum Net Electricity Generation']['value']
    avg_net_generation_mwe = surf_equip_sim['Average Net Electricity Generation']['value']
    max_net_generation_mwe = surf_equip_sim['Maximum Net Electricity Generation']['value']
    max_total_generation_mwe = surf_equip_sim['Maximum Total Electricity Generation']['value']
    parasitic_loss_pct = (
        surf_equip_sim['Average Pumping Power']['value']
        / surf_equip_sim['Average Total Electricity Generation']['value']
        * 100.0
    )
    net_power_idx = result.power_generation_profile[0].index('NET POWER (MW)')

    def n_year_avg_net_power_mwe(years: int) -> float:
        return np.average([it[net_power_idx] for it in result.power_generation_profile[1:]][:years])

    two_year_avg_net_power_mwe = n_year_avg_net_power_mwe(2)
    two_year_avg_net_power_mwe_per_production_well = two_year_avg_net_power_mwe / _number_of_production_wells(result)

    total_fracture_surface_area_per_well_m2 = _total_fracture_surface_area_per_well_m2(result)

    occ_q = _q(r['CAPITAL COSTS (M$)']['Overnight Capital Cost'])

    field_gathering_cost_musd = _q(r['CAPITAL COSTS (M$)']['Field gathering system costs']).to('MUSD').magnitude
    field_gathering_cost_pct_occ = field_gathering_cost_musd / occ_q.to('MUSD').magnitude * 100.0

    redrills = r['ENGINEERING PARAMETERS']['Number of times redrilling']['value']
    total_wells_including_redrilling = redrills * _number_of_wells(result)

    return {
        # Economic Results
        'lcoe_usd_per_mwh': sig_figs(
            _q(r['SUMMARY OF RESULTS']['Electricity breakeven price']).to('USD / MWh').magnitude, 3
        ),
        'irr_pct': sig_figs(r['ECONOMIC PARAMETERS']['After-tax IRR']['value'], 3),
        'npv_musd': sig_figs(r['ECONOMIC PARAMETERS']['Project NPV']['value'], 3),
        # Capital Costs
        'drilling_costs_musd': round(sig_figs(_drilling_costs_musd(result), 3)),
        'drilling_costs_per_well_musd': sig_figs(_drilling_costs_per_well_musd(result), 3),
        'stim_costs_musd': round(sig_figs(_stim_costs_musd(result), 3)),
        'stim_costs_per_well_musd': sig_figs(_stim_costs_per_well_musd(result), 3),
        'surface_power_plant_costs_gusd': sig_figs(
            _q(r['CAPITAL COSTS (M$)']['Surface power plant costs']).to('GUSD').magnitude, 3
        ),
        'field_gathering_cost_musd': round(sig_figs(field_gathering_cost_musd, 3)),
        'field_gathering_cost_pct_occ': round(sig_figs(field_gathering_cost_pct_occ, 1)),
        'occ_gusd': sig_figs(occ_q.to('GUSD').magnitude, 3),
        'total_capex_gusd': sig_figs(total_capex_q.to('GUSD').magnitude, 3),
        'capex_usd_per_kw': round(
            sig_figs((total_capex_q / PlainQuantity(max_net_generation_mwe, 'MW')).to('USD / kW').magnitude, 2)
        ),
        # Technical & Engineering Results
        'bht_temp_degc': r['RESERVOIR PARAMETERS']['Bottom-hole temperature']['value'],
        'min_net_generation_mwe': round(sig_figs(min_net_generation_mwe, 3)),
        'avg_net_generation_mwe': round(sig_figs(avg_net_generation_mwe, 3)),
        'max_net_generation_mwe': round(sig_figs(max_net_generation_mwe, 3)),
        'max_total_generation_mwe': round(sig_figs(max_total_generation_mwe, 3)),
        'two_year_avg_net_power_mwe_per_production_well': sig_figs(two_year_avg_net_power_mwe_per_production_well, 2),
        'parasitic_loss_pct': sig_figs(parasitic_loss_pct, 3),
        'number_of_times_redrilling': redrills,
        'total_wells_including_redrilling': total_wells_including_redrilling,
        'initial_production_temperature_degc': round(
            sig_figs(r['RESERVOIR SIMULATION RESULTS']['Initial Production Temperature']['value'], 3)
        ),
        'average_production_temperature_degc': round(
            sig_figs(r['RESERVOIR SIMULATION RESULTS']['Average Production Temperature']['value'], 3)
        ),
        'total_fracture_surface_area_per_well_mm2': sig_figs(total_fracture_surface_area_per_well_m2 / 1e6, 2),
        'total_fracture_surface_area_per_well_mft2': round(
            sig_figs(
                PlainQuantity(total_fracture_surface_area_per_well_m2, 'm ** 2').to('foot ** 2').magnitude * 1e-6, 2
            )
        ),
        # TODO port all input and result values here instead of hardcoding them in the template
    }


def _number_of_production_wells(result: GeophiresXResult) -> int:
    return result.result['SUMMARY OF RESULTS']['Number of production wells']['value']


def _number_of_wells(result: GeophiresXResult) -> int:
    r: dict[str, dict[str, Any]] = result.result

    number_of_wells = r['SUMMARY OF RESULTS']['Number of injection wells']['value'] + _number_of_production_wells(
        result
    )

    return number_of_wells


def _drilling_costs_musd(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result

    return _q(r['CAPITAL COSTS (M$)']['Drilling and completion costs']).to('MUSD').magnitude


def _drilling_costs_per_well_musd(result: GeophiresXResult) -> float:
    return _drilling_costs_musd(result) / _number_of_wells(result)


def _stim_costs_per_well_musd(result: GeophiresXResult) -> float:
    stim_costs_per_well_musd = _stim_costs_musd(result) / _number_of_wells(result)
    return stim_costs_per_well_musd


def _stim_costs_musd(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result

    stim_costs_musd = _q(r['CAPITAL COSTS (M$)']['Stimulation costs']).to('MUSD').magnitude
    return stim_costs_musd


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


def generate_res_eng_reference_sim_params_table_md(
    base_case_input_params: GeophiresInputParameters, res_eng_reference_sim_params: dict[str, Any]
) -> str:
    return get_fpc_category_parameters_table_md(
        ImmutableGeophiresInputParameters(
            # from_file_path=base_case_input_params.as_file_path(),
            params=res_eng_reference_sim_params
        ),
        None,
    )


def generate_fervo_project_cape_5_md(
    input_params: GeophiresInputParameters,
    result: GeophiresXResult,
    res_eng_reference_sim_params: dict[str, Any] | None = None,
    project_root: Path = _PROJECT_ROOT,
) -> None:
    if res_eng_reference_sim_params is None:
        res_eng_reference_sim_params = {}

    # noinspection PyDictCreation
    template_values = {**get_fpc5_input_parameter_values(input_params, result), **get_result_values(result)}

    for template_key, md_method in {
        'reservoir_parameters_table_md': generate_fpc_reservoir_parameters_table_md,
        'surface_plant_parameters_table_md': generate_fpc_surface_plant_parameters_table_md,
        'well_bores_parameters_table_md': generate_fpc_well_bores_parameters_table_md,
        'economics_parameters_table_md': generate_fpc_economics_parameters_table_md,
        'construction_parameters_table_md': generate_fpc_construction_parameters_table_md,
    }.items():
        template_values[template_key] = md_method(input_params)

    template_values['reservoir_engineering_reference_simulation_params_table_md'] = (
        generate_res_eng_reference_sim_params_table_md(input_params, res_eng_reference_sim_params)
    )

    docs_dir = project_root / 'docs'

    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader(docs_dir), autoescape=True)
    template = env.get_template('Fervo_Project_Cape-5.md.jinja')

    # Render template
    print('Rendering template...')
    output = template.render(**template_values)

    # Write output
    output_file = docs_dir / 'Fervo_Project_Cape-5.md'
    output_file.write_text(output, encoding='utf-8')

    print(f'✓ Generated {output_file}')
    print('\nKey results:')
    print(f"\tLCOE: ${template_values['lcoe_usd_per_mwh']}/MWh")
    print(f"\tIRR: {template_values['irr_pct']}%")
    print(f"\tTotal CAPEX: ${template_values['total_capex_gusd']}B")


def main(project_root: Path = _PROJECT_ROOT):
    """
    Generate Fervo_Project_Cape-5.md (markdown documentation) from the Jinja template.
    """

    input_params: GeophiresInputParameters = ImmutableGeophiresInputParameters(from_file_path=_FPC5_INPUT_FILE_PATH)
    result = GeophiresXResult(_FPC5_RESULT_FILE_PATH)
    generate_fervo_project_cape_5_md(input_params, result, project_root=project_root)


if __name__ == '__main__':
    main()

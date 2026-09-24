#!python
"""
Script to generate Fervo_Project_Cape-5.md from its jinja template.
This ensures the markdown documentation stays in sync with actual GEOPHIRES results.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import select_autoescape
from pint.facets.plain import PlainQuantity

from geophires_docs import _FPC5_ORC_UNIT_GROSS_CAPACITY_MW
from geophires_docs import _FPC5_PPA_MINIMUM_NET_GENERATION_MW
from geophires_docs import _NON_BREAKING_SPACE
from geophires_docs import _PROJECT_ROOT
from geophires_docs import _get_fpc5_input_file_path
from geophires_docs import _get_fpc5_orc_unit_count
from geophires_docs import _get_fpc5_result_file_path
from geophires_docs import _get_input_parameters_dict
from geophires_docs import _get_logger
from geophires_docs import _get_project_root
from geophires_docs.fervo_project_cape_5_scenarios import FlowRateParametricRow
from geophires_docs.fervo_project_cape_5_scenarios import get_fpc5_flow_rate_parametric_summary
from geophires_docs.fervo_project_cape_5_scenarios import get_irr_changes_pct_pts
from geophires_docs.fervo_project_cape_5_scenarios import load_fpc5_flow_rate_parametric
from geophires_x.GeoPHIRESUtils import is_int
from geophires_x.GeoPHIRESUtils import sig_figs
from geophires_x.ParameterUtils import COMMENT_PARAMETER_NAME_PREFIX
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXResult
from geophires_x_client import ImmutableGeophiresInputParameters

# Module-level variable to hold the current project root for schema access
_current_project_root: Path | None = None

_log = _get_logger(__name__)


def _get_schema(schema_file_name: str) -> dict[str, Any]:
    project_root = _current_project_root if _current_project_root is not None else _get_project_root()
    schema_file = project_root / 'src/geophires_x_schema_generator' / schema_file_name
    with open(schema_file, encoding='utf-8') as f:
        return json.loads(f.read())


def _get_geophires_request_schema() -> dict[str, Any]:
    return _get_schema('geophires-request.json')


def _get_input_parameter_schema(param_name: str) -> dict[str, Any]:
    return _get_geophires_request_schema()['properties'][param_name]


def _get_input_parameter_schema_type(param_name: str) -> dict[str, Any]:
    return _get_input_parameter_schema(param_name)['type']


def _get_input_parameter_category(param_name: str) -> str:
    return _get_input_parameter_schema(param_name)['category']


def _get_input_parameter_units(param_name: str) -> str | None:
    unit = _get_geophires_request_schema()['properties'][param_name]['units']

    if unit == '':
        return 'dimensionless'

    return unit


def _get_geophires_result_schema() -> dict[str, Any]:
    return _get_schema('geophires-result.json')


def _get_output_parameter_schema(param_name: str) -> dict[str, Any]:
    categorized_schema: dict[str, dict[str, Any]] = _get_geophires_result_schema()['properties']

    for _category, category_data in categorized_schema.items():
        if param_name in category_data['properties']:
            return category_data['properties'][param_name]

    raise ValueError(f'Parameter "{param_name}" not found in GEOPHIRES result schema.')


def _get_output_parameter_description(param_name: str) -> str:
    return _get_output_parameter_schema(param_name)['description']


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


def generate_fpc_reservoir_parameters_table_md(input_params: GeophiresInputParameters, result: GeophiresXResult) -> str:
    params_to_exclude = [
        'Maximum Temperature',
        'Reservoir Porosity',
        'Reservoir Volume Option',
    ]

    return get_fpc_category_parameters_table_md(input_params, 'Reservoir', params_to_exclude)


def generate_fpc_well_bores_parameters_table_md(
    input_params: GeophiresInputParameters, result: GeophiresXResult
) -> str:
    return get_fpc_category_parameters_table_md(
        input_params,
        'Well Bores',
        parameters_to_exclude=['Number of Multilateral Sections'],
    )


def generate_fpc_surface_plant_parameters_table_md(
    input_params: GeophiresInputParameters, result: GeophiresXResult
) -> str:
    return get_fpc_category_parameters_table_md(
        input_params,
        'Surface Plant',
        parameters_to_exclude=['End-Use Option', 'Construction Years'],
    )


def generate_fpc_construction_parameters_table_md(
    input_params: GeophiresInputParameters, result: GeophiresXResult
) -> str:
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


def generate_fpc_economics_parameters_table_md(input_params: GeophiresInputParameters, result: GeophiresXResult) -> str:
    stim_cost_per_well_additional_display_data = (
        f' baseline cost; ${_stim_costs_per_well_musd(result):.2f}M/well all-in cost'
    )

    drilling_cost_per_well_additional_display_data = (
        f' (Yields all-in cost of ' f'${sig_figs(_drilling_costs_per_well_musd(result),3)}M/well)'
    )

    # Doesn't seem to work as intended...
    drilling_cost_per_well_additional_display_data = drilling_cost_per_well_additional_display_data.replace(
        ' ', _NON_BREAKING_SPACE
    )

    input_params_dict = _get_input_parameters_dict(input_params)
    stim_cost_per_well_param_names = [
        'Reservoir Stimulation Capital Cost per Production Well',
        'Reservoir Stimulation Capital Cost per Injection Well',
    ]
    additional_display_data_by_param_name = {
        'Well Drilling and Completion Capital Cost Adjustment Factor': drilling_cost_per_well_additional_display_data,
        'Reservoir Stimulation Capital Cost per Fracture Surface Area': stim_cost_per_well_additional_display_data,
        # Parameter units are MUSD, but the value is an annual cost
        'Annual License Fees Etc': '/yr',
    }
    value_display_override_by_param_name = {}
    for stim_cost_per_well_param_name in stim_cost_per_well_param_names:
        if _is_stimulated_well_sentinel(input_params_dict.get(stim_cost_per_well_param_name)):
            value_display_override_by_param_name[stim_cost_per_well_param_name] = (
                'Stimulated (cost from per-area input)'
            )
        elif 'Reservoir Stimulation Capital Cost per Fracture Surface Area' not in input_params_dict:
            additional_display_data_by_param_name[stim_cost_per_well_param_name] = (
                stim_cost_per_well_additional_display_data
            )

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
        additional_display_data_by_param_name=additional_display_data_by_param_name,
        value_display_override_by_param_name=value_display_override_by_param_name,
    )


def get_fpc_category_parameters_table_md(
    input_params: GeophiresInputParameters,
    category_name: str | None,
    parameters_to_exclude: list[str] | None = None,
    additional_display_data_by_param_name: dict[str, str] | None = None,
    value_display_override_by_param_name: dict[str, str] | None = None,
) -> str:
    if parameters_to_exclude is None:
        parameters_to_exclude = []

    if additional_display_data_by_param_name is None:
        additional_display_data_by_param_name = {}

    if value_display_override_by_param_name is None:
        value_display_override_by_param_name = {}

    input_params_dict = _get_input_parameters_dict(
        input_params, include_parameter_comments=True, include_line_comments=True
    )

    # noinspection MarkdownIncorrectTableFormatting
    table_md = f"""
| Parameter         | Input{_NON_BREAKING_SPACE}Value    | Comment      |
|-------------------|-------------------------------------------|-------------|
"""

    table_entries = []
    for param_name, param_val_comment in input_params_dict.items():
        if param_name.startswith(('#', COMMENT_PARAMETER_NAME_PREFIX)):
            continue

        if param_name in parameters_to_exclude:
            continue

        category = _get_input_parameter_category(param_name)
        if category_name is None or category == category_name:
            param_val_comment_split = param_val_comment.split(
                # ',',
                ',' if _get_input_parameter_schema_type(param_name) != 'array' else ', ',
                maxsplit=1,
            )

            param_val = param_val_comment_split[0]

            param_comment = (
                param_val_comment_split[1].replace('-- ', '') if len(param_val_comment_split) > 1 else ' .. N/A '
            )

            param_name_display = param_name.replace(' ', _NON_BREAKING_SPACE, 2)

            additional_display_data = additional_display_data_by_param_name.get(param_name, '')

            value_display = value_display_override_by_param_name.get(
                param_name, _get_input_parameter_value_display(param_name, param_val)
            )

            table_entries.append(
                [
                    param_name_display,
                    f'{value_display}{additional_display_data}',
                    param_comment,
                ]
            )

    for table_entry in table_entries:
        table_md += f'| {table_entry[0]} | {table_entry[1]} | {table_entry[2]} |\n'

    return table_md.strip()


def _q(d: dict[str, Any]) -> PlainQuantity:
    return PlainQuantity(d['value'], d['unit'])


def _get_input_parameter_value_display(param_name: str, param_val: Any) -> str:
    """
    :param param_val: Input parameter value as it appears in the input file, without comment (may include a unit, e.g.
        '7500 feet')
    :return: Value with display units, e.g. '$115/MWh', '72%', '3.06 km'
    """
    param_unit = _get_input_parameter_units(param_name)
    if param_unit == 'dimensionless':
        param_unit_display = '%'
        param_val = sig_figs(
            PlainQuantity(float(param_val), 'dimensionless').to('percent').magnitude,
            10,  # trim floating point errors
        )
    elif param_unit == 'USD/kWh':
        price_unit = 'USD/MWh'
        param_unit_display = _get_unit_display(price_unit)
        param_val = sig_figs(
            PlainQuantity(float(param_val), 'USD/kWh').to(price_unit).magnitude,
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

    param_schema = _get_input_parameter_schema(param_name)
    if param_schema and 'enum_values' in param_schema:
        for enum_value in param_schema['enum_values']:
            if enum_value['int_value'] == param_val:
                enum_display = enum_value['value']
                # param_val = f'{param_val} ({enum_display})'
                param_val = enum_display
                break

    return f'{param_unit_display_prefix}{param_val}{param_unit_display}'


def get_fpc5_input_parameter_values(input_params: GeophiresInputParameters, result: GeophiresXResult) -> dict[str, Any]:
    _log.info('Extracting input parameter values...')

    params = _get_input_parameters_dict(input_params)
    r: dict[str, dict[str, Any]] = result.result

    exploration_cost_musd = _q(r['CAPITAL COSTS (M$)']['Exploration costs']).to('MUSD').magnitude
    assert exploration_cost_musd == float(
        params['Exploration Capital Cost']
    ), 'Exploration cost mismatch between parameters and result'

    starting_ppa_price_usd_per_mwh = (
        PlainQuantity(float(params['Starting Electricity Sale Price']), 'USD/kWh').to('USD/MWh').magnitude
    )

    # Drilling and completion cost (including indirect costs) scales linearly with the adjustment factor.
    drilling_cost_adjustment_factor = float(params['Well Drilling and Completion Capital Cost Adjustment Factor'])
    drilling_costs_per_well_at_unit_adjustment_factor_musd = (
        _drilling_costs_per_well_musd(result) / drilling_cost_adjustment_factor
    )

    # Yusifov & Enriquez, 2025
    drilling_to_stimulation_cost_ratio = 46.0 / 54.0

    return {
        'exploration_cost_musd': round(sig_figs(exploration_cost_musd, 2)),
        'wacc_pct': sig_figs(r['ECONOMIC PARAMETERS']['WACC']['value'], 3),
        'reservoir_volume_m3': f"{r['RESERVOIR PARAMETERS']['Reservoir volume']['value']:,}",
        'starting_ppa_price_usd_per_mwh': round(starting_ppa_price_usd_per_mwh),
        'production_flow_rate_kg_per_s_display': f"{float(params['Production Flow Rate per Well']):g}",
        'drilling_costs_per_well_at_unit_adjustment_factor_musd': sig_figs(
            drilling_costs_per_well_at_unit_adjustment_factor_musd, 3
        ),
        'stim_costs_per_well_drilling_ratio_reference_musd': sig_figs(
            _drilling_costs_per_well_musd(result) / drilling_to_stimulation_cost_ratio, 3
        ),
    }


def get_max_net_generation_mwe(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result
    return _q(r['SURFACE EQUIPMENT SIMULATION RESULTS']['Maximum Net Electricity Generation']).to('MW').magnitude


def get_result_values(result: GeophiresXResult) -> dict[str, Any]:
    _log.info('Extracting result values...')

    r: dict[str, dict[str, Any]] = result.result

    econ = r['ECONOMIC PARAMETERS']

    total_capex_q: PlainQuantity = _q(r['CAPITAL COSTS (M$)']['Total CAPEX'])

    surf_equip_sim = r['SURFACE EQUIPMENT SIMULATION RESULTS']
    min_net_generation_mwe = surf_equip_sim['Minimum Net Electricity Generation']['value']
    avg_net_generation_mwe = surf_equip_sim['Average Net Electricity Generation']['value']
    max_net_generation_mwe = get_max_net_generation_mwe(result)
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
    total_wells_including_redrilling = (1 + redrills) * _number_of_wells(result)
    redrilling_years = _get_redrilling_years(result)
    if len(redrilling_years) != redrills:
        raise ValueError(
            f'Redrilling years detected from production temperature profile ({redrilling_years}) do not match '
            f'Number of times redrilling ({redrills}).'
        )

    first_cycle_peak_year, first_cycle_peak_temperature_degc = _get_first_cycle_peak_production_temperature(
        result, redrilling_years
    )
    initial_production_temperature_degc = r['RESERVOIR SIMULATION RESULTS']['Initial Production Temperature']['value']

    total_capex_musd = total_capex_q.to('MUSD').magnitude
    interconnection_cost_musd = _interconnection_cost_musd(result)
    interconnection_share_of_total_capex_musd = _interconnection_share_of_total_capex_musd(result)

    max_net_generation_q = PlainQuantity(max_net_generation_mwe, 'MW')
    transmission_cost_musd_per_yr = _annual_license_fees_musd_per_yr(result)

    orc_unit_count = _get_fpc5_orc_unit_count(max_total_generation_mwe)

    return {
        # Economic Results
        'lcoe_usd_per_mwh': round(
            _q(r['SUMMARY OF RESULTS']['Electricity breakeven price']).to('USD / MWh').magnitude, 1
        ),
        'lppa_usd_per_mwh': round(_get_levelized_ppa_price_usd_per_mwh(result), 1),
        'irr_pct': sig_figs(econ['After-tax IRR']['value'], 3),
        'operations_year_of_irr': econ['Project lifetime']['value'],
        'npv_musd': sig_figs(econ['Project NPV']['value'], 3),
        'project_moic': sig_figs(econ['Project MOIC']['value'], 3),
        'project_vir': sig_figs(econ['Project VIR=PI=PIR']['value'], 3),
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
        'exploration_atb_reference_musd': sig_figs(_drilling_costs_per_well_musd(result) * 5, 3),
        'interconnection_cost_musd': round(sig_figs(interconnection_cost_musd, 3)),
        'interconnection_cost_usd_per_kw_ppa_capacity': round(
            sig_figs(
                (
                    PlainQuantity(interconnection_cost_musd, 'MUSD')
                    / PlainQuantity(_FPC5_PPA_MINIMUM_NET_GENERATION_MW, 'MW')
                )
                .to('USD / kW')
                .magnitude,
                3,
            )
        ),
        'interconnection_share_of_total_capex_musd': round(sig_figs(interconnection_share_of_total_capex_musd, 3)),
        'capex_usd_per_kw_excluding_interconnection': round(
            sig_figs(
                (
                    PlainQuantity(total_capex_musd - interconnection_share_of_total_capex_musd, 'MUSD')
                    / max_net_generation_q
                )
                .to('USD / kW')
                .magnitude,
                2,
            )
        ),
        'surface_power_plant_pct_of_wellfield_and_plant_capex': round(
            sig_figs(_surface_power_plant_pct_of_wellfield_and_plant_capex(result), 2)
        ),
        # Operating Costs
        'transmission_cost_musd_per_yr': sig_figs(transmission_cost_musd_per_yr, 3),
        # Technical & Engineering Results
        'bht_temp_degc': r['RESERVOIR PARAMETERS']['Bottom-hole temperature']['value'],
        'min_net_generation_mwe': round(sig_figs(min_net_generation_mwe, 3)),
        'avg_net_generation_mwe': round(sig_figs(avg_net_generation_mwe, 3)),
        'max_net_generation_mwe': round(sig_figs(max_net_generation_mwe, 3)),
        'max_total_generation_mwe': round(sig_figs(max_total_generation_mwe, 3)),
        'two_year_avg_net_power_mwe_per_production_well': sig_figs(two_year_avg_net_power_mwe_per_production_well, 2),
        'heat_to_power_conversion_efficiency_pct': sig_figs(
            _q(surf_equip_sim['Heat to Power Conversion Efficiency']).to('percent').magnitude, 3
        ),
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
        'initial_pumping_power_pct_of_net': sig_figs(
            surf_equip_sim['Initial pumping power/net installed power']['value'], 3
        ),
        'orc_unit_count': orc_unit_count,
        'orc_unit_gross_capacity_mw': round(_FPC5_ORC_UNIT_GROSS_CAPACITY_MW),
        'nameplate_capacity_mw': round(orc_unit_count * _FPC5_ORC_UNIT_GROSS_CAPACITY_MW),
        'number_of_wells': _number_of_wells(result),
        'redrilling_years': redrilling_years,
        'redrilling_years_display': _get_list_display(redrilling_years),
        'initial_production_temperature_degc_precise': round(initial_production_temperature_degc, 1),
        'first_cycle_peak_year': first_cycle_peak_year,
        'first_cycle_peak_temperature_degc': round(first_cycle_peak_temperature_degc, 1),
        # TODO port all input and result values here instead of hardcoding them in the template
    }


_ITC_EXCLUDING_INTERCONNECTION_SCENARIO = 'ITC excluding interconnection from basis'
_CURTAILMENT_5PCT_SCENARIO = 'Curtailment (5% flat derate)'
_CURTAILMENT_10PCT_SCENARIO = 'Curtailment (10% flat derate)'


def get_fpc5_scenario_values(
    input_params: GeophiresInputParameters,
    result: GeophiresXResult,
    scenario_irr_changes_pct_pts: dict[str, float] | None = None,
    flow_rate_parametric_rows: list[FlowRateParametricRow] | None = None,
) -> dict[str, Any]:
    """
    :param scenario_irr_changes_pct_pts: IRR changes for the scenarios returned by
        get_fpc5_scenario_input_parameters; simulated if not provided.
    :param flow_rate_parametric_rows: Production flow rate parametric results; loaded from
        FPC5_FLOW_RATE_PARAMETRIC_CSV_PATH if not provided.
    :return: Template values for scenario results cited in the documentation narrative
    """
    scenario_input_params = get_fpc5_scenario_input_parameters(input_params, result)
    if scenario_irr_changes_pct_pts is None:
        scenario_irr_changes_pct_pts = get_irr_changes_pct_pts(input_params, result, scenario_input_params)

    if flow_rate_parametric_rows is None:
        flow_rate_parametric_rows = load_fpc5_flow_rate_parametric()

    params = _get_input_parameters_dict(input_params)
    flow_rate_summary = get_fpc5_flow_rate_parametric_summary(
        flow_rate_parametric_rows,
        float(params['Production Flow Rate per Well']),
        _FPC5_PPA_MINIMUM_NET_GENERATION_MW,
    )

    def _irr_reduction_display(scenario_name: str) -> str:
        return f'{-scenario_irr_changes_pct_pts[scenario_name]:.1f}'

    itc_rate_excluding_interconnection = scenario_input_params[_ITC_EXCLUDING_INTERCONNECTION_SCENARIO][
        'Investment Tax Credit Rate'
    ]

    return {
        'itc_rate_excluding_interconnection_pct': f'{itc_rate_excluding_interconnection * 100:.2f}',
        'itc_rate_excluding_interconnection_pct_1dp': f'{itc_rate_excluding_interconnection * 100:.1f}',
        'itc_excluding_interconnection_irr_reduction_pct_pts': _irr_reduction_display(
            _ITC_EXCLUDING_INTERCONNECTION_SCENARIO
        ),
        'curtailment_5pct_utilization_factor': scenario_input_params[_CURTAILMENT_5PCT_SCENARIO]['Utilization Factor'],
        'curtailment_10pct_utilization_factor': scenario_input_params[_CURTAILMENT_10PCT_SCENARIO][
            'Utilization Factor'
        ],
        'curtailment_5pct_irr_reduction_pct_pts': _irr_reduction_display(_CURTAILMENT_5PCT_SCENARIO),
        'curtailment_10pct_irr_reduction_pct_pts': _irr_reduction_display(_CURTAILMENT_10PCT_SCENARIO),
        'number_of_production_wells': _number_of_production_wells(result),
        'ppa_minimum_net_generation_mw': f'{_FPC5_PPA_MINIMUM_NET_GENERATION_MW:g}',
        'flow_rate_parametric_redrilling_steps_display': _get_list_display(
            [
                f'from {_get_count_word(it.redrills_below)} to {_get_count_word(it.redrills_at)} between '
                f'{it.flow_below_kg_per_s:g} and {it.flow_at_kg_per_s:g} kg/s per well'
                for it in flow_rate_summary.redrilling_steps
            ]
        ),
        'flow_rate_parametric_base_redrills_word': _get_count_word(flow_rate_summary.base_redrills),
        'flow_rate_parametric_max_irr_change_above_base_pct_pts': (
            f'{flow_rate_summary.max_irr_change_above_base_within_band_pct_pts:.2f}'
        ),
        'flow_rate_parametric_minimum_ppa_feasible_kg_per_s': (
            f'{flow_rate_summary.minimum_ppa_feasible_flow_rate_kg_per_s:g}'
        ),
    }


def get_fpc5_scenario_input_parameters(
    input_params: GeophiresInputParameters, result: GeophiresXResult
) -> dict[str, dict[str, Any]]:
    """
    :return: Input parameter overrides for the single-input scenarios cited in the documentation narrative, by
        scenario name. The ITC scenario applies the rate to total installed cost that removes the interconnection cost
        (including its share of inflation and interest during construction) from the ITC basis. The curtailment
        scenarios reduce the utilization factor by 5% and 10% as flat derates. Values are rounded as in the
        sensitivity analysis.
    """
    params = _get_input_parameters_dict(input_params)
    itc_rate = float(params['Investment Tax Credit Rate'])
    total_capex_musd = _q(result.result['CAPITAL COSTS (M$)']['Total CAPEX']).to('MUSD').magnitude
    itc_rate_excluding_interconnection = itc_rate * (
        1.0 - _interconnection_share_of_total_capex_musd(result) / total_capex_musd
    )
    utilization_factor = float(params['Utilization Factor'])

    return {
        _ITC_EXCLUDING_INTERCONNECTION_SCENARIO: {
            'Investment Tax Credit Rate': round(itc_rate_excluding_interconnection, 4)
        },
        _CURTAILMENT_5PCT_SCENARIO: {'Utilization Factor': round(utilization_factor * 0.95, 3)},
        _CURTAILMENT_10PCT_SCENARIO: {'Utilization Factor': round(utilization_factor * 0.90, 3)},
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


def _total_fracture_surface_area_per_well_m2(result: GeophiresXResult) -> float:
    r: dict[str, dict[str, Any]] = result.result
    res_params = r['RESERVOIR PARAMETERS']
    return (
        _q(res_params['Fracture area']).to('m ** 2').magnitude
        * res_params['Number of fractures']['value']
        / _number_of_wells(result)
    )


def _is_stimulated_well_sentinel(param_value: str | None) -> bool:
    """
    GEOPHIRES interprets -1 for Reservoir Stimulation Capital Cost per Production Well (or Injection Well) as an
    indication that the wells are stimulated, with cost apportioned from the per-fracture-surface-area input.
    """
    if param_value is None:
        return False

    try:
        return float(str(param_value).split(',')[0].strip()) == -1
    except ValueError:
        return False


def _interconnection_cost_musd(result: GeophiresXResult) -> float:
    """
    The case study enters grid interconnection cost as One-time Flat License Fees Etc.
    """
    flat_fees = result.result['CAPITAL COSTS (M$)'].get('One-time Flat License Fees Etc')
    if flat_fees is None:
        return 0.0

    return _q(flat_fees).to('MUSD').magnitude


def _annual_license_fees_musd_per_yr(result: GeophiresXResult) -> float:
    """
    The case study enters firm transmission service cost as Annual License Fees Etc.
    Note the value is output with MUSD (rather than MUSD/yr) units, matching the input parameter units.
    """
    annual_fees = result.result['OPERATING AND MAINTENANCE COSTS (M$/yr)'].get('Annual License Fees Etc')
    if annual_fees is None:
        return 0.0

    return float(annual_fees['value'])


def _interconnection_share_of_total_capex_musd(result: GeophiresXResult) -> float:
    """
    Interconnection cost is spent on the construction CAPEX schedule along with the rest of overnight capital cost,
    so its share of inflation and interest during construction is proportional to its share of overnight capital.
    """
    capex = result.result['CAPITAL COSTS (M$)']
    total_capex_musd = _q(capex['Total CAPEX']).to('MUSD').magnitude
    occ_musd = _q(capex['Overnight Capital Cost']).to('MUSD').magnitude
    return total_capex_musd * _interconnection_cost_musd(result) / occ_musd


def _surface_power_plant_pct_of_wellfield_and_plant_capex(result: GeophiresXResult) -> float:
    """
    :return: Surface power plant cost as a percentage of drilling, completion, stimulation, field gathering and
        surface power plant costs (i.e. excluding exploration and interconnection)
    """
    capex = result.result['CAPITAL COSTS (M$)']
    surface_plant_musd = _q(capex['Surface power plant costs']).to('MUSD').magnitude
    wellfield_musd = (
        _drilling_costs_musd(result)
        + _stim_costs_musd(result)
        + _q(capex['Field gathering system costs']).to('MUSD').magnitude
    )
    return surface_plant_musd / (surface_plant_musd + wellfield_musd) * 100.0


def _get_levelized_ppa_price_usd_per_mwh(result: GeophiresXResult) -> float:
    lppa_row_name = 'LPPA Levelized PPA price nominal (cents/kWh)'
    for row in result.result.get('SAM CASH FLOW PROFILE') or []:
        if row and row[0] == lppa_row_name:
            cents_per_kwh_to_usd_per_mwh = 10.0
            return float(row[1]) * cents_per_kwh_to_usd_per_mwh

    raise ValueError(f'{lppa_row_name} not found in SAM cash flow profile.')


def _get_annual_production_temperature_profile_degc(result: GeophiresXResult) -> tuple[list[int], list[float]]:
    profile = result.power_generation_profile
    year_idx = profile[0].index('YEAR')
    temp_idx = profile[0].index('GEOFLUID TEMPERATURE (degC)')
    return [int(row[year_idx]) for row in profile[1:]], [float(row[temp_idx]) for row in profile[1:]]


def _get_redrilling_years(result: GeophiresXResult) -> list[int]:
    """
    Redrilling restores production temperature, so the operating year in which a redrilling event occurs appears as a
    local minimum in the annual average production temperature profile.
    See also generate_fervo_project_cape_5_graphs._get_redrilling_event_indexes, which detects redrilling events at
    time step resolution from the full profile.
    """
    years, temps = _get_annual_production_temperature_profile_degc(result)
    return [years[i] for i in range(1, len(temps) - 1) if temps[i - 1] > temps[i] < temps[i + 1]]


def _get_first_cycle_peak_production_temperature(
    result: GeophiresXResult, redrilling_years: list[int]
) -> tuple[int, float]:
    """
    :return: Year and value of the peak annual production temperature prior to the first redrilling event
    """
    years, temps = _get_annual_production_temperature_profile_degc(result)
    first_cycle_end_idx = years.index(redrilling_years[0]) if len(redrilling_years) > 0 else len(years)
    first_cycle_temps = temps[:first_cycle_end_idx]
    peak_idx = int(np.argmax(first_cycle_temps))
    return years[peak_idx], first_cycle_temps[peak_idx]


def _get_count_word(count: int) -> str:
    words = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
    return words[count] if 0 <= count < len(words) else str(count)


def _get_list_display(items: list[Any]) -> str:
    items_str = [str(it) for it in items]
    if len(items_str) <= 2:
        return ' and '.join(items_str)

    return f'{", ".join(items_str[:-1])}, and {items_str[-1]}'


# Previous version of the case study documented in the Previous Versions section (last updated 2026-07-03). The files
# are copies of tests/examples/Fervo_Project_Cape-5.{txt,out} as of that version.
_FPC5_PREVIOUS_VERSION_FILE_STEM = 'Fervo_Project_Cape-5_2026-07'


def _get_fpc5_previous_version(project_root: Path) -> tuple[GeophiresInputParameters, GeophiresXResult]:
    previous_versions_dir = project_root / 'src/geophires_docs/previous_versions'
    return (
        ImmutableGeophiresInputParameters(
            from_file_path=previous_versions_dir / f'{_FPC5_PREVIOUS_VERSION_FILE_STEM}.txt'
        ),
        GeophiresXResult(str(previous_versions_dir / f'{_FPC5_PREVIOUS_VERSION_FILE_STEM}.out')),
    )


def _get_non_comment_input_parameters_dict(input_params: GeophiresInputParameters) -> dict[str, str]:
    return {
        k: v
        for k, v in _get_input_parameters_dict(input_params).items()
        if not k.startswith(('#', COMMENT_PARAMETER_NAME_PREFIX))
    }


def _get_version_comparison_input_value_display(param_name: str, param_val: str | None) -> str:
    if param_val is None:
        # Defaults are not displayed because they are not necessarily the effective values; for example, per-well
        # stimulation cost defaults do not apply when stimulation cost per fracture surface area is provided.
        return 'Not set'

    if _is_stimulated_well_sentinel(param_val):
        return 'Stimulated (cost from per-area input)'

    if _get_input_parameter_schema_type(param_name) == 'array':
        return param_val.replace(',', ', ')

    try:
        value_display = _get_input_parameter_value_display(param_name, param_val)
    except ValueError:
        # e.g. boolean values
        return param_val

    if param_name == 'Annual License Fees Etc':
        # Parameter units are MUSD, but the value is an annual cost
        value_display += '/yr'

    return value_display


def _format_version_comparison_number(value: float | None, decimals: int) -> str:
    if value is None:
        return '.. N/A'

    return f'{value:,.{decimals}f}'


def _format_version_comparison_change(
    previous_value: float | None, value: float | None, decimals: int, is_percent: bool
) -> str:
    if previous_value is None or value is None:
        return '.. N/A'

    change = value - previous_value
    if round(change, decimals) == 0:
        return 'No change'

    if is_percent:
        return f'{change:+,.{decimals}f} pts'

    if previous_value == 0:
        return f'{change:+,.{decimals}f}'

    return f'{change:+,.{decimals}f} ({change / abs(previous_value) * 100.0:+.0f}%)'


def _result_value(category: str, field: str) -> Callable[[GeophiresXResult], float | None]:
    def _get(result: GeophiresXResult) -> float | None:
        entry = result.result.get(category, {}).get(field)
        if entry is None:
            return None

        return float(entry['value'])

    return _get


def _result_value_or_zero(category: str, field: str) -> Callable[[GeophiresXResult], float | None]:
    """
    For outputs that are only printed when the corresponding input is non-zero
    """

    def _get(result: GeophiresXResult) -> float | None:
        value = _result_value(category, field)(result)
        return 0.0 if value is None else value

    return _get


def _average_pumping_power_pct_of_total_generation(result: GeophiresXResult) -> float:
    surf_equip_sim = result.result['SURFACE EQUIPMENT SIMULATION RESULTS']
    return (
        surf_equip_sim['Average Pumping Power']['value']
        / surf_equip_sim['Average Total Electricity Generation']['value']
        * 100.0
    )


def _total_wells_including_redrilling(result: GeophiresXResult) -> float:
    redrills = result.result['ENGINEERING PARAMETERS']['Number of times redrilling']['value']
    return float((1 + redrills) * _number_of_wells(result))


def _lcoe_usd_per_mwh(result: GeophiresXResult) -> float:
    return float(_q(result.result['SUMMARY OF RESULTS']['Electricity breakeven price']).to('USD / MWh').magnitude)


_CAPEX = 'CAPITAL COSTS (M$)'
_OPEX = 'OPERATING AND MAINTENANCE COSTS (M$/yr)'
_ECON = 'ECONOMIC PARAMETERS'
_SURF = 'SURFACE EQUIPMENT SIMULATION RESULTS'

# (label, value getter, display decimals, whether the value is a percentage)
_FPC5_VERSION_COMPARISON_RESULT_METRICS: list[tuple[str, Callable[[GeophiresXResult], float | None], int, bool]] = [
    ('LCOE ($/MWh)', _lcoe_usd_per_mwh, 1, False),
    ('Levelized PPA price ($/MWh)', _get_levelized_ppa_price_usd_per_mwh, 1, False),
    ('After-tax IRR (%)', _result_value(_ECON, 'After-tax IRR'), 1, True),
    ('Project NPV ($M)', _result_value(_ECON, 'Project NPV'), 1, False),
    ('Levered equity profitability index', _result_value(_ECON, 'Project VIR=PI=PIR'), 2, False),
    ('WACC (%)', _result_value(_ECON, 'WACC'), 2, True),
    ('Investment Tax Credit ($M)', _result_value(_ECON, 'Investment Tax Credit'), 1, False),
    ('Total CAPEX ($M)', _result_value(_CAPEX, 'Total CAPEX'), 1, False),
    ('Total CAPEX ($/kW)', _result_value('SUMMARY OF RESULTS', 'Total CAPEX ($/kW)'), 0, False),
    ('Overnight capital cost ($M)', _result_value(_CAPEX, 'Overnight Capital Cost'), 1, False),
    ('Exploration ($M)', _result_value(_CAPEX, 'Exploration costs'), 1, False),
    ('Well drilling and completion ($M)', _drilling_costs_musd, 1, False),
    ('Well drilling and completion per well ($M)', _drilling_costs_per_well_musd, 2, False),
    ('Stimulation ($M)', _stim_costs_musd, 1, False),
    ('Stimulation per well ($M)', _stim_costs_per_well_musd, 2, False),
    ('Surface power plant ($M)', _result_value(_CAPEX, 'Surface power plant costs'), 1, False),
    ('Field gathering system ($M)', _result_value(_CAPEX, 'Field gathering system costs'), 1, False),
    ('Grid interconnection ($M)', _result_value_or_zero(_CAPEX, 'One-time Flat License Fees Etc'), 1, False),
    ('Total O&M ($M/yr)', _result_value(_OPEX, 'Total operating and maintenance costs'), 1, False),
    ('Redrilling ($M/yr)', _result_value(_OPEX, 'Redrilling costs'), 1, False),
    ('Transmission service ($M/yr)', _result_value_or_zero(_OPEX, 'Annual License Fees Etc'), 1, False),
    ('Production wells', _result_value('SUMMARY OF RESULTS', 'Number of production wells'), 0, False),
    ('Injection wells', _result_value('SUMMARY OF RESULTS', 'Number of injection wells'), 0, False),
    ('Redrilling events', _result_value('ENGINEERING PARAMETERS', 'Number of times redrilling'), 0, False),
    ('Total wells over project lifetime', _total_wells_including_redrilling, 0, False),
    ('Minimum net generation (MW)', _result_value(_SURF, 'Minimum Net Electricity Generation'), 1, False),
    ('Average net generation (MW)', _result_value(_SURF, 'Average Net Electricity Generation'), 1, False),
    ('Maximum net generation (MW)', _result_value(_SURF, 'Maximum Net Electricity Generation'), 1, False),
    ('Maximum total generation (MW)', _result_value(_SURF, 'Maximum Total Electricity Generation'), 1, False),
    (
        'Average annual net generation (GWh)',
        _result_value(_SURF, 'Average Annual Net Electricity Generation'),
        0,
        False,
    ),
    (
        'Initial pumping power / net installed power (%)',
        _result_value(_SURF, 'Initial pumping power/net installed power'),
        1,
        True,
    ),
    ('Average pumping power / average total generation (%)', _average_pumping_power_pct_of_total_generation, 1, True),
    ('Heat to power conversion efficiency (%)', _result_value(_SURF, 'Heat to Power Conversion Efficiency'), 1, True),
    ('Bottom-hole temperature (℃)', _result_value('RESERVOIR PARAMETERS', 'Bottom-hole temperature'), 1, False),
    (
        'Initial production temperature (℃)',
        _result_value('RESERVOIR SIMULATION RESULTS', 'Initial Production Temperature'),
        1,
        False,
    ),
    (
        'Average production temperature (℃)',
        _result_value('RESERVOIR SIMULATION RESULTS', 'Average Production Temperature'),
        1,
        False,
    ),
    (
        'Fracture surface area per well (10⁶ m²)',
        lambda r: _total_fracture_surface_area_per_well_m2(r) / 1e6,
        2,
        False,
    ),
]


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


def generate_fpc_opex_output_table_md(input_params: GeophiresInputParameters, result: GeophiresXResult) -> str:
    table_md = """| Metric | Result Value | Reference Value(s) | Reference Source |
|-----|-----|-----|-----|\n"""

    for output_param_name, result_value_unit_dict in result.result['OPERATING AND MAINTENANCE COSTS (M$/yr)'].items():
        if result_value_unit_dict is None:
            continue

        unit = result_value_unit_dict['unit']
        value_unit_display = (
            f'${result_value_unit_dict["value"]}M/yr'
            if unit == 'MUSD/yr'
            else f'{result_value_unit_dict["value"]} {unit}'
        )

        reference_value_display = '.. N/A'

        if output_param_name == 'Total operating and maintenance costs':
            reference_source_display = '.. N/A '
        elif output_param_name == 'Annual License Fees Etc':
            # Output unit is MUSD (matching the input parameter) although the value is an annual cost
            value_unit_display = f'${result_value_unit_dict["value"]}M/yr'
            reference_value_display = '$16.4M/yr; ~$10M/yr'
            reference_source_display = (
                'Long-term firm point-to-point transmission service for 500 MW, entered as '
                '`Annual License Fees Etc` (see Economic Parameters). Reference values apply 2017 PacifiCorp '
                'OATT Schedule 7 and 1 rates (PacifiCorp, 2017) and the BPA fiscal year 2024–2025 long-term firm '
                'point-to-point rate (BPA, 2026) to 500 MW; the case study value escalates the PacifiCorp rate at '
                '3% per year to 2026.'
            )
        else:
            reference_source_display = _get_output_parameter_description(output_param_name)

            if output_param_name == 'Water costs':
                water_cost_adjustment_param_name = 'Water Cost Adjustment Factor'
                reference_source_display = reference_source_display.split(
                    f'. Provide {water_cost_adjustment_param_name}', maxsplit=1
                )[0]
                water_cost_adjustment_percent = (
                    PlainQuantity(
                        float(_get_input_parameters_dict(input_params)[water_cost_adjustment_param_name]),
                        'dimensionless',
                    )
                    .to('percent')
                    .magnitude
                )
                reference_source_display = (
                    f'{reference_source_display}. '
                    f'The default correlation is adjusted by the {water_cost_adjustment_param_name} parameter value '
                    f'of {water_cost_adjustment_percent:.0f}%.'
                )

            if reference_source_display.startswith(('O&M', 'Total O&M')):
                reference_source_display = reference_source_display.split('. ', maxsplit=1)[1]

            for suffix in ('s', ''):
                reference_source_display = reference_source_display.replace(f'O&M cost{suffix}', 'OPEX')

        table_md += (
            f'| {output_param_name} | {value_unit_display} | {reference_value_display} | {reference_source_display} |\n'
        )

        if output_param_name == 'Total operating and maintenance costs':
            opex_usd_per_kw_per_year = (
                _q(result_value_unit_dict) / PlainQuantity(get_max_net_generation_mwe(result), 'MW')
            ).to('USD / year / kilowatt')

            reference_source = '2024b ATB: 2028 Deep EGS Binary Conservative Scenario (NREL, 2025). '
            # TODO explain why we're higher than ATB (e.g. redrilling not modeled by ATB)

            transmission_cost_musd_per_yr = _annual_license_fees_musd_per_yr(result)
            if transmission_cost_musd_per_yr != 0:
                opex_excluding_transmission_usd_per_kw_per_year = (
                    (_q(result_value_unit_dict) - PlainQuantity(transmission_cost_musd_per_yr, 'MUSD / year'))
                    / PlainQuantity(get_max_net_generation_mwe(result), 'MW')
                ).to('USD / year / kilowatt')
                reference_source += (
                    f'The case study value includes transmission service '
                    f'(${(opex_usd_per_kw_per_year - opex_excluding_transmission_usd_per_kw_per_year).magnitude:.0f}'
                    f'/kW-yr); excluding it, total OPEX is '
                    f'${opex_excluding_transmission_usd_per_kw_per_year.magnitude:.0f}/kW-yr.'
                )

            table_md += f'| {output_param_name}: $/kW-yr | ${opex_usd_per_kw_per_year.magnitude:.2f}/kW-yr | $226.31/kW-yr | {reference_source} |\n'

    return table_md


def generate_fpc5_previous_version_input_changes_table_md(
    previous_input_params: GeophiresInputParameters, input_params: GeophiresInputParameters
) -> str:
    """
    :return: Markdown table of input parameters whose values differ between the previous version and this version,
        including parameters that were added or removed
    """
    previous_params = _get_non_comment_input_parameters_dict(previous_input_params)
    params = _get_non_comment_input_parameters_dict(input_params)

    param_names = list(params.keys()) + [it for it in previous_params if it not in params]

    table_md = '| Parameter | Previous Version | This Version |\n|---|---|---|\n'
    for param_name in param_names:
        previous_value_display = _get_version_comparison_input_value_display(
            param_name, previous_params.get(param_name)
        )
        value_display = _get_version_comparison_input_value_display(param_name, params.get(param_name))
        if previous_value_display == value_display:
            continue

        table_md += f'| {param_name} | {previous_value_display} | {value_display} |\n'

    return table_md.strip()


def generate_fpc5_previous_version_result_changes_table_md(
    previous_result: GeophiresXResult, result: GeophiresXResult
) -> str:
    """
    :return: Markdown table comparing key results of the previous version and this version
    """
    table_md = '| Result | Previous Version | This Version | Change |\n|---|---|---|---|\n'
    for label, getter, decimals, is_percent in _FPC5_VERSION_COMPARISON_RESULT_METRICS:
        previous_value = getter(previous_result)
        value = getter(result)
        table_md += (
            f'| {label} '
            f'| {_format_version_comparison_number(previous_value, decimals)} '
            f'| {_format_version_comparison_number(value, decimals)} '
            f'| {_format_version_comparison_change(previous_value, value, decimals, is_percent)} |\n'
        )

    return table_md.strip()


def generate_fervo_project_cape_5_md(
    input_params: GeophiresInputParameters,
    result: GeophiresXResult,
    res_eng_reference_sim_params: dict[str, Any] | None = None,
    project_root: Path = _PROJECT_ROOT,
    previous_version: tuple[GeophiresInputParameters, GeophiresXResult] | None = None,
    scenario_irr_changes_pct_pts: dict[str, float] | None = None,
) -> None:
    if res_eng_reference_sim_params is None:
        res_eng_reference_sim_params = {}

    if previous_version is None:
        previous_version = _get_fpc5_previous_version(project_root)

    result_values: dict[str, Any] = get_result_values(result)

    # noinspection PyDictCreation
    template_values = {
        **get_fpc5_input_parameter_values(input_params, result),
        **result_values,
        **get_fpc5_scenario_values(input_params, result, scenario_irr_changes_pct_pts),
    }

    for template_key, md_method in {
        'opex_result_outputs_table_md': generate_fpc_opex_output_table_md,
        'reservoir_parameters_table_md': generate_fpc_reservoir_parameters_table_md,
        'surface_plant_parameters_table_md': generate_fpc_surface_plant_parameters_table_md,
        'well_bores_parameters_table_md': generate_fpc_well_bores_parameters_table_md,
        'economics_parameters_table_md': generate_fpc_economics_parameters_table_md,
        'construction_parameters_table_md': generate_fpc_construction_parameters_table_md,
    }.items():
        template_values[template_key] = md_method(input_params, result)

    template_values['reservoir_engineering_reference_simulation_params_table_md'] = (
        generate_res_eng_reference_sim_params_table_md(input_params, res_eng_reference_sim_params)
    )

    template_values['previous_version_input_changes_table_md'] = generate_fpc5_previous_version_input_changes_table_md(
        previous_version[0], input_params
    )
    template_values['previous_version_result_changes_table_md'] = (
        generate_fpc5_previous_version_result_changes_table_md(previous_version[1], result)
    )

    docs_dir = project_root / 'docs'

    # Set up Jinja environment
    # The template renders markdown, so only HTML and XML templates are autoescaped. HTML-escaping characters such as
    # '&' in parameter comments and table labels would be escaped again by the markdown-to-reStructuredText conversion
    # and render literally in the documentation (e.g. 'O&amp;M').
    env = Environment(loader=FileSystemLoader(docs_dir), autoescape=select_autoescape(['html', 'xml']))
    template = env.get_template('Fervo_Project_Cape-5.md.jinja')

    # Render template
    _log.info('Rendering template...')
    output = template.render(**template_values)

    # Write output
    output_file = docs_dir / 'Fervo_Project_Cape-5.md'
    output_file.write_text(output, encoding='utf-8')

    _log.info(f'✓ Generated {output_file}')
    _log.info('\nKey results:')
    _log.info(f"\tLCOE: ${template_values['lcoe_usd_per_mwh']}/MWh")
    _log.info(f"\tIRR: {template_values['irr_pct']}%")
    _log.info(f"\tTotal CAPEX: ${template_values['total_capex_gusd']}B")


def main(project_root: Path | None = None):
    """
    Generate Fervo_Project_Cape-5.md (markdown documentation) from the Jinja template.
    """
    global _current_project_root

    if project_root is None:
        project_root = _get_project_root()

    _current_project_root = project_root

    input_params: GeophiresInputParameters = ImmutableGeophiresInputParameters(
        from_file_path=_get_fpc5_input_file_path(project_root)
    )
    result = GeophiresXResult(_get_fpc5_result_file_path(project_root))
    generate_fervo_project_cape_5_md(input_params, result, project_root=project_root)


if __name__ == '__main__':
    main()

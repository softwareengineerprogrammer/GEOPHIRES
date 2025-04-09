from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from decimal import Decimal

import numpy as np
# noinspection PyPackageRequirements
from PySAM import CustomGeneration

# noinspection PyPackageRequirements
from PySAM import Grid

# noinspection PyPackageRequirements
from PySAM import Singleowner

# noinspection PyPackageRequirements
import PySAM.Utilityrate5 as UtilityRate

import geophires_x.Model as Model
from geophires_x.OptionList import EndUseOptions


@lru_cache(maxsize=12)
def calculate_sam_economics(
        model: Model
) -> dict[str, dict[str, Any]]:
    custom_gen = CustomGeneration.new()
    grid = Grid.from_existing(custom_gen)
    utility_rate = UtilityRate.from_existing(custom_gen)
    single_owner = Singleowner.from_existing(custom_gen)

    project_name = 'Generic_400_MWe'
    project_dir = Path(os.path.dirname(model.economics.MyPath), 'sam_economics', project_name)
    # noinspection SpellCheckingInspection
    file_names = [f'{project_name}_{module}' for module in ['custom_generation', 'grid', 'utilityrate5', 'singleowner']]
    modules = [custom_gen, grid, utility_rate, single_owner]

    for module_file, module in zip(file_names, modules):
        with open(Path(project_dir, f'{module_file}.json'), encoding='utf-8') as file:
            data = json.load(file)
            for k, v in data.items():
                if k != 'number_inputs':
                    module.value(k, v)

    for k, v in _get_single_owner_parameters(model).items():
        single_owner.value(k, v)

    for module in modules:
        module.execute()

    display_data = [
        ('LCOE', single_owner.Outputs.lcoe_real, 'cents/kWh'),
        ('IRR', single_owner.Outputs.project_return_aftertax_irr, '%'),
        ('NPV', single_owner.Outputs.project_return_aftertax_npv * 1e-6, 'MUSD'),
        ('CAPEX', single_owner.Outputs.adjusted_installed_cost * 1e-6, 'MUSD'),

        ('Electricity Price (cents/kWh)', [p * 1e-2 for p in single_owner.Outputs.cf_ppa_price], 'cents/kWh'),
        ('Electricity Ann. Rev. (MUSD/yr)', [e * 1e-6 for e in single_owner.Outputs.cf_energy_value], '(MUSD/yr)'),

        # TODO determine if this is the 'appropriate' cashflow variable
        ('Project Net Rev (MUSD/yr)', [c * 1e-6 for c in single_owner.Outputs.cf_pretax_cashflow], 'MUSD/yr'),

        # ('Gross Output', gt.Outputs.gross_output, 'MW'),
        # ('Net Output', gt.Outputs.gross_output - gt.Outputs.pump_work, 'MW')
    ]

    # max_field_name_len = max(len(x[0]) for x in display_data)

    ret = {}
    for e in display_data:
        # field_display = e[0] + ':' + ' ' * (max_field_name_len - len(e[0]) - 1)
        # print(f'{field_display}\t{sig_figs(e[1], 5)} {e[2]}')
        ret[e[0]] = {'value': _sig_figs(e[1], 5), 'unit': e[2]}

    return ret


def _get_single_owner_parameters(model: Model) -> dict[str, Any]:
    econ = model.economics

    ret: dict[str, Any] = {}

    itc = econ.CCap.value * econ.RITC.value
    total_capex_musd = (
            econ.CCap.value - itc
    )
    ret['total_installed_cost'] = total_capex_musd * 1e6

    opex_musd = econ.Coam.value
    ret['om_fixed'] = [opex_musd * 1e6]

    average_net_generation_MW = _get_average_net_generation_MW(model)
    ret['system_capacity'] = average_net_generation_MW * 1e3

    geophires_ctr_tenths = Decimal(econ.CTR.value)
    fed_rate_tenths = geophires_ctr_tenths * (Decimal(0.7))
    state_rate_tenths = geophires_ctr_tenths - fed_rate_tenths
    ret['federal_tax_rate'] = [float(fed_rate_tenths * Decimal(100))]
    ret['state_tax_rate'] = [float(state_rate_tenths * Decimal(100))]

    geophires_itc_tenths = Decimal(econ.RITC.value)
    ret['itc_fed_percent'] = [float(geophires_itc_tenths * Decimal(100))]

    geophires_ptr_tenths = Decimal(econ.PTR.value)
    ret['property_tax_rate'] = float(geophires_ptr_tenths * Decimal(100))

    ret['ppa_price_input'] = [econ.ElecStartPrice.value]

    # TODO interest rate
    # TODO debt/equity ratio

    return ret


@lru_cache(maxsize=12)
def calculate_sam_economics_cashflow(model: Model):
    """
    ENERGY
    Electricity Provided -> cf_energy_sales

    REVENUE
    Electricity Price -> cf_ppa_price
    Electricity Revenue -> cf_energy_value

    OPERATING EXPENSES
    O&M fixed expense -> cf_om_fixed_expense

    PROJECT RETURNS
    Net Revenue -> cf_total_revenue
    """

    econ = model.economics
    sam_econ = calculate_sam_economics(model)

    construction_years = model.surfaceplant.construction_years.value
    plant_lifetime = model.surfaceplant.plant_lifetime.value
    total_duration = plant_lifetime + construction_years

    # econ.ElecRevenue.value = [0.0] * total_duration
    # econ.ElecCummRevenue.value = [0.0] * total_duration
    # econ.HeatRevenue.value = [0.0] * total_duration
    # econ.HeatCummRevenue.value = [0.0] * total_duration
    # econ.CoolingRevenue.value = [0.0] * total_duration
    # econ.CoolingCummRevenue.value = [0.0] * total_duration
    # econ.CarbonRevenue.value = [0.0] * total_duration
    # econ.CarbonCummCashFlow.value = [0.0] * total_duration
    # econ.TotalRevenue.value = [0.0] * total_duration
    # econ.TotalCummRevenue.value = [0.0] * total_duration
    # econ.CarbonThatWouldHaveBeenProducedTotal.value = 0.0

    def _cumm(cash_flow: list) -> list:
        cumm_cash_flow = [0.0] * total_duration
        for i in range(construction_years, total_duration, 1):
            cumm_cash_flow[i] = cumm_cash_flow[i - 1] + cash_flow[i]

        return cumm_cash_flow

    # Based on the style of the project, calculate the revenue & cumulative revenue
    if model.surfaceplant.enduse_option.value == EndUseOptions.ELECTRICITY:
        econ.ElecPrice.value = sam_econ['Electricity Price (cents/kWh)']['value'].copy()
        econ.ElecRevenue.value = sam_econ['Electricity Ann. Rev. (MUSD/yr)']['value'].copy()  # FIXME WIP
        econ.ElecCummRevenue.value = _cumm(econ.ElecRevenue.value)

        # econ.ElecRevenue.value, econ.ElecCummRevenue.value = CalculateRevenue(
        #     model.surfaceplant.plant_lifetime.value, model.surfaceplant.construction_years.value,
        #     model.surfaceplant.NetkWhProduced.value, econ.ElecPrice.value)
        # econ.TotalRevenue.value = econ.ElecRevenue.value.copy()
        # econ.TotalCummRevenue.value = econ.ElecCummRevenue.value
    else:
        raise ValueError(f'Unexpected End-Use Option: {model.surfaceplant.enduse_option.value}')

    if econ.DoCarbonCalculations.value:
        raise NotImplementedError

        # FIXME TODO
        #     econ.CarbonRevenue.value, econ.CarbonCummCashFlow.value, econ.CarbonThatWouldHaveBeenProducedAnnually.value, \
        #      econ.CarbonThatWouldHaveBeenProducedTotal.value = econ.CalculateCarbonRevenue(model,
        #           model.surfaceplant.plant_lifetime.value, model.surfaceplant.construction_years.value,
        #           econ.CarbonPrice.value, econ.GridCO2Intensity.value, econ.NaturalGasCO2Intensity.value,
        #           model.surfaceplant.NetkWhProduced.value, model.surfaceplant.HeatkWhProduced.value)
        #     for i in range(model.surfaceplant.construction_years.value, model.surfaceplant.plant_lifetime.value + model.surfaceplant.construction_years.value, 1):
        #         econ.TotalRevenue.value[i] = econ.TotalRevenue.value[i] + econ.CarbonRevenue.value[i]
        #         #econ.TotalCummRevenue.value[i] = econ.TotalCummRevenue.value[i] + econ.CarbonCummCashFlow.value[i]

    # FIXME WIP TODO pass/reconcile non-1 construction years in/from SAM
    # for the sake of display, insert zeros at the beginning of the pricing arrays
    for i in range(0, model.surfaceplant.construction_years.value, 1):
        # econ.ElecPrice.value.insert(0, 0.0)
        econ.HeatPrice.value.insert(0, 0.0)
        econ.CoolingPrice.value.insert(0, 0.0)
        econ.CarbonPrice.value.insert(0, 0.0)

    # Insert the cost of construction into the front of the array that will be used to calculate NPV
    # the convention is that the upfront CAPEX is negative
    # This is the same for all projects
    # ProjectCAPEXPerConstructionYear = econ.CCap.value / model.surfaceplant.construction_years.value
    # for i in range(0, model.surfaceplant.construction_years.value, 1):
    #     econ.TotalRevenue.value[i] = -1.0 * ProjectCAPEXPerConstructionYear
    #     econ.TotalCummRevenue.value[i] = -1.0 * ProjectCAPEXPerConstructionYear
    #        econ.TotalRevenue.value, econ.TotalCummRevenue.value = CalculateTotalRevenue(
    #            model.surfaceplant.plant_lifetime.value, model.surfaceplant.construction_years.value, econ.CCap.value,
    #                econ.Coam.value, econ.TotalRevenue.value, econ.TotalCummRevenue.value)

    econ.TotalRevenue.value = sam_econ['Project Net Rev (MUSD/yr)']['value'].copy()

    econ.TotalCummRevenue.value = _cumm(econ.TotalRevenue.value)


def _get_average_net_generation_MW(model: Model) -> float:
    return np.average(model.surfaceplant.NetElectricityProduced.value)


def _sig_figs(val: float | list[float] | tuple[float], num_sig_figs: int) -> float:
    if val is None:
        return None

    if isinstance(val, list) or isinstance(val, tuple):
        return [_sig_figs(v, num_sig_figs) for v in val]

    try:
        return float('%s' % float(f'%.{num_sig_figs}g' % val))  # pylint: disable=consider-using-f-string
    except TypeError as te:
        raise RuntimeError from te

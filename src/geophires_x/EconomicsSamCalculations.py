from __future__ import annotations

from dataclasses import dataclass, field
from math import isnan
from typing import Any

import numpy_financial as npf
from geophires_x.EconomicsSamCashFlow import _SAM_CASH_FLOW_NAN_STR
from geophires_x.EconomicsSamPreRevenue import PreRevenueCostsAndCashflow, _TOTAL_AFTER_TAX_RETURNS_CASH_FLOW_ROW_NAME
from geophires_x.EconomicsUtils import overnight_capital_cost_output_parameter, total_capex_parameter_output_parameter, \
    royalty_cost_output_parameter, after_tax_irr_parameter, nominal_discount_rate_parameter, wacc_output_parameter, \
    moic_parameter, project_vir_parameter, project_payback_period_parameter
from geophires_x.GeoPHIRESUtils import is_float
from geophires_x.Parameter import OutputParameter
from geophires_x.Units import Units, EnergyCostUnit, CurrencyUnit


@dataclass
class SamEconomicsCalculations:
    sam_cash_flow_profile: list[list[Any]]
    pre_revenue_costs_and_cash_flow: PreRevenueCostsAndCashflow

    lcoe_nominal: OutputParameter = field(
        default_factory=lambda: OutputParameter(
            UnitType=Units.ENERGYCOST,
            CurrentUnits=EnergyCostUnit.CENTSSPERKWH,
        )
    )

    @property
    def _sam_repro_lcoe_nominal_derived_cents_per_kWh(self) -> float:
        """
        FIXME WIP...
        """

        cash_flow: list[list[Any]] = self.sam_cash_flow_profile_all_years

        def _get_row(row_name__: str) -> list[Any]:
            for r in cash_flow:
                if r[0] == row_name__:
                    return r[1:]

            raise ValueError(f'Could not find row with name {row_name__}')

        equity_amount_usd = [float(it) for it in _get_row('Issuance of equity ($)') if is_float(it)][0]

        def _get_row_values(row_name_: str) -> list[float]:
            row_values_raw = _get_row(row_name_)
            row_values = [float(it) for it in row_values_raw if is_float(it)]
            return row_values

        def _get_pv(row_name: str) -> int:
            row_values = _get_row_values(row_name)

            row_values_pv = npf.npv(
                self.nominal_discount_rate.quantity().to('dimensionless').magnitude,
                row_values,
            )
            return int(round(row_values_pv))

        annual_costs_pv_usd = -1.0 * _get_pv('Annual costs ($)')
        electricity_to_grid_pv_kWh = _get_pv('Electricity to grid (kWh)')
        lcoe_nominal_derived = round((annual_costs_pv_usd / electricity_to_grid_pv_kWh) * 100.0, 2)

        return lcoe_nominal_derived

    @property
    def _adjusted_annual_costs_and_annual_energy_pvs(self) -> tuple[float, float]:
        cash_flow: list[list[Any]] = self.sam_cash_flow_profile

        def _get_row(row_name__: str) -> list[Any]:
            for r in cash_flow:
                if r[0] == row_name__:
                    return r[1:]
            raise ValueError(f'Could not find row with name {row_name__}')

        def _get_aligned_values(row_name_: str) -> list[float]:
            # CRITICAL: Do not filter out empty strings. Replace them with 0.0.
            # This preserves the timeline so Year 1 of operations is discounted
            # by the correct number of construction years.
            row_raw = _get_row(row_name_)
            return [float(it) if is_float(it) else 0.0 for it in row_raw]

        def _get_pv(row_name: str) -> float:
            values = _get_aligned_values(row_name)
            rate = self.nominal_discount_rate.quantity().to('dimensionless').magnitude
            return npf.npv(rate, values)

        annual_costs_row_name = 'Annual costs ($)'
        electricity_to_grid_row_name = 'Electricity to grid (kWh)'

        # 1. PV of Costs
        # "Annual costs" in the profile are derived as (Returns - Revenue).
        # During construction, Returns are negative (outflows).
        # We invert the sign because LCOE numerator represents "Total Life Cycle Cost" as a positive magnitude.
        annual_costs_pv_usd = -1.0 * _get_pv(annual_costs_row_name)

        # 2. PV of Energy
        # Backfilled with 0.0 during construction via _get_aligned_values
        electricity_to_grid_pv_kWh = _get_pv(electricity_to_grid_row_name)

        return annual_costs_pv_usd, electricity_to_grid_pv_kWh

    @property
    def lcoe_nominal_derived_cents_per_kWh(self) -> float:
        """
        Calculates Nominal LCOE based on the full stitched cash flow profile.
        Ensures construction years (zeros) are included in discounting to align
        PV(Costs) and PV(Energy) to the same start year.
        """

        # cash_flow: list[list[Any]] = self.sam_cash_flow_profile_all_years
        #
        # def _get_row(row_name__: str) -> list[Any]:
        #     for r in cash_flow:
        #         if r[0] == row_name__:
        #             return r[1:]
        #     raise ValueError(f'Could not find row with name {row_name__}')
        #
        # def _get_aligned_values(row_name_: str) -> list[float]:
        #     # CRITICAL: Do not filter out empty strings. Replace them with 0.0.
        #     # This preserves the timeline so Year 1 of operations is discounted
        #     # by the correct number of construction years.
        #     row_raw = _get_row(row_name_)
        #     return [float(it) if is_float(it) else 0.0 for it in row_raw]
        #
        # def _get_pv(row_name: str) -> float:
        #     values = _get_aligned_values(row_name)
        #     rate = self.nominal_discount_rate.quantity().to('dimensionless').magnitude
        #     return npf.npv(rate, values)
        #
        # # 1. PV of Costs
        # # "Annual costs" in the profile are derived as (Returns - Revenue).
        # # During construction, Returns are negative (outflows).
        # # We invert the sign because LCOE numerator represents "Total Life Cycle Cost" as a positive magnitude.
        # annual_costs_pv_usd = -1.0 * _get_pv('Annual costs ($)')
        #
        # # 2. PV of Energy
        # # Backfilled with 0.0 during construction via _get_aligned_values
        # electricity_to_grid_pv_kWh = _get_pv('Electricity to grid (kWh)')

        # annual_costs_pv_usd, electricity_to_grid_pv_kWh =  self._adjusted_annual_costs_and_annual_energy_pvs

        cash_flow: list[list[Any]] = self.sam_cash_flow_profile_all_years

        def _get_row(row_name__: str) -> list[Any]:
            for r in cash_flow:
                if r[0] == row_name__:
                    return r[1:][-1]
            raise ValueError(f'Could not find row with name {row_name__}')

        annual_costs_pv_usd, electricity_to_grid_pv_kWh = _get_row('Present value of annual costs ($)') , _get_row('Present value of annual energy nominal (kWh)')

        if electricity_to_grid_pv_kWh == 0:
            return 0.0

        # 3. Calculate LCOE
        # (USD / kWh) * 100 cents/USD
        lcoe_nominal_derived = (annual_costs_pv_usd / electricity_to_grid_pv_kWh) * 100.0

        return round(lcoe_nominal_derived, 2)

    overnight_capital_cost: OutputParameter = field(default_factory=overnight_capital_cost_output_parameter)

    capex: OutputParameter = field(default_factory=total_capex_parameter_output_parameter)

    royalties_opex: OutputParameter = field(default_factory=royalty_cost_output_parameter)

    project_npv: OutputParameter = field(
        default_factory=lambda: OutputParameter(
            UnitType=Units.CURRENCY,
            CurrentUnits=CurrencyUnit.MDOLLARS,
        )
    )

    after_tax_irr: OutputParameter = field(default_factory=after_tax_irr_parameter)
    nominal_discount_rate: OutputParameter = field(default_factory=nominal_discount_rate_parameter)
    wacc: OutputParameter = field(default_factory=wacc_output_parameter)
    moic: OutputParameter = field(default_factory=moic_parameter)
    project_vir: OutputParameter = field(default_factory=project_vir_parameter)

    project_payback_period: OutputParameter = field(default_factory=project_payback_period_parameter)
    """TODO remove or clarify project payback period: https://github.com/NREL/GEOPHIRES-X/issues/413"""

    @property
    def _pre_revenue_years_count(self) -> int:
        return len(
            self.pre_revenue_costs_and_cash_flow.pre_revenue_cash_flow_profile_dict[
                _TOTAL_AFTER_TAX_RETURNS_CASH_FLOW_ROW_NAME
            ]
        )

    @property
    def sam_cash_flow_profile_all_years(self) -> list[list[Any]]:
        ret: list[list[Any]] = self.sam_cash_flow_profile.copy()
        col_count = len(self.sam_cash_flow_profile[0])

        pre_revenue_years_to_insert = self._pre_revenue_years_count - 1

        construction_rows: list[list[Any]] = [['CONSTRUCTION'] + [''] * (len(self.sam_cash_flow_profile[0]) - 1)]

        for row_index in range(len(self.sam_cash_flow_profile)):
            pre_revenue_row_content = [''] * pre_revenue_years_to_insert
            insert_index = 1

            if row_index == 0:
                for pre_revenue_year in range(pre_revenue_years_to_insert):
                    negative_year_index: int = self._pre_revenue_years_count - 1 - pre_revenue_year
                    pre_revenue_row_content[pre_revenue_year] = f'Year -{negative_year_index}'

                for _, row_ in enumerate(self.pre_revenue_costs_and_cash_flow.pre_revenue_cash_flow_profile):
                    pre_revenue_row = row_.copy()
                    pre_revenue_row.extend([''] * (col_count - len(pre_revenue_row)))
                    construction_rows.append(pre_revenue_row)

            #  TODO zero-vectors e.g. Debt principal payment ($)

            adjusted_row = [ret[row_index][0]] + pre_revenue_row_content + ret[row_index][insert_index:]
            ret[row_index] = adjusted_row

        construction_rows.append([''] * len(self.sam_cash_flow_profile[0]))
        for construction_row in reversed(construction_rows):
            ret.insert(1, construction_row)

        def _get_row_index(row_name_: str) -> list[Any]:
            return [it[0] for it in ret].index(row_name_)

        def _get_row(row_name__: str) -> list[Any]:
            for r in ret:
                if r[0] == row_name__:
                    return r[1:]

            raise ValueError(f'Could not find row with name {row_name__}')

        after_tax_cash_flow: list[float] = (
            _get_row('Total after-tax returns [construction] ($)')
            + _get_row('Total after-tax returns ($)')[self._pre_revenue_years_count :]
        )
        after_tax_cash_flow = [float(it) for it in after_tax_cash_flow if is_float(it)]
        npv_usd = []
        irr_pct = []
        for year in range(len(after_tax_cash_flow)):
            npv_usd.append(
                round(
                    npf.npv(
                        self.nominal_discount_rate.quantity().to('dimensionless').magnitude,
                        after_tax_cash_flow[: year + 1],
                    )
                )
            )

            year_irr = npf.irr(after_tax_cash_flow[: year + 1]) * 100.0
            irr_pct.append(year_irr if not isnan(year_irr) else _SAM_CASH_FLOW_NAN_STR)

        ret[_get_row_index('After-tax cumulative NPV ($)')] = ['After-tax cumulative NPV ($)'] + npv_usd
        ret[_get_row_index('After-tax cumulative IRR (%)')] = ['After-tax cumulative IRR (%)'] + irr_pct

        adjusted_costs_pv, adjusted_energy_pv = self._adjusted_annual_costs_and_annual_energy_pvs
        annual_costs_pv_row_name = 'Present value of annual costs ($)'
        ret[_get_row_index(annual_costs_pv_row_name)] = [
            annual_costs_pv_row_name,
            *(['']*pre_revenue_years_to_insert),
            adjusted_costs_pv
            ]

        annual_energy_pv_row_name = 'Present value of annual energy nominal (kWh)'
        # ret[_get_row_index(annual_energy_pv_row_name)] =adjusted_energy_pv
        ret[_get_row_index(annual_energy_pv_row_name)] = [
            annual_energy_pv_row_name,
             * ([''] * pre_revenue_years_to_insert),
            adjusted_energy_pv
        ]
        return ret

import math
import sys
import os
import numpy as np
import numpy_financial as npf
import geophires_x.Economics as Economics
import geophires_x.Model as Model
from geophires_x.EconomicsUtils import expand_schedule
from geophires_x.OptionList import EndUseOptions, EconomicModel
from geophires_x.Parameter import listParameter, OutputParameter
from geophires_x.Units import *


class EconomicsAddOns(Economics.Economics):
    def __init__(self, model: Model):
        """
        The __init__ function is called automatically when a class is instantiated.
        It initializes the attributes of an object, and sets default values for certain arguments that can be
        overridden by user input.
        The __init__ function is used to set up all the parameters in Economics AddOns.
        Set up all the Parameters that will be predefined by this class using the different types of parameter classes.
        Setting up includes giving it a name, a default value, The Unit Type (length, volume, temperature, etc.)
        and Unit Name of that value, sets it as required (or not), sets allowable range, the error message if
        that range is exceeded, the ToolTip Text, and the name of the class that created it.
        This includes setting up temporary variables that will be available to all the class but noy read in by user,
        or used for Output
        This also includes all Parameters that are calculated and then published using the Printouts function.
        If you choose to subclass this master class, you can do so before or after you create your own parameters.
        If you do, you can also choose to call this method from you class, which will effectively add and
        set all these parameters to your class.
        set up the parameters using the Parameter Constructors (intParameter, floatParameter, strParameter, etc.);
        initialize with their name, default value, and valid range (if int or float).  Optionally, you can specify:
        Required (is it required to run? default value = False), ErrMessage (what GEOPHIRES will report if the value
        provided is invalid, "assume default value (see manual)"), ToolTipText (when there is a GIU, this is the
        text that the user will see, "This is ToolTip Text"), UnitType (the type of units associated with this
        parameter (length, temperature, density, etc), Units.NONE), CurrentUnits (what the units are for this
        parameter (meters, Celsius, gm/cc, etc., Units:NONE), and PreferredUnits (usually equal to CurrentUnits,
        but these are the units that the calculations assume when running, Units.NONE
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """

        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().__init__(model)  # initialize the parent parameters and variables
        sclass = str(__class__).replace("<class \'", "")
        self.MyClass = sclass.replace("\'>", "")
        self.MyPath = os.path.abspath(__file__)

        def multi_addon_tooltip_text(param_name: str) -> str:
            return (f'If using multiple add-ons: either (1) specify this value as an array or '
                    f'(2) use multiple parameters suffixed with a number '
                    f'e.g. \'{param_name} 1\', \'{param_name} 2\', etc.')

        self.AddOnNickname = self.ParameterDict[self.AddOnNickname.Name] = listParameter(
            "AddOn Nickname",
            UnitType=Units.NONE,
            Min=0.0,
            Max=1000.0,
            ToolTipText=multi_addon_tooltip_text("AddOn Nickname")
        )
        self.AddOnCAPEX = self.ParameterDict[self.AddOnCAPEX.Name] = listParameter(
            "AddOn CAPEX",
            Min=0.0,
            Max=1000.0,
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS,
            ToolTipText=multi_addon_tooltip_text("AddOn CAPEX")
        )
        self.AddOnOPEXPerYear = self.ParameterDict[self.AddOnOPEXPerYear.Name] = listParameter(
            "AddOn OPEX",
            Min=0.0,
            Max=1000.0,
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            ToolTipText=f'Annual operating cost. {multi_addon_tooltip_text("AddOn OPEX")}'
        )
        self.AddOnElecGainedPerYear = self.ParameterDict[self.AddOnElecGainedPerYear.Name] = listParameter(
            "AddOn Electricity Gained",
            Min=0.0,
            Max=1000.0,
            UnitType=Units.ENERGYFREQUENCY,
            PreferredUnits=EnergyFrequencyUnit.KWPERYEAR,
            CurrentUnits=EnergyFrequencyUnit.KWPERYEAR,
            ToolTipText=f'Annual electricity gained. {multi_addon_tooltip_text("AddOn Electricity Gained")}'
        )
        self.AddOnHeatGainedPerYear = self.ParameterDict[self.AddOnHeatGainedPerYear.Name] = listParameter(
            "AddOn Heat Gained",
            Min=0.0,
            Max=1000.0,
            UnitType=Units.ENERGYFREQUENCY,
            PreferredUnits=EnergyFrequencyUnit.KWPERYEAR,
            CurrentUnits=EnergyFrequencyUnit.KWPERYEAR,
            ToolTipText=f'Annual heat gained. {multi_addon_tooltip_text("AddOn Heat Gained")}'
        )
        self.AddOnProfitGainedPerYear = self.ParameterDict[self.AddOnProfitGainedPerYear.Name] = listParameter(
            "AddOn Profit Gained",
            Min=0.0,
            Max=1000.0,
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            ToolTipText=f'Annual profit gained. {multi_addon_tooltip_text("AddOn Profit Gained")}'
        )
        self.AddOnAppliesDuringConstruction = self.ParameterDict[
            self.AddOnAppliesDuringConstruction.Name
        ] = listParameter(
            'AddOn Applies During Construction',
            UnitType=Units.NONE,
            ToolTipText='If True, the add-on schedule index 0 corresponds to the first '
                        'construction year. If False (default), index 0 corresponds to '
                        'operational year 1 and construction years are filled with 0.0. '
                        f'{multi_addon_tooltip_text("AddOn Applies During Construction")}'
        )

        self.AddOnGoesToRoyaltyHolder = self.ParameterDict[
            self.AddOnGoesToRoyaltyHolder.Name
        ] = listParameter(
            'AddOn Goes To Royalty Holder',
            UnitType=Units.NONE,
            ToolTipText='If True, the cash flows from this add-on (e.g. negative profit '
                        'acting as a payment) are aggregated into the royalty holder cash '
                        'flow for NPV and revenue tracking. Default is False. '
                        f'{multi_addon_tooltip_text("AddOn Goes To Royalty Holder")}'
        )

        # local variables that need initialization
        # results
        self.AddOnCAPEXTotal = self.OutputParameterDict[self.AddOnCAPEXTotal.Name] = OutputParameter(
            "AddOn CAPEX Total",
            display_name='Total Add-on CAPEX',
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS,
        )
        self.AddOnOPEXTotalPerYear = self.OutputParameterDict[self.AddOnOPEXTotalPerYear.Name] = OutputParameter(
            "AddOn OPEX Total Per Year",
            display_name='Total Add-on OPEX',
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.AddOnElecGainedTotalPerYear = self.OutputParameterDict[
            self.AddOnElecGainedTotalPerYear.Name] = OutputParameter(
            "AddOn Electricity Gained Total Per Year",
            UnitType=Units.ENERGYFREQUENCY,
            PreferredUnits=EnergyFrequencyUnit.KWPERYEAR,
            CurrentUnits=EnergyFrequencyUnit.KWPERYEAR
        )
        self.AddOnHeatGainedTotalPerYear = self.OutputParameterDict[
            self.AddOnHeatGainedTotalPerYear.Name] = OutputParameter(
            "AddOn Heat Gained Total Per Year",
            UnitType=Units.ENERGYFREQUENCY,
            PreferredUnits=EnergyFrequencyUnit.KWPERYEAR,
            CurrentUnits=EnergyFrequencyUnit.KWPERYEAR
        )
        self.AddOnProfitGainedTotalPerYear = self.OutputParameterDict[
            self.AddOnProfitGainedTotalPerYear.Name] = OutputParameter(
            "AddOn Profit Gained Total Per Year",
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.AddOnPaybackPeriod = self.OutputParameterDict[self.AddOnPaybackPeriod.Name] = OutputParameter(
            "AddOn Payback Period",
            UnitType=Units.TIME,
            PreferredUnits=TimeUnit.YEAR,
            CurrentUnits=TimeUnit.YEAR
        )
        self.AdjustedProjectCAPEX = self.OutputParameterDict[self.AdjustedProjectCAPEX.Name] = OutputParameter(
            "Adjusted CAPEX",
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS
        )
        self.AdjustedProjectOPEX = self.OutputParameterDict[self.AdjustedProjectOPEX.Name] = OutputParameter(
            "Adjusted OPEX",
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS
        )
        self.AddOnCashFlow = self.OutputParameterDict[self.AddOnCashFlow.Name] = OutputParameter(
            "Annual AddOn Cash Flow",
            value=[0.0],
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.AddOnCummCashFlow = self.OutputParameterDict[self.AddOnCummCashFlow.Name] = OutputParameter(
            "Cumulative AddOn Cash Flow",
            value=[0.0],
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS
        )
        self.ProjectCashFlow = self.OutputParameterDict[self.ProjectCashFlow.Name] = OutputParameter(
            "Annual Project Cash Flow",
            value=[0.0],
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.ProjectCummCashFlow = self.OutputParameterDict[self.ProjectCummCashFlow.Name] = OutputParameter(
            "Cumulative Project Cash Flow",
            value=[0.0],
            UnitType=Units.CURRENCY,
            PreferredUnits=CurrencyUnit.MDOLLARS,
            CurrentUnits=CurrencyUnit.MDOLLARS
        )
        self.AddOnElecRevenue = self.OutputParameterDict[self.AddOnElecRevenue.Name] = OutputParameter(
            "Annual Revenue Generated from Electricity Sales",
            value=[0.0],
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.AddOnHeatRevenue = self.OutputParameterDict[self.AddOnHeatRevenue.Name] = OutputParameter(
            "Annual Revenue Generated from Heat Sales",
            value=[0.0],
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )
        self.AddOnRevenue = self.OutputParameterDict[self.AddOnRevenue.Name] = OutputParameter(
            "Annual Revenue Generated from AddOns",
            value=[0.0],
            UnitType=Units.CURRENCYFREQUENCY,
            PreferredUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR,
            CurrentUnits=CurrencyFrequencyUnit.MDOLLARSPERYEAR
        )

        model.logger.info("Complete " + str(__class__) + ": " + sys._getframe().f_code.co_name)

    def read_parameters(self, model: Model) -> None:
        """
        The read_parameters function is called by the model to read in all the parameters that are used for this
        extension.  The user can create as many or as few parameters
        as needed.  Each parameter is created by a call to the InputParameter class, which is defined below, and then
        stored in a dictionary with a name assigned to
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: None
        """
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().read_parameters(model)  # read the parameters for the parent.

        is_sam_econ_model = model.economics.econmodel.value == EconomicModel.SAM_SINGLE_OWNER_PPA

        # Deal with all the parameter values that the user has provided that relate to this extension.
        # super.read_parameter will have already dealt with all the regular values, but anything unusual
        # may not be dealt with, so check.
        # In this case, all the values are array values, and weren't correctly dealt with, so below is where
        # we process them.  The problem is that they have a position number i.e., "AddOnCAPEX 1, AddOnCAPEX 2"
        # appended to them, while the
        # Parameter name is just "AddOnCAPEX" and the position indicates where in the array the user wants it stored.
        # So we need to look for the 5 arrays and position values and insert them into the arrays.

        # this does not deal with units if the user wants to do any conversions...
        # In this case, the read_parameters function didn't deal with the arrays of values we wanted,
        # so we will craft that here.
        for key in model.InputParameters.keys():
            if key.startswith("AddOn Nickname"):
                val = str(model.InputParameters[key].sValue)
                self.AddOnNickname.value.append(val)  # this assumes they put the values in the file in consecutive fashion
            if key.startswith("AddOn CAPEX"):
                val = float(model.InputParameters[key].sValue)
                self.AddOnCAPEX.value.append(val)  # this assumes they put the values in the file in consecutive fashion
            if key.startswith("AddOn OPEX"):
                val = float(model.InputParameters[key].sValue)
                self.AddOnOPEXPerYear.value.append(val)  # this assumes they put the values in the file in consecutive fashion

            if key.startswith("AddOn Electricity Gained"):
                if is_sam_econ_model:
                    raise NotImplementedError('AddOn Electricity is not supported for SAM Economic Models')

                val = float(model.InputParameters[key].sValue)
                self.AddOnElecGainedPerYear.value.append(val)  # this assumes they put the values in the file in consecutive fashion

            if key.startswith("AddOn Heat Gained"):
                if is_sam_econ_model:
                    raise NotImplementedError('AddOn Heat is not supported for SAM Economic Models')

                val = float(model.InputParameters[key].sValue)
                self.AddOnHeatGainedPerYear.value.append(val)  # this assumes they put the values in the file in consecutive fashion

            if key.startswith("AddOn Profit Gained"):
                val = str(model.InputParameters[key].sValue)
                self.AddOnProfitGainedPerYear.value.append(val)
            if key.startswith('AddOn Applies During Construction'):
                val = str(model.InputParameters[key].sValue).strip().lower() in ('true', '1', 'yes')
                self.AddOnAppliesDuringConstruction.value.append(val)
            if key.startswith('AddOn Goes To Royalty Holder'):
                val = str(model.InputParameters[key].sValue).strip().lower() in ('true', '1', 'yes')
                self.AddOnGoesToRoyaltyHolder.value.append(val)

        # Guardrail: AddOn Applies During Construction requires SAM Single Owner PPA
        for i, applies in enumerate(self.AddOnAppliesDuringConstruction.value):
            if applies and not is_sam_econ_model:
                nickname = (
                    self.AddOnNickname.value[i]
                    if i < len(self.AddOnNickname.value)
                    else f'#{i + 1}'
                )
                raise NotImplementedError(
                    f'AddOn "{nickname}" has Applies During Construction = True, '
                    f'but this feature is only supported with the '
                    f'SAM Single Owner PPA economic model '
                    f'(Economic Model = {EconomicModel.SAM_SINGLE_OWNER_PPA.int_value}).'
                )
        model.logger.info(f"complete {__class__!s}: {sys._getframe().f_code.co_name}")

    def Calculate(self, model: Model) -> None:
        """
        The Calculate function is where all the calculations are done.
        This function can be called multiple times, and will only recalculate what has changed each time it is called.
        This is where all the calculations are made using all the values that have been set.
        If you subclass this class, you can choose to run these calculations before (or after) your calculations,
        but that assumes you have set all the values that are required for these calculations
        If you choose to subclass this master class, you can also choose to override this method (or not),
        and if you do, do it before or after you call you own version of this method.
        If you do, you can also choose to call this method from you class, which can effectively run the
        calculations of the superclass, making all thr values available to your methods.
        but you had better have set all the parameters!
        :param model: The container class of the application, giving access to everything else, including the logger
        :type model: :class:`~geophires_x.Model.Model`
        :return: Nothing, but it does make calculations and set values in the model
        """
        model.logger.info(f"Init {str(__class__)}: {sys._getframe().f_code.co_name}")

        is_sam_em = model.economics.econmodel.value == EconomicModel.SAM_SINGLE_OWNER_PPA

        construction_years: int = model.surfaceplant.construction_years.value
        plant_lifetime: int = model.surfaceplant.plant_lifetime.value
        total_years: int = construction_years + plant_lifetime

        # Determine the number of add-ons from the longest value list
        num_addons = max(
            len(self.AddOnCAPEX.value),
            len(self.AddOnOPEXPerYear.value),
            len(self.AddOnElecGainedPerYear.value),
            len(self.AddOnHeatGainedPerYear.value),
            len(self.AddOnProfitGainedPerYear.value),
            1,
        ) if any(len(lst.value) > 0 for lst in [
            self.AddOnCAPEX, self.AddOnOPEXPerYear, self.AddOnElecGainedPerYear,
            self.AddOnHeatGainedPerYear, self.AddOnProfitGainedPerYear,
        ]) else 0

        # Ensure boolean lists are padded with defaults (False) to match num_addons
        while len(self.AddOnAppliesDuringConstruction.value) < num_addons:
            self.AddOnAppliesDuringConstruction.value.append(False)
        while len(self.AddOnGoesToRoyaltyHolder.value) < num_addons:
            self.AddOnGoesToRoyaltyHolder.value.append(False)

        def _expand_addon_schedule(
            raw_values: list, addon_index: int, _applies_during_construction: bool
        ) -> list[float]:
            """Expand a single add-on's value into a full time-series array."""
            if addon_index >= len(raw_values) or raw_values[addon_index] in (None, ''):
                return [0.0] * total_years

            raw_val = raw_values[addon_index]
            schedule_str = str(raw_val).strip()

            # Check if value contains DSL syntax (has '*' or ',')
            if '*' in schedule_str or ',' in schedule_str:
                segments = [s.strip() for s in schedule_str.split(',')]
                if _applies_during_construction:
                    expanded = expand_schedule(segments, total_years)
                else:
                    expanded = expand_schedule(segments, plant_lifetime)
                    expanded = [0.0] * construction_years + expanded
                return expanded

            # Legacy scalar path: single numeric value broadcast uniformly
            scalar = float(schedule_str)
            if _applies_during_construction:
                return [scalar] * total_years
            else:
                return [0.0] * construction_years + [scalar] * plant_lifetime

        # Build per-addon time-series and aggregate
        agg_capex = np.zeros(total_years)
        agg_opex = np.zeros(total_years)
        agg_profit = np.zeros(total_years)
        agg_elec = np.zeros(total_years)
        agg_heat = np.zeros(total_years)
        agg_royalty_holder_cf = np.zeros(total_years)

        for i in range(num_addons):
            applies_during_construction = self.AddOnAppliesDuringConstruction.value[i]
            goes_to_royalty_holder = self.AddOnGoesToRoyaltyHolder.value[i]

            capex_ts = np.array(
                _expand_addon_schedule(self.AddOnCAPEX.value, i, applies_during_construction)
            )
            opex_ts = np.array(
                _expand_addon_schedule(self.AddOnOPEXPerYear.value, i, applies_during_construction)
            )
            profit_ts = np.array(
                _expand_addon_schedule(self.AddOnProfitGainedPerYear.value, i, applies_during_construction)
            )
            elec_ts = np.array(
                _expand_addon_schedule(self.AddOnElecGainedPerYear.value, i, applies_during_construction)
            )
            heat_ts = np.array(
                _expand_addon_schedule(self.AddOnHeatGainedPerYear.value, i, applies_during_construction)
            )

            agg_capex += capex_ts
            agg_opex += opex_ts
            agg_profit += profit_ts
            agg_elec += elec_ts
            agg_heat += heat_ts

            if goes_to_royalty_holder:
                addon_cf = profit_ts - opex_ts
                agg_royalty_holder_cf += addon_cf

        # Store per-year arrays for downstream consumers (SAM integration, etc.)
        self._addon_capex_timeseries = agg_capex.tolist()
        self._addon_opex_timeseries = agg_opex.tolist()
        self._addon_profit_timeseries = agg_profit.tolist()
        self._addon_elec_timeseries = agg_elec.tolist()
        self._addon_heat_timeseries = agg_heat.tolist()
        self._royalty_holder_cash_flow = agg_royalty_holder_cf.tolist()

        # Compute aggregate totals (backward-compatible scalar summaries)
        self.AddOnCAPEXTotal.value = float(np.sum(agg_capex))
        # Operational-year totals only (construction years excluded for OPEX/energy/profit)
        self.AddOnOPEXTotalPerYear.value = float(
            np.mean(agg_opex[construction_years:]) if plant_lifetime > 0 else 0.0
        )
        self.AddOnElecGainedTotalPerYear.value = float(
            np.mean(agg_elec[construction_years:]) if plant_lifetime > 0 else 0.0
        )
        self.AddOnHeatGainedTotalPerYear.value = float(
            np.mean(agg_heat[construction_years:]) if plant_lifetime > 0 else 0.0
        )
        self.AddOnProfitGainedTotalPerYear.value = float(
            np.mean(agg_profit[construction_years:]) if plant_lifetime > 0 else 0.0
        )

        # The amount of electricity and/or heat have for the project already been calculated in SurfacePlant,
        # so we need to update them here so when they get used in the final economic calculation (below),
        # the new values reflect the addition of the AddOns
        for i in range(0, plant_lifetime):
            ts_idx = construction_years + i
            addon_elec_this_year = float(agg_elec[ts_idx]) if ts_idx < total_years else 0.0
            addon_heat_this_year = float(agg_heat[ts_idx]) if ts_idx < total_years else 0.0
            if model.surfaceplant.enduse_option.value is not EndUseOptions.HEAT:  # all these end-use options have an electricity generation component
                model.surfaceplant.TotalkWhProduced.value[i] = model.surfaceplant.TotalkWhProduced.value[i] + addon_elec_this_year
                model.surfaceplant.NetkWhProduced.value[i] = model.surfaceplant.NetkWhProduced.value[i] + addon_elec_this_year
                if model.surfaceplant.enduse_option.value is not EndUseOptions.ELECTRICITY:
                    model.surfaceplant.HeatkWhProduced.value[i] = model.surfaceplant.HeatkWhProduced.value[i] + addon_heat_this_year
            else:
                # all the end-use option of direct-use only components have a heat generation component
                model.surfaceplant.HeatkWhProduced.value[i] = model.surfaceplant.HeatkWhProduced.value[i] + addon_heat_this_year

        # Calculate the adjusted OPEX and CAPEX
        self.AdjustedProjectCAPEX.value = model.economics.CCap.value + self.AddOnCAPEXTotal.value
        self.AdjustedProjectOPEX.value = model.economics.Coam.value + self.AddOnOPEXTotalPerYear.value

        if is_sam_em:
            # SAM econ models incorporate add-ons into main economics, not as separate extended economics
            model.economics.CCap.value = self.AdjustedProjectCAPEX.value
            model.economics.Coam.value = self.AdjustedProjectOPEX.value

        AddOnCapCostPerYear = self.AddOnCAPEXTotal.value / construction_years
        ProjectCapCostPerYear = self.AdjustedProjectCAPEX.value / construction_years

        # (re)Calculate the revenues
        self.AddOnElecRevenue.value = [0.0] * plant_lifetime
        self.AddOnHeatRevenue.value = [0.0] * plant_lifetime
        self.AddOnRevenue.value = [0.0] * plant_lifetime
        self.AddOnCashFlow.value = [0.0] * plant_lifetime
        self.ProjectCashFlow.value = [0.0] * plant_lifetime
        for i in range(0, plant_lifetime, 1):
            ts_idx = construction_years + i
            addon_opex_this_year = float(agg_opex[ts_idx]) if ts_idx < total_years else self.AddOnOPEXTotalPerYear.value
            addon_profit_this_year = float(agg_profit[ts_idx]) if ts_idx < total_years else self.AddOnProfitGainedTotalPerYear.value

            ProjectElectricalEnergy = 0.0
            ProjectHeatEnergy = 0.0
            AddOnElectricalEnergy = 0.0
            AddOnHeatEnergy = 0.0
            if model.surfaceplant.enduse_option.value == EndUseOptions.ELECTRICITY:  # This option has no heat component
                ProjectElectricalEnergy = model.surfaceplant.NetkWhProduced.value[i]
                AddOnElectricalEnergy = float(agg_elec[ts_idx]) if ts_idx < total_years else self.AddOnElecGainedTotalPerYear.value
            elif model.surfaceplant.enduse_option.value == EndUseOptions.HEAT:  # has heat component but no electricity
                ProjectHeatEnergy = model.surfaceplant.HeatkWhProduced.value[i]
                AddOnHeatEnergy = float(agg_heat[ts_idx]) if ts_idx < total_years else self.AddOnHeatGainedTotalPerYear.value
            else:  # everything else has a component of both
                ProjectElectricalEnergy = model.surfaceplant.NetkWhProduced.value[i]
                ProjectHeatEnergy = model.surfaceplant.HeatkWhProduced.value[i]
                AddOnElectricalEnergy = float(agg_elec[ts_idx]) if ts_idx < total_years else self.AddOnElecGainedTotalPerYear.value
                AddOnHeatEnergy = float(agg_heat[ts_idx]) if ts_idx < total_years else self.AddOnHeatGainedTotalPerYear.value

            self.AddOnElecRevenue.value[i] = (AddOnElectricalEnergy * model.economics.ElecPrice.value[
                i]) / 1_000_000.0  # Electricity revenue in MUSD
            self.AddOnHeatRevenue.value[i] = (AddOnHeatEnergy * model.economics.HeatPrice.value[
                i]) / 1_000_000.0  # Heat revenue in MUSD
            self.AddOnRevenue.value[i] = self.AddOnElecRevenue.value[i] + self.AddOnHeatRevenue.value[
                i] + addon_profit_this_year - addon_opex_this_year
            self.AddOnCashFlow.value[i] = self.AddOnRevenue.value[i]
            self.ProjectCashFlow.value[i] = self.AddOnRevenue.value[i] + (((ProjectElectricalEnergy *
                                            model.economics.ElecPrice.value[i]) + (ProjectHeatEnergy *
                                            model.economics.HeatPrice.value[i])) / 1_000_000.0) - model.economics.Coam.value  # MUSD

        # now insert the cost of construction into the front of the array that will be used to calculate
        # NPV = the convention is that the upfront CAPEX is negative
        for i in range(0, construction_years, 1):
            self.AddOnCashFlow.value.insert(0, -1.0 * AddOnCapCostPerYear)
            self.ProjectCashFlow.value.insert(0, -1.0 * ProjectCapCostPerYear)

        # Now calculate a new "NPV", "IRR", "VIR", "Payback Period", and "MOIC"
        # Calculate more financial values using numpy financials
        self.ProjectNPV.value = Economics.calculate_npv(
            self.FixedInternalRate.value / 100,
            self.ProjectCashFlow.value.copy(),
            self.discount_initial_year_cashflow.value
        )

        self.ProjectIRR.value = npf.irr(self.ProjectCashFlow.value)
        if math.isnan(self.ProjectIRR.value):
            self.ProjectIRR.value = 0.0
        self.ProjectVIR.value = 1.0 + (self.ProjectNPV.value / self.AdjustedProjectCAPEX.value)

        # calculate Cummcashflows and payback period
        self.ProjectCummCashFlow.value = [0.0] * len(self.ProjectCashFlow.value)
        i = 0
        for val in self.ProjectCashFlow.value:
            if i == 0:
                self.ProjectCummCashFlow.value[i] = val
            else:
                self.ProjectCummCashFlow.value[i] = self.ProjectCummCashFlow.value[i - 1] + val
            i = i + 1
        i = 0
        self.AddOnCummCashFlow.value = [0.0] * len(self.AddOnCashFlow.value)
        for val in self.AddOnCashFlow.value:
            if i == 0:
                self.AddOnCummCashFlow.value[0] = val
            else:
                self.AddOnCummCashFlow.value[i] = self.AddOnCummCashFlow.value[i - 1] + val
                if self.AddOnCummCashFlow.value[i] > 0 >= self.AddOnCummCashFlow.value[
                    i - 1]:  # we just crossed the threshold into positive project cummcashflow, so we can calculate payback period
                    dFullDiff = self.AddOnCummCashFlow.value[i] + math.fabs(self.AddOnCummCashFlow.value[(i - 1)])
                    dPerc = math.fabs(self.AddOnCummCashFlow.value[(i - 1)]) / dFullDiff
                    self.AddOnPaybackPeriod.value = i + dPerc
            i = i + 1

        # Calculate MOIC which depends on CumCashFlow
        self.ProjectMOIC.value = self.ProjectCummCashFlow.value[len(self.ProjectCummCashFlow.value) - 1] / (
                self.AdjustedProjectCAPEX.value + (
                    self.AdjustedProjectOPEX.value * plant_lifetime))

        if not is_sam_em:
            # recalculate LCOE/LCOH
            self.LCOE.value, self.LCOH.value, LCOC = Economics.CalculateLCOELCOHLCOC(self, model)

        self._calculate_derived_outputs(model)
        model.logger.info(f'complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def __str__(self):
        return "EconomicsAddOns"

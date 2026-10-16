"""
Coupled Wellbore Power Cycle surface plant (Power Plant Type 10).

Electricity generation from the wellhead state computed by the coupled inflow-wellbore production wellbore model
(Production Wellbore Model 2). Three plant policies (Coupled Wellbore Plant Policy):

* cycle-only: the coupled-wellbore power cycle (superhot-wellbore; Scott, 2026; DiPippo, 2012/2016) at every time
  step: a binary cycle when the wellhead stream is superheated or single-phase supercritical, a single-flash cycle
  when it is two-phase, with a two-stage turbine expansion including the Baumann wet-stage correction. Unlike the ORC
  and flash plant correlations, which are fits in temperature for liquid water, this cycle works from the enthalpy
  and pressure the well actually delivers.
* correlation-first: the plant follows the phase of the wellhead stream at each time step. A sub-critical liquid
  wellhead (a pumped well, or a dense self-flowing one) is served by GEOPHIRES's own liquid-water correlations: the
  supercritical ORC fit up to Coupled Wellbore ORC Maximum Wellhead Temperature and the double-flash fit above it. A
  sub-critical two-phase wellhead of steam quality x is served by a wet double flash: the double-flash correlation on
  the separated liquid at the saturation temperature of the wellhead pressure plus the dry-steam turbine work of the
  steam fraction expanded from the wellhead pressure (the coupled-wellbore cycle's two-stage turbine), which is
  continuous in x as x goes to 0. A superheated or vapor-like supercritical wellhead is served by the
  coupled-wellbore cycle, as under cycle-only; a dense (liquid-like) supercritical wellhead, whose enthalpy is below
  that cycle's own binary/flash selection boundary, is served by the liquid correlations at the wellhead temperature
  like a sub-critical liquid, so that the plant is continuous across the critical pressure. The liquid-water
  correlations are net plant fits; only the coupled-wellbore cycle and the dry-steam turbine are gross and are
  derated by the parasitic load. The double-flash fit is evaluated no hotter than LIQUID_CORRELATION_MAX_TEMPERATURE_C.
* best-output: the same paths are admissible for a given wellhead state as under correlation-first, plus the
  coupled-wellbore cycle for a two-phase or saturated-vapor wellhead and both liquid correlations for a liquid one,
  and at each time step the admissible path that yields the most electricity is taken. This removes the step at the
  phase label (a pumped liquid wellhead and the two-phase wellhead of the same well are no longer valued on different
  bases by fiat), at the price of comparing the gross-derated coupled-wellbore paths against the net correlations.
  A liquid wellhead hotter than Coupled Wellbore ORC Maximum Wellhead Temperature stays admissible to the ORC
  correlation, valued at that temperature: a plant designed for the ceiling makes at least its design output from
  hotter brine, and the enthalpy above the ceiling is simply not converted. The double-flash correlation takes over
  where it yields more (about 266 C for a 245 C ceiling), so the plant output has no step at the ceiling.

The coupled-wellbore power cycle reports gross turbine power with no parasitic loads (cooling, gas extraction, feed
pumps) and no generator losses, which Scott (2026) puts at 5 to 15 percent of gross for typical plants. Coupled
Wellbore Power Cycle Parasitic Load derates it to the plant output GEOPHIRES reports as electricity produced;
production well pumping (when the coupled wellbore model pumps the well) and injection pumping are subtracted as
usual. The power cycle parameters follow the superhot-wellbore defaults (flash separation at 1 MPa, condenser at
0.01 MPa, dry turbine efficiency 0.85, working fluid pressure 1 MPa) except that the dead state for exergy is Ambient
Temperature and the binary cycle rejects the geofluid at Injection Temperature, so that its heat balance agrees with
GEOPHIRES'. Heat extraction is enthalpy based, as the wellhead stream is generally not liquid.

Requires Production Wellbore Model 2 (Coupled Inflow-Wellbore) and supports the electricity end-use only. The plant
is costed with the conventional correlation of the plant path that serves most of the plant lifetime (supercritical
ORC for the ORC correlation and the coupled-wellbore binary cycle, double flash for the double-flash correlation and
the wet double flash, single flash for the coupled-wellbore flash cycle), unless Capital Cost for Power Plant for
Electricity Generation is given.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import CoolProp.CoolProp as CP

from .OptionList import EndUseOptions, PlantType
from .Parameter import floatParameter, strParameter, OutputParameter
from .SurfacePlant import SurfacePlant
from .SurfacePlantUtils import liquid_plant_correlation
from .Units import Units, PercentUnit, TemperatureUnit
from geophires_x.GeoPHIRESUtils import enthalpy_water_kJ_per_kg, quantity
import geophires_x.Model as Model

PLANT_POLICIES = ('cycle-only', 'correlation-first', 'best-output')

# The liquid-water plant correlations are fits in temperature. The double-flash fit is evaluated no hotter than this
# (the saturation temperature of a wellhead at the critical pressure is 373.9 C; a compressed-liquid wellhead can be
# hotter still); the ORC fit is evaluated no hotter than Coupled Wellbore ORC Maximum Wellhead Temperature.
LIQUID_CORRELATION_MAX_TEMPERATURE_C = 375.0

# Specific enthalpy of water at the critical point [MJ/kg]: the coupled-wellbore cycle's own boundary between a dense
# (liquid-like) and a vapor-like supercritical wellhead, used when the installed superhot-wellbore predates its
# public helper.
WATER_CRITICAL_ENTHALPY_MJ_PER_KG = 2.084

# Plant paths served by the coupled-wellbore power cycle rather than a GEOPHIRES correlation; the prefix is what
# _calculate_wellhead_state_policy dispatches on, so PLANT_PATH_COST_TYPES and _plant_path must both use it.
COUPLED_WELLBORE_PATH_PREFIX = 'coupled_wellbore_'

# Plant paths of the correlation-first policy, and the conventional plant each one is costed as.
PLANT_PATH_COST_TYPES = {
    'correlation_orc': PlantType.SUPER_CRITICAL_ORC,
    'correlation_double_flash': PlantType.DOUBLE_FLASH,
    # TODO: the wet double flash is two turbine trains, a double-flash plant for the separated liquid and a steam turbine
    # admitted at the wellhead pressure (3-20 MPa, far above geothermal practice) for the steam share, but is costed
    # as one double-flash plant. Splitting it into GEOPHIRES's double- and single-flash correlations moves the plant
    # cost by only -2 to -5 % (single flash is costed 20 % below double flash, and the economies of scale are weak),
    # so the missing premium needs a high-pressure steam turbine cost, which GEOPHIRES has no correlation for.
    'wet_double_flash': PlantType.DOUBLE_FLASH,
    f'{COUPLED_WELLBORE_PATH_PREFIX}binary': PlantType.SUPER_CRITICAL_ORC,
    f'{COUPLED_WELLBORE_PATH_PREFIX}flash': PlantType.SINGLE_FLASH,
}

WATER_CRITICAL_PRESSURE_MPA = 22.064

# A sub-critical vapor wellhead is superheated (served by the coupled-wellbore cycle) when its enthalpy exceeds that
# of saturated steam at the wellhead pressure by this margin; the cycle uses the same margin to pick binary over flash.
SUPERHEAT_MARGIN_KJ_PER_KG = 50.0


# noinspection string-conversion-without-dunder-method
class SurfacePlantCoupledWellbore(SurfacePlant):
    def __init__(self, model: Model):
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().__init__(model)
        self.MyClass = self.__class__.__name__
        self.MyPath = Path(__file__).resolve()

        self.coupled_cost_plant_type: PlantType = PlantType.SUPER_CRITICAL_ORC
        """Conventional plant type the coupled wellbore plant is costed as (Economics), available after Calculate()"""
        self.coupled_plant_path: list = []
        """Plant path serving each time step (see PLANT_PATH_COST_TYPES), available after Calculate()"""

        self.parasitic_load = self.ParameterDict[self.parasitic_load.Name] = floatParameter(
            'Coupled Wellbore Power Cycle Parasitic Load',
            DefaultValue=0.10,
            Min=0.0,
            Max=0.5,
            UnitType=Units.PERCENT,
            PreferredUnits=PercentUnit.TENTH,
            CurrentUnits=PercentUnit.TENTH,
            ToolTipText='Fraction of the gross turbine power of the coupled-wellbore power cycle consumed by plant '
            'parasitic loads (cooling, gas extraction, feed pumps) and generator losses. The coupled-wellbore power '
            'cycle reports gross turbine power; Scott (2026) cites 5 to 15 percent for typical geothermal plants. '
            'Applies to the coupled-wellbore cycle and to the dry-steam turbine of the wet double flash only; the '
            'liquid water plant correlations are net. Production and injection well pumping are accounted for '
            'separately.',
        )

        self.plant_policy = self.ParameterDict[self.plant_policy.Name] = strParameter(
            'Coupled Wellbore Plant Policy',
            DefaultValue='cycle-only',
            UnitType=Units.NONE,
            ToolTipText='cycle-only: the coupled-wellbore power cycle (the binary/flash cycle of superhot-wellbore) at '
            'every time step. '
            'correlation-first: per time step, a sub-critical liquid wellhead is served by GEOPHIRES\'s supercritical '
            'ORC correlation (up to Coupled Wellbore ORC Maximum Wellhead Temperature) or double-flash correlation, '
            'a sub-critical two-phase wellhead by a wet double flash (double-flash correlation on the separated '
            'liquid plus the dry-steam turbine work of the steam fraction), a dense supercritical wellhead by the '
            'liquid correlations and a superheated or vapor-like supercritical wellhead by the coupled-wellbore '
            'cycle. best-output: per time step, the admissible path (as under correlation-first, plus the '
            'coupled-wellbore cycle for a two-phase wellhead and both liquid correlations for a liquid one, the ORC '
            'correlation above its ceiling valued at the ceiling) that yields the most electricity.',
        )

        self.liquid_orc_max_temperature = self.ParameterDict[self.liquid_orc_max_temperature.Name] = floatParameter(
            'Coupled Wellbore ORC Maximum Wellhead Temperature',
            DefaultValue=245.0,
            Min=150.0,
            Max=300.0,
            UnitType=Units.TEMPERATURE,
            PreferredUnits=TemperatureUnit.CELSIUS,
            CurrentUnits=TemperatureUnit.CELSIUS,
            ToolTipText='Under the correlation-first plant policy, a sub-critical liquid wellhead up to this temperature '
            'is served by the supercritical ORC correlation (whose utilization efficiency fit peaks near 245 degC), '
            'a hotter one by the double-flash correlation. Under best-output, a hotter liquid wellhead can still take '
            'the ORC correlation, valued at this temperature (the enthalpy above it is not converted), when that '
            'yields more than the double-flash correlation.',
        )

        self.coupled_power_cycle = self.OutputParameterDict[self.coupled_power_cycle.Name] = OutputParameter(
            Name='Wellhead Power Cycle',
            value='',
            UnitType=Units.NONE,
            ToolTipText='The coupled-wellbore power cycle\'s binary or flash selection: binary for a superheated or '
            'vapor-like supercritical wellhead stream, flash for a two-phase one, over the time steps it served; '
            'empty when every time step was served by a GEOPHIRES plant correlation',
        )

        self.coupled_plant_path_output = self.OutputParameterDict[self.coupled_plant_path_output.Name] = (
            OutputParameter(
                Name='Power Cycle Path',
                value='',
                UnitType=Units.NONE,
                ToolTipText='Plant path(s) serving the plant lifetime, most frequent first: correlation_orc, '
                'correlation_double_flash, wet_double_flash, coupled_wellbore_binary or coupled_wellbore_flash',
            )
        )

        self.coupled_utilization_efficiency = self.OutputParameterDict[self.coupled_utilization_efficiency.Name] = (
            OutputParameter(
                Name='Power Cycle Utilization Efficiency',
                value=[],
                UnitType=Units.PERCENT,
                PreferredUnits=PercentUnit.TENTH,
                CurrentUnits=PercentUnit.TENTH,
                ToolTipText='Electricity produced divided by the exergetic power of the wellhead stream, after the '
                'parasitic load',
            )
        )

        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def __str__(self):
        return 'SurfacePlantCoupledWellbore'

    @property
    def coupled_cycle_is_flash(self) -> bool:
        """Whether the plant is costed as a flash plant (True) or a binary/ORC plant (False)"""
        return self.coupled_cost_plant_type == PlantType.SINGLE_FLASH

    def read_parameters(self, model: Model) -> None:
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().read_parameters(model)

        if self.enduse_option.value != EndUseOptions.ELECTRICITY:
            raise ValueError(
                f'{self.plant_type.Name} {self.plant_type.value.value} supports {self.enduse_option.Name} '
                f'{EndUseOptions.ELECTRICITY.int_value} ({EndUseOptions.ELECTRICITY.value}) only.'
            )

        self.plant_policy.value = str(self.plant_policy.value).strip().lower()
        if self.plant_policy.value not in PLANT_POLICIES:
            raise ValueError(
                f'{self.plant_policy.Name} must be one of {", ".join(PLANT_POLICIES)}; got {self.plant_policy.value!r}.'
            )

        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def Calculate(self, model: Model) -> None:
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')

        # Imported here rather than at module scope: CoupledWellBores -> WellBores -> Model -> SurfacePlantCoupledWellbore
        # is a circular import at load time.
        from .CoupledWellBores import COUPLED_WELLBORE_MODEL_LABEL  # noqa: PLC0415

        wellbores = model.wellbores
        if not getattr(wellbores, 'uses_coupled_wellbore_model', False):
            raise ValueError(
                f'{self.plant_type.Name} {self.plant_type.value.value} requires {COUPLED_WELLBORE_MODEL_LABEL}, '
                'which provides the wellhead state the power cycle runs on.'
            )
        profile = wellbores.coupled_profile

        nprod = int(wellbores.nprod.value)
        flow_rate_kgs = float(wellbores.prodwellflowrate.value)
        derate = 1.0 - float(self.parasitic_load.value)

        self.TenteringPP.value = np.array(wellbores.ProducedTemperature.value, dtype=float)

        if self.plant_policy.value == 'cycle-only':
            self._calculate_coupled_wellbore_cycle_policy(model, profile, nprod, flow_rate_kgs, derate)
        else:
            self._calculate_wellhead_state_policy(model, profile, nprod, flow_rate_kgs, derate)

        # The coupled-wellbore cycle's binary/flash selection, for the time steps that cycle actually served.
        served_by_cycle = [path.startswith(COUPLED_WELLBORE_PATH_PREFIX) for path in self.coupled_plant_path]
        cycles = sorted({ts.cycle for ts, served in zip(profile.timesteps, served_by_cycle) if served and ts.cycle})
        self.coupled_power_cycle.value = ', '.join(cycles)

        path_counts = Counter(self.coupled_plant_path)
        paths_by_frequency = [path for path, _ in path_counts.most_common()]
        self.coupled_plant_path_output.value = ', '.join(paths_by_frequency)
        self.coupled_cost_plant_type = PLANT_PATH_COST_TYPES[paths_by_frequency[0]]
        if len(paths_by_frequency) > 1:
            model.logger.warning(
                f'The coupled wellbore plant path changes between {" and ".join(paths_by_frequency)} over the plant lifetime '
                f'as the wellhead state changes; the plant is costed as a {self.coupled_cost_plant_type.value} plant.'
            )

        # Heat extracted from an enthalpy balance between the wellhead stream and the injected liquid.
        h_injection_kJ_per_kg = enthalpy_water_kJ_per_kg(
            wellbores.Tinj.value, pressure=quantity(float(profile.initial.whp_MPa), 'MPa')
        )
        h_wellhead_kJ_per_kg = np.array(profile.h_wellhead_MJkg, dtype=float) * 1000.0
        self.HeatExtracted.value = nprod * flow_rate_kgs * (h_wellhead_kJ_per_kg - h_injection_kJ_per_kg) / 1e3
        self.HeatProduced.value = np.empty(0)

        self.NetElectricityProduced.value = self.ElectricityProduced.value - wellbores.PumpingPower.value
        self.FirstLawEfficiency.value = self.NetElectricityProduced.value / self.HeatExtracted.value

        (
            self.HeatkWhExtracted.value,
            self.PumpingkWh.value,
            self.TotalkWhProduced.value,
            self.NetkWhProduced.value,
            self.HeatkWhProduced.value,
        ) = SurfacePlant.annual_electricity_pumping_power(
            self,
            self.plant_lifetime.value,
            self.enduse_option.value,
            self.HeatExtracted.value,
            model.economics.timestepsperyear.value,
            self.utilization_factor.value,
            wellbores.PumpingPower.value,
            self.ElectricityProduced.value,
            self.NetElectricityProduced.value,
            self.HeatProduced.value,
        )

        self.RemainingReservoirHeatContent.value = SurfacePlant.remaining_reservoir_heat_content(
            self, model.reserv.InitialReservoirHeatContent.value, self.HeatkWhExtracted.value
        )

        self._calculate_derived_outputs(model)

        model.logger.info(
            f'coupled wellbore plant ({self.plant_policy.value}): path {self.coupled_plant_path_output.value}; power cycle '
            f'{self.coupled_power_cycle.value}; {self.ElectricityProduced.value[0]:.2f} MW initial plant output '
            f'after a parasitic load of {self.parasitic_load.value * 100:.0f}% on gross cycle power; utilization '
            f'efficiency {self.coupled_utilization_efficiency.value[0] * 100:.1f}%; costed as '
            f'{self.coupled_cost_plant_type.value}'
        )
        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def _calculate_coupled_wellbore_cycle_policy(
        self, model: Model, profile, nprod: int, flow_rate_kgs: float, derate: float
    ) -> None:
        """The coupled-wellbore power cycle at every time step (the cycle-only policy)."""
        gross_power_MWe = np.array(profile.power_MWe, dtype=float)
        exergy_rate_MW = np.array(profile.exergy_rate_MW, dtype=float)
        if not np.all(np.isfinite(gross_power_MWe)) or not np.all(np.isfinite(exergy_rate_MW)):
            raise RuntimeError(
                'The power cycle analysis failed for at least one time step; the wellhead stream may be '
                'too cold or its pressure below the flash separation pressure. Check the reservoir state, the '
                'operating point and the superhot-wellbore log notes.'
            )

        cycle_path = f'{COUPLED_WELLBORE_PATH_PREFIX}{profile.timesteps[0].cycle}'
        self.coupled_plant_path = [cycle_path] * len(profile.timesteps)
        cycles = sorted({ts.cycle for ts in profile.timesteps if ts.cycle})
        if len(cycles) > 1:
            model.logger.warning(
                f'The power cycle changes between {" and ".join(cycles)} over the plant lifetime as the '
                f'wellhead state changes; the plant is costed as a {profile.timesteps[0].cycle} plant.'
            )

        self.Availability.value = exergy_rate_MW / flow_rate_kgs
        self.ElectricityProduced.value = nprod * gross_power_MWe * derate
        self.coupled_utilization_efficiency.value = np.array(profile.eta_utilization, dtype=float) * derate

    def _calculate_wellhead_state_policy(
        self, model: Model, profile, nprod: int, flow_rate_kgs: float, derate: float
    ) -> None:
        """
        Per time step, the plant path that fits the phase of the wellhead stream (correlation-first), or the
        admissible path that yields the most electricity (best-output); see the module docstring.
        """
        timesteps = profile.timesteps
        n = len(timesteps)
        T_ambient = float(self.ambient_temperature.value)
        orc_max_T = float(self.liquid_orc_max_temperature.value)
        best_output = self.plant_policy.value == 'best-output'

        T_wellhead_C = np.array([ts.T_wellhead_C for ts in timesteps], dtype=float)
        clamped = T_wellhead_C > LIQUID_CORRELATION_MAX_TEMPERATURE_C
        if np.any(clamped):
            model.logger.warning(
                f'coupled wellbore plant: the wellhead is hotter than {LIQUID_CORRELATION_MAX_TEMPERATURE_C:g} C at '
                f'{int(np.sum(clamped))} of {n} time steps; the double-flash correlation is evaluated at '
                f'{LIQUID_CORRELATION_MAX_TEMPERATURE_C:g} C there'
            )
        A_orc, etau_orc, _ = liquid_plant_correlation(
            np.minimum(T_wellhead_C, orc_max_T), T_ambient, PlantType.SUPER_CRITICAL_ORC
        )
        A_df, etau_df, _ = liquid_plant_correlation(
            np.minimum(T_wellhead_C, LIQUID_CORRELATION_MAX_TEMPERATURE_C), T_ambient, PlantType.DOUBLE_FLASH
        )

        electricity_MW = np.zeros(n)
        availability = np.zeros(n)
        paths = []
        for i, ts in enumerate(timesteps):
            candidates = self._candidate_paths(ts, orc_max_T) if best_output else [self._plant_path(ts, orc_max_T)]
            evaluated = []
            reasons = []
            for path in candidates:
                result = self._path_electricity(
                    path, ts, nprod, flow_rate_kgs, derate, T_ambient, A_orc[i], etau_orc[i], A_df[i], etau_df[i]
                )
                if isinstance(result, str):
                    reasons.append(f'{path}: {result}')
                else:
                    evaluated.append((path, *result))
            if not evaluated:
                raise RuntimeError(
                    f'No plant path could serve the wellhead at t = {ts.time_yr:.2f} yr ({float(ts.whp_MPa):.2f} MPa, '
                    f'{ts.T_wellhead_C:.1f} C, {ts.wellhead_phase or "unknown phase"}): {"; ".join(reasons)}. '
                    'Check the reservoir state, the operating point and the superhot-wellbore log notes.'
                )
            path, electricity_MW[i], availability[i] = max(evaluated, key=lambda candidate: candidate[1])
            paths.append(path)

        invalid = [i for i in range(n) if not (math.isfinite(electricity_MW[i]) and electricity_MW[i] >= 0.0)]
        if invalid:
            i = invalid[0]
            raise RuntimeError(
                f'Electricity production is {electricity_MW[i]:.3f} MW at t = {timesteps[i].time_yr:.2f} yr '
                f'({paths[i]}); the plant correlation is outside its range for this wellhead state.'
            )

        self.coupled_plant_path = paths
        self.Availability.value = availability
        self.ElectricityProduced.value = electricity_MW
        safe_availability = np.where(availability > 0, availability, 1.0)
        utilization = np.where(availability > 0, electricity_MW / (nprod * flow_rate_kgs * safe_availability), 0.0)
        self.coupled_utilization_efficiency.value = utilization

    def _path_electricity(
        self,
        path: str,
        ts,
        nprod: int,
        flow_rate_kgs: float,
        derate: float,
        T_ambient: float,
        A_orc: float,
        etau_orc: float,
        A_df: float,
        etau_df: float,
    ):
        """
        Electricity [MW] and availability [MJ/kg] of one plant path at one time step, or a string saying why the
        path cannot serve that state.
        """
        whp_MPa = float(ts.whp_MPa)
        if path.startswith(COUPLED_WELLBORE_PATH_PREFIX):
            if not (math.isfinite(ts.power_MWe) and math.isfinite(ts.exergy_rate_MW)):
                return 'the coupled-wellbore power cycle analysis failed for this wellhead state'
            return nprod * float(ts.power_MWe) * derate, float(ts.exergy_rate_MW) / flow_rate_kgs
        if path == 'correlation_orc':
            return A_orc * etau_orc * nprod * flow_rate_kgs, A_orc
        if path == 'correlation_double_flash':
            return A_df * etau_df * nprod * flow_rate_kgs, A_df

        # TODO: the steam fraction is expanded from the full wellhead pressure without the exit-moisture limit of
        # geothermal practice (x >= 0.85): from 7-20 MPa the turbine exit quality is 0.83-0.72. A real plant would admit
        # at ~3-4 MPa, which gives about the same specific work here (~0.56 MJ/kg of steam), so the output is barely
        # affected; the plant as drawn is just not buildable. See also the PLANT_PATH_COST_TYPES TODO.
        # wet double flash: the double-flash correlation on the separated liquid at the saturation temperature of the
        # wellhead pressure, plus the dry-steam turbine work of the steam fraction.
        quality = float(ts.wellhead_quality)
        if ts.wellhead_phase == 'single_phase_vapor' or not math.isfinite(quality):
            quality = 1.0
        quality = min(max(quality, 0.0), 1.0)
        T_sat_C = min(self._saturation_temperature_C(whp_MPa), LIQUID_CORRELATION_MAX_TEMPERATURE_C)
        A_sat, etau_sat, _ = liquid_plant_correlation(T_sat_C, T_ambient, PlantType.DOUBLE_FLASH)
        dry_steam_work_MJkg = float(ts.dry_steam_work_MJkg)
        if quality > 0.0 and not math.isfinite(dry_steam_work_MJkg):
            # superhot-wellbore reports this per time step, but a profile whose earlier time steps were supercritical
            # can leave it undefined here. It depends on the wellhead pressure alone, so recompute it.
            dry_steam_work_MJkg = self._dry_steam_work_MJkg(whp_MPa)
        if quality > 0.0 and not math.isfinite(dry_steam_work_MJkg):
            return (
                f'no dry-steam turbine work for a wellhead at {whp_MPa:.2f} MPa with quality {quality:.3f} (a '
                'saturated-vapor or two-phase wellhead must sit below the critical pressure and above the condenser '
                'pressure of the coupled-wellbore power cycle)'
            )
        liquid_MW = (1.0 - quality) * float(A_sat) * float(etau_sat)
        steam_MW = quality * dry_steam_work_MJkg * derate if quality > 0.0 else 0.0
        exergy = float(ts.exergy_rate_MW)
        availability = exergy / flow_rate_kgs if math.isfinite(exergy) and exergy > 0 else float(A_sat)
        return nprod * flow_rate_kgs * (liquid_MW + steam_MW), availability

    def _candidate_paths(self, ts, orc_max_temperature_C: float) -> list:
        """
        The plant paths admissible for the wellhead state of one time step, for the best-output policy: a liquid
        wellhead (including a dense supercritical one) can go to the ORC correlation, valued at no more than its
        ceiling temperature (a plant designed for the ceiling fed hotter brine; the enthalpy above it is not
        converted), and to the double-flash correlation; a two-phase or saturated-vapor wellhead to the wet double
        flash or the coupled-wellbore flash cycle; a superheated or vapor-like supercritical wellhead only to the
        coupled-wellbore cycle.
        """
        phase = ts.wellhead_phase
        whp_MPa = float(ts.whp_MPa)
        cycle_path = f'{COUPLED_WELLBORE_PATH_PREFIX}{ts.cycle or "binary"}'
        # The ORC correlation is evaluated at min(wellhead temperature, ceiling) (_calculate_wellhead_state_policy), so
        # above the ceiling it offers the ceiling's output rather than dropping out: no step in output at the ceiling.
        liquid_paths = ['correlation_orc', 'correlation_double_flash']
        if not phase:
            return [cycle_path]
        if phase == 'supercritical' or whp_MPa >= WATER_CRITICAL_PRESSURE_MPA:
            return liquid_paths if self._is_dense_supercritical(whp_MPa, float(ts.h_wellhead_MJkg)) else [cycle_path]
        if phase == 'single_phase_vapor':
            return [cycle_path] if self._is_superheated(ts) else ['wet_double_flash', cycle_path]
        if phase == 'single_phase_liquid':
            return liquid_paths
        return ['wet_double_flash', cycle_path]

    @staticmethod
    def _is_dense_supercritical(whp_MPa: float, h_wellhead_MJkg: float) -> bool:
        """
        Whether a wellhead at or above the critical pressure is dense (liquid-like: its enthalpy is below the
        coupled-wellbore cycle's own binary/flash selection boundary), so that the liquid-water plant correlations at
        the wellhead temperature describe it and the coupled-wellbore fixed-pressure flash cycle does not. A
        vapor-like supercritical wellhead is left to the coupled-wellbore cycle.
        """
        if not math.isfinite(h_wellhead_MJkg):
            return False
        try:
            from superhot_wellbore.client import is_dense_supercritical  # noqa: PLC0415  (optional dependency)

            return bool(is_dense_supercritical(whp_MPa, h_wellhead_MJkg))
        except (ImportError, AttributeError):
            return whp_MPa >= WATER_CRITICAL_PRESSURE_MPA and h_wellhead_MJkg < WATER_CRITICAL_ENTHALPY_MJ_PER_KG

    @staticmethod
    def _dry_steam_work_MJkg(whp_MPa: float) -> float:
        """
        Gross specific turbine work of saturated steam expanded from the wellhead pressure [MJ/kg], from the
        coupled-wellbore power cycle model (superhot-wellbore), or NaN when the pressure is outside its range. Used
        when a timestep carries no value of its own (see the wet double flash above).
        """
        try:
            from superhot_wellbore import power_cycle  # noqa: PLC0415  (optional dependency)

            return float(power_cycle.dry_steam_specific_work(float(whp_MPa)))
        except Exception:  # noqa: BLE001  (any failure means "no work available", handled by the caller)
            return float('nan')

    def _plant_path(self, ts, orc_max_temperature_C: float) -> str:
        """
        Plant path of one time step from its wellhead phase (correlation-first): the coupled-wellbore cycle for a
        vapor-like supercritical or superheated wellhead (or an unknown phase), the liquid correlations for a
        sub-critical liquid or a dense supercritical wellhead, the wet double flash for a two-phase or saturated-vapor
        wellhead.
        """
        phase = ts.wellhead_phase
        whp_MPa = float(ts.whp_MPa)
        cycle_path = f'{COUPLED_WELLBORE_PATH_PREFIX}{ts.cycle or "binary"}'
        liquid_path = (
            'correlation_orc' if float(ts.T_wellhead_C) <= orc_max_temperature_C else 'correlation_double_flash'
        )
        if not phase:
            return cycle_path
        if phase == 'supercritical' or whp_MPa >= WATER_CRITICAL_PRESSURE_MPA:
            return liquid_path if self._is_dense_supercritical(whp_MPa, float(ts.h_wellhead_MJkg)) else cycle_path
        if phase == 'single_phase_vapor':
            return cycle_path if self._is_superheated(ts) else 'wet_double_flash'
        if phase == 'single_phase_liquid':
            return liquid_path
        return 'wet_double_flash'

    @staticmethod
    def _is_superheated(ts) -> bool:
        """A sub-critical vapor wellhead is superheated when its enthalpy exceeds that of saturated steam at the
        wellhead pressure by SUPERHEAT_MARGIN_KJ_PER_KG."""
        whp_MPa = float(ts.whp_MPa)
        h_saturated_vapor_kJ_per_kg = CP.PropsSI('H', 'P', whp_MPa * 1e6, 'Q', 1, 'Water') / 1000.0
        return float(ts.h_wellhead_MJkg) * 1000.0 >= h_saturated_vapor_kJ_per_kg + SUPERHEAT_MARGIN_KJ_PER_KG

    @staticmethod
    def _saturation_temperature_C(pressure_MPa: float) -> float:
        return float(CP.PropsSI('T', 'P', pressure_MPa * 1e6, 'Q', 0, 'Water')) - 273.15

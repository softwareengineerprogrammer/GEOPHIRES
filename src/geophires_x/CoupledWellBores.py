"""
Coupled inflow-wellbore production wellbore model (Production Wellbore Model, 2).

Couples GEOPHIRES to the superhot-wellbore package (Scott, 2026), which solves a steady-state production
well: radial Darcy inflow from the far-field reservoir state, a bottom-to-surface thermohydraulic wellbore march
(friction, gravity, kinetic energy and conductive heat loss to the formation) and the resulting wellhead state, with a
downhole production pump (superhot-wellbore's client-side pump stage) when the prescribed flow rate cannot reach the
surface on its own or arrives below a minimum wellhead pressure.

In GEOPHIRES terms this is a production wellbore model, an alternative to Ramey's model and the constant temperature
drop that also replaces the productivity-index inflow model and the productivity-index production pump model: it
determines the flow rate (or the wellhead pressure), the reservoir drawdown, whether and where the well is pumped, the
pump pressure rise and power, and the wellhead pressure, temperature and enthalpy of the produced fluid. It pairs with
any thermal reservoir model. The reservoir model supplies the far-field temperature history over the plant lifetime
(for example Gringarten's Multiple Parallel Fractures model from the usual fracture parameterization, or a
user-provided temperature profile), GEOPHIRES supplies the far-field pressure history (Reservoir Hydrostatic Pressure with the
Overpressure Percentage / Depletion Rate mechanism), and superhot-wellbore is solved along both. Injection wells, the
surface plant and the economics remain GEOPHIRES' job as usual.

Parameter mapping
-----------------
The standard GEOPHIRES parameters are reused wherever their meaning is the same:

* Far-field reservoir temperature: the reservoir model's bottom-hole temperature and temperature history. The
  geothermal gradient segment(s) also define the formation temperature profile used for wellbore heat loss. Maximum
  Temperature is raised automatically (with a warning) if it would cap the drilling depth above the reservoir.
* Far-field reservoir pressure: the production reservoir pressure history GEOPHIRES computes from Reservoir
  Hydrostatic Pressure (or the built-in correlation), Overpressure Percentage and Overpressure Depletion Rate.
* Deliverability: Productivity Index, converted to the transmissivity (permeability-thickness product) of the Darcy
  inflow model at the initial reservoir state. Coupled Wellbore Feedzone Transmissivity can be given instead to specify the
  transmissivity directly, as in Scott (2026).
* Drainage geometry: the feedzone thickness is the fracture height, and the drainage radius is that of a cylinder of
  that thickness holding one production well's share of the (calculated) reservoir volume.
* Well: Reservoir Depth (feedzone depth) and Production Well Diameter (casing inner diameter).
* Operating point: either Production Flow Rate per Well (prescribed) or Production Wellhead Pressure (the initial
  flow rate that delivers it is solved for; 10 MPa is assumed if neither is given). GEOPHIRES carries one flow rate
  per well, so the flow rate is then held constant over the plant lifetime and the wellhead pressure and temperature
  respond to the reservoir decline. When the flow rate is solved for, the reservoir model is re-run with it so that
  its thermal decline reflects the actual production, before the standard wellbore calculation runs. Both may be
  given when the production pump is enabled: the flow rate is then prescribed and the wellhead pressure is the pump's
  set point.
* Production pump: Circulation Pump Efficiency is the pump efficiency. Coupled Wellbore Pump Policy (never / auto /
  always) decides whether a well that does not self-flow (does not reach the surface, or reaches it below Coupled
  Wellbore Minimum Self-Flow Wellhead Pressure) gets a downhole pump at the shallowest depth from which the column below is
  single-phase liquid with a net positive suction head margin (Coupled Wellbore Pump NPSH Margin, the same 344.7 kPa as the
  productivity-index pump model). The pump raises the pressure so that the wellhead stream stays liquid. Coupled
  Wellbore Pump Maximum Depth and Maximum Intake Temperature bound the pump; Coupled Wellbore Pump Envelope says
  whether a pump outside them is modelled and flagged (flag), aborts the run (enforce) or is not installed, the
  well being left self-flowing below the minimum wellhead pressure when it reaches the surface on its own (omit).

The remaining inputs (casing roughness, wellbore heat-loss coefficient, integration step and the number of
coupled-model solves) are the "Coupled Wellbore ..." parameters declared below.

What GEOPHIRES sees
-------------------
The standard wellbore calculation runs first, including redrilling of the far-field temperature history, with Ramey's
model, the constant temperature drop, the productivity-index production pump model and the impedance model switched
off. The coupled wellbore simulation is then solved along the final far-field history: the produced temperature is the
wellhead temperature, the production well temperature drop is the difference from the reservoir output temperature,
and the production wellhead pressure and reservoir pressure drop are histories. When the pump stage lifts the flow,
the production well pumping power, pump pressure drop and pump depth of the standard model are set from it, so that
the pumping power is subtracted from the plant output and the pumps are costed with the standard correlation. If the
well cannot deliver the flow rate at some reservoir state along the history (and the pump is disabled or not
admissible), the run aborts with an explanation rather than extrapolating. The feedzone temperature, wellhead
enthalpy, flowing bottom-hole pressure, the coupled-wellbore power cycle's gross-power estimate, the pump depth and
power, the self-flow wellhead pressure and the wellhead phase are reported as well bore outputs. Note that the
GEOPHIRES surface plant heat balance assumes liquid water, so the reported heat extraction understates the enthalpy of
a steam-dominated wellhead stream.

Repeated solves of the same production history within one process (goal seeking on the number of wells re-evaluates
the same reservoir decline) reuse the wellbore solution from a small in-process memo keyed on the request.

superhot-wellbore is an optional dependency. Install it with::

    pip install git+https://github.com/softwareengineerprogrammer/superhot-wellbore.git@geophires-client

Reference: Scott, S.W. (2026), Thermo-hydraulic drivers of superhot geothermal well performance, Geothermics, 141,
103784. https://doi.org/10.1016/j.geothermics.2026.103784
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import sys
from collections import Counter, OrderedDict

import numpy as np

from .Parameter import boolParameter, floatParameter, intParameter, strParameter, OutputParameter
from .Units import (
    Units,
    LengthUnit,
    PressureUnit,
    TemperatureUnit,
    FlowRateUnit,
    EnthalpyUnit,
    PowerUnit,
    PercentUnit,
    ThermalConductivityUnit,
)
from .WellBores import WellBores, get_hydrostatic_pressure_kPa, PRODUCTION_WELLBORE_MODEL_PARAMETER_NAME
from .OptionList import PlantType, ProductionWellboreModel, RedrillingTriggerTemperature
from geophires_x.GeoPHIRESUtils import density_water_kg_per_m3, quantity, viscosity_water_Pa_sec
import geophires_x.Model as Model

COUPLED_WELLBORE_MODEL_LABEL = (
    f'{PRODUCTION_WELLBORE_MODEL_PARAMETER_NAME} '
    f'{ProductionWellboreModel.COUPLED_INFLOW_WELLBORE.int_value} '
    f'({ProductionWellboreModel.COUPLED_INFLOW_WELLBORE.value})'
)

SUPERHOT_WELLBORE_INSTALL_HINT = (
    f'{COUPLED_WELLBORE_MODEL_LABEL} requires the superhot-wellbore package, which is not installed. Install it '
    'with: pip install git+https://github.com/softwareengineerprogrammer/superhot-wellbore.git@geophires-client'
)

DEFAULT_TARGET_WELLHEAD_PRESSURE_MPA = 10.0

MILLIDARCY_M2 = 9.869233e-16

PUMP_MODES = ('never', 'auto', 'always')
PUMP_ENVELOPES = ('flag', 'enforce', 'omit')

# Pump stage flags that abort the run under the 'enforce' envelope policy. Under 'omit' the pump stage installs no
# pump outside the envelope (the well is left self-flowing when it reaches the surface on its own, and fails
# otherwise), so only a choked prescribed flow remains to be enforced here.
PUMP_ENFORCED_FLAGS = ('pump_outside_envelope', 'no_liquid_intake', 'choked_flow')
PUMP_OMIT_ENFORCED_FLAGS = ('choked_flow',)

# Pump setting depth above which the productivity-index pump model of WellBores logs a warning.
PUMP_DEPTH_WARNING_M = 600.0

# In-process memo of solved production histories, keyed on the request (see _history_memo_key). Goal seeking on the
# number of wells re-evaluates the same reservoir decline many times within one process.
_HISTORY_MEMO: OrderedDict = OrderedDict()
_HISTORY_MEMO_MAX_ENTRIES = 16


def _import_coupled_wellbore_client():
    """
    Import the superhot-wellbore client lazily so that GEOPHIRES stays importable, and every other wellbore model
    stays usable, without the optional dependency.
    """
    try:
        from superhot_wellbore import client as coupled_wellbore_client
    except ImportError as e:
        raise ImportError(SUPERHOT_WELLBORE_INSTALL_HINT) from e
    return coupled_wellbore_client


class CoupledWellBores(WellBores):
    """
    GEOPHIRES production wellbore model backed by the superhot-wellbore coupled inflow-wellbore model. See module
    docstring.
    """

    uses_coupled_wellbore_model = True

    def __init__(self, model: Model):
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().__init__(model)
        sclass = str(__class__).replace("<class '", '')
        self.MyClass = sclass.replace("'>", '')

        self._coupled_wellbore_client = None
        self.coupled_profile = None
        """superhot_wellbore.client.ProductionProfile over the GEOPHIRES time vector, available after Calculate()"""
        self.transmissivity_md_m: float = float('nan')
        """Transmissivity used by the Darcy inflow model [md*m], available after Calculate()"""
        self.drainage_radius_m: float = float('nan')
        """Drainage radius per production well derived from the reservoir volume [m], available after Calculate()"""

        self.transmissivity = self.ParameterDict[self.transmissivity.Name] = floatParameter(
            'Coupled Wellbore Feedzone Transmissivity',
            DefaultValue=-1.0,
            Min=-1.0,
            Max=1e7,
            UnitType=Units.NONE,
            ToolTipText='Permeability-thickness product (k*b) of the feedzone in millidarcy-metres (md*m), which '
            'controls the radial Darcy drawdown in the coupled wellbore model. Leave at -1 to derive it '
            'from the Productivity Index at the initial reservoir state; specify it to parameterize the inflow as in '
            'Scott (2026).',
        )

        self.casing_roughness = self.ParameterDict[self.casing_roughness.Name] = floatParameter(
            'Coupled Wellbore Casing Roughness',
            DefaultValue=4.6e-5,
            Min=0.0,
            Max=1e-2,
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ToolTipText='Absolute roughness of the production casing used for the frictional pressure gradient in '
            'the coupled wellbore model.',
        )

        self.heat_loss_coefficient = self.ParameterDict[self.heat_loss_coefficient.Name] = floatParameter(
            'Coupled Wellbore Heat Loss Coefficient',
            DefaultValue=2.5,
            Min=0.0,
            Max=100.0,
            UnitType=Units.THERMAL_CONDUCTIVITY,
            PreferredUnits=ThermalConductivityUnit.WPERMPERK,
            CurrentUnits=ThermalConductivityUnit.WPERMPERK,
            ToolTipText='Overall wellbore-to-formation heat transfer coefficient U per metre of well (W/m/K) used '
            'for conductive heat loss in the coupled wellbore model, in place of Ramey\'s model.',
        )

        self.integration_step = self.ParameterDict[self.integration_step.Name] = intParameter(
            'Coupled Wellbore Integration Step',
            DefaultValue=10,
            AllowableRange=list(range(1, 101)),
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ToolTipText='Vertical step, in whole metres, of the bottom-to-surface wellbore march in the coupled '
            'production wellbore model. The well depth is rounded to a whole number of steps.',
        )

        self.max_solve_points = self.ParameterDict[self.max_solve_points.Name] = intParameter(
            'Coupled Wellbore Maximum Solve Points',
            DefaultValue=8,
            AllowableRange=list(range(0, 1001)),
            UnitType=Units.NONE,
            ToolTipText='Maximum number of coupled inflow-wellbore solves over the plant lifetime (or per redrilling '
            'period) in the coupled wellbore model. Each solve takes seconds; time steps in between are '
            'linearly interpolated. Use 0 to solve at every time step. A reservoir that does not decline is solved '
            'once regardless.',
        )

        self.production_pump = self.ParameterDict[self.production_pump.Name] = strParameter(
            'Coupled Wellbore Pump Policy',
            DefaultValue='auto',
            UnitType=Units.NONE,
            ToolTipText='Production pump policy of the coupled wellbore model: never (a well that cannot '
            'deliver the prescribed flow rate to the surface aborts the run), auto (a downhole pump is added when the '
            'unpumped well does not reach the surface or reaches it below Coupled Wellbore Minimum Self-Flow '
            'Wellhead Pressure) or always (pumped whenever a liquid pump intake exists). Circulation Pump Efficiency is the '
            'pump efficiency.',
        )

        self.production_pump_envelope = self.ParameterDict[self.production_pump_envelope.Name] = strParameter(
            'Coupled Wellbore Pump Envelope',
            DefaultValue='flag',
            UnitType=Units.NONE,
            ToolTipText='What happens when the production pump would have to be set deeper than Coupled Wellbore Pump '
            'Maximum Depth or with an intake hotter than Coupled Wellbore Pump Maximum Intake Temperature, '
            'or when the column has no single-phase liquid intake: flag (the pump is modelled and the condition '
            'reported in Production Pump Flags), enforce (the run aborts with the reason) or omit (no such pump is '
            'installed: a well that reaches the surface on its own is left self-flowing below Coupled Wellbore '
            'Minimum Self-Flow Wellhead Pressure, with the condition reported in Production Pump Flags, and the run '
            'aborts only when it does not).',
        )

        self.production_pump_max_depth = self.ParameterDict[self.production_pump_max_depth.Name] = floatParameter(
            'Coupled Wellbore Pump Maximum Depth',
            DefaultValue=1500.0,
            Min=0.0,
            Max=15000.0,
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ToolTipText='Deepest admissible setting depth of the production pump (electric submersible pump '
            'envelope) in the coupled wellbore model.',
        )

        self.production_pump_max_intake_temperature = self.ParameterDict[
            self.production_pump_max_intake_temperature.Name
        ] = floatParameter(
            'Coupled Wellbore Pump Maximum Intake Temperature',
            DefaultValue=250.0,
            Min=0.0,
            Max=400.0,
            UnitType=Units.TEMPERATURE,
            PreferredUnits=TemperatureUnit.CELSIUS,
            CurrentUnits=TemperatureUnit.CELSIUS,
            ToolTipText='Hottest admissible fluid temperature at the production pump intake (electric submersible '
            'pump envelope) in the coupled wellbore model.',
        )

        self.min_self_flow_wellhead_pressure = self.ParameterDict[self.min_self_flow_wellhead_pressure.Name] = (
            floatParameter(
                'Coupled Wellbore Minimum Self-Flow Wellhead Pressure',
                DefaultValue=1000.0,
                Min=0.0,
                Max=50000.0,
                UnitType=Units.PRESSURE,
                PreferredUnits=PressureUnit.KPASCAL,
                CurrentUnits=PressureUnit.KPASCAL,
                ToolTipText='Wellhead pressure below which a well that reaches the surface on its own is pumped '
                'anyway (Coupled Wellbore Pump Policy auto). Production Wellhead Pressure, when given together with '
                'Production Flow Rate per Well, raises this floor and becomes the pumped wellhead pressure.',
            )
        )

        self.pump_npsh_margin = self.ParameterDict[self.pump_npsh_margin.Name] = floatParameter(
            'Coupled Wellbore Pump NPSH Margin',
            DefaultValue=344.7,
            Min=0.0,
            Max=10000.0,
            UnitType=Units.PRESSURE,
            PreferredUnits=PressureUnit.KPASCAL,
            CurrentUnits=PressureUnit.KPASCAL,
            ToolTipText='Margin the pressure must keep above the vapor pressure of the fluid at the production pump '
            'intake (net positive suction head and non-condensable gas allowance, 50 psi in the productivity-index '
            'pump model); the pumped wellhead pressure keeps the same margin so the wellhead stream stays liquid.',
        )

        self.coupled_feedzone_temperature = self.OutputParameterDict[self.coupled_feedzone_temperature.Name] = (
            OutputParameter(
                Name='Feedzone Temperature',
                value=[],
                UnitType=Units.TEMPERATURE,
                PreferredUnits=TemperatureUnit.CELSIUS,
                CurrentUnits=TemperatureUnit.CELSIUS,
                ToolTipText='Feedzone (bottom-hole) fluid temperature history after Darcy drawdown and isenthalpic '
                'expansion into the well, i.e. the temperature at which the fluid enters the wellbore',
            )
        )

        self.coupled_wellhead_enthalpy = self.OutputParameterDict[self.coupled_wellhead_enthalpy.Name] = (
            OutputParameter(
                Name='Wellhead Enthalpy',
                value=[],
                UnitType=Units.ENTHALPY,
                PreferredUnits=EnthalpyUnit.KJPERKG,
                CurrentUnits=EnthalpyUnit.KJPERKG,
                ToolTipText='Specific enthalpy history of the fluid at the wellhead',
            )
        )

        self.coupled_bottomhole_pressure = self.OutputParameterDict[self.coupled_bottomhole_pressure.Name] = (
            OutputParameter(
                Name='Flowing Bottom-hole Pressure',
                value=[],
                UnitType=Units.PRESSURE,
                PreferredUnits=PressureUnit.KPASCAL,
                CurrentUnits=PressureUnit.KPASCAL,
                ToolTipText='Flowing bottom-hole flowing pressure history of the production well',
            )
        )

        self.coupled_gross_power = self.OutputParameterDict[self.coupled_gross_power.Name] = OutputParameter(
            Name='Wellhead Power Cycle Gross Electric Power',
            value=[],
            UnitType=Units.POWER,
            PreferredUnits=PowerUnit.MW,
            CurrentUnits=PowerUnit.MW,
            ToolTipText='Gross turbine power per production well from the coupled-wellbore power cycle (the '
            'binary/flash cycle analysis of the wellhead state by superhot-wellbore). Used by the Coupled Wellbore '
            'Power Cycle surface plant (Power Plant Type 10); reported for comparison with the other surface plant '
            'models otherwise.',
        )

        self.coupled_pump_depth = self.OutputParameterDict[self.coupled_pump_depth.Name] = OutputParameter(
            Name='Production Pump Depth',
            UnitType=Units.LENGTH,
            PreferredUnits=LengthUnit.METERS,
            CurrentUnits=LengthUnit.METERS,
            ToolTipText='Deepest setting depth of the production pump over the plant lifetime; 0 when the well '
            'self-flows throughout',
        )

        self.coupled_pump_power = self.OutputParameterDict[self.coupled_pump_power.Name] = OutputParameter(
            Name='Production Pump Power',
            value=[],
            UnitType=Units.POWER,
            PreferredUnits=PowerUnit.MW,
            CurrentUnits=PowerUnit.MW,
            ToolTipText='Production pump power history per production well (m dP / (rho eta)); 0 when self-flowing',
        )

        self.coupled_self_flow_wellhead_pressure = self.OutputParameterDict[
            self.coupled_self_flow_wellhead_pressure.Name
        ] = OutputParameter(
            Name='Self-Flow Wellhead Pressure',
            value=[],
            UnitType=Units.PRESSURE,
            PreferredUnits=PressureUnit.KPASCAL,
            CurrentUnits=PressureUnit.KPASCAL,
            ToolTipText='Wellhead pressure history the unpumped well would deliver; NaN where the unpumped column does '
            'not reach the surface',
        )

        self.coupled_self_flowing_fraction = self.OutputParameterDict[self.coupled_self_flowing_fraction.Name] = (
            OutputParameter(
                Name='Production Well Self-Flowing Fraction',
                UnitType=Units.PERCENT,
                PreferredUnits=PercentUnit.TENTH,
                CurrentUnits=PercentUnit.TENTH,
                ToolTipText='Fraction of the plant lifetime over which the production well self-flows (no pump)',
            )
        )

        self.coupled_wellhead_phase = self.OutputParameterDict[self.coupled_wellhead_phase.Name] = OutputParameter(
            Name='Wellhead Fluid Phase',
            value='',
            UnitType=Units.NONE,
            ToolTipText='Dominant phase of the wellhead stream over the plant lifetime: single_phase_liquid, '
            'two_phase, single_phase_vapor or supercritical',
        )

        self.coupled_pump_flags = self.OutputParameterDict[self.coupled_pump_flags.Name] = OutputParameter(
            Name='Production Pump Flags',
            value='',
            UnitType=Units.NONE,
            ToolTipText='Conditions the production pump stage reported at any time step: temperature_limit, '
            'depth_limit, self_flow_below_floor, two_phase_at_sandface, pump_outside_envelope, no_liquid_intake',
        )

        self._pump_target_whp_MPa = None
        """Pumped wellhead pressure set point from Production Wellhead Pressure with a prescribed flow rate"""

        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def __str__(self):
        return 'CoupledWellBores'

    def read_parameters(self, model: Model) -> None:
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')
        super().read_parameters(model)

        # Fail early, before any calculation, if the optional dependency is missing.
        self._coupled_wellbore_client = _import_coupled_wellbore_client()

        for parameter, choices in (
            (self.production_pump, PUMP_MODES),
            (self.production_pump_envelope, PUMP_ENVELOPES),
        ):
            parameter.value = str(parameter.value).strip().lower()
            if parameter.value not in choices:
                raise ValueError(f'{parameter.Name} must be one of {", ".join(choices)}; got {parameter.value!r}.')

        if self.redrilling_trigger_temperature.Name in model.InputParameters and (
            self.redrilling_trigger_temperature.value is not RedrillingTriggerTemperature.RESERVOIR
        ):
            model.logger.warning(
                f'{self.redrilling_trigger_temperature.Name} {self.redrilling_trigger_temperature.value.int_value} '
                f'is ignored because {COUPLED_WELLBORE_MODEL_LABEL} measures {self.maxdrawdown.Name} on the reservoir '
                'output temperature: its wellhead temperature is only known once the redrilled history is solved.'
            )
        self.redrilling_trigger_temperature.value = RedrillingTriggerTemperature.RESERVOIR

        # The standard wellbore pass sizes the injection pumps from the plant outlet pressure. With production well
        # pumping switched off below, the built-in outlet correlation of the ORC and direct-use plants reaches a branch
        # that has no wellhead pressure to work from, so a plant other than the Coupled Wellbore Power Cycle needs the
        # outlet pressure given explicitly.
        plant_type = model.InputParameters.get('Power Plant Type')
        plant_type_value = plant_type.sValue if plant_type is not None else None
        if plant_type_value not in (str(PlantType.COUPLED_WELLBORE.int_value), PlantType.COUPLED_WELLBORE.value) and (
            'Plant Outlet Pressure' not in model.InputParameters
        ):
            raise ValueError(
                f'{COUPLED_WELLBORE_MODEL_LABEL} with Power Plant Type {plant_type_value or "(default)"} requires '
                'Plant Outlet Pressure to be given: the injection pumps are sized from it. Alternatively use Power '
                f'Plant Type {PlantType.COUPLED_WELLBORE.int_value} ({PlantType.COUPLED_WELLBORE.value}).'
            )

        # The coupled wellbore simulation replaces Ramey's model, the constant temperature drop, the
        # productivity-index production pump model and the impedance model.
        if self.rameyoptionprod.Provided and self.rameyoptionprod.value:
            model.logger.warning(
                f'{self.rameyoptionprod.Name} is ignored because {COUPLED_WELLBORE_MODEL_LABEL} simulates the production '
                'wellbore heat loss itself.'
            )

        self.rameyoptionprod.value = False
        self.tempdropprod.value = 0.0
        self.productionwellpumping.value = False
        if self.impedancemodelused.value:
            msg = (
                f'{self.impedance.Name} is ignored because {COUPLED_WELLBORE_MODEL_LABEL} computes the reservoir and '
                'production wellbore pressure drops itself.'
            )
            print(f'Warning: {msg}')
            model.logger.warning(msg)
            self.impedancemodelused.value = False

        self._admit_reservoir_temperature(model)

        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def Calculate(self, model: Model) -> None:
        """
        Run the standard wellbore calculation, determine the initial operating point of the well, re-run the
        reservoir model with the resulting flow rate if it was solved for, and solve the coupled inflow-wellbore
        model along the final far-field pressure and temperature histories.
        """
        model.logger.info(f'Init {str(__class__)}: {sys._getframe().f_code.co_name}')

        if self._coupled_wellbore_client is None:
            self._coupled_wellbore_client = _import_coupled_wellbore_client()

        reserv = model.reserv

        P_initial_MPa = self._initial_reservoir_pressure_kPa(model) / 1000.0
        T_initial_C = float(reserv.Trock.value)

        self.drainage_radius_m = self._drainage_radius_m(model)
        self.transmissivity_md_m = self._transmissivity_md_m(model, P_initial_MPa, T_initial_C)

        flow_rate_kgs, prescribed = self._initial_flow_rate_kgs(model, P_initial_MPa, T_initial_C)
        if not prescribed:
            # GEOPHIRES carries one flow rate per well; the reservoir model's thermal decline is redone with the flow
            # rate the well delivers (the base reservoir calculation is cached, so only the model-specific
            # part re-runs, as in the district heating recalculation).
            self.prodwellflowrate.value = flow_rate_kgs
            self.prodwellflowrate.CurrentUnits = FlowRateUnit.KGPERSEC
            reserv.Calculate(model)

        # Far-field temperature history from the reservoir model, before the standard calculation applies redrilling.
        farfield_temperature_C = np.array(reserv.Tresoutput.value, dtype=float)

        # The standard wellbore calculation: reservoir pressure history, redrilling, injection wells.
        super().Calculate(model)

        pressure_history_kPa = np.array(self.production_reservoir_pressure.value, dtype=float)
        if abs(float(pressure_history_kPa[0]) / 1000.0 - P_initial_MPa) > 1e-6:
            model.logger.warning(
                f'superhot-wellbore: initial reservoir pressure used for the operating point ({P_initial_MPa:.3f} MPa) '
                f'differs from the calculated reservoir pressure history ({pressure_history_kPa[0] / 1000.0:.3f} MPa)'
            )

        profile = self._solve_production_history(model, flow_rate_kgs, farfield_temperature_C, pressure_history_kPa)
        self.coupled_profile = profile

        wellhead_temperature_C = np.array(profile.production_temperature_C, dtype=float)
        self.ProdTempDrop.value = np.array(reserv.Tresoutput.value, dtype=float) - wellhead_temperature_C
        self.ProducedTemperature.value = wellhead_temperature_C
        self.Pprodwellhead.value = np.array(profile.whp_MPa, dtype=float) * 1000.0
        self.DPReserv.value = np.array(profile.dP_reservoir_MPa, dtype=float) * 1000.0

        self._apply_production_pumping(model, profile)

        # The wellhead pressure at the start of production is what GEOPHIRES otherwise takes as an input.
        self.ppwellhead.value = float(profile.initial.whp_MPa) * 1000.0
        self.ppwellhead.CurrentUnits = PressureUnit.KPASCAL
        self.usebuiltinppwellheadcorrelation = False

        self.coupled_feedzone_temperature.value = np.array(profile.reservoir_output_temperature_C, dtype=float)
        self.coupled_wellhead_enthalpy.value = np.array(profile.h_wellhead_MJkg, dtype=float) * 1000.0
        self.coupled_bottomhole_pressure.value = np.array([ts.P_bh_MPa for ts in profile.timesteps]) * 1000.0
        self.coupled_gross_power.value = np.array(profile.power_MWe, dtype=float)

        first = profile.initial
        last = profile.timesteps[-1]
        model.logger.info(
            f'superhot-wellbore: {flow_rate_kgs:.2f} kg/s per well; wellhead pressure '
            f'{first.whp_MPa * 1000.0:.0f} to {last.whp_MPa * 1000.0:.0f} kPa, wellhead temperature '
            f'{first.T_wellhead_C:.1f} to {last.T_wellhead_C:.1f} C, feedzone temperature {first.T_feedzone_C:.1f} '
            f'to {last.T_feedzone_C:.1f} C over the plant lifetime; wellhead phase '
            f'{self.coupled_wellhead_phase.value or "unknown"}, self-flowing '
            f'{self.coupled_self_flowing_fraction.value * 100:.0f}% of the time'
        )

        model.logger.info(f'Complete {str(__class__)}: {sys._getframe().f_code.co_name}')

    def _apply_production_pumping(self, model: Model, profile) -> None:
        """
        Set the standard production pumping outputs from the pump stage of the solved production history, so that
        the pumping power is subtracted from the plant output and the pumps are costed like the productivity-index
        pump model's: PumpingPowerProd (all production wells), PumpingPower (injection plus production),
        productionwellpumping, pumpdepth and DPProdWell, plus the pump outputs.
        """
        nprod = int(self.nprod.value)

        pump_power_per_well_MW = np.nan_to_num(np.array(profile.pump_power_MWe, dtype=float), nan=0.0)
        pump_depths_m = np.nan_to_num(np.array(profile.pump_depth_m, dtype=float), nan=0.0)
        pump_dP_kPa = np.nan_to_num(np.array(profile.dP_pump_MPa, dtype=float), nan=0.0) * 1000.0
        pumped = bool(profile.any_pumped)

        self.PumpingPowerProd.value = nprod * pump_power_per_well_MW
        self.productionwellpumping.value = pumped
        self.pumpdepth.value = float(np.max(pump_depths_m)) if pump_depths_m.size else 0.0
        self.DPProdWell.value = pump_dP_kPa
        pumping_power_MW = np.array(self.PumpingPowerInj.value, dtype=float) + self.PumpingPowerProd.value
        self.PumpingPower.value = np.where(pumping_power_MW < 0.0, 0.0, pumping_power_MW)

        self.coupled_pump_depth.value = self.pumpdepth.value
        self.coupled_pump_power.value = pump_power_per_well_MW
        self.coupled_self_flow_wellhead_pressure.value = np.array(profile.self_flow_whp_MPa, dtype=float) * 1000.0
        self_flowing_fraction = float(profile.self_flowing_fraction)
        self.coupled_self_flowing_fraction.value = (
            self_flowing_fraction if math.isfinite(self_flowing_fraction) else 0.0
        )
        # Every phase the wellhead stream takes over the plant lifetime, most frequent first, as the plant path is
        # reported: the phase can change as the reservoir declines and as the pump engages, and a single label would
        # hide a lifetime that crosses the critical point or the saturation envelope.
        phase_counts = Counter(ts.wellhead_phase for ts in profile.timesteps if ts.success and ts.wellhead_phase)
        self.coupled_wellhead_phase.value = ', '.join(phase for phase, _ in phase_counts.most_common())
        flags = sorted({flag for ts in profile.timesteps if ts.success for flag in ts.pump_flags})
        self.coupled_pump_flags.value = ', '.join(flags)

        if pumped:
            model.logger.info(
                f'superhot-wellbore: production pump set at {self.pumpdepth.value:.0f} m, '
                f'{np.max(pump_power_per_well_MW):.3f} MW per well at most '
                f'({np.max(self.PumpingPowerProd.value):.2f} MW for {nprod} wells), pump pressure rise '
                f'{np.max(pump_dP_kPa):.0f} kPa at most' + (f'; flags: {", ".join(flags)}' if flags else '')
            )
            if self.pumpdepth.value > PUMP_DEPTH_WARNING_M:
                model.logger.warning(
                    f'superhot-wellbore: production pump depth of {self.pumpdepth.value:.0f} m is deeper than '
                    f'{PUMP_DEPTH_WARNING_M:.0f} m; verify the reservoir pressure, flow rate and well dimensions '
                    f'({self.production_pump_max_depth.Name} is {self.production_pump_max_depth.value:g} m)'
                )

    # ------------------------------------------------------------------------------------------------------------
    # Inflow model from the GEOPHIRES parameters
    # ------------------------------------------------------------------------------------------------------------

    def _initial_reservoir_pressure_kPa(self, model: Model) -> float:
        """
        Far-field reservoir pressure at the start of production, as the standard wellbore calculation will compute it:
        Reservoir Hydrostatic Pressure (or the built-in correlation) times the Overpressure Percentage.
        """
        reserv = model.reserv
        if self.usebuiltinhydrostaticpressurecorrelation:
            hydrostatic_kPa = get_hydrostatic_pressure_kPa(
                reserv.Trock.value,
                reserv.Tsurf.value,
                reserv.depth.quantity().to('m').magnitude,
                reserv.averagegradient.value,
                reserv.hydrostatic_pressure(),
            )
        else:
            hydrostatic_kPa = self.Phydrostatic.quantity().to('kPa').magnitude
        return float(hydrostatic_kPa) * float(self.overpressure_percentage.value) / 100.0

    def _wellbore_radius_m(self) -> float:
        return float(self.prodwelldiam.quantity().to('m').magnitude) / 2.0

    def _drainage_radius_m(self, model: Model) -> float:
        """
        Radius of the cylinder, of thickness equal to the fracture height, holding one production well's share of
        the calculated reservoir volume.
        """
        reserv = model.reserv
        thickness_m = float(reserv.fracheightcalc.value)
        volume_per_well_m3 = float(reserv.resvolcalc.value) / max(int(self.nprod.value), 1)
        radius_m = math.sqrt(volume_per_well_m3 / (math.pi * thickness_m))

        if radius_m <= 2.0 * self._wellbore_radius_m():
            raise ValueError(
                f'The drainage radius per production well derived from {reserv.resvol.Name} and '
                f'{reserv.fracheight.Name} ({radius_m:.1f} m) is not larger than the wellbore; increase the reservoir '
                'volume or reduce the fracture height.'
            )

        model.logger.info(
            f'superhot-wellbore: drainage radius per production well {radius_m:.0f} m from a reservoir volume of '
            f'{float(reserv.resvolcalc.value):.3e} m3 shared by {int(self.nprod.value)} production wells and a '
            f'feedzone thickness (fracture height) of {thickness_m:.0f} m'
        )
        return radius_m

    def _transmissivity_md_m(self, model: Model, P_reservoir_MPa: float, T_reservoir_C: float) -> float:
        """
        Transmissivity of the Darcy inflow model: specified directly, or derived from the Productivity Index.

        The superhot-wellbore Darcy model gives a drawdown dP = mu * m * ln(re/rw) / (2 pi rho k b) with the fluid
        properties evaluated at the far-field reservoir state, so a productivity index PI = m / dP corresponds to
        k b = PI * mu * ln(re/rw) / (2 pi rho) at that state. The effective productivity index of the solved well is
        somewhat higher because expansion cooling raises the fluid density near the wellbore.
        """
        if self.transmissivity.value > 0:
            model.logger.info(
                f'superhot-wellbore: transmissivity of {self.transmissivity.value:g} md*m specified; '
                f'{self.PI.Name} is not used'
            )
            return float(self.transmissivity.value)

        pressure = quantity(P_reservoir_MPa, 'MPa')
        rho = density_water_kg_per_m3(T_reservoir_C, pressure=pressure)
        mu = viscosity_water_Pa_sec(T_reservoir_C, pressure=pressure)

        PI_kg_per_sec_per_Pa = float(self.PI.quantity().to('kg/s/bar').magnitude) / 1e5
        kb_m3 = (
            PI_kg_per_sec_per_Pa
            * mu
            * math.log(self.drainage_radius_m / self._wellbore_radius_m())
            / (2.0 * math.pi * rho)
        )
        transmissivity_md_m = kb_m3 / MILLIDARCY_M2

        model.logger.info(
            f'superhot-wellbore: {self.PI.Name} of {self.PI.value:g} {self.PI.CurrentUnits.value} corresponds to a '
            f'transmissivity of {transmissivity_md_m:.1f} md*m at {T_reservoir_C:.1f} C and {P_reservoir_MPa:.2f} MPa '
            f'(density {rho:.1f} kg/m3, viscosity {mu:.3e} Pa.s)'
        )
        return transmissivity_md_m

    # ------------------------------------------------------------------------------------------------------------
    # superhot-wellbore requests
    # ------------------------------------------------------------------------------------------------------------

    def _initial_flow_rate_kgs(self, model: Model, P_reservoir_MPa: float, T_reservoir_C: float) -> tuple:
        """
        :return: (flow rate per well [kg/s], whether it was prescribed rather than solved for)
        """
        flow_provided = self.prodwellflowrate.Provided
        # -1 selects the GEOPHIRES built-in wellhead pressure correlation, which does not apply here.
        whp_provided = self.ppwellhead.Provided and self.ppwellhead.value > 0

        self._pump_target_whp_MPa = None
        if flow_provided and whp_provided:
            if self.production_pump.value == 'never':
                raise ValueError(
                    f'{COUPLED_WELLBORE_MODEL_LABEL} needs either {self.prodwellflowrate.Name} (prescribed flow rate) or '
                    f'{self.ppwellhead.Name} (target wellhead pressure), not both, when {self.production_pump.Name} '
                    'is never: the coupled inflow-wellbore model computes the other one.'
                )
            self._pump_target_whp_MPa = float(self.ppwellhead.quantity().to('MPa').magnitude)

        if flow_provided:
            flow_rate_kgs = float(self.prodwellflowrate.value)
            model.logger.info(
                f'superhot-wellbore: prescribed flow rate of {flow_rate_kgs:g} kg/s per well; the wellhead pressure '
                'will be computed'
                + (
                    f' (pumped to {self._pump_target_whp_MPa:g} MPa where the well does not self-flow at that pressure)'
                    if self._pump_target_whp_MPa is not None
                    else ''
                )
            )
            return flow_rate_kgs, True

        if whp_provided:
            target_whp_MPa = float(self.ppwellhead.quantity().to('MPa').magnitude)
        else:
            target_whp_MPa = DEFAULT_TARGET_WELLHEAD_PRESSURE_MPA
            model.logger.info(
                f'superhot-wellbore: neither {self.prodwellflowrate.Name} nor {self.ppwellhead.Name} provided; '
                f'assuming a target wellhead pressure of {target_whp_MPa:g} MPa'
            )

        sh = self._coupled_wellbore_client
        request = self._request(
            model,
            sh.OperatingConfig(control='whp', target_whp_MPa=target_whp_MPa),
            P_reservoir_MPa,
            T_reservoir_C,
        )
        result = sh.CoupledWellboreClient(request).solve_steady_state()
        if not result.success:
            raise RuntimeError(
                'The coupled wellbore model could not find a flow rate delivering a wellhead pressure of '
                f'{target_whp_MPa:g} MPa at {T_reservoir_C:.1f} C and {P_reservoir_MPa:.2f} MPa: {result.message}. '
                f'Check the reservoir temperature, pressure, {self.PI.Name} and target wellhead pressure.'
            )

        effective_PI = (
            result.mass_flow_kgs / (result.dP_reservoir_MPa * 10.0) if result.dP_reservoir_MPa > 0 else float('nan')
        )
        model.logger.info(
            f'superhot-wellbore: a wellhead pressure of {target_whp_MPa:g} MPa is delivered by '
            f'{result.mass_flow_kgs:.2f} kg/s per well with a reservoir drawdown of {result.dP_reservoir_MPa:.2f} MPa '
            f'(effective productivity index {effective_PI:.2f} kg/s/bar)'
        )
        return float(result.mass_flow_kgs), False

    def _solve_production_history(
        self,
        model: Model,
        flow_rate_kgs: float,
        farfield_temperature_C: np.ndarray,
        pressure_history_kPa: np.ndarray,
    ):
        """
        Solve the coupled inflow-wellbore model at the held flow rate along the far-field pressure history and the
        (possibly redrilled) far-field temperature history in Reservoir Temperature History, over the GEOPHIRES time
        vector.

        When redrilling repeats the far-field temperature history and the pressure is constant, one redrilling period
        is solved and the result is repeated, so that the solve points resolve the decline within a period.

        :return: superhot_wellbore.client.ProductionProfile with one entry per element of the time vector
        """
        times = np.array(model.reserv.timevector.value, dtype=float)
        temperatures_C = np.array(model.reserv.Tresoutput.value, dtype=float)

        period = self._redrilling_period(farfield_temperature_C, temperatures_C)
        if period is not None and np.ptp(pressure_history_kPa) < 1e-9:
            model.logger.info(
                f'superhot-wellbore: solving one redrilling period of {period} time steps and repeating it '
                f'{self.redrill.value} times'
            )
            solve_times = times[:period]
            solve_temperatures = temperatures_C[:period]
            solve_pressures = pressure_history_kPa[:period]
        else:
            if period is not None:
                model.logger.warning(
                    'superhot-wellbore: redrilling with a varying reservoir pressure; the repeated far-field '
                    f'temperature history is resolved only as far as {self.max_solve_points.Name} '
                    f'({self.max_solve_points.value}) allows'
                )
            solve_times, solve_temperatures, solve_pressures = times, temperatures_C, pressure_history_kPa

        client = self._history_client(model, flow_rate_kgs, solve_times, solve_pressures, solve_temperatures)
        profile = self._memoized_profile(model, client, solve_times)
        self._check_production_history(model, profile, flow_rate_kgs)

        for note in profile.notes:
            model.logger.warning(f'superhot-wellbore: {note}')

        if len(profile.timesteps) < len(times):
            repeated = []
            while len(repeated) < len(times):
                repeated.extend(profile.timesteps)
            profile.timesteps = [
                dataclasses.replace(ts, time_yr=float(t)) for ts, t in zip(repeated[: len(times)], times)
            ]

        return profile

    def _memoized_profile(self, model: Model, client, solve_times: np.ndarray):
        """
        The client's production profile, from the in-process memo when the same request (rounded, see
        _history_memo_key) was solved before in this process, else solved and memoized.
        """
        key = self._history_memo_key(client.request, solve_times)
        memoized = _HISTORY_MEMO.get(key)
        if memoized is not None:
            _HISTORY_MEMO.move_to_end(key)
            model.logger.info(f'superhot-wellbore: production history memo hit ({key[:12]})')
            return copy.deepcopy(memoized)

        model.logger.info(f'superhot-wellbore: production history memo miss ({key[:12]}); solving')
        try:
            profile = client.solve_profile(time_yr=solve_times)
        except RuntimeError as e:
            raise RuntimeError(
                f'The well cannot sustain {client.request.operating.mass_flow_kgs:.1f} kg/s along the '
                f'reservoir decline: {e}. Reduce the flow rate or target wellhead pressure, enlarge the fracture '
                f'surface area to slow the thermal decline, allow redrilling ({self.maxdrawdown.Name}), or revise '
                f'the production pump settings ({self.production_pump.Name}).'
            ) from e
        _HISTORY_MEMO[key] = copy.deepcopy(profile)
        while len(_HISTORY_MEMO) > _HISTORY_MEMO_MAX_ENTRIES:
            _HISTORY_MEMO.popitem(last=False)
        return profile

    @staticmethod
    def _history_memo_key(request, solve_times: np.ndarray) -> str:
        """
        SHA-256 of the request with the decline histories rounded (temperatures to 0.05 degC, pressures to 1 kPa,
        times to 1e-6 yr), the transmissivity to 3 significant figures and the drainage radius to 0.1 m, so that the
        small perturbations of a goal seek on the number of wells reuse the solved history. Everything else in the
        request (well geometry, roughness, heat loss, pump section, power cycle, solver settings) is part of the key
        at full precision.
        """

        def _round_table(table, value_decimals: int):
            if table is None:
                return None
            return [[round(float(row[0]), 6)] + [round(float(v), value_decimals) for v in row[1:]] for row in table]

        def _round_to(value, step: float):
            return None if value is None else round(round(float(value) / step) * step, 10)

        d = request.to_dict()
        reservoir = d['reservoir']
        reservoir['T_reservoir_C'] = _round_to(reservoir['T_reservoir_C'], 0.05)
        reservoir['P_reservoir_MPa'] = _round_to(reservoir['P_reservoir_MPa'], 0.001)
        if reservoir.get('transmissivity_md_m') is not None:
            reservoir['transmissivity_md_m'] = float(f'{float(reservoir["transmissivity_md_m"]):.3g}')
        reservoir['drainage_radius_m'] = _round_to(reservoir['drainage_radius_m'], 0.1)
        decline = d['decline']
        if decline.get('temperature_profile') is not None:
            decline['temperature_profile'] = [
                [round(float(t), 6), _round_to(T, 0.05)] for t, T in decline['temperature_profile']
            ]
        decline['pressure_profile'] = _round_table(decline.get('pressure_profile'), 3)
        decline['feedzone_profile'] = _round_table(decline.get('feedzone_profile'), 6)
        decline['mass_flow_profile'] = _round_table(decline.get('mass_flow_profile'), 6)
        d['solve_times_yr'] = [round(float(t), 6) for t in np.asarray(solve_times, dtype=float)]

        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode('utf-8')).hexdigest()

    def _check_production_history(self, model: Model, profile, flow_rate_kgs: float) -> None:
        """
        Abort with an explanation if the coupled model failed at any solved state (the well cannot deliver the flow
        rate and the pump is disabled or, under the enforce and omit envelope policies, not admissible), or if a pump
        stage flag that the envelope policy forbids was raised (PUMP_ENFORCED_FLAGS, PUMP_OMIT_ENFORCED_FLAGS).
        """
        envelope = self.production_pump_envelope.value
        enforced = (
            PUMP_ENFORCED_FLAGS if envelope == 'enforce' else PUMP_OMIT_ENFORCED_FLAGS if envelope == 'omit' else ()
        )
        for ts in profile.timesteps:
            if not ts.solved:
                continue
            enforced_flags = [flag for flag in ts.pump_flags if flag in enforced]
            if ts.success and not enforced_flags:
                continue
            flags = ', '.join(ts.pump_flags) if ts.pump_flags else 'none'
            detail = (
                f'at t = {ts.time_yr:.2f} yr (reservoir {ts.P_reservoir_MPa:.2f} MPa, {ts.T_reservoir_C:.1f} C)'
                f': {ts.message or "the coupled inflow-wellbore model failed"}; pump flags: {flags}'
            )
            if ts.pumped or ts.pump_depth_m > 0:
                detail += (
                    f'; pump intake {ts.pump_depth_m:.0f} m, {ts.T_pump_intake_C:.1f} C '
                    f'(limits {self.production_pump_max_depth.value:g} m, '
                    f'{self.production_pump_max_intake_temperature.value:g} C)'
                )
            raise RuntimeError(
                f'The well cannot sustain {flow_rate_kgs:.1f} kg/s along the reservoir decline {detail}. '
                'Reduce the flow rate or target wellhead pressure, enlarge the fracture surface area to slow the '
                f'thermal decline, allow redrilling ({self.maxdrawdown.Name}), or revise the production pump '
                f'settings ({self.production_pump.Name}, {self.production_pump_envelope.Name}).'
            )

    def _redrilling_period(self, farfield_temperature_C: np.ndarray, redrilled_temperature_C: np.ndarray):
        """
        Length in time steps of the repeated far-field temperature history when WellBores.calculate_redrilling has
        applied redrilling, or None. The redrilled history is the un-redrilled one repeated from the redrilling
        trigger onwards, so the trigger index is where the two first differ.
        """
        if self.redrill.value <= 0 or len(farfield_temperature_C) != len(redrilled_temperature_C):
            return None
        differing = np.flatnonzero(~np.isclose(redrilled_temperature_C, farfield_temperature_C, rtol=0, atol=1e-9))
        if differing.size == 0:
            return None
        return int(differing[0])

    def _history_client(
        self,
        model: Model,
        flow_rate_kgs: float,
        times_yr: np.ndarray,
        pressure_history_kPa: np.ndarray,
        temperature_history_C: np.ndarray,
    ):
        """
        Client for the production history: prescribed (held) flow rate along the far-field pressure and temperature
        histories from GEOPHIRES and the reservoir model.
        """
        sh = self._coupled_wellbore_client
        times = np.array(times_yr, dtype=float)
        pressures_MPa = np.array(pressure_history_kPa, dtype=float) / 1000.0

        def _table(values):
            return [[float(t), float(v)] for t, v in zip(times, values)]

        temperature_varies = np.ptp(temperature_history_C) > 1e-9
        pressure_varies = np.ptp(pressures_MPa) > 1e-9
        decline = sh.DeclineConfig(
            temperature_mode='explicit' if temperature_varies else 'none',
            temperature_profile=_table(temperature_history_C) if temperature_varies else None,
            min_temperature_C=1.0,
            pressure_mode='explicit' if pressure_varies else 'none',
            pressure_profile=_table(pressures_MPa) if pressure_varies else None,
            min_pressure_MPa=0.1,
        )

        request = self._request(
            model,
            sh.OperatingConfig(control='flow', mass_flow_kgs=flow_rate_kgs),
            float(pressures_MPa[0]),
            float(temperature_history_C[0]),
            decline=decline,
        )
        return sh.CoupledWellboreClient(request)

    def _request(self, model: Model, operating, P_reservoir_MPa: float, T_reservoir_C: float, decline=None):
        sh = self._coupled_wellbore_client
        depth_m = self._snapped_well_depth_m(model)

        return sh.CoupledWellboreRequest(
            name='geophires',
            reservoir=sh.ReservoirConfig(
                P_reservoir_MPa=P_reservoir_MPa,
                T_reservoir_C=T_reservoir_C,
                transmissivity_md_m=self.transmissivity_md_m,
                drainage_radius_m=self.drainage_radius_m,
            ),
            well=sh.WellConfig(
                depth_m=depth_m,
                diameter_m=2.0 * self._wellbore_radius_m(),
                delta_z_m=float(self.integration_step.value),
                roughness_m=float(self.casing_roughness.quantity().to('m').magnitude),
                heat_loss_factor=float(self.heat_loss_coefficient.value),
            ),
            rock_temperature=self._rock_temperature_config(model, depth_m),
            operating=operating,
            decline=decline if decline is not None else sh.DeclineConfig(),
            time=sh.TimeConfig(
                plant_lifetime_yr=model.surfaceplant.plant_lifetime.value,
                timesteps_per_year=model.economics.timestepsperyear.value,
            ),
            # Failed states are inspected by _check_production_history (with the pump flags) rather than raised.
            solver=sh.SolverConfig(max_solve_points=int(self.max_solve_points.value), strict=False),
            # Power cycle of every solved state (used by the Coupled Wellbore Power Cycle surface plant, reported
            # otherwise): superhot-wellbore defaults, with the exergy dead state at ambient temperature and the binary
            # cycle rejecting the geofluid at the injection temperature, so that its heat balance agrees with GEOPHIRES'.
            power_cycle=sh.PowerCycleConfig(
                T_ambient_C=float(model.surfaceplant.ambient_temperature.value),
                T_reject_C=max(float(self.Tinj.value), sh.PowerCycleConfig().T_wf_inlet_C + 1.0),
            ),
            pump=self._pump_config(model),
        )

    def _pump_config(self, model: Model):
        """
        Production pump section of the request from the Coupled Wellbore Pump Policy parameters, Circulation Pump
        Efficiency and, with a prescribed flow rate, Production Wellhead Pressure as the pumped wellhead pressure.
        """
        sh = self._coupled_wellbore_client
        return sh.PumpConfig(
            mode=str(self.production_pump.value),
            efficiency=float(model.surfaceplant.pump_efficiency.value),
            npsh_margin_MPa=float(self.pump_npsh_margin.quantity().to('MPa').magnitude),
            min_self_flow_whp_MPa=float(self.min_self_flow_wellhead_pressure.quantity().to('MPa').magnitude),
            max_depth_m=float(self.production_pump_max_depth.quantity().to('m').magnitude),
            max_intake_temperature_C=float(self.production_pump_max_intake_temperature.value),
            envelope=str(self.production_pump_envelope.value),
            target_whp_MPa=self._pump_target_whp_MPa,
        )

    def _snapped_well_depth_m(self, model: Model) -> float:
        """
        Feedzone depth rounded to a whole number of wellbore integration steps, as the wellbore march requires.
        """
        depth_m = float(model.reserv.depth.quantity().to('m').magnitude)
        step = int(self.integration_step.value)
        snapped = max(int(round(depth_m / step)), 1) * step
        if abs(snapped - depth_m) > 1e-9:
            model.logger.info(
                f'superhot-wellbore: well depth rounded from {depth_m:.1f} m to {snapped} m, '
                f'a whole number of {step} m wellbore integration steps'
            )
        return float(snapped)

    def _rock_temperature_config(self, model: Model, depth_m: float):
        """
        Formation temperature profile for wellbore heat loss: piecewise linear through the GEOPHIRES gradient
        segments, anchored to the bottom-hole temperature at the feedzone. Gradients are in C/m and thicknesses in m
        after Reservoir.read_parameters.
        """
        reserv = model.reserv
        T_surface_C = float(reserv.Tsurf.value)
        profile = {0.0: T_surface_C}
        z = 0.0
        T = T_surface_C
        numseg = int(reserv.numseg.value)
        for i in range(numseg):
            thickness = float(reserv.layerthickness.value[i])
            if i == numseg - 1 or z + thickness >= depth_m:
                break
            z += thickness
            T += float(reserv.gradient.value[i]) * thickness
            profile[z] = T
        profile[depth_m] = float(reserv.Trock.value)

        return self._coupled_wellbore_client.RockTemperatureConfig(
            mode='user', T_surface_C=T_surface_C, profile_C=profile
        )

    # ------------------------------------------------------------------------------------------------------------
    # Reservoir temperature admissibility
    # ------------------------------------------------------------------------------------------------------------

    def _admit_reservoir_temperature(self, model: Model) -> None:
        """
        Raise Maximum Temperature if it would cap the drilling depth above the reservoir. Superhot
        reservoirs typically exceed the GEOPHIRES default of 400 C, and silently truncating the well depth would
        change the modelled system. Runs after the reservoir parameters are read and before any calculation.
        """
        reserv = model.reserv
        projected_Trock = self._projected_bottom_hole_temperature_C(model)
        if projected_Trock <= reserv.Tmax.value:
            return

        if projected_Trock > reserv.Tmax.Max:
            raise ValueError(
                f'The bottom-hole temperature implied by {reserv.depth.Name} and the geothermal gradient(s) '
                f'({projected_Trock:.1f} C) exceeds the {reserv.Tmax.Max:g} C limit of {reserv.Tmax.Name}.'
            )

        raised_Tmax = min(projected_Trock + 1.0, float(reserv.Tmax.Max))
        msg = (
            f'Raising {reserv.Tmax.Name} from {reserv.Tmax.value:g} C to {raised_Tmax:g} C so that the coupled '
            f'reservoir temperature of {projected_Trock:.1f} C is admissible. Set {reserv.Tmax.Name} explicitly to '
            'silence this warning.'
        )
        print(f'Warning: {msg}')
        model.logger.warning(msg)
        reserv.Tmax.value = raised_Tmax

    def _projected_bottom_hole_temperature_C(self, model: Model) -> float:
        """
        Bottom-hole temperature that Reservoir.Calculate will derive from the depth and gradient segments
        (with no Maximum Temperature depth cap applied).
        """
        reserv = model.reserv
        depth_m = float(reserv.depth.quantity().to('m').magnitude)
        numseg = int(reserv.numseg.value)
        T = float(reserv.Tsurf.value)
        z = 0.0
        for i in range(numseg):
            thickness = float(reserv.layerthickness.value[i])
            if i == numseg - 1 or depth_m <= z + thickness:
                return T + float(reserv.gradient.value[i]) * (depth_m - z)
            T += float(reserv.gradient.value[i]) * thickness
            z += thickness
        return T

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np
import CoolProp.CoolProp as CP

from tests.base_test_case import BaseTestCase

# Ruff disabled because imports are order-dependent
# ruff: noqa: I001
from geophires_x.Model import Model
from geophires_x.MPFReservoir import MPFReservoir
from geophires_x.OptionList import PlantType
import geophires_x.CoupledWellBores as coupled_well_bores_module
from geophires_x.CoupledWellBores import SUPERHOT_WELLBORE_INSTALL_HINT
from geophires_x.CoupledWellBores import CoupledWellBores
from geophires_x.SurfacePlantCoupledWellbore import SurfacePlantCoupledWellbore, PLANT_PATH_COST_TYPES
from geophires_x.SurfacePlantUtils import liquid_plant_correlation
from geophires_x.WellBores import WellPressureDrop
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXClient
from geophires_x_client import GeophiresXResult

SUPERHOT_WELLBORE_AVAILABLE = importlib.util.find_spec('superhot_wellbore') is not None

_EXAMPLE_FILE = 'examples/example_SHR-4.txt'
_PUMPED_EXAMPLE_FILE = 'examples/example_SHR-6.txt'

# Keeps the secondary tests short: the thermal decline is solved at two points and interpolated in between.
_FAST_SOLVE = {'Coupled Wellbore Maximum Solve Points': 2}


def _synthetic_profile(times_yr, **fields):
    """
    A superhot-wellbore ProductionProfile with one identical, successful, solved time step per time (no physics),
    for tests of the GEOPHIRES bookkeeping around the client. Keyword arguments override TimestepResult fields.
    """
    from superhot_wellbore.client.config import CoupledWellboreRequest
    from superhot_wellbore.client.results import ProductionProfile, TimestepResult

    defaults = {
        'P_reservoir_MPa': 30.0,
        'T_reservoir_C': 450.0,
        'mass_flow_kgs': 60.0,
        'whp_MPa': 10.0,
        'T_wellhead_C': 317.0,
        'h_wellhead_MJkg': 2.77,
        'T_feedzone_C': 391.0,
        'h_feedzone_MJkg': 2.82,
        'P_bh_MPa': 18.5,
        'dP_reservoir_MPa': 11.5,
        'power_MWe': 32.0,
        'cycle': 'flash',
        'eta_utilization': 0.4,
        'exergy_rate_MW': 80.0,
        'wellhead_phase': 'single_phase_vapor',
        'self_flowing': True,
        'self_flow_whp_MPa': 10.0,
        'converged': True,
        'success': True,
        'solved': True,
    }
    defaults.update(fields)
    request = CoupledWellboreRequest.from_dict(
        {
            'name': 'synthetic',
            'reservoir': {'P_reservoir_MPa': 30.0, 'T_reservoir_C': 450.0},
            'well': {'depth_m': 3500},
            'operating': {'control': 'flow', 'mass_flow_kgs': defaults['mass_flow_kgs']},
        }
    )
    timesteps = [
        TimestepResult(time_yr=float(t), **{k: (list(v) if isinstance(v, list) else v) for k, v in defaults.items()})
        for t in times_yr
    ]
    return ProductionProfile(request=request, depth_m=3500.0, timesteps=timesteps)


class CoupledWellBoresTestCase(BaseTestCase):
    """
    Tests of the coupled inflow-wellbore production wellbore model. The ones that solve the coupled model require the optional
    superhot-wellbore package and are skipped without it.
    """

    def _example_path(self) -> str:
        return self._get_test_file_path(Path('..', _EXAMPLE_FILE))

    def _model(self, params: dict | None = None, without: tuple[str, ...] = (), calculate: bool = True) -> Model:
        """
        Build, read and (optionally) calculate a model from the example input file, optionally overriding parameters
        (params) or removing them from the input (without).
        """
        example_path = self._example_path()
        if without:
            with open(example_path, encoding='utf-8') as f:
                lines = [line for line in f if line.split(',')[0].strip() not in without]
            example_path = os.path.join(tempfile.gettempdir(), f'example_SHR-4-{uuid.uuid4()!s}.txt')
            with open(example_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

        input_params = GeophiresInputParameters(from_file_path=example_path, params=params)

        stash_cwd = Path.cwd()
        stash_sys_argv = sys.argv
        sys.argv = ['', input_params.as_file_path()]
        try:
            model = Model(enable_geophires_logging_config=False)
            model.read_parameters()
            if calculate:
                model.Calculate()
        finally:
            sys.argv = stash_sys_argv
            os.chdir(stash_cwd)

        return model

    def test_wellbore_model_selection(self):
        """The flag swaps in the superhot well bores without needing the optional dependency at construction."""
        stash_sys_argv = sys.argv
        try:
            sys.argv = ['', GeophiresInputParameters({'Production Wellbore Model': 2}).as_file_path()]
            model = Model(enable_geophires_logging_config=False)
            self.assertIsInstance(model.wellbores, CoupledWellBores)

            sys.argv = ['', GeophiresInputParameters({'Production Wellbore Model': 1}).as_file_path()]
            model = Model(enable_geophires_logging_config=False)
            self.assertNotIsInstance(model.wellbores, CoupledWellBores)

            sys.argv = [
                '',
                GeophiresInputParameters(
                    {'Production Wellbore Model': 2, 'Reservoir Model': 8, 'Is AGS': True}
                ).as_file_path(),
            ]
            with self.assertRaises(ValueError) as cm:
                Model(enable_geophires_logging_config=False)
            self.assertIn('cannot be combined', str(cm.exception))
        finally:
            sys.argv = stash_sys_argv

    def test_missing_dependency_is_reported_clearly(self):
        """Without superhot-wellbore, reading parameters fails with an installation hint rather than later."""
        import geophires_x.CoupledWellBores as module

        original_import = module._import_coupled_wellbore_client

        def _unavailable():
            raise ImportError(SUPERHOT_WELLBORE_INSTALL_HINT)

        module._import_coupled_wellbore_client = _unavailable
        try:
            with self.assertRaises(ImportError) as cm:
                self._model(calculate=False)
        finally:
            module._import_coupled_wellbore_client = original_import

        self.assertIn('pip install', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_example_couples_gringarten_and_superhot_wellbore(self):
        model = self._model()
        reserv = model.reserv
        wellbores: CoupledWellBores = model.wellbores
        profile = wellbores.coupled_profile

        self.assertIsInstance(reserv, MPFReservoir)
        self.assertIsNotNone(profile)
        self.assertEqual(len(profile.timesteps), len(reserv.timevector.value))
        self.assertEqual(profile.n_failed, 0)

        # Reservoir state and inflow geometry assembled from the standard GEOPHIRES parameters
        self.assertAlmostEqual(reserv.Trock.value, 450.0, delta=0.1)
        self.assertAlmostEqual(profile.request.reservoir.P_reservoir_MPa, 30.0, delta=1e-6)
        self.assertAlmostEqual(profile.request.reservoir.T_reservoir_C, reserv.Trock.value, delta=1e-9)
        self.assertAlmostEqual(profile.depth_m, 3500.0, delta=1e-9)
        self.assertAlmostEqual(profile.request.well.diameter_m, 0.217, delta=1e-3)
        self.assertAlmostEqual(wellbores.drainage_radius_m, 500.0, delta=15.0)  # per-well share of the fracture volume
        self.assertAlmostEqual(wellbores.transmissivity_md_m, 1000.0, delta=50.0)  # from Productivity Index 0.35
        self.assertEqual(profile.request.operating.control, 'flow')

        # Initial operating point: the flow rate delivering the 10 MPa target wellhead pressure, then held constant
        first = profile.initial
        self.assertGreater(first.mass_flow_kgs, 0)
        self.assertAlmostEqual(first.whp_MPa, 10.0, delta=0.5)
        self.assertAlmostEqual(wellbores.prodwellflowrate.value, first.mass_flow_kgs, delta=1e-9)
        flows = np.array(profile.mass_flow_kgs)
        self.assertAlmostEqual(float(np.max(flows) - np.min(flows)), 0.0, delta=1e-9)
        self.assertLess(first.T_wellhead_C, first.T_feedzone_C)
        self.assertLess(first.T_feedzone_C, reserv.Trock.value)

        # Gringarten far-field decline (with redrilling, as in Fervo_Project_Cape-6) drives the superhot solves; the
        # wellhead pressure and temperature respond with the flow held
        self.assertAlmostEqual(reserv.Tresoutput.value[0], reserv.Trock.value, delta=1e-9)
        self.assertGreater(wellbores.redrill.value, 0)
        self.assertLess(np.min(reserv.Tresoutput.value), 0.95 * reserv.Trock.value)
        np.testing.assert_allclose(profile.T_reservoir_C, reserv.Tresoutput.value)
        # (with the flow held, the wellhead pressure rises slightly as the cooler fluid gets denser)
        self.assertGreater(np.max(profile.whp_MPa) - np.min(profile.whp_MPa), 0.05)
        self.assertLess(np.min(profile.production_temperature_C), first.T_wellhead_C)
        self.assertLess(np.min(wellbores.coupled_feedzone_temperature.value), first.T_feedzone_C)

        # Production well state reported through the standard well bore outputs
        self.assertFalse(wellbores.rameyoptionprod.value)
        self.assertFalse(wellbores.productionwellpumping.value)
        self.assertFalse(wellbores.impedancemodelused.value)
        # Self-flowing throughout: the production pump stage leaves the well and the pumping power untouched
        self.assertFalse(profile.any_pumped)
        self.assertTrue(all(not ts.pumped for ts in profile.timesteps))
        np.testing.assert_allclose(wellbores.PumpingPower.value, wellbores.PumpingPowerInj.value)
        self.assertEqual(float(np.max(wellbores.PumpingPowerProd.value)), 0.0)
        self.assertEqual(wellbores.pumpdepth.value, 0.0)
        self.assertEqual(wellbores.coupled_self_flowing_fraction.value, 1.0)
        # Every phase over the plant lifetime, most frequent first: this well is vapor-dominated but crosses into
        # two-phase as the reservoir declines.
        self.assertEqual(wellbores.coupled_wellhead_phase.value, 'single_phase_vapor, two_phase')
        self.assertEqual(wellbores.coupled_pump_flags.value, '')
        self.assertAlmostEqual(
            wellbores.coupled_self_flow_wellhead_pressure.value[0], first.whp_MPa * 1000.0, delta=1e-6
        )
        np.testing.assert_allclose(wellbores.ProducedTemperature.value, profile.production_temperature_C)
        np.testing.assert_allclose(
            wellbores.ProdTempDrop.value, np.array(reserv.Tresoutput.value) - np.array(profile.production_temperature_C)
        )
        np.testing.assert_allclose(wellbores.Pprodwellhead.value, np.array(profile.whp_MPa) * 1000.0)
        np.testing.assert_allclose(wellbores.DPReserv.value, np.array(profile.dP_reservoir_MPa) * 1000.0)
        self.assertAlmostEqual(wellbores.ppwellhead.value, first.whp_MPa * 1000.0, delta=1e-6)
        np.testing.assert_allclose(wellbores.production_reservoir_pressure.value, 30000.0)

        # Coupled wellbore model outputs
        self.assertTrue(np.all(np.isfinite(wellbores.coupled_feedzone_temperature.value)))
        self.assertTrue(np.all(wellbores.coupled_bottomhole_pressure.value < 30000.0))
        self.assertTrue(np.all(wellbores.coupled_gross_power.value > 0))

        # Coupled Wellbore Power Cycle plant: electricity from the coupled-wellbore cycle, derated by the parasitic load
        plant = model.surfaceplant
        self.assertIsInstance(plant, SurfacePlantCoupledWellbore)
        self.assertEqual(plant.coupled_power_cycle.value, 'flash')
        self.assertTrue(plant.coupled_cycle_is_flash)
        self.assertEqual(plant.plant_policy.value, 'cycle-only')
        self.assertEqual(plant.coupled_plant_path_output.value, 'coupled_wellbore_flash')
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SINGLE_FLASH)
        nprod = wellbores.nprod.value
        gross = np.array(profile.power_MWe)
        np.testing.assert_allclose(plant.ElectricityProduced.value, nprod * gross * (1 - plant.parasitic_load.value))
        np.testing.assert_allclose(wellbores.coupled_gross_power.value, gross)
        np.testing.assert_allclose(plant.Availability.value, np.array(profile.exergy_rate_MW) / first.mass_flow_kgs)
        self.assertGreater(plant.ElectricityProduced.value[0], 0)
        # Enthalpy-based heat extraction exceeds the liquid-water cp estimate for a steam-dominated wellhead stream
        cp_based_MW = (
            nprod * first.mass_flow_kgs * reserv.cpwater.value * (first.T_wellhead_C - wellbores.Tinj.value) / 1e6
        )
        self.assertGreater(plant.HeatExtracted.value[0], cp_based_MW)
        self.assertGreater(plant.FirstLawEfficiency.value[0], 0.1)
        self.assertLess(plant.FirstLawEfficiency.value[0], 0.3)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_prescribed_flow_rate(self):
        model = self._model(
            {'Production Flow Rate per Well': 40, **_FAST_SOLVE}, without=('Production Wellhead Pressure',)
        )
        wellbores: CoupledWellBores = model.wellbores
        profile = wellbores.coupled_profile

        self.assertEqual(profile.request.operating.control, 'flow')
        self.assertAlmostEqual(profile.initial.mass_flow_kgs, 40.0, delta=1e-9)
        self.assertAlmostEqual(wellbores.prodwellflowrate.value, 40.0, delta=1e-9)
        self.assertGreater(profile.initial.whp_MPa, 10.0)  # less flow than the 10 MPa solution, so higher pressure
        self.assertAlmostEqual(wellbores.ppwellhead.value, profile.initial.whp_MPa * 1000.0, delta=1e-6)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_flow_rate_and_wellhead_pressure_are_mutually_exclusive_without_a_pump(self):
        with self.assertRaises(ValueError) as cm:
            self._model({'Production Flow Rate per Well': 40, 'Coupled Wellbore Pump Policy': 'never'})
        self.assertIn('not both', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_prescribed_flow_rate_with_wellhead_pressure_is_the_pump_set_point(self):
        """With the pump enabled, both may be given: the flow rate is prescribed and the pressure is pumped to."""
        model = self._model({'Production Flow Rate per Well': 40, **_FAST_SOLVE})
        wellbores: CoupledWellBores = model.wellbores
        profile = wellbores.coupled_profile

        self.assertEqual(profile.request.operating.control, 'flow')
        self.assertAlmostEqual(profile.request.pump.target_whp_MPa, 10.0, delta=1e-9)
        self.assertEqual(profile.request.pump.mode, 'auto')
        # 40 kg/s self-flows above the 10 MPa set point, so no pump is needed
        self.assertGreater(profile.initial.whp_MPa, 10.0)
        self.assertFalse(profile.any_pumped)
        self.assertFalse(wellbores.productionwellpumping.value)

    def test_invalid_pump_parameters_are_rejected(self):
        for params in ({'Coupled Wellbore Pump Policy': 'sometimes'}, {'Coupled Wellbore Pump Envelope': 'ignore'}):
            with self.subTest(params=params):
                with self.assertRaises(ValueError) as cm:
                    self._model(params, calculate=False)
                self.assertIn('must be one of', str(cm.exception))

    # ------------------------------------------------------------------------------------------------------------
    # Production pump
    # ------------------------------------------------------------------------------------------------------------

    def _pumped_model(self, params: dict | None = None, calculate: bool = True) -> Model:
        stash = self._example_path
        self._example_path = lambda: self._get_test_file_path(Path('..', _PUMPED_EXAMPLE_FILE))
        try:
            return self._model(params, calculate=calculate)
        finally:
            self._example_path = stash

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_pumped_liquid_well(self):
        """
        example_SHR-6: a 200 C well at 5.12 km that cannot lift 60 kg/s to the surface is pumped from about 600 m,
        delivers a liquid wellhead to the ORC correlation, and the pumping power and pump cost reach the economics.
        """
        model = self._pumped_model()
        wellbores: CoupledWellBores = model.wellbores
        plant: SurfacePlantCoupledWellbore = model.surfaceplant
        profile = wellbores.coupled_profile
        nprod = int(wellbores.nprod.value)
        first = profile.initial

        self.assertTrue(profile.any_pumped)
        self.assertTrue(all(ts.pumped for ts in profile.timesteps))
        self.assertTrue(wellbores.productionwellpumping.value)
        self.assertGreater(float(np.max(wellbores.PumpingPowerProd.value)), 0.0)
        np.testing.assert_allclose(wellbores.PumpingPowerProd.value, nprod * np.array(profile.pump_power_MWe))
        np.testing.assert_allclose(
            wellbores.PumpingPower.value, np.array(wellbores.PumpingPowerInj.value) + wellbores.PumpingPowerProd.value
        )
        self.assertGreaterEqual(wellbores.pumpdepth.value, 500.0)
        self.assertLessEqual(wellbores.pumpdepth.value, 700.0)
        self.assertEqual(wellbores.pumpdepth.value, float(np.max(profile.pump_depth_m)))
        self.assertEqual(wellbores.coupled_pump_depth.value, wellbores.pumpdepth.value)
        self.assertGreaterEqual(wellbores.DPProdWell.value[0], 4500.0)
        self.assertLessEqual(wellbores.DPProdWell.value[0], 6500.0)
        np.testing.assert_allclose(wellbores.DPProdWell.value, np.array(profile.dP_pump_MPa) * 1000.0)
        np.testing.assert_allclose(wellbores.coupled_pump_power.value, profile.pump_power_MWe)

        # Pumped liquid wellhead just above its vapor pressure (NPSH margin), a little cooler than the intake
        self.assertGreaterEqual(wellbores.ProducedTemperature.value[0], 185.0)
        self.assertLessEqual(wellbores.ProducedTemperature.value[0], 195.0)
        P_sat_intake_kPa = CP.PropsSI('P', 'T', first.T_pump_intake_C + 273.15, 'Q', 0, 'Water') / 1000.0
        self.assertAlmostEqual(
            wellbores.Pprodwellhead.value[0], P_sat_intake_kPa + wellbores.pump_npsh_margin.value, delta=15.0
        )
        self.assertEqual(wellbores.coupled_wellhead_phase.value, 'single_phase_liquid')
        self.assertEqual(wellbores.coupled_self_flowing_fraction.value, 0.0)
        self.assertTrue(all(np.isnan(wellbores.coupled_self_flow_wellhead_pressure.value)))
        self.assertEqual(wellbores.coupled_pump_flags.value, '')
        self.assertEqual(wellbores.redrill.value, 1)

        # Plant: the liquid wellhead goes to the ORC correlation; the plant is costed as a supercritical ORC plant
        self.assertEqual(plant.plant_policy.value, 'correlation-first')
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        self.assertEqual(plant.coupled_plant_path_output.value, 'correlation_orc')
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SUPER_CRITICAL_ORC)
        self.assertFalse(plant.coupled_cycle_is_flash)
        flow = float(wellbores.prodwellflowrate.value)
        A, etau, _ = liquid_plant_correlation(
            wellbores.ProducedTemperature.value, plant.ambient_temperature.value, PlantType.SUPER_CRITICAL_ORC
        )
        np.testing.assert_allclose(plant.ElectricityProduced.value, A * etau * nprod * flow)
        np.testing.assert_allclose(plant.Availability.value, A)
        np.testing.assert_allclose(
            plant.NetElectricityProduced.value, plant.ElectricityProduced.value - wellbores.PumpingPower.value
        )
        self.assertGreater(plant.NetElectricityProduced.value[0], 0.0)

        # Economics: the production pumps are priced with the standard correlation (Cpumpsprod > 0)
        econ = model.economics
        prodpumphp = np.max(wellbores.PumpingPowerProd.value) / nprod * 1341
        Cpumpsprod = (
            nprod
            * 1.5
            * (1750 * prodpumphp**0.7 + 5750 * prodpumphp**0.2 + 10000 + wellbores.pumpdepth.value * 50 * 3.281)
        )
        self.assertGreater(Cpumpsprod, 0.0)
        self.assertGreater(econ.Cpumps, Cpumpsprod)

        # Cross-check against the productivity-index pump model with the same PI, depth, diameter and flow rate:
        # the same order of magnitude (the difference is the temperature-dependent density along the column)
        depth_m = float(model.reserv.depth.quantity().to('m').magnitude)
        DP_kPa, f3, vprod, rho = WellPressureDrop(
            model, np.array(model.reserv.Tresoutput.value), flow, wellbores.prodwelldiam.value, False, depth_m
        )
        P_hydrostatic_kPa = float(wellbores.production_reservoir_pressure.value[0])
        P_minimum_kPa = CP.PropsSI('P', 'T', model.reserv.Trock.value + 273.15, 'Q', 0, 'Water') / 1000.0 + 344.7
        PI_kPa = float(wellbores.PI.value) / 100.0
        pi_pump_depth_m = np.max(
            depth_m
            + (P_minimum_kPa - P_hydrostatic_kPa + flow / PI_kPa)
            / (f3 * (rho * vprod**2 / 2.0) * (1 / wellbores.prodwelldiam.value) / 1e3 + rho * 9.81 / 1e3)
        )
        pi_DP_kPa = P_minimum_kPa - (
            P_hydrostatic_kPa
            - flow / PI_kPa
            - rho * 9.81 * depth_m / 1e3
            - f3 * (rho * vprod**2 / 2.0) * (depth_m / wellbores.prodwelldiam.value) / 1e3
        )
        pi_pump_power_MW = np.max(pi_DP_kPa * flow / rho / plant.pump_efficiency.value / 1e3)
        self.assertAlmostEqualWithinPercentage(pi_pump_depth_m, wellbores.pumpdepth.value, percent=25)
        self.assertAlmostEqualWithinPercentage(pi_pump_power_MW, np.max(profile.pump_power_MWe), percent=25)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_pumped_example_result(self):
        """The pumped example input reproduces its checked-in result (see also test_geophires_examples)."""
        client = GeophiresXClient()
        example_path = self._get_test_file_path(Path('..', _PUMPED_EXAMPLE_FILE))
        result = client.get_geophires_result(GeophiresInputParameters(from_file_path=example_path))
        expected = self._strip_metadata(GeophiresXResult(example_path.replace('.txt', '.out')))
        self.assertDictEqual(expected.result, self._strip_metadata(result).result)

        reservoir_results = result.result['RESERVOIR SIMULATION RESULTS']
        self.assertEqual(reservoir_results['Wellhead Fluid Phase']['value'], 'single_phase_liquid')
        self.assertEqual(reservoir_results['Production Well Self-Flowing Fraction']['value'], 0.0)
        self.assertGreater(reservoir_results['Production Pump Depth']['value'], 500.0)
        self.assertGreater(reservoir_results['Average Production Well Pumping Power']['value'], 0.0)
        self.assertGreater(reservoir_results['Average Production Well Pump Pressure Drop']['value'], 0.0)
        self.assertEqual(
            result.result['SURFACE EQUIPMENT SIMULATION RESULTS']['Power Cycle Path']['value'], 'correlation_orc'
        )

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_enforced_pump_envelope_aborts(self):
        with self.assertRaises(RuntimeError) as cm:
            self._pumped_model(
                {'Coupled Wellbore Pump Envelope': 'enforce', 'Coupled Wellbore Pump Maximum Depth': 400}
            )
        self.assertIn('depth_limit', str(cm.exception))
        self.assertIn('400', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_flagged_pump_envelope_reports(self):
        model = self._pumped_model({'Coupled Wellbore Pump Maximum Depth': 400, **_FAST_SOLVE})
        wellbores: CoupledWellBores = model.wellbores
        self.assertTrue(wellbores.productionwellpumping.value)
        self.assertIn('depth_limit', wellbores.coupled_pump_flags.value)
        self.assertIn('pump_outside_envelope', wellbores.coupled_pump_flags.value)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_omitted_pump_envelope_leaves_a_self_flowing_well_unpumped(self):
        """
        A self-flowing well whose wellhead pressure is below the floor wants a pump; when that pump would sit outside
        the envelope, 'omit' leaves the well self-flowing (flags kept) where 'enforce' aborts.
        """
        params = {
            'Production Flow Rate per Well': 40,
            'Coupled Wellbore Minimum Self-Flow Wellhead Pressure': 50000,
            'Coupled Wellbore Pump Maximum Intake Temperature': 50,
            **_FAST_SOLVE,
        }
        with self.assertRaises(RuntimeError):
            self._model(
                {**params, 'Coupled Wellbore Pump Envelope': 'enforce'}, without=('Production Wellhead Pressure',)
            )

        model = self._model(
            {**params, 'Coupled Wellbore Pump Envelope': 'omit'}, without=('Production Wellhead Pressure',)
        )
        wellbores: CoupledWellBores = model.wellbores
        profile = wellbores.coupled_profile
        self.assertFalse(profile.any_pumped)
        self.assertFalse(wellbores.productionwellpumping.value)
        self.assertTrue(all(ts.success for ts in profile.timesteps))
        self.assertIn('self_flow_below_floor', wellbores.coupled_pump_flags.value)
        self.assertTrue(
            {'pump_outside_envelope', 'no_liquid_intake'} & set(wellbores.coupled_pump_flags.value.split(', ')),
            wellbores.coupled_pump_flags.value,
        )
        self.assertEqual(wellbores.coupled_self_flowing_fraction.value, 0.0)
        self.assertLess(float(wellbores.coupled_self_flow_wellhead_pressure.value[0]), 50000.0)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_omitted_pump_envelope_aborts_a_well_that_cannot_reach_the_surface(self):
        with self.assertRaises(RuntimeError) as cm:
            self._pumped_model(
                {'Coupled Wellbore Pump Envelope': 'omit', 'Coupled Wellbore Pump Maximum Depth': 400, **_FAST_SOLVE}
            )
        self.assertIn('depth_limit', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_pump_never_aborts_a_well_that_cannot_self_flow(self):
        with self.assertRaises(RuntimeError) as cm:
            self._pumped_model({'Coupled Wellbore Pump Policy': 'never', **_FAST_SOLVE})
        self.assertIn('cannot sustain', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_pump_wiring_with_synthetic_profile(self):
        """
        The GEOPHIRES bookkeeping around the client, without the physics: a synthetic pumped profile returned in
        place of the solve fills the standard pumping outputs and the superhot outputs.
        """
        pumped = {
            'pumped': True,
            'pump_depth_m': 600.0,
            'P_pump_intake_MPa': 1.3,
            'T_pump_intake_C': 192.0,
            'dP_pump_MPa': 5.0,
            'pump_power_MWe': 0.45,
            'self_flowing': False,
            'self_flow_whp_MPa': float('nan'),
            'wellhead_phase': 'single_phase_liquid',
            'wellhead_quality': float('nan'),
            'whp_MPa': 1.65,
            'T_wellhead_C': 191.0,
            'h_wellhead_MJkg': 0.812,
            'pump_flags': ['depth_limit', 'pump_outside_envelope'],
        }
        original = CoupledWellBores._memoized_profile
        CoupledWellBores._memoized_profile = lambda self_, model_, client_, times_: _synthetic_profile(times_, **pumped)
        try:
            model = self._model(
                {
                    'Production Flow Rate per Well': 60,
                    'Coupled Wellbore Plant Policy': 'correlation-first',
                    **_FAST_SOLVE,
                },
                without=('Production Wellhead Pressure',),
            )
        finally:
            CoupledWellBores._memoized_profile = original

        wellbores: CoupledWellBores = model.wellbores
        nprod = int(wellbores.nprod.value)
        n = len(model.reserv.timevector.value)
        self.assertTrue(wellbores.productionwellpumping.value)
        np.testing.assert_allclose(wellbores.PumpingPowerProd.value, np.full(n, nprod * 0.45))
        np.testing.assert_allclose(
            wellbores.PumpingPower.value, np.array(wellbores.PumpingPowerInj.value) + nprod * 0.45
        )
        self.assertEqual(wellbores.pumpdepth.value, 600.0)
        np.testing.assert_allclose(wellbores.DPProdWell.value, np.full(n, 5000.0))
        np.testing.assert_allclose(wellbores.coupled_pump_power.value, np.full(n, 0.45))
        self.assertEqual(wellbores.coupled_pump_depth.value, 600.0)
        self.assertEqual(wellbores.coupled_wellhead_phase.value, 'single_phase_liquid')
        self.assertEqual(wellbores.coupled_self_flowing_fraction.value, 0.0)
        self.assertEqual(wellbores.coupled_pump_flags.value, 'depth_limit, pump_outside_envelope')
        np.testing.assert_allclose(wellbores.Pprodwellhead.value, np.full(n, 1650.0))
        np.testing.assert_allclose(wellbores.ProducedTemperature.value, np.full(n, 191.0))
        self.assertEqual(model.surfaceplant.coupled_plant_path_output.value, 'correlation_orc')
        self.assertGreater(model.economics.Cpumps, 0.0)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_production_history_memo(self):
        """Repeated solves of the same (rounded) request reuse the memoized profile; a changed request does not."""
        from superhot_wellbore.client.config import CoupledWellboreRequest

        class _FakeClient:
            def __init__(self, request):
                self.request = request
                self.calls = 0

            def solve_profile(self, time_yr):
                self.calls += 1
                return _synthetic_profile(time_yr)

        def _request(T_offset_C: float = 0.0, roughness_m: float = 4.6e-5) -> CoupledWellboreRequest:
            return CoupledWellboreRequest.from_dict(
                {
                    'reservoir': {'P_reservoir_MPa': 30.0, 'T_reservoir_C': 450.0 + T_offset_C},
                    'well': {'depth_m': 3500, 'roughness_m': roughness_m},
                    'operating': {'control': 'flow', 'mass_flow_kgs': 60.0},
                    'decline': {
                        'temperature_mode': 'explicit',
                        'temperature_profile': [[0.0, 450.0 + T_offset_C], [10.0, 440.0 + T_offset_C]],
                    },
                }
            )

        model = self._model(calculate=False)
        wellbores: CoupledWellBores = model.wellbores
        coupled_well_bores_module._HISTORY_MEMO.clear()
        times = np.linspace(0.0, 10.0, 5)

        client = _FakeClient(_request())
        first = wellbores._memoized_profile(model, client, times)
        second = wellbores._memoized_profile(model, client, times)
        self.assertEqual(client.calls, 1)
        self.assertIsNot(first, second)  # a copy, so that tiling one profile does not alter the memo
        self.assertEqual(len(second.timesteps), len(times))

        # a temperature perturbation within the 0.05 C rounding is a hit, a larger one a miss
        client = _FakeClient(_request(T_offset_C=0.02))
        wellbores._memoized_profile(model, client, times)
        self.assertEqual(client.calls, 0)
        client = _FakeClient(_request(T_offset_C=0.1))
        wellbores._memoized_profile(model, client, times)
        self.assertEqual(client.calls, 1)

        # any other request change (here the casing roughness) or time vector is a miss
        client = _FakeClient(_request(roughness_m=5e-5))
        wellbores._memoized_profile(model, client, times)
        self.assertEqual(client.calls, 1)
        client = _FakeClient(_request())
        wellbores._memoized_profile(model, client, np.linspace(0.0, 10.0, 6))
        self.assertEqual(client.calls, 1)

        self.assertLessEqual(
            len(coupled_well_bores_module._HISTORY_MEMO), coupled_well_bores_module._HISTORY_MEMO_MAX_ENTRIES
        )
        coupled_well_bores_module._HISTORY_MEMO.clear()

    # ------------------------------------------------------------------------------------------------------------
    # Plant policy
    # ------------------------------------------------------------------------------------------------------------

    def _plant_model(self, policy: str = 'correlation-first') -> Model:
        """A read model with a calculated reservoir, ready for a surface plant calculation on a synthetic profile."""
        model = self._model(
            {'Production Flow Rate per Well': 60}, without=('Production Wellhead Pressure',), calculate=False
        )
        model.reserv.Calculate(model)
        model.surfaceplant.plant_policy.value = policy
        return model

    def _plant_on(self, model: Model, **fields) -> SurfacePlantCoupledWellbore:
        wellbores = model.wellbores
        profile = _synthetic_profile(model.reserv.timevector.value, **fields)
        wellbores.coupled_profile = profile
        wellbores.prodwellflowrate.value = 60.0
        wellbores.ProducedTemperature.value = np.array(profile.production_temperature_C)
        wellbores.PumpingPower.value = np.zeros(len(profile.timesteps))
        model.surfaceplant.Calculate(model)
        return model.surfaceplant

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_wellhead_state_policy_paths(self):
        model = self._plant_model()
        nprod = int(model.wellbores.nprod.value)
        flow = 60.0
        T_ambient = model.surfaceplant.ambient_temperature.value
        derate = 1.0 - model.surfaceplant.parasitic_load.value

        # sub-critical liquid at 190 C: ORC correlation
        liquid_190 = {
            'wellhead_phase': 'single_phase_liquid',
            'whp_MPa': 1.65,
            'T_wellhead_C': 190.0,
            'h_wellhead_MJkg': 0.81,
        }
        plant = self._plant_on(model, **liquid_190)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        A, etau, _ = liquid_plant_correlation(np.array([190.0]), T_ambient, PlantType.SUPER_CRITICAL_ORC)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A[0] * etau[0] * nprod * flow, delta=1e-9)
        self.assertAlmostEqual(plant.Availability.value[0], A[0], delta=1e-12)
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SUPER_CRITICAL_ORC)
        self.assertFalse(plant.coupled_cycle_is_flash)

        # sub-critical liquid at 280 C: double-flash correlation
        plant = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=10.0, T_wellhead_C=280.0, h_wellhead_MJkg=1.24
        )
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_double_flash'})
        A, etau, _ = liquid_plant_correlation(np.array([280.0]), T_ambient, PlantType.DOUBLE_FLASH)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A[0] * etau[0] * nprod * flow, delta=1e-9)
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.DOUBLE_FLASH)

        # the ORC maximum temperature decides between the two liquid correlations
        liquid_245 = {
            'wellhead_phase': 'single_phase_liquid',
            'whp_MPa': 5.0,
            'T_wellhead_C': 245.5,
            'h_wellhead_MJkg': 1.06,
        }
        plant = self._plant_on(model, **liquid_245)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_double_flash'})
        model.surfaceplant.liquid_orc_max_temperature.value = 260.0
        plant = self._plant_on(model, **liquid_245)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        model.surfaceplant.liquid_orc_max_temperature.value = 245.0

        # two-phase at 1.8 MPa with x -> 0: the wet double flash tends to the double-flash correlation at T_sat
        whp = 1.8
        T_sat = CP.PropsSI('T', 'P', whp * 1e6, 'Q', 0, 'Water') - 273.15
        w_dry = 0.517
        two_phase = {
            'wellhead_phase': 'two_phase',
            'whp_MPa': whp,
            'T_wellhead_C': T_sat,
            'h_wellhead_MJkg': 1.0,
            'dry_steam_work_MJkg': w_dry,
            'exergy_rate_MW': 40.0,
        }
        plant = self._plant_on(model, wellhead_quality=0.001, **two_phase)
        self.assertEqual(set(plant.coupled_plant_path), {'wet_double_flash'})
        A, etau, _ = liquid_plant_correlation(np.array([T_sat]), T_ambient, PlantType.DOUBLE_FLASH)
        self.assertAlmostEqualWithinPercentage(
            A[0] * etau[0] * nprod * flow, plant.ElectricityProduced.value[0], percent=0.5
        )
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.DOUBLE_FLASH)
        self.assertAlmostEqual(plant.Availability.value[0], 40.0 / flow, delta=1e-12)
        # ...and with x = 1 to the dry-steam turbine work, derated by the parasitic load
        plant = self._plant_on(model, wellhead_quality=1.0, **two_phase)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], nprod * flow * w_dry * derate, delta=1e-9)
        # ...in between, linear in x
        plant = self._plant_on(model, wellhead_quality=0.06, **two_phase)
        expected = nprod * flow * (0.94 * A[0] * etau[0] + 0.06 * w_dry * derate)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], expected, delta=1e-9)

        # saturated vapor below the superheat margin counts as x = 1; superheated vapor goes to the coupled-wellbore cycle
        h_g = CP.PropsSI('H', 'P', 16.0e6, 'Q', 1, 'Water') / 1e6
        plant = self._plant_on(
            model,
            wellhead_phase='single_phase_vapor',
            whp_MPa=16.0,
            T_wellhead_C=348.0,
            h_wellhead_MJkg=h_g + 0.01,
            dry_steam_work_MJkg=0.55,
            wellhead_quality=float('nan'),
        )
        self.assertEqual(set(plant.coupled_plant_path), {'wet_double_flash'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], nprod * flow * 0.55 * derate, delta=1e-9)
        plant = self._plant_on(
            model,
            wellhead_phase='single_phase_vapor',
            whp_MPa=16.0,
            T_wellhead_C=363.0,
            h_wellhead_MJkg=h_g + 0.1,
            cycle='binary',
            power_MWe=25.0,
            exergy_rate_MW=70.0,
        )
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_binary'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], nprod * 25.0 * derate, delta=1e-9)
        self.assertAlmostEqual(plant.Availability.value[0], 70.0 / flow, delta=1e-12)
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SUPER_CRITICAL_ORC)

        # vapor-like supercritical (enthalpy above the critical point's): the coupled-wellbore cycle, costed by the cycle it
        # selected. A dense supercritical wellhead takes the liquid path instead (see the dense-supercritical test).
        supercritical = {
            'wellhead_phase': 'supercritical',
            'whp_MPa': 26.2,
            'T_wellhead_C': 450.0,
            'h_wellhead_MJkg': 2.9,
        }
        plant = self._plant_on(model, cycle='binary', power_MWe=30.0, exergy_rate_MW=80.0, **supercritical)
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_binary'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], nprod * 30.0 * derate, delta=1e-9)
        plant = self._plant_on(model, cycle='flash', power_MWe=30.0, exergy_rate_MW=80.0, **supercritical)
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_flash'})
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SINGLE_FLASH)
        self.assertTrue(plant.coupled_cycle_is_flash)

        # a failed coupled-wellbore cycle aborts only when the path needs it
        plant = self._plant_on(model, power_MWe=float('nan'), exergy_rate_MW=float('nan'), **liquid_190)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        with self.assertRaises(RuntimeError):
            self._plant_on(model, power_MWe=float('nan'), **supercritical)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_cycle_only_policy_reproduces_the_coupled_wellbore_cycle(self):
        model = self._plant_model('cycle-only')
        nprod = int(model.wellbores.nprod.value)
        derate = 1.0 - model.surfaceplant.parasitic_load.value

        # even a liquid wellhead goes to the coupled-wellbore cycle under the cycle-only policy
        plant = self._plant_on(
            model,
            wellhead_phase='single_phase_liquid',
            whp_MPa=1.65,
            T_wellhead_C=190.0,
            cycle='binary',
            power_MWe=4.0,
            exergy_rate_MW=12.0,
            eta_utilization=0.3,
        )
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_binary'})
        np.testing.assert_allclose(plant.ElectricityProduced.value, nprod * 4.0 * derate)
        np.testing.assert_allclose(plant.Availability.value, 12.0 / 60.0)
        np.testing.assert_allclose(plant.coupled_utilization_efficiency.value, 0.3 * derate)
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SUPER_CRITICAL_ORC)

        plant = self._plant_on(model, cycle='flash', power_MWe=32.0, exergy_rate_MW=80.0)
        self.assertEqual(plant.coupled_cost_plant_type, PlantType.SINGLE_FLASH)
        self.assertTrue(plant.coupled_cycle_is_flash)
        with self.assertRaises(RuntimeError):
            self._plant_on(model, power_MWe=float('nan'))

    def test_plant_path_cost_mapping(self):
        self.assertEqual(PLANT_PATH_COST_TYPES['correlation_orc'], PlantType.SUPER_CRITICAL_ORC)
        self.assertEqual(PLANT_PATH_COST_TYPES['coupled_wellbore_binary'], PlantType.SUPER_CRITICAL_ORC)
        self.assertEqual(PLANT_PATH_COST_TYPES['correlation_double_flash'], PlantType.DOUBLE_FLASH)
        self.assertEqual(PLANT_PATH_COST_TYPES['wet_double_flash'], PlantType.DOUBLE_FLASH)
        self.assertEqual(PLANT_PATH_COST_TYPES['coupled_wellbore_flash'], PlantType.SINGLE_FLASH)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_dense_supercritical_wellhead_takes_the_liquid_path(self):
        """A compressed-liquid wellhead above the critical pressure is continuous with its sub-critical neighbour."""
        model = self._plant_model()
        nprod = int(model.wellbores.nprod.value)
        flow = 60.0
        T_ambient = model.surfaceplant.ambient_temperature.value
        dense = {'wellhead_phase': 'supercritical', 'T_wellhead_C': 365.0, 'h_wellhead_MJkg': 1.75}

        # Dense (h below the critical enthalpy): the double-flash correlation at the wellhead temperature, and the
        # coupled-wellbore cycle's power for that state is irrelevant, even NaN.
        plant = self._plant_on(model, whp_MPa=22.5, power_MWe=float('nan'), exergy_rate_MW=float('nan'), **dense)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_double_flash'})
        A, etau, _ = liquid_plant_correlation(np.array([365.0]), T_ambient, PlantType.DOUBLE_FLASH)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A[0] * etau[0] * nprod * flow, delta=1e-9)

        # Its sub-critical neighbour: the same path and the same number.
        neighbour = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=21.9, T_wellhead_C=365.0, h_wellhead_MJkg=1.75
        )
        self.assertEqual(set(neighbour.coupled_plant_path), {'correlation_double_flash'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], neighbour.ElectricityProduced.value[0], delta=1e-9)

        # Vapor-like supercritical (h above the boundary): the coupled-wellbore cycle, as before.
        plant = self._plant_on(
            model,
            wellhead_phase='supercritical',
            whp_MPa=26.2,
            T_wellhead_C=450.0,
            h_wellhead_MJkg=2.9,
            cycle='binary',
            power_MWe=30.0,
            exergy_rate_MW=80.0,
        )
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_binary'})

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_best_output_policy_takes_the_most_productive_admissible_path(self):
        model = self._plant_model(policy='best-output')
        nprod = int(model.wellbores.nprod.value)
        flow = 60.0
        derate = 1.0 - model.surfaceplant.parasitic_load.value
        T_ambient = model.surfaceplant.ambient_temperature.value

        # A two-phase wellhead: the wet double flash competes with the coupled-wellbore flash cycle; a generous cycle power
        # wins, a stingy one loses.
        two_phase = {
            'wellhead_phase': 'two_phase',
            'whp_MPa': 3.0,
            'T_wellhead_C': 233.9,
            'h_wellhead_MJkg': 1.4,
            'dry_steam_work_MJkg': 0.5,
            'exergy_rate_MW': 40.0,
            'wellhead_quality': 0.2,
            'cycle': 'flash',
        }
        plant = self._plant_on(model, power_MWe=40.0, **two_phase)
        self.assertEqual(set(plant.coupled_plant_path), {'coupled_wellbore_flash'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], nprod * 40.0 * derate, delta=1e-9)
        plant = self._plant_on(model, power_MWe=1.0, **two_phase)
        self.assertEqual(set(plant.coupled_plant_path), {'wet_double_flash'})

        # A liquid wellhead below the ORC ceiling: whichever of ORC and double flash is higher (ORC, at 190 C).
        plant = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=1.65, T_wellhead_C=190.0, h_wellhead_MJkg=0.81
        )
        A, etau, _ = liquid_plant_correlation(np.array([190.0]), T_ambient, PlantType.SUPER_CRITICAL_ORC)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A[0] * etau[0] * nprod * flow, delta=1e-9)

        # The coupled-wellbore cycle's binary/flash selection is reported only for the time steps it served.
        self.assertEqual('', plant.coupled_power_cycle.value)

        # Just above the ORC ceiling: the ORC correlation valued at the ceiling, not the double-flash correlation's
        # 17 % lower output, so the output has no step at the ceiling; well above it the double flash takes over.
        ceiling = model.surfaceplant.liquid_orc_max_temperature.value
        A_c, etau_c, _ = liquid_plant_correlation(np.array([ceiling]), T_ambient, PlantType.SUPER_CRITICAL_ORC)
        at_ceiling = A_c[0] * etau_c[0] * nprod * flow
        plant = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=5.0, T_wellhead_C=ceiling + 0.5, h_wellhead_MJkg=1.06
        )
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_orc'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], at_ceiling, delta=1e-9)
        plant = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=9.0, T_wellhead_C=300.0, h_wellhead_MJkg=1.34
        )
        A_df, etau_df, _ = liquid_plant_correlation(np.array([300.0]), T_ambient, PlantType.DOUBLE_FLASH)
        self.assertEqual(set(plant.coupled_plant_path), {'correlation_double_flash'})
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A_df[0] * etau_df[0] * nprod * flow, delta=1e-9)
        self.assertGreater(plant.ElectricityProduced.value[0], at_ceiling)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_correlation_input_is_clamped_to_the_fit_domain(self):
        """A liquid wellhead hotter than the double-flash fit is priced at the top of the fit, not extrapolated."""
        model = self._plant_model()
        nprod = int(model.wellbores.nprod.value)
        T_ambient = model.surfaceplant.ambient_temperature.value
        plant = self._plant_on(
            model, wellhead_phase='single_phase_liquid', whp_MPa=30.0, T_wellhead_C=390.0, h_wellhead_MJkg=1.9
        )
        A, etau, _ = liquid_plant_correlation(np.array([375.0]), T_ambient, PlantType.DOUBLE_FLASH)
        self.assertAlmostEqual(plant.ElectricityProduced.value[0], A[0] * etau[0] * nprod * 60.0, delta=1e-9)

    def test_conventional_plant_needs_its_outlet_pressure(self):
        """A conventional plant type is sized from Plant Outlet Pressure, which the coupled model cannot derive."""
        with self.assertRaises(ValueError) as cm:
            self._model({'Power Plant Type': 2}, without=('Plant Outlet Pressure',), calculate=False)
        self.assertIn('Plant Outlet Pressure', str(cm.exception))

    def test_redrilling_trigger_is_the_reservoir_output_temperature(self):
        """The coupled model measures Maximum Drawdown on the reservoir output temperature, whatever the deck asks."""
        from geophires_x.OptionList import RedrillingTriggerTemperature

        model = self._model({'Redrilling Trigger Temperature': 0}, calculate=False)
        self.assertIs(model.wellbores.redrilling_trigger_temperature.value, RedrillingTriggerTemperature.RESERVOIR)

    def test_invalid_plant_policy_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self._model({'Coupled Wellbore Plant Policy': 'correlations'}, calculate=False)
        self.assertIn('must be one of', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_overpressure_transmissivity_and_maximum_temperature(self):
        """
        The GEOPHIRES overpressure mechanism drives the far-field pressure; transmissivity may be given directly;
        Maximum Temperature is raised to admit the reservoir instead of capping the depth.
        """
        model = self._model(
            {
                'Overpressure Percentage': 110,
                'Overpressure Depletion Rate': 3,
                'Injection Reservoir Depth': 3500,
                'Injection Reservoir Temperature': 300,
                'Injection Reservoir Inflation Rate': 0,
                'Coupled Wellbore Feedzone Transmissivity': 1000,
                'Maximum Temperature': 400,
                **_FAST_SOLVE,
            }
        )
        reserv = model.reserv
        wellbores: CoupledWellBores = model.wellbores
        profile = wellbores.coupled_profile

        self.assertAlmostEqual(wellbores.transmissivity_md_m, 1000.0, delta=1e-9)

        pressures_kPa = np.array(profile.P_reservoir_MPa) * 1000.0
        self.assertAlmostEqual(pressures_kPa[0], 33000.0, delta=1e-6)
        self.assertLess(pressures_kPa[-1], pressures_kPa[0])
        np.testing.assert_allclose(pressures_kPa, wellbores.production_reservoir_pressure.value)

        self.assertAlmostEqual(reserv.Trock.value, 450.0, delta=0.1)
        self.assertAlmostEqual(reserv.depth.quantity().to('m').magnitude, 3500.0, delta=1e-6)
        self.assertGreater(reserv.Tmax.value, 450.0)

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_coupled_power_cycle_requires_superhot_wellbores(self):
        with self.assertRaises(ValueError) as cm:
            self._model(
                {'Ramey Production Wellbore Model': True, **_FAST_SOLVE},
                without=('Production Wellbore Model',),
            )
        self.assertIn('requires Production Wellbore Model 2', str(cm.exception))

    def test_coupled_power_cycle_is_electricity_only(self):
        with self.assertRaises(ValueError) as cm:
            self._model({'End-Use Option': 2}, calculate=False)
        self.assertIn('supports End-Use Option', str(cm.exception))

    @unittest.skipUnless(SUPERHOT_WELLBORE_AVAILABLE, 'superhot-wellbore is not installed')
    def test_example_result(self):
        """The example input reproduces its checked-in result (see also test_geophires_examples)."""
        client = GeophiresXClient()
        result = client.get_geophires_result(GeophiresInputParameters(from_file_path=self._example_path()))
        expected = self._strip_metadata(GeophiresXResult(self._example_path().replace('.txt', '.out')))
        self.assertDictEqual(expected.result, self._strip_metadata(result).result)

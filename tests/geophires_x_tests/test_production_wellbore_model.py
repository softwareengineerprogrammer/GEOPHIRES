from __future__ import annotations

import sys

import numpy as np

from geophires_x.Model import Model
from geophires_x.OptionList import ProductionWellboreModel
from geophires_x_client import GeophiresInputParameters
from tests.base_test_case import BaseTestCase


class ProductionWellboreModelTestCase(BaseTestCase):
    """
    Production Wellbore Model selects the production wellbore model; Ramey Production Wellbore Model, which it
    supersedes, is retained for backwards compatibility and remains the internal source of truth for the
    Ramey/constant-temperature-drop branch.
    """

    def _model(self, params: dict) -> Model:
        stash_sys_argv = sys.argv
        try:
            sys.argv = ['', GeophiresInputParameters(params).as_file_path()]
            model = Model(enable_geophires_logging_config=False)
            model.read_parameters()
            return model
        finally:
            sys.argv = stash_sys_argv

    def assertSelects(self, params: dict, expected: ProductionWellboreModel, ramey: bool) -> Model:
        model = self._model(params)
        self.assertIs(model.wellbores.production_wellbore_model.value, expected)
        self.assertEqual(model.wellbores.rameyoptionprod.value, ramey)
        return model

    def test_default_is_ramey(self):
        """A deck that gives neither name behaves exactly as before the selector existed."""
        self.assertSelects({'Reservoir Depth': 3}, ProductionWellboreModel.RAMEY, ramey=True)

    def test_legacy_boolean_alone_is_honored(self):
        self.assertSelects({'Ramey Production Wellbore Model': 1}, ProductionWellboreModel.RAMEY, ramey=True)
        self.assertSelects(
            {'Ramey Production Wellbore Model': 0},
            ProductionWellboreModel.CONSTANT_TEMPERATURE_DROP,
            ramey=False,
        )

    def test_selector_alone_sets_the_legacy_boolean(self):
        self.assertSelects({'Production Wellbore Model': 1}, ProductionWellboreModel.RAMEY, ramey=True)
        self.assertSelects(
            {'Production Wellbore Model': 0}, ProductionWellboreModel.CONSTANT_TEMPERATURE_DROP, ramey=False
        )

    def test_agreeing_values_do_not_warn(self):
        for selector, ramey_value, expected in (
            (1, 1, ProductionWellboreModel.RAMEY),
            (0, 0, ProductionWellboreModel.CONSTANT_TEMPERATURE_DROP),
        ):
            with self.subTest(selector=selector):
                params = {'Production Wellbore Model': selector, 'Ramey Production Wellbore Model': ramey_value}
                model = self.assertSelects(params, expected, ramey=bool(ramey_value))
                self.assertIsNotNone(model)

    def test_selector_takes_precedence_over_the_legacy_boolean(self):
        """Contradicting values resolve in favor of the selector, with a warning naming the ignored one."""
        for selector, ramey_value, expected, ramey_result in (
            (1, 0, ProductionWellboreModel.RAMEY, True),
            (0, 1, ProductionWellboreModel.CONSTANT_TEMPERATURE_DROP, False),
        ):
            with self.subTest(selector=selector):
                params = {'Production Wellbore Model': selector, 'Ramey Production Wellbore Model': ramey_value}
                with self.assertLogs('root', level='WARNING') as logs:
                    self.assertSelects(params, expected, ramey=ramey_result)
                self.assertTrue(
                    any(
                        'Ramey Production Wellbore Model' in it and 'Production Wellbore Model' in it
                        for it in logs.output
                    ),
                    logs.output,
                )

    def test_redrilling_trigger_temperature_basis(self):
        """Ramey's warm-up delays a produced-temperature trigger; the reservoir-output basis fires on the reservoir."""
        from geophires_x.OptionList import RedrillingTriggerTemperature

        params = {
            'Reservoir Model': 1,
            'Maximum Drawdown': 0.0025,
            'Ramey Production Wellbore Model': 1,
            'Production Wellbore Model': 1,
        }
        produced = self._model(params)
        self.assertIs(produced.wellbores.redrilling_trigger_temperature.value, RedrillingTriggerTemperature.PRODUCED)
        reservoir = self._model({**params, 'Redrilling Trigger Temperature': 1})
        self.assertIs(reservoir.wellbores.redrilling_trigger_temperature.value, RedrillingTriggerTemperature.RESERVOIR)
        produced.Calculate()
        reservoir.Calculate()
        # The same reservoir, so the same output temperature history; the reservoir-output basis cannot trigger
        # later than the produced basis, because Ramey's warm-up only ever raises the produced temperature.
        self.assertGreaterEqual(reservoir.wellbores.redrill.value, produced.wellbores.redrill.value)
        np.testing.assert_allclose(reservoir.reserv.Tresoutput.value[:12], produced.reserv.Tresoutput.value[:12])

    def test_reservoir_model_9_is_rejected(self):
        """The Fimbul feedzone reservoir model is gone; its number is refused by the range check, not later."""
        with self.assertRaises(ValueError) as cm:
            self._model({'Reservoir Model': 9})
        self.assertIn('Reservoir Model', str(cm.exception))

    def test_value_outside_the_allowable_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self._model({'Production Wellbore Model': 3})

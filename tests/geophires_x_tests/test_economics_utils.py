from __future__ import annotations

from geophires_x.EconomicsUtils import expand_schedule_dsl
from tests.base_test_case import BaseTestCase


class EconomicsUtilsTestCase(BaseTestCase):

    def test_expand_schedule_dsl(self):
        total_years = 25
        expanded = expand_schedule_dsl(['0.03', '0.03 * 9', '0.04 * 10', '0.05'], total_years)
        self.assertListEqual([*[0.03] * 10, *[0.04] * 10, *[0.05] * 5], expanded)

        self.assertEqual(len(expanded), total_years)

        for invalid_case in [['foo'], ['0.5 * bar'], ['0.5 * 0.5'], ['0.5 * -2'], ['-0.5 * 2']]:
            with self.assertRaises(ValueError) as ve:
                expand_schedule_dsl(invalid_case, total_years)
                self.assertIn('Invalid', str(ve))

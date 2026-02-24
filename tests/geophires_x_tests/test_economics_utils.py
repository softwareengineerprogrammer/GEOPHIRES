from __future__ import annotations

from geophires_x.EconomicsUtils import expand_schedule
from tests.base_test_case import BaseTestCase


class EconomicsUtilsTestCase(BaseTestCase):

    def test_expand_schedule(self):
        expanded = expand_schedule(['0.03', '0.03 * 9', '0.04 * 10', '0.05'], 25)
        self.assertListEqual([*[0.03] * 10, *[0.04] * 10, *[0.05] * 5], expanded)

        self.assertEqual(len(expanded), 25)

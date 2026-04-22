from __future__ import annotations

from typing import Any

from pint.facets.plain import PlainQuantity

from base_test_case import BaseTestCase
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXClient


class FervoProjectRed2026TestCase(BaseTestCase):

    def test_fervo_project_red_2026_results_against_reference_values(self):
        """
        Asserts that results conform to some of the key reference values claimed in docs/Fervo_Project_Cape-4.md.
        """

        def _q(v: float, u: str) -> PlainQuantity:
            return PlainQuantity(v, u)

        def _vuq(v_u: dict[str, Any]) -> PlainQuantity:
            return self.value_unit_as_quantity(v_u)

        r = GeophiresXClient().get_geophires_result(
            GeophiresInputParameters(from_file_path=self._get_test_file_path('../examples/Fervo_Project_Red-2026.txt'))
        )

        self.assertEqual(_q(0.7, 'MW'), _vuq(r.result['SURFACE EQUIPMENT SIMULATION RESULTS']['Average Pumping Power']))

        self.assertLess(_vuq(r.result['SUMMARY OF RESULTS']['Average Net Electricity Production']), _q(2.0, 'MW'))

        max_total_power_q = _vuq(
            r.result['SURFACE EQUIPMENT SIMULATION RESULTS']['Maximum Total Electricity Generation']
        )
        self.assertGreaterEqual(max_total_power_q, _q(2.1, 'MW'))
        self.assertLess(max_total_power_q, _q(2.8, 'MW'))

        reference_geofluid_availability_q = _q(60, 'kW/(kg/s)')
        result_geofluid_availability_q = _vuq(
            r.result['SURFACE EQUIPMENT SIMULATION RESULTS']['Initial geofluid availability']
        )
        self.assertGreaterEqual(result_geofluid_availability_q, reference_geofluid_availability_q)
        self.assertLessEqual(result_geofluid_availability_q, reference_geofluid_availability_q * 2.5)

        avg_production_temp_q = _vuq(r.result['RESERVOIR SIMULATION RESULTS']['Average Production Temperature'])
        self.assertGreater(avg_production_temp_q, _q(346, 'degF'))
        self.assertLess(avg_production_temp_q, _q(356, 'degF'))

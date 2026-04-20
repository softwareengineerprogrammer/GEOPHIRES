from __future__ import annotations

from base_test_case import BaseTestCase
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXClient


class FervoProjectCape4TestCase(BaseTestCase):

    def test_fervo_project_red_2026_results_against_reference_values(self):
        """
        Asserts that results conform to some of the key reference values claimed in docs/Fervo_Project_Cape-4.md.
        """

        r = GeophiresXClient().get_geophires_result(
            GeophiresInputParameters(from_file_path=self._get_test_file_path('../examples/Fervo_Project_Red-2026.txt'))
        )

        avg_pumping_power_mw = r.result['SURFACE EQUIPMENT SIMULATION RESULTS']['Average Pumping Power']['value']
        self.assertEqual(0.7, avg_pumping_power_mw)

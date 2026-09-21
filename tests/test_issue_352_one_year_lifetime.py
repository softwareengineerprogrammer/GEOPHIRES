import unittest
from pathlib import Path

from geophires_x_client import GeophiresXClient
from geophires_x_client import ImmutableGeophiresInputParameters


class OneYearLifetimeTestCase(unittest.TestCase):
    def test_one_time_step_per_year_and_one_year_lifetime(self):
        input_file = Path(__file__).parent / 'examples' / 'Fervo_Project_Cape-2.txt'
        params = ImmutableGeophiresInputParameters(
            from_file_path=input_file,
            params={'Plant Lifetime': 1, 'Time steps per year': 1},
        )

        result = GeophiresXClient().get_geophires_result(params)

        self.assertEqual(1, result.result['ECONOMIC PARAMETERS']['Project lifetime']['value'])


if __name__ == '__main__':
    unittest.main()

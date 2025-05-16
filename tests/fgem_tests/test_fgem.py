from __future__ import annotations


from base_test_case import BaseTestCase
from geophires_x_client import GeophiresXResult, GeophiresXClient, GeophiresInputParameters


# ruff: noqa: I001  # Successful module initialization is dependent on this specific import order.

# noinspection PyProtectedMember

# noinspection PyProtectedMember


# noinspection SpellCheckingInspection
class FgemTestCase(BaseTestCase):

    def test_fgem(self):
        r = self._get_result({})
        self.assertIsNotNone(r)

    def _egs_test_file_path(self) -> str:
        # return self._get_test_file_path('generic-egs-case-2_sam-single-owner-ppa.txt')
        return self._get_test_file_path('../examples/example4.txt')

    def _get_result(self, _params, file_path=None) -> GeophiresXResult:
        if file_path is None:
            file_path = self._egs_test_file_path()

        return GeophiresXClient().get_geophires_result(
            GeophiresInputParameters(
                from_file_path=file_path,
                params={'Power Plant Type': 10, **_params},
            )
        )

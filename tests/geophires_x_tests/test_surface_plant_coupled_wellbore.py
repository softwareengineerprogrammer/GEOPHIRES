"""
Wellhead-state plant policy of SurfacePlantCoupledWellbore.

The wet double flash prices a sub-critical two-phase or saturated-vapor wellhead: the separated liquid with the
double-flash correlation, the steam fraction with the dry-steam turbine work of the superhot-wellbore package. That
work is reported per timestep and is undefined at a supercritical wellhead, so a profile that starts supercritical
and cools into the vapor region can hand the plant a timestep without it. The plant derives it from the wellhead
pressure instead of losing the timestep.
"""

import math
import unittest

from tests.base_test_case import BaseTestCase

# Ruff disabled because imports are order-dependent
# ruff: noqa: I001
from geophires_x.SurfacePlantCoupledWellbore import SurfacePlantCoupledWellbore


class SurfacePlantCoupledWellboreDrySteamWorkTestCase(BaseTestCase):
    def test_dry_steam_work_is_derived_from_the_wellhead_pressure(self):
        """A sub-critical wellhead always has a turbine work, whatever the timestep carries."""
        work_MJkg = SurfacePlantCoupledWellbore._dry_steam_work_MJkg(10.0)
        self.assertTrue(math.isfinite(work_MJkg), 'saturated steam at 10 MPa can drive a turbine')
        self.assertGreater(work_MJkg, 0.0)

        # The three cells that used to fail: 12.39, 13.76 and 21.51 MPa saturated vapor.
        for whp_MPa in (12.39, 13.76, 21.51):
            self.assertTrue(
                math.isfinite(SurfacePlantCoupledWellbore._dry_steam_work_MJkg(whp_MPa)),
                f'{whp_MPa} MPa is sub-critical and above the condenser pressure',
            )

    def test_no_work_outside_the_turbine_range(self):
        """Above the critical pressure, and at or below the condenser, there is no saturated steam to expand."""
        for whp_MPa in (22.1, 30.0, 0.0, -1.0, float('nan')):
            self.assertFalse(
                math.isfinite(SurfacePlantCoupledWellbore._dry_steam_work_MJkg(whp_MPa)),
                f'{whp_MPa} MPa is outside the dry-steam turbine range',
            )


if __name__ == '__main__':
    unittest.main()

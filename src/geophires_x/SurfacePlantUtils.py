from __future__ import annotations

import numpy as np

from geophires_x.OptionList import PlantType

MAX_CONSTRUCTION_YEARS = 15

# Utilization efficiency (etau) and reinjection temperature quadratics of the liquid-water plant correlations, keyed
# on the plant type name and on whether the ambient temperature is below 15 degC (the lower and upper fits are then
# blended on the ambient temperature as in SurfacePlant.reinjection_temperature). The coefficients are those of
# SurfacePlantSupercriticalORC.Calculate and SurfacePlantDoubleFlash.Calculate.
_LIQUID_PLANT_COEFFICIENTS = {
    PlantType.SUPER_CRITICAL_ORC.name: {
        True: dict(
            C21=-1.55e-5,
            C11=7.604e-3,
            C01=-3.78e-1,
            D21=-1.499e-5,
            D11=7.4268e-3,
            D01=-3.7915e-1,
            C22=0.0,
            C12=0.02,
            C02=49.26,
            D22=0.0,
            D12=0.02,
            D02=56.26,
        ),
        False: dict(
            C21=-1.499e-5,
            C11=7.4268e-3,
            C01=-3.7915e-1,
            D21=-1.55e-5,
            D11=7.55136e-3,
            D01=-4.041e-1,
            C22=0.0,
            C12=0.02,
            C02=56.26,
            D22=0.0,
            D12=0.02,
            D02=63.26,
        ),
    },
    PlantType.DOUBLE_FLASH.name: {
        True: dict(
            C21=-1.200e-6,
            C11=1.22731e-3,
            C01=2.26956e-1,
            D21=-1.42165e-6,
            D11=1.37050e-3,
            D01=1.99847e-1,
            C22=-7.70928e-4,
            C12=5.02466e-1,
            C02=5.22091,
            D22=-7.69455e-4,
            D12=5.09406e-1,
            D02=11.6859,
        ),
        False: dict(
            C21=-1.42165e-6,
            C11=1.37050e-3,
            C01=1.99847e-1,
            D21=-1.66771e-6,
            D11=1.53079e-3,
            D01=1.69439e-1,
            C22=-7.69455e-4,
            C12=5.09406e-1,
            C02=11.6859,
            D22=-7.67751e-4,
            D12=5.16356e-1,
            D02=18.0798,
        ),
    },
}


def availability_water_MJ_per_kg(T0: float, T1, T2) -> np.ndarray:
    """
    Availability (exergy) of liquid water between temperatures T1 and T2 relative to the dead state T0 [MJ/kg]; the
    same expression as SurfacePlant.availability_water (GEOPHIRES v1.0 Fortran code), kept here so that it can be used
    without a surface plant instance.
    """
    A = 4.041650
    B = -1.204e-2
    C = 1.60500e-5

    T0 = T0 + 273.15
    T1 = np.asarray(T1, dtype=float) + 273.15
    T2 = np.asarray(T2, dtype=float) + 273.15
    return (
        (
            (A - B * T0) * (T1 - T2)
            + (B - C * T0) / 2.0 * (T1**2 - T2**2)
            + C / 3.0 * (T1**3 - T2**3)
            - A * T0 * np.log(T1 / T2)
        )
        * 2.2046
        / 947.83
    )


def liquid_plant_correlation(T_entering: np.ndarray, T_ambient: float, plant_type: PlantType) -> tuple:
    """
    GEOPHIRES's liquid-water power plant correlations evaluated at the plant entering temperature(s), without the side
    effects of the surface plant classes (no injection temperature override).

    :param T_entering: plant entering (produced) temperature(s) [degC]
    :param T_ambient: ambient temperature [degC]
    :param plant_type: PlantType.SUPER_CRITICAL_ORC or PlantType.DOUBLE_FLASH
    :return: (availability [MJ/kg] of the liquid at T_entering relative to the ambient dead state, utilization
        efficiency etau [-], reinjection temperature [degC]); each an array shaped like T_entering
    """
    if plant_type.name not in _LIQUID_PLANT_COEFFICIENTS:
        raise ValueError(f'No liquid plant correlation for {plant_type}')

    T = np.asarray(T_entering, dtype=float)
    T_ambient = float(T_ambient)
    c = _LIQUID_PLANT_COEFFICIENTS[plant_type.name][T_ambient < 15.0]

    availability = availability_water_MJ_per_kg(T_ambient, T, T_ambient)

    if T_ambient < 15.0:
        Tfraction = (T_ambient - 5.0) / 10.0
    else:
        Tfraction = (T_ambient - 15.0) / 10.0
    etaull = c['C21'] * T**2 + c['C11'] * T + c['C01']
    etauul = c['D21'] * T**2 + c['D11'] * T + c['D01']
    etau = (1.0 - Tfraction) * etaull + Tfraction * etauul

    reinjtll = c['C22'] * T**2 + c['C12'] * T + c['C02']
    reinjtul = c['D22'] * T**2 + c['D12'] * T + c['D02']
    reinjection_temperature = (1.0 - Tfraction) * reinjtll + Tfraction * reinjtul

    return availability, etau, reinjection_temperature

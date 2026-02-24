from __future__ import annotations

from geophires_x.Parameter import OutputParameter
from geophires_x.Units import Units, PercentUnit, TimeUnit, CurrencyUnit, CurrencyFrequencyUnit

CONSTRUCTION_CAPEX_SCHEDULE_PARAMETER_NAME = 'Construction CAPEX Schedule'

_YEAR_INDEX_VALUE_EXPLANATION_SNIPPET = (
    f'The value is specified as a project year index corresponding to the ' f'Year row in the cash flow profile'
)


def BuildPricingModel(
    plantlifetime: int,
    StartPrice: float,
    EndPrice: float,
    EscalationStartYear: int,
    EscalationRate: float,
    PTCAddition: list,
) -> list:
    """
    BuildPricingModel builds the price model array for the project lifetime.  It is used to calculate the revenue
    stream for the project.
    :param plantlifetime: The lifetime of the project in years
    :type plantlifetime: int
    :param StartPrice: The price in the first year of the project in $/kWh
    :type StartPrice: float
    :param EndPrice: The price in the last year of the project in $/kWh
    :type EndPrice: float
    :param EscalationStartYear: The year the price escalation starts in years (not including construction years) in years
    :type EscalationStartYear: int
    :param EscalationRate: The rate of price escalation in $/kWh/year
    :type EscalationRate: float
    :param PTCAddition: The PTC addition array for the project in $/kWh
    :type PTCAddition: list
    :return: Price: The price model array for the project in $/kWh
    :rtype: list
    """
    Price = [0.0] * plantlifetime
    for i in range(0, plantlifetime, 1):
        Price[i] = StartPrice
        if i >= EscalationStartYear:
            # TODO: This is arguably an unwanted/incorrect interpretation of escalation start year, see
            # https://github.com/NREL/GEOPHIRES-X/issues/340?title=Price+Escalation+Start+Year+seemingly+off+by+1
            Price[i] = Price[i] + ((i - EscalationStartYear) * EscalationRate)
        if Price[i] > EndPrice:
            Price[i] = EndPrice
        Price[i] = Price[i] + PTCAddition[i]
    return Price


_SAM_EM_MOIC_RETURNS_TAX_QUALIFIER = 'after-tax'


def moic_parameter() -> OutputParameter:
    return OutputParameter(
        "Project MOIC",
        ToolTipText='Project Multiple of Invested Capital. For SAM Economic Models, this is calculated as the '
        f'sum of Total {_SAM_EM_MOIC_RETURNS_TAX_QUALIFIER} returns (total value received) '
        'divided by Issuance of equity (total capital invested).',
        UnitType=Units.PERCENT,
        PreferredUnits=PercentUnit.TENTH,
        CurrentUnits=PercentUnit.TENTH,
    )


def project_vir_parameter() -> OutputParameter:
    return OutputParameter(
        "Project Value Investment Ratio",
        display_name='Project VIR=PI=PIR',
        UnitType=Units.PERCENT,
        PreferredUnits=PercentUnit.TENTH,
        CurrentUnits=PercentUnit.TENTH,
        ToolTipText="Value Investment Ratio (VIR). "
        "VIR is frequently referred to interchangeably as Profitability Index (PI) or "
        "Profit Investment Ratio (PIR) in financial literature. "
        "All three terms describe the same fundamental ratio: the present value of future cash flows "
        "divided by the initial investment. "
        "For SAM Economic Models, this metric is calculated as the Levered Equity Profitability Index. "
        "It is calculated as the Present Value of After-Tax Equity Cash Flows (Returns) divided by the "
        "Present Value of Equity Invested. It measures the efficiency of the sponsor's specific capital "
        "contribution, accounting for leverage.",
    )


def project_payback_period_parameter() -> OutputParameter:
    return OutputParameter(
        "Project Payback Period",
        UnitType=Units.TIME,
        PreferredUnits=TimeUnit.YEAR,
        CurrentUnits=TimeUnit.YEAR,
        ToolTipText='The time at which cumulative cash flow reaches zero. '
        'For projects that never pay back, the calculated value will be "N/A". '
        'For SAM Economic Models, this is Simple Payback Period (SPB): the time at which cumulative non-discounted '
        'cash flow reaches zero, calculated using non-discounted after-tax net cash flow. '
        'See https://samrepo.nrelcloud.org/help/mtf_payback.html for important considerations regarding the '
        'limitations of this metric.',
    )


def after_tax_irr_parameter() -> OutputParameter:
    return OutputParameter(
        Name='After-tax IRR',
        UnitType=Units.PERCENT,
        CurrentUnits=PercentUnit.PERCENT,
        PreferredUnits=PercentUnit.PERCENT,
        ToolTipText='The After-tax IRR (internal rate of return) is the nominal discount rate that corresponds to '
        'a net present value (NPV) of zero for PPA SAM Economic models. '
        # TODO describe backfilled calculation using After-tax net cash flow
        'See https://samrepo.nrelcloud.org/help/mtf_irr.html.',
    )


def real_discount_rate_parameter() -> OutputParameter:
    return OutputParameter(
        Name="Real Discount Rate",
        UnitType=Units.PERCENT,
        CurrentUnits=PercentUnit.PERCENT,
        PreferredUnits=PercentUnit.PERCENT,
    )


def nominal_discount_rate_parameter() -> OutputParameter:
    return OutputParameter(
        Name="Nominal Discount Rate",
        ToolTipText="Nominal Discount Rate is displayed for SAM Economic Models. "
        "It is calculated "
        "per https://samrepo.nrelcloud.org/help/fin_single_owner.html?q=nominal+discount+rate: "
        "Nominal Discount Rate = [ ( 1 + Real Discount Rate ÷ 100 ) "
        "× ( 1 + Inflation Rate ÷ 100 ) - 1 ] × 100.",
        UnitType=Units.PERCENT,
        CurrentUnits=PercentUnit.PERCENT,
        PreferredUnits=PercentUnit.PERCENT,
    )


def wacc_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='WACC',
        ToolTipText='Weighted Average Cost of Capital displayed for SAM Economic Models. '
        'It is calculated per https://samrepo.nrelcloud.org/help/fin_commercial.html?q=wacc: '
        'WACC = [ Nominal Discount Rate ÷ 100 × (1 - Debt Percent ÷ 100) '
        '+ Debt Percent ÷ 100 × Loan Rate ÷ 100 ×  (1 - Effective Tax Rate ÷ 100 ) ] × 100; '
        'Effective Tax Rate = [ Federal Tax Rate ÷ 100 × ( 1 - State Tax Rate ÷ 100 ) '
        '+ State Tax Rate ÷ 100 ] × 100; ',
        UnitType=Units.PERCENT,
        CurrentUnits=PercentUnit.PERCENT,
        PreferredUnits=PercentUnit.PERCENT,
    )


def overnight_capital_cost_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='Overnight Capital Cost',
        UnitType=Units.CURRENCY,
        PreferredUnits=CurrencyUnit.MDOLLARS,
        CurrentUnits=CurrencyUnit.MDOLLARS,
        ToolTipText='Overnight Capital Cost (OCC) represents the total capital cost required '
        'to construct the plant if it were built instantly ("overnight"). '
        'This value excludes time-dependent costs such as inflation and '
        'interest incurred during the construction period.',
    )


def inflation_cost_during_construction_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='Inflation costs during construction',
        UnitType=Units.CURRENCY,
        PreferredUnits=CurrencyUnit.MDOLLARS,
        CurrentUnits=CurrencyUnit.MDOLLARS,
        ToolTipText='The calculated amount of cost escalation due to inflation over the construction period.',
    )


def interest_during_construction_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='Interest during construction',
        UnitType=Units.CURRENCY,
        PreferredUnits=CurrencyUnit.MDOLLARS,
        CurrentUnits=CurrencyUnit.MDOLLARS,
        ToolTipText='Interest During Construction (IDC) is the total accumulated interest '
        'incurred on debt during the construction phase. This cost is capitalized '
        '(added to the loan principal and total installed cost) rather than paid in cash.',
    )


def total_capex_parameter_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='Total CAPEX',
        UnitType=Units.CURRENCY,
        CurrentUnits=CurrencyUnit.MDOLLARS,
        PreferredUnits=CurrencyUnit.MDOLLARS,
        ToolTipText='The total capital expenditure (CAPEX) required to construct the plant. '
        'This value includes all direct and indirect costs, and contingency. '
        'For SAM Economic models, it also includes any cost escalation from inflation during construction. '
        'It is used as the total installed cost input for SAM Economic Models.',
    )


def royalty_cost_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name='Royalty Cost',
        UnitType=Units.CURRENCYFREQUENCY,
        PreferredUnits=CurrencyFrequencyUnit.DOLLARSPERYEAR,
        CurrentUnits=CurrencyFrequencyUnit.DOLLARSPERYEAR,
        ToolTipText='The annual costs paid to a royalty holder, calculated as a percentage of the '
        'project\'s gross annual revenue. This is modeled as a variable operating expense.',
    )


def investment_tax_credit_output_parameter() -> OutputParameter:
    return OutputParameter(
        Name="Investment Tax Credit Value",
        display_name='Investment Tax Credit',
        UnitType=Units.CURRENCY,
        PreferredUnits=CurrencyUnit.MDOLLARS,
        CurrentUnits=CurrencyUnit.MDOLLARS,
        ToolTipText='Represents the total undiscounted ITC sum. '
        'For SAM Economic Models, this accounts for the standard Year 1 Federal ITC as well as any '
        'applicable State ITCs or multi-year credit schedules.',
    )


def expand_schedule(schedule_strings: list[str | float], total_years: int) -> list[float]:
    """
    Parse a duration-based scheduling DSL and expand it into a fixed-length time-series array.

    Syntax: ``[Value] * [Years], [Value] * [Years], ..., [Terminal Value]``

    The terminal (last) value is repeated to fill ``total_years``.  A bare scalar
    (e.g. ``['2.5']``) is treated as a terminal value and broadcast across all years.

    Examples::

        expand_schedule(['1.0 * 3', '0.1'], total_years=6)
        # => [1.0, 1.0, 1.0, 0.1, 0.1, 0.1]

        expand_schedule(['2.5'], total_years=4)
        # => [2.5, 2.5, 2.5, 2.5]

    :param schedule_strings: list of DSL segment strings.  Each element is either
        ``"<value> * <years>"`` (a run-length segment) or ``"<value>"`` (a scalar,
        which becomes the terminal value when it is the last element, or a 1-year
        segment otherwise).
    :param total_years: The total number of years the expanded array must span
        (typically ``construction_years + plant_lifetime``).
    :returns: A ``list[float]`` of length ``total_years``.
    :raises ValueError: On malformed DSL strings or when explicit segments exceed
        ``total_years``.
    """
    if total_years <= 0:
        return []

    if not schedule_strings:
        return [0.0] * total_years

    segments: list[tuple[float, int | None]] = []
    for raw in schedule_strings:
        raw = str(raw).strip()
        if '*' in raw:
            parts = raw.split('*')
            if len(parts) != 2:
                raise ValueError(f'Invalid schedule segment "{raw}": expected "<value> * <years>".')
            value = float(parts[0].strip())
            years = int(parts[1].strip())
            if years < 0:
                raise ValueError(f'Invalid schedule segment "{raw}": year count must be non-negative.')
            segments.append((value, years))
        else:
            value = float(raw)
            segments.append((value, None))

    result: list[float] = []
    terminal_value = 0.0

    for idx, (value, years) in enumerate(segments):
        is_last = idx == len(segments) - 1
        if years is not None:
            result.extend([value] * years)
            terminal_value = value
        else:
            if is_last:
                terminal_value = value
            else:
                result.append(value)
                terminal_value = value

    if len(result) > total_years:
        raise ValueError(f'Schedule expands to {len(result)} years which exceeds total_years={total_years}.')

    remaining = total_years - len(result)
    if remaining > 0:
        result.extend([terminal_value] * remaining)

    return result

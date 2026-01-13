from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

from geophires_docs import _FPC5_INPUT_FILE_PATH
from geophires_docs import _FPC5_RESULT_FILE_PATH
from geophires_docs import _PROJECT_ROOT
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXResult
from geophires_x_client import ImmutableGeophiresInputParameters


def generate_net_power_graph(
    result: GeophiresXResult, output_dir: Path, filename='fervo_project_cape-5-net-power-production.png'
) -> str:
    """
    Generate a graph of time vs net power production and save it to the output directory.

    Args:
        result: The GEOPHIRES result object
        output_dir: Directory to save the graph image

    Returns:
        The filename of the generated graph
    """
    print('Generating net power production graph...')

    # Extract data from power generation profile
    profile = result.power_generation_profile
    headers = profile[0]
    data = profile[1:]

    # Find the indices for YEAR and NET POWER columns
    year_idx = headers.index('YEAR')
    net_power_idx = headers.index('NET POWER (MW)')

    # Extract years and net power values
    years = np.array([row[year_idx] for row in data])
    net_power = np.array([row[net_power_idx] for row in data])

    # Create the figure
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot the data
    ax.plot(years, net_power, color='#3399e6', linewidth=2, marker='o', markersize=4)

    # Set labels and title
    ax.set_xlabel('Time (Years)', fontsize=12)
    ax.set_ylabel('Net Power Production (MW)', fontsize=12)
    ax.set_title('Net Power Production Over Project Lifetime', fontsize=14)

    # Set axis limits
    ax.set_xlim(years.min(), years.max())

    # Add grid for better readability
    ax.grid(True, linestyle='--', alpha=0.7)

    # Ensure the output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the figure
    save_path = output_dir / filename
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f'✓ Generated {save_path}')
    return filename


def generate_production_temperature_graph(
    result: GeophiresXResult, output_dir: Path, filename='fervo_project_cape-5-production-temperature.png'
) -> str:
    """
    Generate a graph of time vs production temperature and save it to the output directory.

    Args:
        result: The GEOPHIRES result object
        output_dir: Directory to save the graph image

    Returns:
        The filename of the generated graph
    """
    print('Generating production temperature graph...')

    # Extract data from power generation profile
    profile = result.power_generation_profile
    headers = profile[0]
    data = profile[1:]

    # Find the indices for YEAR and THERMAL DRAWDOWN columns
    year_idx = headers.index('YEAR')
    # Look for production temperature column - could be labeled differently
    temp_idx = headers.index('GEOFLUID TEMPERATURE (degC)')

    # Extract years and temperature values
    years = np.array([row[year_idx] for row in data])
    temperatures_celsius = np.array([row[temp_idx] for row in data])

    # Convert Celsius to Fahrenheit
    temperatures_fahrenheit = temperatures_celsius * 9 / 5 + 32

    # Create the figure - taller than wide (portrait orientation)
    fig, ax = plt.subplots(figsize=(6, 8))

    # Plot the data - just the curve, no markers
    ax.plot(years, temperatures_fahrenheit, color='#e63333', linewidth=2)

    # Set labels and title
    ax.set_xlabel('Simulation time (Years)', fontsize=12)
    ax.set_ylabel('Wellhead temperature (°F)', fontsize=12)
    # ax.set_title('Production Temperature Over Project Lifetime', fontsize=14)

    # Set axis limits
    ax.set_xlim(years.min(), years.max())
    ax.set_ylim(200, 450)

    # Set y-axis ticks every 50 degrees, with 400 explicitly labeled but not 200 or 450
    ax.set_yticks([250, 300, 350, 400])

    # Add grid for better readability
    ax.grid(True, linestyle='--', alpha=0.7)

    # Ensure the output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the figure
    save_path = output_dir / filename
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f'✓ Generated {save_path}')
    return filename


def generate_fervo_project_cape_5_graphs(
    base_case: tuple[GeophiresInputParameters, GeophiresXResult],
    singh_et_al_base_simulation: tuple[GeophiresInputParameters, GeophiresXResult],
    output_dir: Path,
) -> None:
    # base_case_input_params: GeophiresInputParameters = base_case[0]
    # result:GeophiresXResult = base_case[1]

    # generate_net_power_graph(result, output_dir)
    # generate_production_temperature_graph(result, output_dir)

    singh_et_al_base_simulation_result: GeophiresXResult = singh_et_al_base_simulation[1]

    # generate_net_power_graph(
    #     singh_et_al_base_simulation_result, output_dir, filename='singh_et_al_base_simulation-net-power-production.png'
    # )
    generate_production_temperature_graph(
        singh_et_al_base_simulation_result,
        output_dir,
        filename='singh_et_al_base_simulation-production-temperature.png',
    )


if __name__ == '__main__':
    docs_dir = _PROJECT_ROOT / 'docs'
    images_dir = docs_dir / '_images'

    input_params_: GeophiresInputParameters = ImmutableGeophiresInputParameters(from_file_path=_FPC5_INPUT_FILE_PATH)

    result_ = GeophiresXResult(_FPC5_RESULT_FILE_PATH)

    generate_fervo_project_cape_5_graphs(input_params_, result_, images_dir)

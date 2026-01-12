from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

from geophires_x_client import GeophiresXResult


def generate_net_power_graph(result: GeophiresXResult, output_dir: Path) -> str:
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
    filename = 'fervo_project_cape-4-net-power-production.png'
    save_path = output_dir / filename
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f'✓ Generated {save_path}')
    return filename


def generate_production_temperature_graph(result: GeophiresXResult, output_dir: Path) -> str:
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
    temperatures = np.array([row[temp_idx] for row in data])

    # Create the figure
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot the data
    ax.plot(years, temperatures, color='#e63333', linewidth=2, marker='o', markersize=4)

    # Set labels and title
    ax.set_xlabel('Time (Years)', fontsize=12)
    ax.set_ylabel('Production Temperature (°C)', fontsize=12)
    ax.set_title('Production Temperature Over Project Lifetime', fontsize=14)

    # Set axis limits
    ax.set_xlim(years.min(), years.max())
    ax.set_ylim(100, 230)

    # Add grid for better readability
    ax.grid(True, linestyle='--', alpha=0.7)

    # Ensure the output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the figure
    filename = 'fervo_project_cape-4-production-temperature.png'
    save_path = output_dir / filename
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    print(f'✓ Generated {save_path}')
    return filename


def generate_fervo_project_cape_4_graphs(result: GeophiresXResult, output_dir: Path) -> None:
    generate_net_power_graph(result, output_dir)
    generate_production_temperature_graph(result, output_dir)


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / 'docs'
    images_dir = docs_dir / '_images'

    result = GeophiresXResult(project_root / 'tests/examples/Fervo_Project_Cape-4.out')

    generate_fervo_project_cape_4_graphs(result, images_dir)

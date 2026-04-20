from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.ndimage import maximum_filter

from geophires_docs import _PROJECT_ROOT
from geophires_docs import _get_full_production_temperature_profile
from geophires_docs import _get_input_parameters_dict
from geophires_docs import _get_logger
from geophires_x_client import GeophiresInputParameters
from geophires_x_client import GeophiresXResult
from geophires_x_client import ImmutableGeophiresInputParameters

_log = _get_logger(__name__)

_BUILD_DIR: Path = _PROJECT_ROOT / 'build' / 'generate_fervo_project_red_2026_docs'

_PRODUCTION_CSV_FILENAME = 'project_red_2026_production_data.csv'
_MODEL_CSV_FILENAME = 'project_red_2026_model_data.csv'
_STEADY_STATE_CSV_FILENAME = 'project_red_2026_variance_analysis.csv'
_REGENERATED_GRAPH_FILENAME = 'project_red_2026_figure-5_regenerated.png'

_STEADY_STATE_START_YEARS = 0.041625

_HOUGH_MIN_DIST_PX = 4

_MODEL_OUTLIER_STD_THRESHOLD = 2.5
_MODEL_ROLLING_WINDOW = 15

_CONTINUOUS_OPERATION_MIN_TEMP_C = 175.0
_STATISTICAL_BUFFER_SIZE = 5
_STATISTICAL_MIN_BUFFER = 3
_STATISTICAL_Z_SCORE = 2.0
_STATISTICAL_MIN_STD = 1.5


def extract_plot_data(
    image_path: Path | str, production_image_path: Path | str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f'Could not load image at {image_path}')

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    height, width, _ = img.shape
    x_min_px, x_max_px = int(width * 0.10), int(width * 0.96)
    y_min_px, y_max_px = int(height * 0.06), int(height * 0.80)

    x_min_val, x_max_val = 0.0, 2.0
    y_min_val, y_max_val = 0.0, 200.0

    def pixel_to_data(px: float, py: float) -> tuple[float, float]:
        x = x_min_val + (px - x_min_px) / (x_max_px - x_min_px) * (x_max_val - x_min_val)
        y = y_min_val + (y_max_px - py) / (y_max_px - y_min_px) * (y_max_val - y_min_val)
        return x, y

    plot_mask = np.zeros((height, width), dtype=np.uint8)
    plot_mask[y_min_px:y_max_px, x_min_px:x_max_px] = 255

    prod_target_path = production_image_path if production_image_path else image_path
    df_prod = _extract_red_circles(prod_target_path, plot_mask, pixel_to_data)
    df_model = _extract_black_dashed_line(hsv, plot_mask, pixel_to_data)

    return df_prod, df_model


def _calculate_variance_analysis(
    df_actual: pd.DataFrame, df_model: pd.DataFrame, steady_state_start_years: float = _STEADY_STATE_START_YEARS
) -> pd.DataFrame:
    post_ramp_mask = df_actual['Time_Years'] > steady_state_start_years
    n_before = len(df_actual[post_ramp_mask])

    is_steady = _get_steady_state_mask(df_actual, steady_state_start_years)
    df_steady_state = df_actual[is_steady].copy()

    _log.info(f'Continuous operation filter: dropped {n_before - len(df_steady_state)} transient/dip points.')

    model_interpolator = interp1d(
        df_model['Time_Years'],
        df_model['Temperature_C'],
        kind='linear',
        fill_value='extrapolate',
    )

    df_steady_state['Model_Temperature_C'] = model_interpolator(df_steady_state['Time_Years'])
    df_steady_state['Error_C'] = df_steady_state['Temperature_C'] - df_steady_state['Model_Temperature_C']

    return df_steady_state.reset_index(drop=True)


def _extract_red_circles(
    img_path: Path | str,
    plot_mask: np.ndarray,
    pixel_to_data,
) -> pd.DataFrame:
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f'Could not load image at {img_path}')

    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        _, mask_alpha = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
        hsv = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2HSV)
    else:
        mask_alpha = np.ones(img.shape[:2], dtype=np.uint8) * 255
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 20, 20])
    upper_red1 = np.array([20, 255, 255])
    lower_red2 = np.array([160, 20, 20])
    upper_red2 = np.array([180, 255, 255])

    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)
    mask_red = cv2.bitwise_and(mask_red, mask_alpha)
    mask_red = cv2.bitwise_and(mask_red, plot_mask)

    dist_transform = cv2.distanceTransform(mask_red, cv2.DIST_L2, 5)

    local_max = maximum_filter(dist_transform, size=3) == dist_transform
    peak_mask = local_max & (dist_transform > 1.0)

    y_coords, x_coords = np.where(peak_mask)
    centers_px = [(int(x), int(y)) for x, y in zip(x_coords, y_coords)]

    if not centers_px:
        _log.warning('No valid pixels found in the production data mask.')
        return pd.DataFrame(columns=['Time_Years', 'Temperature_C'])

    deduped_centers_px = _dedupe_centers(centers_px, min_dist_px=_HOUGH_MIN_DIST_PX)

    _log.info(f'Red-marker detection: Extracted {len(deduped_centers_px)} topological ridge points from edited mask.')

    production_data = [pixel_to_data(cx, cy) for cx, cy in deduped_centers_px]
    df_prod = pd.DataFrame(production_data, columns=['Time_Years', 'Temperature_C'])
    return df_prod.sort_values('Time_Years').reset_index(drop=True)


def _extract_black_dashed_line(hsv: np.ndarray, plot_mask: np.ndarray, pixel_to_data) -> pd.DataFrame:
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([180, 255, 50])
    mask_black = cv2.inRange(hsv, lower_black, upper_black)
    mask_black = cv2.bitwise_and(mask_black, plot_mask)

    y_coords, x_coords = np.where(mask_black > 0)
    model_data = [pixel_to_data(px, py) for px, py in zip(x_coords, y_coords)]

    df_model_raw = pd.DataFrame(model_data, columns=['Time_Years', 'Temperature_C'])
    if df_model_raw.empty:
        return df_model_raw

    df_model_raw['Time_Years_Rounded'] = df_model_raw['Time_Years'].round(3)
    df_model = (
        df_model_raw.groupby('Time_Years_Rounded', as_index=False)['Temperature_C']
        .mean()
        .rename(columns={'Time_Years_Rounded': 'Time_Years'})
        .sort_values('Time_Years')
        .reset_index(drop=True)
    )

    rolling_median = (
        df_model['Temperature_C'].rolling(window=_MODEL_ROLLING_WINDOW, center=True, min_periods=3).median()
    )
    rolling_std = df_model['Temperature_C'].rolling(window=_MODEL_ROLLING_WINDOW, center=True, min_periods=3).std()
    rolling_std = rolling_std.fillna(rolling_std.median()).replace(0, rolling_std.median())

    deviations = (df_model['Temperature_C'] - rolling_median).abs()
    inlier_mask = deviations <= _MODEL_OUTLIER_STD_THRESHOLD * rolling_std
    inlier_mask = inlier_mask.fillna(True)

    n_before = len(df_model)
    df_model = df_model[inlier_mask].reset_index(drop=True)
    _log.info(f'Model-curve outlier rejection: {n_before - len(df_model)} of {n_before} points dropped')

    return df_model


def _dedupe_centers(centers_px: list[tuple[int, int]], min_dist_px: float) -> list[tuple[int, int]]:
    if not centers_px:
        return []

    accepted: list[tuple[int, int]] = []
    min_dist_sq = min_dist_px * min_dist_px
    for cx, cy in centers_px:
        duplicate = False
        for ax, ay in accepted:
            if (cx - ax) * (cx - ax) + (cy - ay) * (cy - ay) < min_dist_sq:
                duplicate = True
                break
        if not duplicate:
            accepted.append((cx, cy))
    return accepted


def _get_steady_state_mask(df_prod: pd.DataFrame, steady_state_start_years: float) -> pd.Series:
    """
    Identifies steady-state production points iteratively. Maintains a rolling
    buffer of verified plateau points to mathematically isolate and reject
    the steep walls and floors of transient shut-ins.
    """
    is_steady = pd.Series(False, index=df_prod.index)
    post_ramp_idx = df_prod.index[df_prod['Time_Years'] > steady_state_start_years]

    valid_buffer: list[float] = []

    for idx in post_ramp_idx:
        temp = df_prod.at[idx, 'Temperature_C']

        if temp < _CONTINUOUS_OPERATION_MIN_TEMP_C:
            continue

        if len(valid_buffer) >= _STATISTICAL_MIN_BUFFER:
            history = valid_buffer[-_STATISTICAL_BUFFER_SIZE:]
            mean_temp = float(np.mean(history))
            std_temp = float(np.std(history, ddof=1))

            std_temp = max(std_temp, _STATISTICAL_MIN_STD)

            if abs(temp - mean_temp) > _STATISTICAL_Z_SCORE * std_temp:
                continue

        is_steady.at[idx] = True
        valid_buffer.append(temp)

    return is_steady


def _generate_production_temperature_comparison_graph(
    production_csv_path: Path,
    model_csv_path: Path,
    steady_state_csv_path: Path,
    output_path: Path,
    steady_state_start_years: float = _STEADY_STATE_START_YEARS,
    geophires_data: pd.Series | None = None,
) -> None:
    df_prod = pd.read_csv(production_csv_path)
    df_model = pd.read_csv(model_csv_path)

    is_thermal_conditioning = df_prod['Time_Years'] <= steady_state_start_years  # noqa: F841
    is_steady_state = _get_steady_state_mask(df_prod, steady_state_start_years)

    df_included = df_prod[
        # is_thermal_conditioning |
        is_steady_state
    ]
    df_excluded = df_prod[
        ~(
            # is_thermal_conditioning |
            is_steady_state
        )
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.scatter(
        df_included['Time_Years'],
        df_included['Temperature_C'],
        facecolors='none',
        edgecolors='#d62728',
        s=22,
        linewidths=1.0,
        alpha=0.85,
        label='Measured '
        # f'Flowing '
        'Temperature (Steady State)',
        # f', n={len(df_included)}',
    )

    if not df_excluded.empty:
        ax.scatter(
            df_excluded['Time_Years'],
            df_excluded['Temperature_C'],
            facecolors='none',
            edgecolors='gray',
            s=22,
            linewidths=1.0,
            alpha=0.5,
            label='Measured '
            # f'Flowing '
            'Temperature (Thermal Conditioning '
            '& Excluded Operational Periods'  # TODO better wording/phrasing
            ')',
            # f', n={len(df_excluded)}',
        )

    ax.plot(
        df_model['Time_Years'],
        df_model['Temperature_C'],
        color='black',
        linestyle='--',
        linewidth=1.5,
        label='Fervo-Modeled Temperature' if geophires_data is not None else 'Modeled output',
    )

    if geophires_data is not None:
        ax.plot(
            geophires_data.index,
            geophires_data.values,
            color='#1f77b4',
            linestyle='-.',
            linewidth=1.5,
            label='GEOPHIRES-Modeled Temperature (Gringarten)',
        )

    ax.set_xlabel('Time (Years)', fontsize=12)
    ax.set_ylabel('Flowing Temperature (°C)', fontsize=12)

    title = 'Fervo Project Red: Measured vs. Modeled Flowing Temperature (Regenerated)'
    if geophires_data is not None:
        title = 'Project Red Temperature: Measured vs. Fervo-Modeled vs. GEOPHIRES-Modeled'
    ax.set_title(title, fontsize=13)

    ax.set_xlim(0.0, 2.0)
    ax.set_ylim(0.0, 200.0)
    ax.grid(True, linestyle='--', alpha=0.5)

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=1, frameon=False, fontsize=11)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def _get_file_path(file_name: str) -> Path:
    return Path(__file__).parent / file_name


def get_project_red_production_temperature_profile_series(fervo_graph_df_model: pd.Series) -> pd.Series:
    input_params: GeophiresInputParameters = ImmutableGeophiresInputParameters(
        from_file_path=_get_file_path('../../tests/examples/Fervo_Project_Red-2026.txt')
    )
    input_and_result = (
        input_params,
        GeophiresXResult(_get_file_path('../../tests/examples/Fervo_Project_Red-2026.out')),
    )

    project_red_geophires_result_data: list = _get_full_production_temperature_profile(input_and_result)

    # Fetch the 'Time' profile data to align exactly with the GEOPHIRES temperature curve
    time_steps_per_year: int = int(_get_input_parameters_dict(input_params)['Time steps per year'])
    geophires_time_data = [
        float(step) / float(time_steps_per_year) for step, _ in enumerate(project_red_geophires_result_data)
    ]

    geophires_x = geophires_time_data
    geophires_y = [q.magnitude for q in project_red_geophires_result_data]

    # Interpolate the GEOPHIRES curve along the exact timestamps established by the model dashed line extraction
    geophires_interpolator = interp1d(geophires_x, geophires_y, kind='linear', fill_value='extrapolate')
    geophires_interpolated_y = geophires_interpolator(fervo_graph_df_model['Time_Years'])

    geophires_series = pd.Series(data=geophires_interpolated_y, index=fervo_graph_df_model['Time_Years'])

    return geophires_series


if __name__ == '__main__':
    IMAGE_PATH = _get_file_path('fervo-project-red-2026_figure-5_measured-flowing-temperature.png')
    PRODUCTION_IMAGE_PATH = _get_file_path('fervo_project_red-2026_graph-data-extraction_production-series-edited.png')

    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    production_csv_path_ = _BUILD_DIR / _PRODUCTION_CSV_FILENAME
    model_csv_path_ = _BUILD_DIR / _MODEL_CSV_FILENAME
    steady_state_csv_path = _BUILD_DIR / _STEADY_STATE_CSV_FILENAME
    regenerated_graph_path = _BUILD_DIR / _REGENERATED_GRAPH_FILENAME

    _log.info('Extracting data from image...')
    df_actual, df_model_ = extract_plot_data(IMAGE_PATH, PRODUCTION_IMAGE_PATH)

    _log.info(f'Extracted {len(df_actual)} production data points.')
    _log.info(f'Extracted {len(df_model_)} model line data points.')

    df_actual.to_csv(production_csv_path_, index=False)
    df_model_.to_csv(model_csv_path_, index=False)
    _log.info(f'Wrote production data CSV: {production_csv_path_}')
    _log.info(f'Wrote model data CSV:      {model_csv_path_}')

    if not df_actual.empty and not df_model_.empty:
        df_steady_state = _calculate_variance_analysis(df_actual, df_model_)

        rmse = float(np.sqrt((df_steady_state['Error_C'] ** 2).mean()))
        mae = float(df_steady_state['Error_C'].abs().mean())
        max_error = float(df_steady_state['Error_C'].abs().max())

        _log.info(f'--- STATISTICAL ALIGNMENT (Steady-State > {_STEADY_STATE_START_YEARS} Years) ---')
        _log.info(f'Root Mean Square Error (RMSE): {rmse:.2f} °C')
        _log.info(f'Mean Absolute Error (MAE):     {mae:.2f} °C')
        _log.info(f'Max Absolute Error:            {max_error:.2f} °C')

        df_steady_state.to_csv(steady_state_csv_path, index=False)
        _log.info(f'Wrote variance analysis CSV:  {steady_state_csv_path}')

    _generate_production_temperature_comparison_graph(
        production_csv_path_,
        model_csv_path_,
        steady_state_csv_path,
        regenerated_graph_path,
        geophires_data=get_project_red_production_temperature_profile_series(df_model_),
    )
    _log.info(f'Wrote regenerated graph:      {regenerated_graph_path}')

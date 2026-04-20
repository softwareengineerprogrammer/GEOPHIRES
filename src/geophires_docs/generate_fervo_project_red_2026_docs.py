from logging import getLogger
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from geophires_docs import _PROJECT_ROOT

_log = getLogger(__name__)

_BUILD_DIR: Path = _PROJECT_ROOT / 'build' / 'generate_fervo_project_red_2026_docs'

_PRODUCTION_CSV_FILENAME = 'project_red_2026_production_data.csv'
_MODEL_CSV_FILENAME = 'project_red_2026_model_data.csv'
_STEADY_STATE_CSV_FILENAME = 'project_red_2026_variance_analysis.csv'
_REGENERATED_GRAPH_FILENAME = 'project_red_2026_figure-5_regenerated.png'

_STEADY_STATE_START_YEARS = 0.25

_HOUGH_MIN_DIST_PX = 4

_MODEL_OUTLIER_STD_THRESHOLD = 2.5
_MODEL_ROLLING_WINDOW = 15


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
    df_steady_state = df_actual[df_actual['Time_Years'] > steady_state_start_years].copy()

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
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f'Could not load image at {img_path}')

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 50, 50])
    upper_red1 = np.array([15, 255, 255])
    lower_red2 = np.array([165, 50, 50])
    upper_red2 = np.array([180, 255, 255])

    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)
    mask_red = cv2.bitwise_and(mask_red, plot_mask)

    y_coords, x_coords = np.where(mask_red > 0)

    if len(x_coords) == 0:
        _log.warning('No red pixels found in the production data mask.')
        return pd.DataFrame(columns=['Time_Years', 'Temperature_C'])

    df_pixels = pd.DataFrame({'x': x_coords, 'y': y_coords})

    bin_size = int(_HOUGH_MIN_DIST_PX)
    df_pixels['x_binned'] = (df_pixels['x'] // bin_size) * bin_size + (bin_size // 2)
    centerline = df_pixels.groupby('x_binned', as_index=False)[['x', 'y']].mean()

    _log.info(f'Red-marker detection: Extracted {len(centerline)} binned centerline points from edited mask.')

    production_data = [pixel_to_data(row['x'], row['y']) for _, row in centerline.iterrows()]
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


def _regenerate_graph_from_csv(
    production_csv_path: Path,
    model_csv_path: Path,
    output_path: Path,
) -> None:
    df_prod = pd.read_csv(production_csv_path)
    df_model = pd.read_csv(model_csv_path)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.scatter(
        df_prod['Time_Years'],
        df_prod['Temperature_C'],
        facecolors='none',
        edgecolors='#d62728',
        s=22,
        linewidths=1.0,
        alpha=0.85,
        label=f'Measured flowing temperature (Project Red), n={len(df_prod)}',
    )
    ax.plot(
        df_model['Time_Years'],
        df_model['Temperature_C'],
        color='black',
        linestyle='--',
        linewidth=1.5,
        label='Modeled output',
    )

    ax.set_xlabel('Time (Years)', fontsize=12)
    ax.set_ylabel('Flowing Temperature (°C)', fontsize=12)
    ax.set_title('Fervo Project Red: Measured vs. Modeled Flowing Temperature (Regenerated)', fontsize=13)
    ax.set_xlim(0.0, 2.0)
    ax.set_ylim(0.0, 200.0)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend(loc='best')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    IMAGE_PATH = Path(__file__).parent / 'fervo-project-red-2026_figure-5_measured-flowing-temperature.png'
    PRODUCTION_IMAGE_PATH = (
        Path(__file__).parent / 'fervo_project_red-2026_graph-data-extraction_production-series-edited.png'
    )

    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    production_csv_path = _BUILD_DIR / _PRODUCTION_CSV_FILENAME
    model_csv_path = _BUILD_DIR / _MODEL_CSV_FILENAME
    steady_state_csv_path = _BUILD_DIR / _STEADY_STATE_CSV_FILENAME
    regenerated_graph_path = _BUILD_DIR / _REGENERATED_GRAPH_FILENAME

    _log.info('Extracting data from image...')
    df_actual, df_model = extract_plot_data(IMAGE_PATH, PRODUCTION_IMAGE_PATH)

    _log.info(f'Extracted {len(df_actual)} production data points.')
    _log.info(f'Extracted {len(df_model)} model line data points.')

    df_actual.to_csv(production_csv_path, index=False)
    df_model.to_csv(model_csv_path, index=False)
    _log.info(f'Wrote production data CSV: {production_csv_path}')
    _log.info(f'Wrote model data CSV:      {model_csv_path}')

    if not df_actual.empty and not df_model.empty:
        df_steady_state = _calculate_variance_analysis(df_actual, df_model)

        rmse = float(np.sqrt((df_steady_state['Error_C'] ** 2).mean()))
        mae = float(df_steady_state['Error_C'].abs().mean())
        max_error = float(df_steady_state['Error_C'].abs().max())

        _log.info(f'--- STATISTICAL ALIGNMENT (Steady-State > {_STEADY_STATE_START_YEARS} Years) ---')
        _log.info(f'Root Mean Square Error (RMSE): {rmse:.2f} °C')
        _log.info(f'Mean Absolute Error (MAE):     {mae:.2f} °C')
        _log.info(f'Max Absolute Error:            {max_error:.2f} °C')

        df_steady_state.to_csv(steady_state_csv_path, index=False)
        _log.info(f'Wrote variance analysis CSV:  {steady_state_csv_path}')

    _regenerate_graph_from_csv(production_csv_path, model_csv_path, regenerated_graph_path)
    _log.info(f'Wrote regenerated graph:      {regenerated_graph_path}')

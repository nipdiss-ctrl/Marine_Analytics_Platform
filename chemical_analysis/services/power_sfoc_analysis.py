import datetime

import numpy as np
import pandas as pd

from chemical_analysis.models import (
    ChemicalMeasurement,
    ChemicalDosing,
)


# ============================================================
# DATA QUALITY LIMITS
# ============================================================

VALID_MIN_POWER = 500.0

MIN_SFOC = 100.0
MAX_SFOC = 500.0


# ============================================================
# CLAUS PLOTS POWER RANGES
#
# These are the power ranges used in the Claus workbook.
#
# Treated:
#     8500 - 9500 kW
#
# Untreated:
#     8000 - 9500 kW
#
# IMPORTANT:
# These are intentionally different.
# ============================================================

CLAUS_TREATED_MIN_POWER = 8500.0
CLAUS_TREATED_MAX_POWER = 9500.0

CLAUS_UNTREATED_MIN_POWER = 8000.0
CLAUS_UNTREATED_MAX_POWER = 9500.0


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value, default=None):
    """
    Safely convert a value to float.
    """

    try:

        if value is None or pd.isna(value):
            return default

        value = float(value)

        if not np.isfinite(value):
            return default

        return value

    except (
        TypeError,
        ValueError,
    ):

        return default


def _as_date(value):
    """
    Convert supported date/datetime/Timestamp values
    into a plain Python datetime.date.

    Important:
    This function never calls .date() on a value that is
    already datetime.date.
    """

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):

        if pd.isna(value):
            return None

        return value.date()

    if isinstance(value, datetime.datetime):

        return value.date()

    if isinstance(value, datetime.date):

        return value

    try:

        converted = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(converted):
            return None

        return converted.date()

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# LOAD MEASUREMENTS
# ============================================================

def _load_measurements(vessel):
    """
    Load measurement data from ChemicalMeasurement.

    SFOC is calculated exactly as in the Excel workbook:

        Fuel consumption =
            Fuel inlet - Fuel outlet

        SFOC =
            Fuel consumption / Power * 1000

    Result:
        g/kWh
    """

    measurements = list(
        ChemicalMeasurement.objects
        .filter(
            vessel=vessel,
        )
        .values(
            "timestamp",
            "fuel_load",
            "fuel_inlet",
            "fuel_outlet",
            "rpm",
            "speed",
            "power",
            "voyage",
        )
        .order_by(
            "timestamp",
        )
    )

    if not measurements:

        return pd.DataFrame()

    df = pd.DataFrame(
        measurements,
    )

    # ========================================================
    # TIMESTAMP
    #
    # IMPORTANT:
    # Keep the same timestamp interpretation as the working
    # measurement importer.
    # ========================================================

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True,
    )

    # ========================================================
    # NUMERIC COLUMNS
    # ========================================================

    numeric_columns = [
        "fuel_load",
        "fuel_inlet",
        "fuel_outlet",
        "rpm",
        "speed",
        "power",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # ========================================================
    # BASIC CLEANING
    # ========================================================

    df = (
        df
        .dropna(
            subset=[
                "timestamp",
            ],
        )
        .sort_values(
            "timestamp",
        )
        .reset_index(
            drop=True,
        )
    )

    # ========================================================
    # FUEL CONSUMPTION
    #
    # EXACT EXCEL CALCULATION
    #
    #     Fuel consumption =
    #         inlet - outlet
    # ========================================================

    df["fuel_consumption"] = (
        df["fuel_inlet"]
        -
        df["fuel_outlet"]
    )

    # Fuel consumption must be positive.

    df.loc[
        df["fuel_consumption"] <= 0,
        "fuel_consumption",
    ] = np.nan

    # ========================================================
    # SFOC
    #
    # EXACT EXCEL CALCULATION
    #
    #     SFOC =
    #         (inlet - outlet)
    #         / power
    #         * 1000
    #
    # Result:
    #     g/kWh
    # ========================================================

    df["sfoc"] = np.nan

    valid = (
        df["power"].notna()
        &
        df["fuel_consumption"].notna()
        &
        (df["power"] >= VALID_MIN_POWER)
        &
        (df["fuel_consumption"] > 0)
    )

    df.loc[
        valid,
        "sfoc",
    ] = (
        df.loc[
            valid,
            "fuel_consumption",
        ]
        /
        df.loc[
            valid,
            "power",
        ]
        *
        1000.0
    )

    # ========================================================
    # SFOC QUALITY FILTER
    # ========================================================

    df.loc[
        (
            (df["sfoc"] < MIN_SFOC)
            |
            (df["sfoc"] > MAX_SFOC)
        ),
        "sfoc",
    ] = np.nan

    df["sfoc_valid"] = (
        df["sfoc"].notna()
    )

    # ========================================================
    # CALENDAR DATE
    #
    # Used to connect measurements to dosing days.
    # ========================================================

    df["date"] = (
        df["timestamp"]
        .dt
        .date
    )

    return df


# ============================================================
# LOAD DOSING
# ============================================================

def _load_dosing(vessel):
    """
    Load dosing records from ChemicalDosing.

    Uses the actual fields in the current model.
    """

    dosing = list(
        ChemicalDosing.objects
        .filter(
            vessel=vessel,
        )
        .values(
            "date",
            "morning_time",
            "morning_additive",
            "evening_time",
            "evening_additive",
            "total_additive",
            "total_fuel_qty",
            "chemical_rob",
            "remarks",
        )
        .order_by(
            "date",
        )
    )

    if not dosing:

        return pd.DataFrame(
            columns=[
                "date",
                "morning_time",
                "morning_additive",
                "evening_time",
                "evening_additive",
                "total_additive",
                "total_fuel_qty",
                "chemical_rob",
                "remarks",
                "additive_for_classification",
            ]
        )

    df = pd.DataFrame(
        dosing,
    )

    # ========================================================
    # DATE
    # ========================================================

    df["date"] = (
        pd.to_datetime(
            df["date"],
            errors="coerce",
        )
        .apply(_as_date)
    )

    # ========================================================
    # NUMERIC DOSING FIELDS
    # ========================================================

    numeric_columns = [
        "morning_additive",
        "evening_additive",
        "total_additive",
        "total_fuel_qty",
        "chemical_rob",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # ========================================================
    # ADDITIVE USED
    #
    # Normally total_additive is already populated.
    #
    # If missing:
    #
    #     morning additive + evening additive
    # ========================================================

    calculated_total = (
        df["morning_additive"].fillna(0.0)
        +
        df["evening_additive"].fillna(0.0)
    )

    df["additive_for_classification"] = (
        df["total_additive"]
        .where(
            df["total_additive"].notna(),
            calculated_total,
        )
    )

    df["additive_for_classification"] = (
        pd.to_numeric(
            df["additive_for_classification"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    # ========================================================
    # REMARKS
    # ========================================================

    df["remarks"] = (
        df["remarks"]
        .fillna("")
        .astype(str)
    )

    return df


# ============================================================
# BUILD DOSING BLOCKS
# ============================================================

def _build_dosing_blocks(dosing_df):
    """
    Find contiguous positive-dosing periods.

    Example:

        15, 16, 17, 18, 19
        03, 04, 05, 06, 07

    becomes:

        (15 -> 19)
        (03 -> 07)

    Dates with zero dosing create a gap.

    This follows the dosing-period structure used for
    the Claus analysis.
    """

    if dosing_df is None or dosing_df.empty:

        return []

    active_dosing = dosing_df[
        pd.to_numeric(
            dosing_df[
                "additive_for_classification"
            ],
            errors="coerce",
        )
        .fillna(0.0)
        > 0
    ].copy()

    if active_dosing.empty:

        return []

    active_dosing["classification_date"] = (
        active_dosing["date"]
        .apply(_as_date)
    )

    active_dosing = active_dosing[
        active_dosing[
            "classification_date"
        ].notna()
    ].copy()

    if active_dosing.empty:

        return []

    # Remove duplicate dates.

    active_dates = sorted(
        set(
            active_dosing[
                "classification_date"
            ].tolist()
        )
    )

    if not active_dates:

        return []

    blocks = []

    block_start = active_dates[0]
    previous_date = active_dates[0]

    for current_date in active_dates[1:]:

        difference = (
            current_date
            -
            previous_date
        ).days

        if difference == 1:

            previous_date = current_date

        else:

            blocks.append(
                (
                    block_start,
                    previous_date,
                )
            )

            block_start = current_date
            previous_date = current_date

    # Final block.

    blocks.append(
        (
            block_start,
            previous_date,
        )
    )

    return blocks


# ============================================================
# CLASSIFY MEASUREMENTS
# ============================================================

def _classify_measurements(
    measurement_df,
    dosing_df,
):
    """
    Classify individual measurements as:

        With Chemical
        Without Chemical

    Claus treatment convention:

    - Positive dosing dates form dosing blocks.
    - The first day of each dosing block is the
      transition/start day.
    - Therefore the first dosing day is NOT included as
      treated.
    - Treatment starts on the following day.
    - Treatment continues through the final consecutive
      positive dosing day.
    - A zero-dosing gap ends the previous treatment block.
    - A new positive dosing block starts a new treatment
      period.

    No dates are hard-coded.
    """

    df = measurement_df.copy()

    df["chemical_status"] = (
        "Without Chemical"
    )

    if dosing_df is None or dosing_df.empty:

        return df

    dosing_blocks = _build_dosing_blocks(
        dosing_df,
    )

    if not dosing_blocks:

        return df

    treatment_periods = []

    # ========================================================
    # CONVERT DOSING BLOCKS TO TREATMENT PERIODS
    # ========================================================

    for block_start, block_end in dosing_blocks:

        # First dosing day is the transition day.

        treatment_start = (
            block_start
            +
            datetime.timedelta(
                days=1,
            )
        )

        treatment_end = block_end

        # A one-day dosing block produces no treated day.

        if treatment_start > treatment_end:

            continue

        treatment_periods.append(
            (
                treatment_start,
                treatment_end,
            )
        )

    if not treatment_periods:

        return df

    # ========================================================
    # NORMALIZE MEASUREMENT DATE
    # ========================================================

    df["date"] = (
        df["date"]
        .apply(_as_date)
    )

    # ========================================================
    # APPLY TREATMENT PERIODS
    # ========================================================

    for start_date, end_date in treatment_periods:

        mask = (
            (df["date"] >= start_date)
            &
            (df["date"] <= end_date)
        )

        df.loc[
            mask,
            "chemical_status",
        ] = "With Chemical"

    return df


# ============================================================
# CLAUS POWER FILTER
# ============================================================

def _claus_filter(
    df,
    min_power,
    max_power,
):
    """
    Select individual observations within the specified
    Claus power range.

    IMPORTANT:

    This does NOT average or match observations.

    Every individual observation remains separate.
    """

    if df is None or df.empty:

        return df.copy()

    return df[
        df["power"].notna()
        &
        df["sfoc"].notna()
        &
        (df["power"] >= min_power)
        &
        (df["power"] <= max_power)
    ].copy()


# ============================================================
# CLAUS COMPARISON
# ============================================================

def _claus_comparison(
    with_chemical,
    without_chemical,
):
    """
    Calculate effectiveness using the same method as the
    Claus workbook.

    IMPORTANT:

    We are NOT changing the measurement values.

    We are using the individual SFOC observations calculated
    from our actual database data.

    TREATED:
        8500 <= Power <= 9500

    UNTREATED:
        8000 <= Power <= 9500

    Then:

        Treated Mean SFOC
            = arithmetic mean of ALL selected treated
              observations

        Untreated Mean SFOC
            = arithmetic mean of ALL selected untreated
              observations

    Improvement:

        (
            Untreated Mean SFOC
            -
            Treated Mean SFOC
        )
        /
        Untreated Mean SFOC
        *
        100

    Positive percentage:
        treated SFOC is lower.

    Negative percentage:
        treated SFOC is higher.

    There is:

        NO power matching
        NO power bands
        NO equal-band weighting
        NO regression used for the headline result
    """

    empty_result = {
        "success": False,

        "chemical_mean": None,

        "nonchemical_mean": None,

        "improvement": None,

        "chemical_count": 0,

        "nonchemical_count": 0,

        "treated_min_power": (
            CLAUS_TREATED_MIN_POWER
        ),

        "treated_max_power": (
            CLAUS_TREATED_MAX_POWER
        ),

        "untreated_min_power": (
            CLAUS_UNTREATED_MIN_POWER
        ),

        "untreated_max_power": (
            CLAUS_UNTREATED_MAX_POWER
        ),

        "treated_data": pd.DataFrame(),

        "untreated_data": pd.DataFrame(),
    }

    if (
        with_chemical is None
        or
        without_chemical is None
    ):

        return empty_result

    # ========================================================
    # SELECT EXACT CLAUS TREATED POPULATION
    # ========================================================

    treated = _claus_filter(
        with_chemical,
        CLAUS_TREATED_MIN_POWER,
        CLAUS_TREATED_MAX_POWER,
    )

    # ========================================================
    # SELECT EXACT CLAUS UNTREATED POPULATION
    # ========================================================

    untreated = _claus_filter(
        without_chemical,
        CLAUS_UNTREATED_MIN_POWER,
        CLAUS_UNTREATED_MAX_POWER,
    )

    # ========================================================
    # IMPORTANT:
    #
    # Do not require the same number of observations.
    #
    # Do not match treated observations to untreated
    # observations.
    #
    # Claus uses the mean of each selected population.
    # ========================================================

    chemical_count = len(treated)
    nonchemical_count = len(untreated)

    if chemical_count == 0 or nonchemical_count == 0:

        return {
            **empty_result,

            "chemical_count": int(
                chemical_count
            ),

            "nonchemical_count": int(
                nonchemical_count
            ),

            "treated_data": treated,

            "untreated_data": untreated,
        }

    # ========================================================
    # CLAUS MEAN
    #
    # THIS IS THE IMPORTANT CALCULATION.
    #
    # Every individual observation contributes equally.
    # ========================================================

    chemical_mean = float(
        treated["sfoc"]
        .mean()
    )

    nonchemical_mean = float(
        untreated["sfoc"]
        .mean()
    )

    # ========================================================
    # CLAUS IMPROVEMENT CALCULATION
    # ========================================================

    improvement = None

    if (
        np.isfinite(chemical_mean)
        and
        np.isfinite(nonchemical_mean)
        and
        nonchemical_mean != 0
    ):

        improvement = (
            (
                nonchemical_mean
                -
                chemical_mean
            )
            /
            nonchemical_mean
            *
            100.0
        )

    return {
        "success": True,

        "chemical_mean": chemical_mean,

        "nonchemical_mean": nonchemical_mean,

        "improvement": improvement,

        "chemical_count": int(
            chemical_count
        ),

        "nonchemical_count": int(
            nonchemical_count
        ),

        "treated_min_power": (
            CLAUS_TREATED_MIN_POWER
        ),

        "treated_max_power": (
            CLAUS_TREATED_MAX_POWER
        ),

        "untreated_min_power": (
            CLAUS_UNTREATED_MIN_POWER
        ),

        "untreated_max_power": (
            CLAUS_UNTREATED_MAX_POWER
        ),

        "treated_data": treated,

        "untreated_data": untreated,
    }


# ============================================================
# SIMPLE RAW MEANS
# ============================================================

def _raw_comparison(
    with_chemical,
    without_chemical,
):
    """
    Calculate simple arithmetic means.

    This is kept as a separate helper for compatibility.

    It uses individual observations and does not perform
    power matching.
    """

    if (
        with_chemical is None
        or
        without_chemical is None
    ):

        return {
            "chemical_mean": None,
            "nonchemical_mean": None,
            "improvement": None,
        }

    with_values = (
        with_chemical[
            "sfoc"
        ]
        .dropna()
    )

    without_values = (
        without_chemical[
            "sfoc"
        ]
        .dropna()
    )

    chemical_mean = (
        float(
            with_values.mean()
        )
        if not with_values.empty
        else None
    )

    nonchemical_mean = (
        float(
            without_values.mean()
        )
        if not without_values.empty
        else None
    )

    improvement = None

    if (
        chemical_mean is not None
        and
        nonchemical_mean is not None
        and
        nonchemical_mean != 0
    ):

        improvement = (
            (
                nonchemical_mean
                -
                chemical_mean
            )
            /
            nonchemical_mean
            *
            100.0
        )

    return {
        "chemical_mean": chemical_mean,
        "nonchemical_mean": nonchemical_mean,
        "improvement": improvement,
    }


# ============================================================
# TREND FIT
# ============================================================

def _fit_trend(df):
    """
    Linear regression:

        SFOC = slope * Power + intercept

    Used ONLY for the visual trend line.

    It does NOT affect the Claus effectiveness result.
    """

    if df is None or df.empty:

        return None

    regression_df = (
        df[
            [
                "power",
                "sfoc",
            ]
        ]
        .dropna()
        .copy()
    )

    if len(regression_df) < 2:

        return None

    if regression_df["power"].nunique() < 2:

        return None

    try:

        slope, intercept = np.polyfit(
            regression_df["power"].to_numpy(
                dtype=float,
            ),
            regression_df["sfoc"].to_numpy(
                dtype=float,
            ),
            1,
        )

    except (
        TypeError,
        ValueError,
        np.linalg.LinAlgError,
    ):

        return None

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "n": int(len(regression_df)),
    }


# ============================================================
# TREND LINE
# ============================================================

def _trend_line(
    df,
    min_power=None,
    max_power=None,
):
    """
    Generate two points representing the fitted trend line.

    This is visual only.
    """

    fitted = _fit_trend(
        df,
    )

    if fitted is None:

        return []

    slope = fitted["slope"]
    intercept = fitted["intercept"]

    valid_power = (
        df["power"]
        .dropna()
    )

    if valid_power.empty:

        return []

    x_min = (
        float(valid_power.min())
        if min_power is None
        else float(min_power)
    )

    x_max = (
        float(valid_power.max())
        if max_power is None
        else float(max_power)
    )

    if x_max <= x_min:

        return []

    return [
        {
            "x": x_min,
            "y": float(
                slope * x_min
                +
                intercept
            ),
        },
        {
            "x": x_max,
            "y": float(
                slope * x_max
                +
                intercept
            ),
        },
    ]


# ============================================================
# INDIVIDUAL GRAPH POINTS
# ============================================================

def _points(df):
    """
    Convert individual measurement observations into
    Chart.js-compatible points.
    """

    points = []

    if df is None or df.empty:

        return points

    for _, row in df.iterrows():

        points.append(
            {
                "x": round(
                    float(
                        row["power"]
                    ),
                    2,
                ),

                "y": round(
                    float(
                        row["sfoc"]
                    ),
                    3,
                ),

                "timestamp": (
                    row["timestamp"].isoformat()
                    if pd.notna(
                        row["timestamp"]
                    )
                    else ""
                ),

                "rpm": _safe_float(
                    row.get("rpm"),
                ),

                "speed": _safe_float(
                    row.get("speed"),
                ),

                "voyage": str(
                    row.get("voyage")
                    or
                    "UNKNOWN"
                ),
            }
        )

    return points


# ============================================================
# SINGLE VESSEL ANALYSIS
# ============================================================

def analyse_vessel(
    vessel,
    min_power,
    max_power,
):

    # ========================================================
    # MEASUREMENTS
    # ========================================================

    measurements = _load_measurements(
        vessel,
    )

    if measurements.empty:

        return {
            "success": False,

            "message": (
                f"No measurement data found "
                f"for {vessel}."
            ),
        }

    # ========================================================
    # DATA QUALITY
    # ========================================================

    total_measurements = len(
        measurements
    )

    valid_measurements = int(
        measurements[
            "sfoc_valid"
        ].sum()
    )

    rejected_measurements = (
        total_measurements
        -
        valid_measurements
    )

    rejected_percentage = (
        rejected_measurements
        /
        total_measurements
        *
        100.0
        if total_measurements > 0
        else 0.0
    )

    # ========================================================
    # DOSING
    # ========================================================

    dosing = _load_dosing(
        vessel,
    )

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    measurements = _classify_measurements(
        measurements,
        dosing,
    )

    # ========================================================
    # ALL VALID OBSERVATIONS
    # ========================================================

    all_valid = measurements[
        measurements[
            "sfoc_valid"
        ]
    ].copy()

    # ========================================================
    # SPLIT INTO CHEMICAL / NO CHEMICAL
    # ========================================================

    with_chemical = all_valid[
        all_valid[
            "chemical_status"
        ]
        ==
        "With Chemical"
    ].copy()

    without_chemical = all_valid[
        all_valid[
            "chemical_status"
        ]
        ==
        "Without Chemical"
    ].copy()

    # ========================================================
    # CLAUS CALCULATION
    #
    # THIS IS THE HEADLINE CALCULATION.
    #
    # Treated:
    #     8500 - 9500
    #
    # Untreated:
    #     8000 - 9500
    #
    # Simple arithmetic means of all observations.
    # ========================================================

    claus_result = _claus_comparison(
        with_chemical,
        without_chemical,
    )

    # ========================================================
    # GRAPH RANGE
    #
    # Use the complete union of the Claus ranges so both
    # populations can be displayed.
    #
    #     8000 - 9500
    # ========================================================

    graph_min_power = (
        min(
            CLAUS_TREATED_MIN_POWER,
            CLAUS_UNTREATED_MIN_POWER,
        )
    )

    graph_max_power = (
        max(
            CLAUS_TREATED_MAX_POWER,
            CLAUS_UNTREATED_MAX_POWER,
        )
    )

    graph_filtered = _claus_filter(
        all_valid,
        graph_min_power,
        graph_max_power,
    )

    graph_with_chemical = graph_filtered[
        graph_filtered[
            "chemical_status"
        ]
        ==
        "With Chemical"
    ].copy()

    graph_without_chemical = graph_filtered[
        graph_filtered[
            "chemical_status"
        ]
        ==
        "Without Chemical"
    ].copy()

    # ========================================================
    # TREND LINES
    # ========================================================

    with_trend = _trend_line(
        graph_with_chemical,
        graph_min_power,
        graph_max_power,
    )

    without_trend = _trend_line(
        graph_without_chemical,
        graph_min_power,
        graph_max_power,
    )

    # ========================================================
    # CHART DATA
    # ========================================================

    chart_data = {

        "with_chemical": {

            "points": _points(
                graph_with_chemical,
            ),

            "trend": with_trend,
        },

        "without_chemical": {

            "points": _points(
                graph_without_chemical,
            ),

            "trend": without_trend,
        },
    }

    # ========================================================
    # DOSING DAYS
    # ========================================================

    dosing_days = int(
        (
            dosing[
                "additive_for_classification"
            ]
            .fillna(0.0)
            > 0
        ).sum()
    )

    # ========================================================
    # EXACT CLAUS POPULATIONS
    # ========================================================

    treated_population = _claus_filter(
        with_chemical,
        CLAUS_TREATED_MIN_POWER,
        CLAUS_TREATED_MAX_POWER,
    )

    untreated_population = _claus_filter(
        without_chemical,
        CLAUS_UNTREATED_MIN_POWER,
        CLAUS_UNTREATED_MAX_POWER,
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "success": True,

        "vessel": vessel,

        "min_power": graph_min_power,

        "max_power": graph_max_power,

        # ====================================================
        # WITH CHEMICAL
        # ====================================================

        "with_chemical": {

            "points": chart_data[
                "with_chemical"
            ][
                "points"
            ],

            "trend": chart_data[
                "with_chemical"
            ][
                "trend"
            ],

            "count": len(
                treated_population
            ),

            "mean_sfoc": (
                round(
                    claus_result[
                        "chemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "chemical_mean"
                ] is not None
                else None
            ),

            "raw_mean_sfoc": (
                round(
                    claus_result[
                        "chemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "chemical_mean"
                ] is not None
                else None
            ),
        },

        # ====================================================
        # WITHOUT CHEMICAL
        # ====================================================

        "without_chemical": {

            "points": chart_data[
                "without_chemical"
            ][
                "points"
            ],

            "trend": chart_data[
                "without_chemical"
            ][
                "trend"
            ],

            "count": len(
                untreated_population
            ),

            "mean_sfoc": (
                round(
                    claus_result[
                        "nonchemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "nonchemical_mean"
                ] is not None
                else None
            ),

            "raw_mean_sfoc": (
                round(
                    claus_result[
                        "nonchemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "nonchemical_mean"
                ] is not None
                else None
            ),
        },

        # ====================================================
        # CHART
        # ====================================================

        "chart_data": chart_data,

        # ====================================================
        # HEADLINE IMPROVEMENT
        #
        # Claus calculation:
        #
        # (untreated mean - treated mean)
        # / untreated mean * 100
        # ====================================================

        "raw_improvement": (
            round(
                claus_result[
                    "improvement"
                ],
                3,
            )
            if claus_result[
                "improvement"
            ] is not None
            else None
        ),

        "simple_raw_improvement": (
            round(
                claus_result[
                    "improvement"
                ],
                3,
            )
            if claus_result[
                "improvement"
            ] is not None
            else None
        ),

        # ====================================================
        # NO POWER MATCHING
        # ====================================================

        "matched_power_bands": 0,

        "matched_observations": (
            len(treated_population)
            +
            len(untreated_population)
        ),

        "matched_chemical_observations": (
            len(treated_population)
        ),

        "matched_nonchemical_observations": (
            len(untreated_population)
        ),

        "matched_band_data": [],

        # ====================================================
        # CLAUS RANGES
        # ====================================================

        "treated_min_power": (
            CLAUS_TREATED_MIN_POWER
        ),

        "treated_max_power": (
            CLAUS_TREATED_MAX_POWER
        ),

        "untreated_min_power": (
            CLAUS_UNTREATED_MIN_POWER
        ),

        "untreated_max_power": (
            CLAUS_UNTREATED_MAX_POWER
        ),

        # ====================================================
        # DATA QUALITY
        # ====================================================

        "total_measurements": (
            total_measurements
        ),

        "valid_measurements": (
            valid_measurements
        ),

        "rejected_measurements": (
            rejected_measurements
        ),

        "rejected_percentage": round(
            rejected_percentage,
            2,
        ),

        "range_measurements": (
            len(graph_filtered)
        ),

        "dosing_days": dosing_days,

        # ====================================================
        # METHODOLOGY
        # ====================================================

        "calculation_method": (
            "Claus-style arithmetic mean "
            "of individual SFOC observations"
        ),

        "power_matching": False,

        "power_bands": False,
    }


# ============================================================
# COMBINED ANALYSIS
# ============================================================

def analyse_combined(
    min_power,
    max_power,
):

    # ========================================================
    # LOAD MEASUREMENTS
    # ========================================================

    daniel_measurements = _load_measurements(
        "DANIEL N",
    )

    helen_measurements = _load_measurements(
        "HELEN N",
    )

    # ========================================================
    # LOAD DOSING
    # ========================================================

    daniel_dosing = _load_dosing(
        "DANIEL N",
    )

    helen_dosing = _load_dosing(
        "HELEN N",
    )

    # ========================================================
    # CLASSIFY BEFORE COMBINING
    # ========================================================

    if not daniel_measurements.empty:

        daniel_measurements = (
            _classify_measurements(
                daniel_measurements,
                daniel_dosing,
            )
        )

    if not helen_measurements.empty:

        helen_measurements = (
            _classify_measurements(
                helen_measurements,
                helen_dosing,
            )
        )

    # ========================================================
    # COMBINE
    # ========================================================

    available = []

    if not daniel_measurements.empty:

        available.append(
            daniel_measurements
        )

    if not helen_measurements.empty:

        available.append(
            helen_measurements
        )

    if not available:

        return {
            "success": False,

            "message": (
                "No measurement data found "
                "for Daniel N or Helen N."
            ),
        }

    combined_measurements = pd.concat(
        available,
        ignore_index=True,
    )

    # ========================================================
    # VALID MEASUREMENTS
    # ========================================================

    all_valid = combined_measurements[
        combined_measurements[
            "sfoc_valid"
        ]
    ].copy()

    # ========================================================
    # SPLIT TREATED / UNTREATED
    # ========================================================

    with_chemical = all_valid[
        all_valid[
            "chemical_status"
        ]
        ==
        "With Chemical"
    ].copy()

    without_chemical = all_valid[
        all_valid[
            "chemical_status"
        ]
        ==
        "Without Chemical"
    ].copy()

    # ========================================================
    # CLAUS COMPARISON
    #
    # EXACT SAME CALCULATION AS SINGLE VESSEL.
    # ========================================================

    claus_result = _claus_comparison(
        with_chemical,
        without_chemical,
    )

    # ========================================================
    # GRAPH RANGE
    #
    #     8000 - 9500 kW
    # ========================================================

    graph_min_power = (
        min(
            CLAUS_TREATED_MIN_POWER,
            CLAUS_UNTREATED_MIN_POWER,
        )
    )

    graph_max_power = (
        max(
            CLAUS_TREATED_MAX_POWER,
            CLAUS_UNTREATED_MAX_POWER,
        )
    )

    graph_filtered = _claus_filter(
        all_valid,
        graph_min_power,
        graph_max_power,
    )

    graph_with_chemical = graph_filtered[
        graph_filtered[
            "chemical_status"
        ]
        ==
        "With Chemical"
    ].copy()

    graph_without_chemical = graph_filtered[
        graph_filtered[
            "chemical_status"
        ]
        ==
        "Without Chemical"
    ].copy()

    # ========================================================
    # TREND LINES
    # ========================================================

    with_trend = _trend_line(
        graph_with_chemical,
        graph_min_power,
        graph_max_power,
    )

    without_trend = _trend_line(
        graph_without_chemical,
        graph_min_power,
        graph_max_power,
    )

    # ========================================================
    # CHART DATA
    # ========================================================

    chart_data = {

        "with_chemical": {

            "points": _points(
                graph_with_chemical,
            ),

            "trend": with_trend,
        },

        "without_chemical": {

            "points": _points(
                graph_without_chemical,
            ),

            "trend": without_trend,
        },
    }

    # ========================================================
    # CLAUS POPULATIONS
    # ========================================================

    treated_population = _claus_filter(
        with_chemical,
        CLAUS_TREATED_MIN_POWER,
        CLAUS_TREATED_MAX_POWER,
    )

    untreated_population = _claus_filter(
        without_chemical,
        CLAUS_UNTREATED_MIN_POWER,
        CLAUS_UNTREATED_MAX_POWER,
    )

    # ========================================================
    # DATA QUALITY BY VESSEL
    # ========================================================

    daniel_total = (
        len(daniel_measurements)
        if not daniel_measurements.empty
        else 0
    )

    helen_total = (
        len(helen_measurements)
        if not helen_measurements.empty
        else 0
    )

    daniel_valid = (
        int(
            daniel_measurements[
                "sfoc_valid"
            ].sum()
        )
        if not daniel_measurements.empty
        else 0
    )

    helen_valid = (
        int(
            helen_measurements[
                "sfoc_valid"
            ].sum()
        )
        if not helen_measurements.empty
        else 0
    )

    total_measurements = (
        daniel_total
        +
        helen_total
    )

    valid_measurements = (
        daniel_valid
        +
        helen_valid
    )

    rejected_measurements = (
        total_measurements
        -
        valid_measurements
    )

    rejected_percentage = (
        rejected_measurements
        /
        total_measurements
        *
        100.0
        if total_measurements > 0
        else 0.0
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "success": True,

        "vessel": "COMBINED",

        "min_power": graph_min_power,

        "max_power": graph_max_power,

        # ====================================================
        # WITH CHEMICAL
        # ====================================================

        "with_chemical": {

            "points": chart_data[
                "with_chemical"
            ][
                "points"
            ],

            "trend": chart_data[
                "with_chemical"
            ][
                "trend"
            ],

            "count": len(
                treated_population
            ),

            "mean_sfoc": (
                round(
                    claus_result[
                        "chemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "chemical_mean"
                ] is not None
                else None
            ),

            "raw_mean_sfoc": (
                round(
                    claus_result[
                        "chemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "chemical_mean"
                ] is not None
                else None
            ),
        },

        # ====================================================
        # WITHOUT CHEMICAL
        # ====================================================

        "without_chemical": {

            "points": chart_data[
                "without_chemical"
            ][
                "points"
            ],

            "trend": chart_data[
                "without_chemical"
            ][
                "trend"
            ],

            "count": len(
                untreated_population
            ),

            "mean_sfoc": (
                round(
                    claus_result[
                        "nonchemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "nonchemical_mean"
                ] is not None
                else None
            ),

            "raw_mean_sfoc": (
                round(
                    claus_result[
                        "nonchemical_mean"
                    ],
                    3,
                )
                if claus_result[
                    "nonchemical_mean"
                ] is not None
                else None
            ),
        },

        # ====================================================
        # CHART
        # ====================================================

        "chart_data": chart_data,

        # ====================================================
        # HEADLINE EFFECTIVENESS
        # ====================================================

        "raw_improvement": (
            round(
                claus_result[
                    "improvement"
                ],
                3,
            )
            if claus_result[
                "improvement"
            ] is not None
            else None
        ),

        "simple_raw_improvement": (
            round(
                claus_result[
                    "improvement"
                ],
                3,
            )
            if claus_result[
                "improvement"
            ] is not None
            else None
        ),

        # ====================================================
        # NO MATCHING
        # ====================================================

        "matched_power_bands": 0,

        "matched_observations": (
            len(treated_population)
            +
            len(untreated_population)
        ),

        "matched_chemical_observations": (
            len(treated_population)
        ),

        "matched_nonchemical_observations": (
            len(untreated_population)
        ),

        "matched_band_data": [],

        # ====================================================
        # CLAUS POWER RANGES
        # ====================================================

        "treated_min_power": (
            CLAUS_TREATED_MIN_POWER
        ),

        "treated_max_power": (
            CLAUS_TREATED_MAX_POWER
        ),

        "untreated_min_power": (
            CLAUS_UNTREATED_MIN_POWER
        ),

        "untreated_max_power": (
            CLAUS_UNTREATED_MAX_POWER
        ),

        # ====================================================
        # DATA QUALITY
        # ====================================================

        "total_measurements": (
            total_measurements
        ),

        "valid_measurements": (
            valid_measurements
        ),

        "rejected_measurements": (
            rejected_measurements
        ),

        "rejected_percentage": round(
            rejected_percentage,
            2,
        ),

        "range_measurements": (
            len(graph_filtered)
        ),

        # ====================================================
        # VESSEL BREAKDOWN
        # ====================================================

        "vessels": {

            "DANIEL N": {

                "total_measurements": (
                    daniel_total
                ),

                "valid_measurements": (
                    daniel_valid
                ),
            },

            "HELEN N": {

                "total_measurements": (
                    helen_total
                ),

                "valid_measurements": (
                    helen_valid
                ),
            },
        },

        # ====================================================
        # METHODOLOGY
        # ====================================================

        "calculation_method": (
            "Claus-style arithmetic mean "
            "of individual SFOC observations"
        ),

        "power_matching": False,

        "power_bands": False,
    }


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def build_power_sfoc_analysis(
    vessel="DANIEL N",
    min_power=8000,
    max_power=10000,
):

    vessel = str(
        vessel or "DANIEL N"
    ).strip().upper()

    # ========================================================
    # Convert inputs safely.
    #
    # Kept because the existing page sends these values.
    #
    # They do NOT replace the Claus ranges for the headline
    # effectiveness calculation.
    # ========================================================

    try:

        min_power = float(
            min_power,
        )

    except (
        TypeError,
        ValueError,
    ):

        min_power = 8000.0

    try:

        max_power = float(
            max_power,
        )

    except (
        TypeError,
        ValueError,
    ):

        max_power = 10000.0

    # ========================================================
    # COMBINED
    # ========================================================

    if vessel == "COMBINED":

        return analyse_combined(
            min_power,
            max_power,
        )

    # ========================================================
    # VALID VESSEL
    # ========================================================

    if vessel not in {
        "DANIEL N",
        "HELEN N",
    }:

        vessel = "DANIEL N"

    # ========================================================
    # SINGLE VESSEL
    # ========================================================

    return analyse_vessel(
        vessel,
        min_power,
        max_power,
    )
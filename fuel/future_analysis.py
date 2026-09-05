import pandas as pd
import numpy as np


# ============================================================
# DISPLAY NAMES
# ============================================================

DISPLAY_COLUMNS = {
    0: "Date",
    1: "Duration (days)",
    2: "hrs",
    3: "Distance Travelled",
    4: "Distance",
    5: "HSFO",
    6: "LSFO",
    7: "MGO",
    8: "Speed (knots)",
    9: "Target Speed",
    10: "Speed Saved",
    11: "Consumption",
    12: "24h Consumption",
    13: "Distance to Go",
    14: "Majishan",
    15: "Target",
    16: "Avg Speed",
    17: "Expected",
    18: "Extra",
    19: "Cost",
    20: "Consumption Target",
    21: "Consumption (2)",
    22: "Remaining",
    23: "Consumption Cost",
    24: "Expected Total",
    25: "Expected Time - Daily",
    26: "Cumulative Time",
    27: "Cost (2)",
    28: "Fuel - Daily",
    29: "Fuel - Cumulative",
    30: "Cost (3)",
    31: "Total",
    32: "Date - Future",
    33: "Expected Loss",
}


# ============================================================
# IMPORTANT EXCEL POSITIONS
# ============================================================
#
# These positions come directly from the Excel structure
# shown by debug_excel.py.
#
# Excel:
#
# C  = Date
# L  = Today's Speed / Speed knots
# P  = Consumption
#
# pandas positions:
#
# C -> 2
# L -> 11
# P -> 15
#
# ============================================================

DATE_POSITION = 2
SPEED_POSITION = 11
CONSUMPTION_POSITION = 15


# ============================================================
# HELPERS
# ============================================================

def _numeric_series(series):
    """
    Safely convert an Excel column to numeric values.
    """

    return pd.to_numeric(
        series,
        errors="coerce"
    )


def _check_position(df, position, name):
    """
    Make sure the expected Excel column exists.
    """

    if position >= df.shape[1]:
        raise ValueError(
            f"Could not find {name}. "
            f"The Excel file has only {df.shape[1]} columns."
        )


# ============================================================
# CALCULATE FUTURE ANALYSIS
# ============================================================

def calculate_future_analysis(df):
    """
    Calculate cumulative future average speed
    and cumulative future average consumption.

    The Excel file contains multiple header rows and
    merged cells, therefore the important columns are
    identified by their fixed positions.

    Actual Excel structure:

        Column C  -> Date
        Column L  -> Today's Speed
        Column P  -> Consumption

    Four calculated columns are added:

        Future Average Speed
        Future Average Consumption
        Today's Speed
        Today's Consumption
    """

    # ========================================================
    # VALIDATE INPUT
    # ========================================================

    if df is None:
        raise ValueError(
            "No Excel data was provided."
        )

    if not isinstance(df, pd.DataFrame):
        raise ValueError(
            "The uploaded Excel sheet could not "
            "be read as a DataFrame."
        )

    if df.empty:
        raise ValueError(
            "The selected Excel sheet is empty."
        )

    # ========================================================
    # COPY ORIGINAL DATA
    # ========================================================

    result = df.copy()

    # ========================================================
    # CHECK REQUIRED COLUMNS
    # ========================================================

    _check_position(
        result,
        DATE_POSITION,
        "Date column"
    )

    _check_position(
        result,
        SPEED_POSITION,
        "Speed column"
    )

    _check_position(
        result,
        CONSUMPTION_POSITION,
        "Consumption column"
    )

    # ========================================================
    # EXTRACT COLUMNS
    # ========================================================

    date_series = result.iloc[
        :,
        DATE_POSITION
    ]

    speed_series = result.iloc[
        :,
        SPEED_POSITION
    ]

    consumption_series = result.iloc[
        :,
        CONSUMPTION_POSITION
    ]

    # ========================================================
    # CONVERT DATE
    # ========================================================

    date_values = pd.to_datetime(
        date_series,
        errors="coerce",
        dayfirst=True
    )

    # ========================================================
    # CONVERT SPEED
    # ========================================================

    speed_values = _numeric_series(
        speed_series
    )

    # ========================================================
    # CONVERT CONSUMPTION
    # ========================================================

    consumption_values = _numeric_series(
        consumption_series
    )

    # ========================================================
    # IDENTIFY REAL DAILY ROWS
    # ========================================================
    #
    # Your Excel contains several header rows.
    #
    # Example:
    #
    # rows 0-5 = report headers
    # row 6 onward = actual daily data
    #
    # We use the Date column to identify actual rows.
    #
    # ========================================================

    valid_rows = date_values.notna()

    # ========================================================
    # REMOVE HEADER VALUES FROM CALCULATIONS
    # ========================================================

    valid_speed = speed_values.where(
        valid_rows
    )

    valid_consumption = consumption_values.where(
        valid_rows
    )

    # ========================================================
    # CUMULATIVE AVERAGE SPEED
    # ========================================================
    #
    # Example:
    #
    # 11.43
    #
    # then
    #
    # (11.43 + 12.83) / 2
    #
    # then
    #
    # (11.43 + 12.83 + 11.54) / 3
    #
    # etc.
    #
    # ========================================================

    future_average_speed = (
        valid_speed
        .expanding(
            min_periods=1
        )
        .mean()
    )

    # ========================================================
    # CUMULATIVE AVERAGE CONSUMPTION
    # ========================================================

    future_average_consumption = (
        valid_consumption
        .expanding(
            min_periods=1
        )
        .mean()
    )

    # ========================================================
    # ADD CALCULATED COLUMNS
    # ========================================================

    result[
        "Future Average Speed"
    ] = future_average_speed.round(2)

    result[
        "Future Average Consumption"
    ] = future_average_consumption.round(2)

    result[
        "Today's Speed"
    ] = speed_values.round(2)

    result[
        "Today's Consumption"
    ] = consumption_values.round(2)

    # ========================================================
    # RESET INDEX
    # ========================================================

    result = result.reset_index(
        drop=True
    )

    return result


# ============================================================
# PREPARE FUTURE ANALYSIS TABLE
# ============================================================

def prepare_future_analysis_table(result):
    """
    Prepare the calculated result for display in Django.

    Header rows without a valid date are removed.

    The original Excel columns are preserved.

    The four calculated columns remain at the end.
    """

    # ========================================================
    # VALIDATE
    # ========================================================

    if result is None:
        return pd.DataFrame()

    if not isinstance(
        result,
        pd.DataFrame
    ):
        raise ValueError(
            "Future analysis result is not a DataFrame."
        )

    if result.empty:
        return pd.DataFrame()

    # ========================================================
    # COPY
    # ========================================================

    display_df = result.copy()

    # ========================================================
    # CHECK DATE COLUMN
    # ========================================================

    _check_position(
        display_df,
        DATE_POSITION,
        "Date column"
    )

    # ========================================================
    # DATE VALUES
    # ========================================================

    date_values = pd.to_datetime(
        display_df.iloc[
            :,
            DATE_POSITION
        ],
        errors="coerce",
        dayfirst=True
    )

    # ========================================================
    # KEEP ONLY REAL DAILY DATA
    # ========================================================

    valid_rows = date_values.notna()

    display_df = display_df.loc[
        valid_rows
    ].copy()

    date_values = date_values.loc[
        valid_rows
    ]

    # ========================================================
    # RESET INDEX
    # ========================================================

    display_df = display_df.reset_index(
        drop=True
    )

    date_values = date_values.reset_index(
        drop=True
    )

    # ========================================================
    # FORMAT DATE
    # ========================================================

    display_df.iloc[
        :,
        DATE_POSITION
    ] = date_values.dt.strftime(
        "%d-%b-%Y"
    )

    # ========================================================
    # FORMAT FUTURE DATE
    # ========================================================
    #
    # Original Excel Date - Future is position 41
    # in the raw Excel file.
    #
    # But after loading it with header=None,
    # its pandas position is 41.
    #
    # ========================================================

    if display_df.shape[1] > 41:

        future_date_values = pd.to_datetime(
            display_df.iloc[
                :,
                41
            ],
            errors="coerce",
            dayfirst=True
        )

        display_df.iloc[
            :,
            41
        ] = future_date_values.dt.strftime(
            "%d-%b-%Y"
        )

    # ========================================================
    # RENAME ORIGINAL EXCEL COLUMNS
    # ========================================================
    #
    # IMPORTANT:
    #
    # Because your Excel has merged cells and many blank
    # headers, pandas cannot give the columns useful names.
    #
    # Therefore we use the known Excel positions.
    #
    # ========================================================

    new_column_names = []

    for position, column in enumerate(
        display_df.columns
    ):

        # Calculated columns
        if column == "Future Average Speed":

            new_column_names.append(
                "Future Average Speed"
            )

        elif column == "Future Average Consumption":

            new_column_names.append(
                "Future Average Consumption"
            )

        elif column == "Today's Speed":

            new_column_names.append(
                "Today's Speed"
            )

        elif column == "Today's Consumption":

            new_column_names.append(
                "Today's Consumption"
            )

        else:

            # Use our known display name
            if position in DISPLAY_COLUMNS:

                new_column_names.append(
                    DISPLAY_COLUMNS[position]
                )

            else:

                new_column_names.append(
                    f"Column {position + 1}"
                )

    display_df.columns = new_column_names

    # ========================================================
    # NUMERIC COLUMNS
    # ========================================================

    numeric_columns = [

        "Duration (days)",

        "hrs",

        "Distance Travelled",

        "Distance",

        "HSFO",

        "LSFO",

        "MGO",

        "Speed (knots)",

        "Target Speed",

        "Speed Saved",

        "Consumption",

        "24h Consumption",

        "Distance to Go",

        "Majishan",

        "Target",

        "Avg Speed",

        "Expected",

        "Extra",

        "Cost",

        "Consumption Target",

        "Consumption (2)",

        "Remaining",

        "Consumption Cost",

        "Expected Total",

        "Expected Time - Daily",

        "Cumulative Time",

        "Cost (2)",

        "Fuel - Daily",

        "Fuel - Cumulative",

        "Cost (3)",

        "Total",

        "Expected Loss",

        "Future Average Speed",

        "Future Average Consumption",

        "Today's Speed",

        "Today's Consumption",
    ]

    # ========================================================
    # CONVERT NUMERIC VALUES
    # ========================================================

    for column in numeric_columns:

        if column not in display_df.columns:
            continue

        display_df[column] = pd.to_numeric(
            display_df[column],
            errors="coerce"
        ).round(2)

    # ========================================================
    # REMOVE INFINITE VALUES
    # ========================================================

    display_df = display_df.replace(
        [np.inf, -np.inf],
        np.nan
    )

    # ========================================================
    # REPLACE EMPTY VALUES
    # ========================================================

    display_df = display_df.fillna("")

    # ========================================================
    # RETURN DATAFRAME
    # ========================================================

    return display_df
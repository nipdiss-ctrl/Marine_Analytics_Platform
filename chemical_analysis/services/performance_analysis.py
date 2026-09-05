import pandas as pd


# =========================================================
# SAFE HELPERS
# =========================================================

def safe_float(value, default=None):
    """
    Safely convert a value to float.
    """

    try:
        if value is None:
            return default

        if pd.isna(value):
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    """
    Safely convert a value to integer.
    """

    try:
        if value is None:
            return default

        if pd.isna(value):
            return default

        return int(float(value))

    except (TypeError, ValueError):
        return default


# =========================================================
# COLUMN FINDER
# =========================================================

def _find_column(df, possible_names):
    """
    Find a dataframe column using case-insensitive matching.
    """

    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return None

    if df.empty:
        return None

    columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for name in possible_names:

        key = str(name).strip().lower()

        if key in columns:
            return columns[key]

    return None


# =========================================================
# NUMERIC SERIES
# =========================================================

def _numeric_series(df, possible_names):
    """
    Return a numeric pandas Series for a requested field.

    If the column does not exist, return an empty numeric
    series aligned to the dataframe index.
    """

    column = _find_column(
        df,
        possible_names,
    )

    if column is None:

        return pd.Series(
            index=df.index,
            dtype="float64",
        )

    return pd.to_numeric(
        df[column],
        errors="coerce",
    )


# =========================================================
# PREPARE DATAFRAME
# =========================================================

def _prepare_dataframe(daily_df):
    """
    Prepare daily METIS performance data.

    Important rules:

    1. Invalid dates are removed.
    2. Future dates are removed.
    3. Time is removed from timestamps.
    4. Duplicate records belonging to the same calendar
       day are combined into ONE daily record.
    5. Fuel is summed.
    6. Power, speed and RPM are averaged.
    7. SFOC is power-weighted where possible.
    """

    if daily_df is None:
        return pd.DataFrame()

    if not isinstance(
        daily_df,
        pd.DataFrame,
    ):
        return pd.DataFrame()

    if daily_df.empty:
        return pd.DataFrame()

    df = daily_df.copy()

    # =====================================================
    # DATE
    # =====================================================

    date_column = _find_column(
        df,
        [
            "date",
            "timestamp",
            "day",
        ],
    )

    if date_column is None:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(
        df[date_column],
        errors="coerce",
    )

    df = df.dropna(
        subset=["date"]
    ).copy()

    if df.empty:
        return pd.DataFrame()

    # Remove time component.
    df["date"] = df["date"].dt.normalize()

    # =====================================================
    # NUMERIC VALUES
    # =====================================================

    df["avg_sfoc"] = _numeric_series(
        df,
        [
            "avg_sfoc",
            "average_sfoc",
            "sfoc",
            "SFOC",
        ],
    )

    df["fuel_used_kg"] = _numeric_series(
        df,
        [
            "fuel_used_kg",
            "fuel_consumption",
            "fuel_consumption_kg",
            "Fuel_Consumption",
            "fuel",
        ],
    )

    df["avg_speed"] = _numeric_series(
        df,
        [
            "avg_speed",
            "average_speed",
            "speed",
            "Speed",
        ],
    )

    df["avg_power"] = _numeric_series(
        df,
        [
            "avg_power",
            "average_power",
            "power",
            "Power",
        ],
    )

    df["rpm"] = _numeric_series(
        df,
        [
            "avg_rpm",
            "average_rpm",
            "rpm",
            "RPM",
        ],
    )

    # =====================================================
    # REMOVE FUTURE DATA
    # =====================================================

    today = pd.Timestamp.today().normalize()

    df = df[
        df["date"] <= today
    ].copy()

    if df.empty:
        return pd.DataFrame()

    # =====================================================
    # COMBINE DUPLICATE DAYS
    # =====================================================

    grouped = []

    for date_value, group in df.groupby(
        "date",
        sort=True,
    ):

        # -------------------------------------------------
        # FUEL
        # -------------------------------------------------

        fuel_values = group[
            "fuel_used_kg"
        ].dropna()

        if not fuel_values.empty:
            fuel = float(
                fuel_values.sum()
            )
        else:
            fuel = None

        # -------------------------------------------------
        # POWER
        # -------------------------------------------------

        power_values = group[
            "avg_power"
        ].dropna()

        if not power_values.empty:
            power = float(
                power_values.mean()
            )
        else:
            power = None

        # -------------------------------------------------
        # SPEED
        # -------------------------------------------------

        speed_values = group[
            "avg_speed"
        ].dropna()

        if not speed_values.empty:
            speed = float(
                speed_values.mean()
            )
        else:
            speed = None

        # -------------------------------------------------
        # RPM
        # -------------------------------------------------

        rpm_values = group[
            "rpm"
        ].dropna()

        if not rpm_values.empty:
            rpm = float(
                rpm_values.mean()
            )
        else:
            rpm = None

        # -------------------------------------------------
        # SFOC
        # -------------------------------------------------

        valid_sfoc = group[
            [
                "avg_sfoc",
                "avg_power",
            ]
        ].dropna()

        valid_sfoc = valid_sfoc[
            (valid_sfoc["avg_sfoc"] > 0)
            &
            (valid_sfoc["avg_power"] > 0)
        ]

        if not valid_sfoc.empty:

            total_power = float(
                valid_sfoc[
                    "avg_power"
                ].sum()
            )

            if total_power > 0:

                sfoc = float(
                    (
                        valid_sfoc["avg_sfoc"]
                        *
                        valid_sfoc["avg_power"]
                    ).sum()
                    /
                    total_power
                )

            else:

                sfoc = safe_float(
                    valid_sfoc[
                        "avg_sfoc"
                    ].mean()
                )

        else:

            # Keep SFOC missing for zero-power /
            # invalid-power days.
            sfoc = None

        grouped.append(
            {
                "date": date_value,
                "avg_sfoc": sfoc,
                "fuel_used_kg": fuel,
                "avg_speed": speed,
                "avg_power": power,
                "rpm": rpm,
            }
        )

    if not grouped:
        return pd.DataFrame()

    result = pd.DataFrame(
        grouped
    )

    return (
        result
        .sort_values("date")
        .reset_index(drop=True)
    )


# =========================================================
# LOAD CLASSIFICATION
# =========================================================

def classify_load(power):
    """
    Classify daily engine operating condition.

    < 1,000 kW
        Low Load

    1,000–3,999 kW
        Partial Load

    4,000–6,999 kW
        Normal Load

    >= 7,000 kW
        High Load

    Zero power is intentionally classified as Low Load.
    It remains visible in the operating-condition
    distribution, but is NOT treated as usable performance
    data.
    """

    power = safe_float(power)

    if power is None:
        return "Unknown"

    if power < 1000:
        return "Low Load"

    if power < 4000:
        return "Partial Load"

    if power < 7000:
        return "Normal Load"

    return "High Load"


# =========================================================
# ANALYSIS QUALITY
# =========================================================

def determine_analysis_quality(row):
    """
    Determine whether a daily record is suitable for
    performance analysis.

    Rules:

    Valid performance day:
        SFOC > 0
        Power > 0
        Speed >= 0

    Low load:
        Power < 1,000 kW

    Zero / invalid power:
        Incomplete

    Missing SFOC:
        Incomplete
    """

    if row is None:
        return "Incomplete"

    sfoc = safe_float(
        row.get("avg_sfoc")
    )

    power = safe_float(
        row.get("avg_power")
    )

    speed = safe_float(
        row.get("avg_speed")
    )

    # -----------------------------------------------------
    # SFOC
    # -----------------------------------------------------

    if sfoc is None or sfoc <= 0:
        return "Incomplete"

    # -----------------------------------------------------
    # POWER
    # -----------------------------------------------------

    if power is None or power <= 0:
        return "Incomplete"

    # -----------------------------------------------------
    # SPEED
    # -----------------------------------------------------

    if speed is None or speed < 0:
        return "Incomplete"

    # -----------------------------------------------------
    # LOW LOAD
    # -----------------------------------------------------

    if power < 1000:
        return "Low Load"

    # -----------------------------------------------------
    # USABLE
    # -----------------------------------------------------

    return "Usable"


# =========================================================
# USABLE PERFORMANCE DATA
# =========================================================

def _get_usable_data(df):
    """
    Return daily records suitable for general performance
    calculations.

    Requirements:

        SFOC > 0
        Power > 0

    Low-load data remains included here because it is still
    technically operating data. It is excluded only from
    normal-load performance comparisons.
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    usable = df[
        df["avg_sfoc"].notna()
        &
        (df["avg_sfoc"] > 0)
        &
        df["avg_power"].notna()
        &
        (df["avg_power"] > 0)
    ].copy()

    return usable


# =========================================================
# MEANINGFUL PERFORMANCE DATA
# =========================================================

def _get_meaningful_performance_data(df):
    """
    Return normal operating days suitable for meaningful
    SFOC performance comparisons.

    Normal load:

        4,000 <= power < 7,000 kW

    High load is intentionally excluded from this specific
    comparison because the vessel's normal operating band
    is the most appropriate basis for best/worst SFOC.
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    meaningful = df[
        df["avg_power"].notna()
        &
        (df["avg_power"] >= 4000)
        &
        (df["avg_power"] < 7000)
        &
        df["avg_sfoc"].notna()
        &
        (df["avg_sfoc"] > 0)
    ].copy()

    return meaningful


# =========================================================
# NORMAL LOAD SFOC
# =========================================================

def _calculate_normal_load_average_sfoc(df):
    """
    Calculate power-weighted SFOC for normal-load operation.

    Normal load:

        4,000 <= power < 7,000 kW
    """

    normal_load = _get_meaningful_performance_data(
        df
    )

    if normal_load.empty:
        return None

    total_power = safe_float(
        normal_load["avg_power"].sum()
    )

    if total_power is None or total_power <= 0:
        return safe_float(
            normal_load["avg_sfoc"].mean()
        )

    weighted_sfoc = (
        (
            normal_load["avg_sfoc"]
            *
            normal_load["avg_power"]
        ).sum()
        /
        total_power
    )

    return safe_float(
        weighted_sfoc
    )


# =========================================================
# BEST SFOC
# =========================================================

def _get_best_sfoc(df):
    """
    Find the best meaningful SFOC.

    Only normal-load days are considered.
    """

    valid = _get_meaningful_performance_data(
        df
    )

    if valid.empty:
        return None, None

    index = valid[
        "avg_sfoc"
    ].idxmin()

    value = safe_float(
        valid.loc[
            index,
            "avg_sfoc",
        ]
    )

    date = valid.loc[
        index,
        "date",
    ]

    return value, date


# =========================================================
# WORST / HIGHEST MEANINGFUL SFOC
# =========================================================

def _get_worst_sfoc(df):
    """
    Find the highest meaningful SFOC.

    Very low-load values such as:

        282 g/kWh at 2 kW
        279 g/kWh at 1 kW

    are deliberately excluded.

    This prevents idle/near-idle operation from being
    presented as poor engine efficiency.
    """

    valid = _get_meaningful_performance_data(
        df
    )

    if valid.empty:
        return None, None

    index = valid[
        "avg_sfoc"
    ].idxmax()

    value = safe_float(
        valid.loc[
            index,
            "avg_sfoc",
        ]
    )

    date = valid.loc[
        index,
        "date",
    ]

    return value, date


# =========================================================
# PERFORMANCE SUMMARY
# =========================================================

def calculate_performance_summary(daily_df):
    """
    Calculate all performance KPIs from the same prepared
    daily dataframe.

    This guarantees that:

        total_days
        usable_days
        load counts
        SFOC calculations

    all use the same deduplicated dataset.
    """

    df = _prepare_dataframe(
        daily_df
    )

    # =====================================================
    # EMPTY DATA
    # =====================================================

    if df.empty:

        return {
            "total_days": 0,
            "usable_days": 0,

            "low_load_days": 0,
            "partial_load_days": 0,
            "normal_load_days": 0,
            "high_load_days": 0,

            "average_sfoc": None,
            "average_fuel_consumption": None,
            "average_speed": None,
            "average_power": None,

            "normal_load_average_sfoc": None,

            "min_sfoc": None,
            "best_sfoc_date": None,

            "max_sfoc": None,
            "worst_sfoc_date": None,
        }

    # =====================================================
    # LOAD CLASS
    # =====================================================

    df["load_class"] = df[
        "avg_power"
    ].apply(
        classify_load
    )

    low_load_days = int(
        (
            df["load_class"]
            == "Low Load"
        ).sum()
    )

    partial_load_days = int(
        (
            df["load_class"]
            == "Partial Load"
        ).sum()
    )

    normal_load_days = int(
        (
            df["load_class"]
            == "Normal Load"
        ).sum()
    )

    high_load_days = int(
        (
            df["load_class"]
            == "High Load"
        ).sum()
    )

    # =====================================================
    # TOTAL DAYS
    # =====================================================

    total_days = int(
        len(df)
    )

    # =====================================================
    # USABLE DATA
    # =====================================================

    usable = _get_usable_data(
        df
    )

    usable_days = int(
        len(usable)
    )

    # =====================================================
    # AVERAGE SFOC
    # =====================================================

    if not usable.empty:

        average_sfoc = safe_float(
            usable["avg_sfoc"].mean()
        )

    else:

        average_sfoc = None

    # =====================================================
    # AVERAGE DAILY FUEL
    # =====================================================

    if not usable.empty:

        fuel = usable[
            "fuel_used_kg"
        ].dropna()

        if not fuel.empty:

            average_fuel = safe_float(
                fuel.mean()
            )

        else:

            average_fuel = None

    else:

        average_fuel = None

    # =====================================================
    # AVERAGE SPEED
    # =====================================================

    if not usable.empty:

        speed = usable[
            "avg_speed"
        ].dropna()

        if not speed.empty:

            average_speed = safe_float(
                speed.mean()
            )

        else:

            average_speed = None

    else:

        average_speed = None

    # =====================================================
    # AVERAGE POWER
    # =====================================================

    if not usable.empty:

        power = usable[
            "avg_power"
        ].dropna()

        if not power.empty:

            average_power = safe_float(
                power.mean()
            )

        else:

            average_power = None

    else:

        average_power = None

    # =====================================================
    # NORMAL LOAD SFOC
    # =====================================================

    normal_load_average_sfoc = (
        _calculate_normal_load_average_sfoc(
            df
        )
    )

    # =====================================================
    # BEST SFOC
    # =====================================================

    min_sfoc, best_date = _get_best_sfoc(
        df
    )

    # =====================================================
    # WORST MEANINGFUL SFOC
    # =====================================================

    max_sfoc, worst_date = _get_worst_sfoc(
        df
    )

    # =====================================================
    # DATE FORMATTING
    # =====================================================

    if best_date is not None:

        best_sfoc_date = (
            pd.to_datetime(
                best_date
            ).strftime(
                "%d %b %Y"
            )
        )

    else:

        best_sfoc_date = None

    if worst_date is not None:

        worst_sfoc_date = (
            pd.to_datetime(
                worst_date
            ).strftime(
                "%d %b %Y"
            )
        )

    else:

        worst_sfoc_date = None

    # =====================================================
    # RETURN
    # =====================================================

    return {

        "total_days":
            total_days,

        "usable_days":
            usable_days,

        "low_load_days":
            low_load_days,

        "partial_load_days":
            partial_load_days,

        "normal_load_days":
            normal_load_days,

        "high_load_days":
            high_load_days,

        "average_sfoc":
            average_sfoc,

        "average_fuel_consumption":
            average_fuel,

        "average_speed":
            average_speed,

        "average_power":
            average_power,

        "normal_load_average_sfoc":
            normal_load_average_sfoc,

        "min_sfoc":
            min_sfoc,

        "best_sfoc_date":
            best_sfoc_date,

        "max_sfoc":
            max_sfoc,

        "worst_sfoc_date":
            worst_sfoc_date,
    }


# =========================================================
# DAILY PERFORMANCE DATA
# =========================================================

def prepare_performance_daily_data(daily_df):
    """
    Prepare deduplicated daily records for the Django
    template.
    """

    df = _prepare_dataframe(
        daily_df
    )

    if df.empty:
        return []

    records = []

    for _, row in df.iterrows():

        date_value = row.get(
            "date"
        )

        if pd.isna(date_value):
            continue

        sfoc = safe_float(
            row.get("avg_sfoc")
        )

        fuel = safe_float(
            row.get("fuel_used_kg")
        )

        speed = safe_float(
            row.get("avg_speed")
        )

        power = safe_float(
            row.get("avg_power")
        )

        rpm = safe_float(
            row.get("rpm")
        )

        load_class = classify_load(
            power
        )

        analysis_quality = (
            determine_analysis_quality(
                row
            )
        )

        records.append(
            {
                "date":
                    pd.to_datetime(
                        date_value
                    ).strftime(
                        "%d %b"
                    ),

                "full_date":
                    pd.to_datetime(
                        date_value
                    ).strftime(
                        "%d %b %Y"
                    ),

                "sfoc":
                    round(sfoc, 2)
                    if sfoc is not None
                    else None,

                "fuel":
                    round(fuel, 2)
                    if fuel is not None
                    else None,

                "speed":
                    round(speed, 2)
                    if speed is not None
                    else None,

                "power":
                    round(power, 0)
                    if power is not None
                    else None,

                "rpm":
                    round(rpm, 2)
                    if rpm is not None
                    else None,

                "operating_load":
                    load_class,

                "load_class":
                    load_class,

                "analysis_quality":
                    analysis_quality,
            }
        )

    return records


# =========================================================
# CHART DATA
# =========================================================

def prepare_chart_data(daily_df):
    """
    Prepare chart data from the exact same deduplicated
    dataframe used by the KPI calculations.
    """

    df = _prepare_dataframe(
        daily_df
    )

    if df.empty:

        return {
            "dates": [],
            "sfoc": [],
            "fuel": [],
            "speed": [],
            "power": [],
        }

    dates = []
    sfoc = []
    fuel = []
    speed = []
    power = []

    for _, row in df.iterrows():

        date_value = row.get(
            "date"
        )

        if pd.isna(date_value):
            continue

        dates.append(
            pd.to_datetime(
                date_value
            ).strftime(
                "%d %b %Y"
            )
        )

        sfoc_value = safe_float(
            row.get("avg_sfoc")
        )

        fuel_value = safe_float(
            row.get("fuel_used_kg")
        )

        speed_value = safe_float(
            row.get("avg_speed")
        )

        power_value = safe_float(
            row.get("avg_power")
        )

        sfoc.append(
            round(
                sfoc_value,
                2,
            )
            if sfoc_value is not None
            else None
        )

        fuel.append(
            round(
                fuel_value,
                2,
            )
            if fuel_value is not None
            else None
        )

        speed.append(
            round(
                speed_value,
                2,
            )
            if speed_value is not None
            else None
        )

        power.append(
            round(
                power_value,
                0,
            )
            if power_value is not None
            else None
        )

    return {

        "dates":
            dates,

        "sfoc":
            sfoc,

        "fuel":
            fuel,

        "speed":
            speed,

        "power":
            power,
    }


# =========================================================
# COMPLETE PERFORMANCE ANALYSIS
# =========================================================

def get_performance_analysis(daily_df):
    """
    Main function called from views.py.

    All three outputs are generated independently from the
    same source dataframe, with the same duplicate-day
    handling.
    """

    performance_summary = (
        calculate_performance_summary(
            daily_df
        )
    )

    daily_data = (
        prepare_performance_daily_data(
            daily_df
        )
    )

    chart_data = (
        prepare_chart_data(
            daily_df
        )
    )

    return {

        "performance_summary":
            performance_summary,

        "daily_data":
            daily_data,

        "chart_data":
            chart_data,
    }
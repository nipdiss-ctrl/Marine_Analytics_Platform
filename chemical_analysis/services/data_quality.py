import numpy as np


# =========================================================
# DATA QUALITY
# =========================================================

def calculate_data_quality(
    daily_df,
    normalized_comparison=None,
    dosing_without_measurement=None,
):

    normalized_comparison = (
        normalized_comparison
        or {}
    )

    if daily_df is None:

        return {
            "total_days": 0,
            "days_with_sfoc": 0,
            "days_without_sfoc": 0,
            "dosing_days": 0,
            "dosing_without_measurement": 0,
            "matched_observations": 0,
            "rejected_observations": 0,
            "match_rate": np.nan,
        }

    total_days = len(daily_df)

    if "avg_sfoc" in daily_df.columns:

        days_with_sfoc = int(
            daily_df["avg_sfoc"]
            .notna()
            .sum()
        )

    else:

        days_with_sfoc = 0

    days_without_sfoc = (
        total_days
        -
        days_with_sfoc
    )

    if "total_additive" in daily_df.columns:

        dosing_days = int(
            (
                daily_df["total_additive"]
                > 0
            ).sum()
        )

    else:

        dosing_days = 0

    matched_observations = int(
        normalized_comparison.get(
            "matched_observations",
            0,
        )
        or 0
    )

    rejected_observations = int(
        normalized_comparison.get(
            "rejected_observations",
            0,
        )
        or 0
    )

    total_match_attempts = (
        matched_observations
        +
        rejected_observations
    )

    if total_match_attempts > 0:

        match_rate = (
            matched_observations
            /
            total_match_attempts
            *
            100.0
        )

    else:

        match_rate = np.nan

    if dosing_without_measurement is None:

        dosing_without_measurement_count = 0

    else:

        dosing_without_measurement_count = (
            len(
                dosing_without_measurement
            )
        )

    return {

        "total_days":
            total_days,

        "days_with_sfoc":
            days_with_sfoc,

        "days_without_sfoc":
            days_without_sfoc,

        "dosing_days":
            dosing_days,

        "dosing_without_measurement":
            dosing_without_measurement_count,

        "matched_observations":
            matched_observations,

        "rejected_observations":
            rejected_observations,

        "match_rate":
            match_rate,
    }
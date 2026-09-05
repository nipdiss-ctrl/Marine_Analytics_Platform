import numpy as np
import pandas as pd


# =========================================================
# DOSING ANALYSIS
# =========================================================

def calculate_dosing_analysis(daily_df):

    if daily_df is None or daily_df.empty:

        return {
            "dosing_days": 0,
            "non_dosing_days": 0,
            "total_additive": 0.0,
            "average_daily_additive": np.nan,
            "average_dosing_fuel": np.nan,
            "additive_to_fuel_ratio": np.nan,
        }

    df = daily_df.copy()

    # -----------------------------------------------------
    # NUMERIC
    # -----------------------------------------------------

    for column in [
        "total_additive",
        "total_fuel_qty",
        "fuel_used_kg",
    ]:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    if "total_additive" not in df.columns:
        df["total_additive"] = 0.0

    df["total_additive"] = (
        df["total_additive"]
        .fillna(0.0)
    )

    # -----------------------------------------------------
    # DOSING
    # -----------------------------------------------------

    dosing = df[
        df["total_additive"] > 0
    ].copy()

    non_dosing = df[
        df["total_additive"] <= 0
    ].copy()

    total_additive = (
        dosing["total_additive"]
        .sum()
    )

    average_daily_additive = (
        dosing["total_additive"].mean()
        if not dosing.empty
        else np.nan
    )

    # -----------------------------------------------------
    # FUEL DURING DOSING
    # -----------------------------------------------------

    if (
        "fuel_used_kg" in dosing.columns
        and not dosing.empty
    ):

        average_dosing_fuel = (
            dosing["fuel_used_kg"]
            .dropna()
            .mean()
        )

    else:

        average_dosing_fuel = np.nan

    # -----------------------------------------------------
    # ADDITIVE / FUEL RATIO
    # -----------------------------------------------------

    if (
        not dosing.empty
        and "fuel_used_kg" in dosing.columns
    ):

        total_dosing_fuel = (
            dosing["fuel_used_kg"]
            .dropna()
            .sum()
        )

        if total_dosing_fuel > 0:

            additive_to_fuel_ratio = (
                total_additive
                /
                total_dosing_fuel
            )

        else:

            additive_to_fuel_ratio = np.nan

    else:

        additive_to_fuel_ratio = np.nan

    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    return {

        "dosing_days":
            len(dosing),

        "non_dosing_days":
            len(non_dosing),

        "total_additive":
            total_additive,

        "average_daily_additive":
            average_daily_additive,

        "average_dosing_fuel":
            average_dosing_fuel,

        "additive_to_fuel_ratio":
            additive_to_fuel_ratio,
    }
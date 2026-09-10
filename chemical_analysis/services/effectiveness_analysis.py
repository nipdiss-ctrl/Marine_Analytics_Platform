from __future__ import annotations

import math

import numpy as np
import pandas as pd


# =========================================================
# HELPERS
# =========================================================


def _num(value, default=None):
    """
    Safely convert a value to a finite float.
    """
    try:
        if value is None:
            return default

        value = float(value)

        if not math.isfinite(value):
            return default

        return value

    except (TypeError, ValueError):
        return default


def _round(value, digits=2):
    """
    Safely round a numeric value.
    """
    value = _num(value)

    if value is None:
        return None

    return round(value, digits)


def _fmt_date(value):
    """
    Format dates consistently for the management report.
    """
    if value is None:
        return ""

    try:
        return pd.to_datetime(value).strftime("%d %b %Y")

    except Exception:
        return str(value)


def _safe_mean(series):
    """
    Calculate a safe numeric mean.
    """
    if series is None:
        return None

    try:
        values = pd.to_numeric(
            series,
            errors="coerce",
        ).dropna()

        if values.empty:
            return None

        return float(values.mean())

    except Exception:
        return None


# =========================================================
# EFFECTIVENESS REPORT
# =========================================================


def build_effectiveness_report(
    analysis_result,
    fuel_price=0.0,
    additive_price=0.0,
):
    """
    Build the management-oriented chemical effectiveness report.

    IMPORTANT:

    1. Raw dosing vs no-dosing SFOC is shown for context.
    2. Operating-condition-matched SFOC is the PRIMARY effectiveness metric.
    3. Fuel kg/h is NOT used to claim chemical savings because it depends
       strongly on engine load/power.
    4. Financial figures are potential / illustrative scenarios.
    5. Annual financial calculations use the OBSERVED dosing frequency.
       They do NOT assume additive dosing every day.
    """

    analysis_result = analysis_result or {}

    daily = analysis_result.get("daily")

    comparison = (
        analysis_result.get("comparison")
        or {}
    )

    normalized = (
        analysis_result.get("normalized_comparison")
        or {}
    )

    dosing_analysis = (
        analysis_result.get("dosing_analysis")
        or {}
    )

    data_quality = (
        analysis_result.get("data_quality")
        or {}
    )

    # =====================================================
    # DAILY DATA
    # =====================================================

    if not isinstance(daily, pd.DataFrame):

        daily = pd.DataFrame()

    else:

        daily = daily.copy()


    # =====================================================
    # CLEAN DAILY DATA
    # =====================================================

    if (
        not daily.empty
        and "date" in daily.columns
    ):

        daily["date"] = pd.to_datetime(
            daily["date"],
            errors="coerce",
        )

        daily = (
            daily
            .dropna(subset=["date"])
            .sort_values("date")
        )


    numeric_columns = [
        "avg_sfoc",
        "fuel_used_kg",
        "avg_power",
        "avg_speed",
        "rpm",
        "total_additive",
    ]

    for column in numeric_columns:

        if column in daily.columns:

            daily[column] = pd.to_numeric(
                daily[column],
                errors="coerce",
            )


    # -----------------------------------------------------
    # Additive column
    # -----------------------------------------------------

    if "total_additive" not in daily.columns:

        daily["total_additive"] = 0.0


    daily["total_additive"] = (
        daily["total_additive"]
        .fillna(0.0)
    )


    # -----------------------------------------------------
    # Dosing status
    # -----------------------------------------------------

    daily["dosing_status"] = np.where(
        daily["total_additive"] > 0,
        "Dosing",
        "No Dosing",
    )


    # =====================================================
    # OPERATING DAYS
    # =====================================================

    # We exclude clearly non-operational/incomplete days
    # from contextual and financial averages.
    #
    # The existing normalized matcher remains the authority
    # for the actual effectiveness calculation.

    operating = daily.copy()


    if "avg_power" in operating.columns:

        operating = operating[
            operating["avg_power"]
            .fillna(0)
            >= 500
        ].copy()


    if "avg_sfoc" in operating.columns:

        operating = operating[
            operating["avg_sfoc"].notna()
            & (
                operating["avg_sfoc"] > 0
            )
        ].copy()


    # =====================================================
    # RAW COMPARISON
    # =====================================================

    raw_dosing_sfoc = _num(
        comparison.get("dosing_sfoc")
    )

    raw_no_dosing_sfoc = _num(
        comparison.get("non_dosing_sfoc")
    )

    raw_improvement = _num(
        comparison.get("sfoc_improvement")
    )

    raw_dosing_fuel = _num(
        comparison.get("dosing_fuel")
    )

    raw_no_dosing_fuel = _num(
        comparison.get("non_dosing_fuel")
    )


    # -----------------------------------------------------
    # Fallback raw SFOC improvement
    # -----------------------------------------------------

    if (
        raw_improvement is None
        and raw_dosing_sfoc is not None
        and raw_no_dosing_sfoc
    ):

        raw_improvement = (
            (
                raw_no_dosing_sfoc
                - raw_dosing_sfoc
            )
            / raw_no_dosing_sfoc
            * 100.0
        )


    # =====================================================
    # NORMALIZED / MATCHED RESULT
    # =====================================================

    normalized_dosing_sfoc = _num(
        normalized.get("dosing_sfoc")
    )

    normalized_baseline_sfoc = _num(
        normalized.get(
            "matched_baseline_sfoc",
            normalized.get(
                "matched_non_dosing_sfoc"
            ),
        )
    )

    normalized_improvement = _num(
        normalized.get("sfoc_improvement")
    )


    # -----------------------------------------------------
    # Fallback normalized calculation
    # -----------------------------------------------------

    if (
        normalized_improvement is None
        and normalized_baseline_sfoc is not None
        and normalized_dosing_sfoc is not None
        and normalized_baseline_sfoc != 0
    ):

        normalized_improvement = (
            (
                normalized_baseline_sfoc
                - normalized_dosing_sfoc
            )
            / normalized_baseline_sfoc
            * 100.0
        )


    # =====================================================
    # MATCH COUNTS
    # =====================================================

    matched = int(
        _num(
            normalized.get(
                "matched_observations"
            ),
            0,
        )
        or 0
    )

    rejected = int(
        _num(
            normalized.get(
                "rejected_observations"
            ),
            0,
        )
        or 0
    )

    attempts = (
        matched
        + rejected
    )

    match_rate = (
        matched
        / attempts
        * 100.0
        if attempts
        else None
    )


    # =====================================================
    # MATCH DETAILS
    # =====================================================

    matches = (
        normalized.get("matches")
        or []
    )

    if not isinstance(matches, list):

        matches = []


    match_rows = []

    pair_effects = []


    for row in matches:

        if not isinstance(row, dict):
            continue


        effect = _num(
            row.get(
                "sfoc_improvement"
            )
        )


        if effect is not None:

            pair_effects.append(
                effect
            )


        match_rows.append(
            {
                "dosing_date":
                    _fmt_date(
                        row.get(
                            "dosing_date"
                        )
                    ),

                "baseline_date":
                    _fmt_date(
                        row.get(
                            "baseline_date"
                        )
                    ),

                "voyage":
                    str(
                        row.get(
                            "voyage"
                        )
                        or "UNKNOWN"
                    ),

                "baseline_voyage":
                    str(
                        row.get(
                            "baseline_voyage"
                        )
                        or "UNKNOWN"
                    ),

                "dosing_sfoc":
                    _round(
                        row.get(
                            "dosing_sfoc"
                        ),
                        2,
                    ),

                "baseline_sfoc":
                    _round(
                        row.get(
                            "baseline_sfoc"
                        ),
                        2,
                    ),

                "sfoc_improvement":
                    _round(
                        effect,
                        2,
                    ),

                "match_score":
                    _round(
                        row.get(
                            "match_score"
                        ),
                        3,
                    ),

                "match_quality":
                    str(
                        row.get(
                            "match_quality"
                        )
                        or "Unknown"
                    ),

                "load_difference":
                    _round(
                        row.get(
                            "load_difference"
                        ),
                        2,
                    ),

                "power_difference":
                    _round(
                        row.get(
                            "power_difference"
                        ),
                        1,
                    ),

                "speed_difference":
                    _round(
                        row.get(
                            "speed_difference"
                        ),
                        2,
                    ),

                "rpm_difference":
                    _round(
                        row.get(
                            "rpm_difference"
                        ),
                        2,
                    ),

                "date_difference":
                    _round(
                        row.get(
                            "date_difference"
                        ),
                        0,
                    ),
            }
        )


    # =====================================================
    # PAIR STATISTICS
    # =====================================================

    pair_effects = np.asarray(
        pair_effects,
        dtype=float,
    )

    pair_effects = pair_effects[
        np.isfinite(pair_effects)
    ]


    if pair_effects.size:

        pair_mean = float(
            pair_effects.mean()
        )

    else:

        pair_mean = (
            normalized_improvement
        )


    pair_median = (
        float(
            np.median(
                pair_effects
            )
        )
        if pair_effects.size
        else None
    )


    pair_std = (
        float(
            pair_effects.std(
                ddof=1
            )
        )
        if pair_effects.size >= 2
        else None
    )


    standard_error = (

        pair_std
        / math.sqrt(
            pair_effects.size
        )

        if (
            pair_std is not None
            and pair_effects.size >= 2
        )

        else None

    )


    ci_low = None
    ci_high = None


    if standard_error is not None:

        # Indicative normal approximation.
        # This is NOT a formal statistical trial result.

        ci_low = (
            pair_mean
            - 1.96 * standard_error
        )

        ci_high = (
            pair_mean
            + 1.96 * standard_error
        )


    # =====================================================
    # RECOMMENDATION
    # =====================================================

    if (
        normalized_improvement is None
        or matched == 0
    ):

        status = (
            "NO DEMONSTRATED "
            "FUEL-SAVING BENEFIT — "
            "MORE DATA REQUIRED"
        )

        status_level = "warning"

        status_icon = "🟡"

        recommendation = (
            "There is not enough "
            "operating-condition-matched "
            "evidence to demonstrate a "
            "meaningful fuel-saving benefit "
            "attributable to the additive."
        )


    elif normalized_improvement < -0.5:

        status = (
            "NEGATIVE / REVIEW"
        )

        status_level = "negative"

        status_icon = "🔴"

        recommendation = (
            "The normalized result indicates "
            "higher SFOC during dosing. "
            "Review the trial conditions and "
            "commercial case before continuing."
        )


    elif normalized_improvement <= 0.5:

        status = (
            "NO DEMONSTRATED "
            "FUEL-SAVING BENEFIT — "
            "MORE DATA REQUIRED"
        )

        status_level = "warning"

        status_icon = "🟡"

        recommendation = (
            "Based on the data available to "
            "date, no meaningful fuel-saving "
            "benefit has been demonstrated "
            "after correcting for operating "
            "conditions. The additive should "
            "not be continued on the basis "
            "of fuel savings alone. If there "
            "is a separate operational reason "
            "to continue the trial, collect "
            "additional controlled observations "
            "before making a final decision."
        )


    elif matched < 30:

        status = (
            "PROMISING — MORE DATA"
        )

        status_level = "warning"

        status_icon = "🟡"

        recommendation = (
            "The normalized result is positive, "
            "but the number of matched "
            "observations is still limited. "
            "Collect more controlled observations "
            "before treating the saving as proven."
        )


    else:

        status = (
            "POSITIVE — VALIDATE ECONOMICS"
        )

        status_level = "positive"

        status_icon = "🟢"

        recommendation = (
            "The normalized result is positive "
            "and the matched sample is larger. "
            "Confirm statistical robustness and "
            "net financial benefit before making "
            "the additive a permanent operating "
            "practice."
        )


    # =====================================================
    # OPERATING CONDITION SUMMARY
    # =====================================================

    operating_dosing = operating[
        operating["total_additive"] > 0
    ].copy()


    operating_no_dosing = operating[
        operating["total_additive"] <= 0
    ].copy()


    clean_dosing_sfoc = _safe_mean(
        operating_dosing.get(
            "avg_sfoc"
        )
    )

    clean_no_dosing_sfoc = _safe_mean(
        operating_no_dosing.get(
            "avg_sfoc"
        )
    )


    clean_dosing_power = _safe_mean(
        operating_dosing.get(
            "avg_power"
        )
    )

    clean_no_dosing_power = _safe_mean(
        operating_no_dosing.get(
            "avg_power"
        )
    )


    clean_dosing_speed = _safe_mean(
        operating_dosing.get(
            "avg_speed"
        )
    )

    clean_no_dosing_speed = _safe_mean(
        operating_no_dosing.get(
            "avg_speed"
        )
    )


    # =====================================================
    # FUEL CONSUMPTION
    # =====================================================

    average_daily_fuel = _safe_mean(
        operating.get(
            "fuel_used_kg"
        )
    )


    # =====================================================
    # DOSING DAYS / OBSERVATION DAYS
    # =====================================================

    dosing_days = int(
        (
            daily["total_additive"] > 0
        ).sum()
    ) if not daily.empty else 0


    total_additive = _num(
        (
            daily["total_additive"].sum()
            if not daily.empty
            else 0
        ),
        0.0,
    ) or 0.0


    average_daily_additive = (

        total_additive
        / dosing_days

        if dosing_days
        else None

    )


    observation_start = (

        _fmt_date(
            daily["date"].min()
        )

        if not daily.empty
        else ""

    )


    observation_end = (

        _fmt_date(
            daily["date"].max()
        )

        if not daily.empty
        else ""

    )


    observation_days = len(
        daily
    )


    # =====================================================
    # OBSERVED DOSING FREQUENCY
    # =====================================================

    dosing_fraction = (

        dosing_days
        / observation_days

        if observation_days
        else 0.0

    )


    # =====================================================
    # FINANCIAL SCENARIO
    # =====================================================

    fuel_price = max(
        _num(
            fuel_price,
            0.0,
        )
        or 0.0,
        0.0,
    )


    additive_price = max(
        _num(
            additive_price,
            0.0,
        )
        or 0.0,
        0.0,
    )


    # Only use positive normalized effect
    # for potential savings.
    #
    # If normalized effect is negative,
    # potential fuel saving is zero.

    potential_effect = max(
        normalized_improvement or 0.0,
        0.0,
    )


    fuel_saving_fraction = (
        potential_effect / 100.0
    )


    # -----------------------------------------------------
    # TRIAL FINANCIALS
    # -----------------------------------------------------

    trial_fuel_saved_kg = None
    trial_fuel_saved_t = None
    trial_fuel_saving_eur = None
    trial_additive_cost_eur = None
    trial_net_eur = None
    trial_roi = None


    if (
        average_daily_fuel is not None
        and dosing_days
    ):

        trial_fuel_saved_kg = (
            average_daily_fuel
            * fuel_saving_fraction
            * dosing_days
        )

        trial_fuel_saved_t = (
            trial_fuel_saved_kg
            / 1000.0
        )


    if (
        trial_fuel_saved_t is not None
        and fuel_price > 0
    ):

        trial_fuel_saving_eur = (
            trial_fuel_saved_t
            * fuel_price
        )


    if additive_price > 0:

        trial_additive_cost_eur = (
            total_additive
            * additive_price
        )


    if (
        trial_fuel_saving_eur is not None
        and trial_additive_cost_eur is not None
    ):

        trial_net_eur = (
            trial_fuel_saving_eur
            - trial_additive_cost_eur
        )


        if trial_additive_cost_eur > 0:

            trial_roi = (
                trial_net_eur
                / trial_additive_cost_eur
                * 100.0
            )


    # =====================================================
    # ANNUALIZED FINANCIAL SCENARIO
    # =====================================================

    #
    # IMPORTANT CORRECTION
    #
    # The previous version calculated:
    #
    #   average_daily_fuel
    #   × saving %
    #   × 365 days
    #
    # That implicitly assumed the additive was being used
    # every day.
    #
    # That is NOT appropriate for this trial.
    #
    # Instead:
    #
    #   observed dosing fraction
    #       =
    #       dosing days / observation days
    #
    # Then:
    #
    #   annual dosing days
    #       =
    #       observed dosing fraction × 365
    #
    # Both potential fuel savings AND additive cost are
    # annualized using those same observed dosing days.
    #

    annual_dosing_days = (
        dosing_fraction
        * 365.0
    )


    annual_fuel_saved_t = None
    annual_fuel_saving_eur = None
    annual_additive_cost_eur = None
    annual_net_eur = None
    annual_roi = None


    # -----------------------------------------------------
    # Annual potential fuel saving
    # -----------------------------------------------------

    if (
        average_daily_fuel is not None
        and annual_dosing_days > 0
    ):

        annual_fuel_saved_t = (
            average_daily_fuel
            * fuel_saving_fraction
            * annual_dosing_days
            / 1000.0
        )


    # -----------------------------------------------------
    # Annual potential fuel value
    # -----------------------------------------------------

    if (
        annual_fuel_saved_t is not None
        and fuel_price > 0
    ):

        annual_fuel_saving_eur = (
            annual_fuel_saved_t
            * fuel_price
        )


    # -----------------------------------------------------
    # Annual additive cost
    # -----------------------------------------------------

    if (
        average_daily_additive is not None
        and annual_dosing_days > 0
        and additive_price > 0
    ):

        annual_additive_cost_eur = (
            average_daily_additive
            * annual_dosing_days
            * additive_price
        )


    # -----------------------------------------------------
    # Annual potential net effect
    # -----------------------------------------------------

    if (
        annual_fuel_saving_eur is not None
        and annual_additive_cost_eur is not None
    ):

        annual_net_eur = (
            annual_fuel_saving_eur
            - annual_additive_cost_eur
        )


        if annual_additive_cost_eur > 0:

            annual_roi = (
                annual_net_eur
                / annual_additive_cost_eur
                * 100.0
            )


    # =====================================================
    # DAILY CHART DATA
    # =====================================================

    daily_chart = []


    for _, row in daily.iterrows():

        date_value = row.get(
            "date"
        )

        sfoc = _num(
            row.get(
                "avg_sfoc"
            )
        )


        if (
            date_value is None
            or sfoc is None
        ):

            continue


        dosing = (
            _num(
                row.get(
                    "total_additive"
                ),
                0,
            )
            > 0
        )


        daily_chart.append(
            {
                "date":
                    _fmt_date(
                        date_value
                    ),

                "sfoc":
                    _round(
                        sfoc,
                        2,
                    ),

                "power":
                    _round(
                        row.get(
                            "avg_power"
                        ),
                        0,
                    ),

                "speed":
                    _round(
                        row.get(
                            "avg_speed"
                        ),
                        2,
                    ),

                "dosing":
                    (
                        "Dosing"
                        if dosing
                        else "No Dosing"
                    ),
            }
        )


    # =====================================================
    # DOSING TIMELINE
    # =====================================================

    timeline = []


    if not daily.empty:

        # -------------------------------------------------
        # Dosing days
        # -------------------------------------------------

        dosing_rows = daily[
            daily["total_additive"] > 0
        ]


        for _, row in dosing_rows.iterrows():

            timeline.append(
                {
                    "date":
                        _fmt_date(
                            row.get(
                                "date"
                            )
                        ),

                    "status":
                        "Dosing",

                    "additive":
                        _round(
                            row.get(
                                "total_additive"
                            ),
                            2,
                        ),

                    "remarks":
                        str(
                            row.get(
                                "remarks"
                            )
                            or ""
                        ),
                }
            )


        # -------------------------------------------------
        # No-dosing days with remarks
        # -------------------------------------------------

        if "remarks" in daily.columns:

            remarks_series = (
                daily["remarks"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            no_dose_rows = daily[
                (
                    daily["total_additive"]
                    <= 0
                )
                & remarks_series.ne("")
            ]

        else:

            no_dose_rows = (
                daily.iloc[0:0]
            )


        for _, row in no_dose_rows.iterrows():

            timeline.append(
                {
                    "date":
                        _fmt_date(
                            row.get(
                                "date"
                            )
                        ),

                    "status":
                        "No Dosing",

                    "additive":
                        0.0,

                    "remarks":
                        str(
                            row.get(
                                "remarks"
                            )
                            or ""
                        ),
                }
            )


    # -----------------------------------------------------
    # Chronological order
    # -----------------------------------------------------

    timeline.sort(
        key=lambda x:
            pd.to_datetime(
                x["date"],
                errors="coerce",
            )
    )


    # =====================================================
    # COMPARISON CHART
    # =====================================================

    comparison_chart = [

        {
            "label":
                "No dosing",

            "sfoc":
                _round(
                    raw_no_dosing_sfoc,
                    2,
                ),
        },

        {
            "label":
                "Dosing",

            "sfoc":
                _round(
                    raw_dosing_sfoc,
                    2,
                ),
        },

        {
            "label":
                "Matched baseline",

            "sfoc":
                _round(
                    normalized_baseline_sfoc,
                    2,
                ),
        },

        {
            "label":
                "Dosing — normalized",

            "sfoc":
                _round(
                    normalized_dosing_sfoc,
                    2,
                ),
        },

    ]


    comparison_chart = [
        item
        for item in comparison_chart
        if item["sfoc"] is not None
    ]


    # =====================================================
    # FINAL REPORT
    # =====================================================

    return {

        # -------------------------------------------------
        # MANAGEMENT STATUS
        # -------------------------------------------------

        "status":
            status,

        "status_level":
            status_level,

        "status_icon":
            status_icon,

        "recommendation":
            recommendation,


        # -------------------------------------------------
        # RAW
        # -------------------------------------------------

        "raw": {

            "dosing_sfoc":
                _round(
                    raw_dosing_sfoc,
                    2,
                ),

            "no_dosing_sfoc":
                _round(
                    raw_no_dosing_sfoc,
                    2,
                ),

            "improvement":
                _round(
                    raw_improvement,
                    2,
                ),

            "dosing_fuel":
                _round(
                    raw_dosing_fuel,
                    0,
                ),

            "no_dosing_fuel":
                _round(
                    raw_no_dosing_fuel,
                    0,
                ),
        },


        # -------------------------------------------------
        # NORMALIZED
        # -------------------------------------------------

        "normalized": {

            "dosing_sfoc":
                _round(
                    normalized_dosing_sfoc,
                    2,
                ),

            "baseline_sfoc":
                _round(
                    normalized_baseline_sfoc,
                    2,
                ),

            "improvement":
                _round(
                    normalized_improvement,
                    2,
                ),

            "matched":
                matched,

            "rejected":
                rejected,

            "match_rate":
                _round(
                    match_rate,
                    1,
                ),

            "pair_mean":
                _round(
                    pair_mean,
                    2,
                ),

            "pair_median":
                _round(
                    pair_median,
                    2,
                ),

            "pair_std":
                _round(
                    pair_std,
                    2,
                ),

            "ci_low":
                _round(
                    ci_low,
                    2,
                ),

            "ci_high":
                _round(
                    ci_high,
                    2,
                ),

            "quality":
                str(
                    normalized.get(
                        "overall_quality"
                    )
                    or "Unknown"
                ),

            "mean_pair_difference":
                _round(
                    normalized.get(
                        "mean_pair_difference"
                    ),
                    2,
                ),

            "median_pair_difference":
                _round(
                    normalized.get(
                        "median_pair_difference"
                    ),
                    2,
                ),
        },


        # -------------------------------------------------
        # OPERATING CONDITIONS
        # -------------------------------------------------

        "operating": {

            "dosing_sfoc":
                _round(
                    clean_dosing_sfoc,
                    2,
                ),

            "no_dosing_sfoc":
                _round(
                    clean_no_dosing_sfoc,
                    2,
                ),

            "dosing_power":
                _round(
                    clean_dosing_power,
                    0,
                ),

            "no_dosing_power":
                _round(
                    clean_no_dosing_power,
                    0,
                ),

            "dosing_speed":
                _round(
                    clean_dosing_speed,
                    2,
                ),

            "no_dosing_speed":
                _round(
                    clean_no_dosing_speed,
                    2,
                ),

            "average_daily_fuel":
                _round(
                    average_daily_fuel,
                    0,
                ),

            "operating_days":
                len(operating),
        },


        # -------------------------------------------------
        # OBSERVATION
        # -------------------------------------------------

        "observation": {

            "start":
                observation_start,

            "end":
                observation_end,

            "days":
                observation_days,
        },


        # -------------------------------------------------
        # DOSING
        # -------------------------------------------------

        "dosing": {

            "days":
                dosing_days,

            "total_additive":
                _round(
                    total_additive,
                    1,
                ),

            "average_daily_additive":
                _round(
                    average_daily_additive,
                    2,
                ),
        },


        # -------------------------------------------------
        # FINANCIAL
        # -------------------------------------------------

        "financial": {

            "fuel_price":
                _round(
                    fuel_price,
                    2,
                ),

            "additive_price":
                _round(
                    additive_price,
                    2,
                ),


            # Trial
            "trial_fuel_saved_t":
                _round(
                    trial_fuel_saved_t,
                    3,
                ),

            "trial_fuel_saving_eur":
                _round(
                    trial_fuel_saving_eur,
                    2,
                ),

            "trial_additive_cost_eur":
                _round(
                    trial_additive_cost_eur,
                    2,
                ),

            "trial_net_eur":
                _round(
                    trial_net_eur,
                    2,
                ),

            "trial_roi":
                _round(
                    trial_roi,
                    1,
                ),


            # Annualized
            "annual_dosing_days":
                _round(
                    annual_dosing_days,
                    1,
                ),

            "annual_fuel_saved_t":
                _round(
                    annual_fuel_saved_t,
                    2,
                ),

            "annual_fuel_saving_eur":
                _round(
                    annual_fuel_saving_eur,
                    2,
                ),

            "annual_additive_cost_eur":
                _round(
                    annual_additive_cost_eur,
                    2,
                ),

            "annual_net_eur":
                _round(
                    annual_net_eur,
                    2,
                ),

            "annual_roi":
                _round(
                    annual_roi,
                    1,
                ),


            # Always make it clear these are scenarios.
            "is_estimate":
                True,
        },


        # -------------------------------------------------
        # DATA QUALITY
        # -------------------------------------------------

        "data_quality": {

            "total_days":
                int(
                    _num(
                        data_quality.get(
                            "total_days"
                        ),
                        len(daily),
                    )
                    or 0
                ),

            "days_with_sfoc":
                int(
                    _num(
                        data_quality.get(
                            "days_with_sfoc"
                        ),
                        0,
                    )
                    or 0
                ),

            "matched":
                matched,

            "rejected":
                rejected,

            "match_rate":
                _round(
                    match_rate,
                    1,
                ),

            "match_quality":
                str(
                    normalized.get(
                        "overall_quality"
                    )
                    or "Unknown"
                ),
        },


        # -------------------------------------------------
        # TABLE / CHART DATA
        # -------------------------------------------------

        "match_rows":
            match_rows,

        "daily_chart":
            daily_chart,

        "comparison_chart":
            comparison_chart,

        "timeline":
            timeline,

        "voyage_summary":
            analysis_result.get(
                "voyage_summary"
            )
            or [],
    }
import pandas as pd

from django.contrib import messages
from django.db import transaction
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .models import (
    ChemicalDosing,
    ChemicalImportHistory,
    ChemicalMeasurement,
)

from .services.analysis import (
    get_vessel_analysis,
    calculate_performance_summary,
)

from .services.performance_analysis import (
    get_performance_analysis,
)

from .services.measurement_importer import (
    import_measurements,
)

from .services.dosing_importer import (
    import_dosing_log,
)

def performance_analysis(request):

    vessel = normalise_vessel(
        request.GET.get(
            "vessel",
            "DANIEL N",
        )
    )

    result = get_vessel_analysis(
        vessel
    )

    if not result.get(
        "success",
        False,
    ):

        return render(
            request,
            "chemical_analysis/performance_analysis.html",
            {
                "vessel": vessel,
                "error": result.get(
                    "message",
                    "Unable to analyse vessel data.",
                ),
            },
        )

    daily_df = result.get(
        "daily"
    )

    performance_result = (
        get_performance_analysis(
            daily_df
        )
    )

    performance_summary = (
        performance_result.get(
            "performance_summary",
            {},
        )
    )

    daily_data = (
        performance_result.get(
            "daily_data",
            [],
        )
    )

    chart_data = (
        performance_result.get(
            "chart_data",
            {},
        )
    )

    return render(
        request,
        "chemical_analysis/performance_analysis.html",
        {
            "vessel": vessel,

            "performance_summary":
                performance_summary,

            "daily_data":
                daily_data,

            "chart_data":
                chart_data,
        },
    )
# =========================================================
# VALID VESSELS
# =========================================================

VALID_VESSELS = [
    "DANIEL N",
    "HELEN N",
]


# =========================================================
# HELPER — SAFE FLOAT
# =========================================================

def safe_float(value):

    try:

        if value is None:
            return None

        # Avoid pd.isna() on lists/dicts/arrays
        if isinstance(value, (list, tuple, dict)):
            return None

        if pd.isna(value):
            return None

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return None


# =========================================================
# HELPER — SAFE INT
# =========================================================

def safe_int(
    value,
    default=0,
):

    try:

        if value is None:
            return default

        if isinstance(value, (list, tuple, dict)):
            return default

        if pd.isna(value):
            return default

        return int(float(value))

    except (
        TypeError,
        ValueError,
    ):

        return default


# =========================================================
# HELPER — NORMALISE VESSEL
# =========================================================

def normalise_vessel(value):

    if value is None:
        return "DANIEL N"

    value = str(value).strip().upper()

    if value not in VALID_VESSELS:
        return "DANIEL N"

    return value


# =========================================================
# HELPER — CALCULATE RAW SFOC EFFECT
# =========================================================

def calculate_sfoc_effect(comparison):

    if not isinstance(comparison, dict):
        comparison = {}

    comparison = comparison.copy()

    dosing_sfoc = safe_float(
        comparison.get("dosing_sfoc")
    )

    non_dosing_sfoc = safe_float(
        comparison.get("non_dosing_sfoc")
    )

    if (
        dosing_sfoc is None
        or non_dosing_sfoc is None
        or non_dosing_sfoc <= 0
    ):

        comparison["sfoc_change"] = None
        comparison["sfoc_improvement"] = None

        return comparison

    sfoc_change = (
        (
            dosing_sfoc
            - non_dosing_sfoc
        )
        / non_dosing_sfoc
    ) * 100.0

    sfoc_improvement = -sfoc_change

    comparison["sfoc_change"] = round(
        sfoc_change,
        2,
    )

    comparison["sfoc_improvement"] = round(
        sfoc_improvement,
        2,
    )

    return comparison


# =========================================================
# HELPER — UNADJUSTED INTERPRETATION
# =========================================================

def get_unadjusted_interpretation(improvement):

    improvement = safe_float(improvement)

    if improvement is None:
        return "Insufficient data"

    if improvement >= 5:
        return "Potential improvement"

    if improvement > 0.5:
        return "Small improvement"

    if improvement <= -5:
        return "Potential deterioration"

    if improvement < -0.5:
        return "Small increase in SFOC"

    return "No meaningful difference"


# =========================================================
# HELPER — CHEMICAL CONCLUSION
# =========================================================

def get_chemical_conclusion(normalized_comparison):

    if not isinstance(normalized_comparison, dict):
        normalized_comparison = {}

    if not normalized_comparison:

        return {
            "status": "Insufficient data",
            "level": "neutral",
            "message": (
                "There is not enough "
                "operating-condition-matched "
                "data to evaluate the "
                "chemical effect."
            ),
            "recommendation": (
                "Continue collecting "
                "dosing and non-dosing "
                "performance data."
            ),
        }

    improvement = safe_float(
        normalized_comparison.get(
            "sfoc_improvement"
        )
    )

    matched_days = safe_int(
        normalized_comparison.get(
            "matched_days",
            normalized_comparison.get(
                "matched_observations",
                0,
            ),
        )
    )

    # =====================================================
    # INSUFFICIENT DATA
    # =====================================================

    if improvement is None:

        return {
            "status": "Insufficient data",
            "level": "neutral",
            "message": (
                "The dashboard could not "
                "calculate a reliable "
                "operating-condition-normalized "
                "SFOC effect."
            ),
            "recommendation": (
                "Continue collecting comparable "
                "dosing and non-dosing "
                "observations."
            ),
        }

    # =====================================================
    # POSITIVE
    # =====================================================

    if improvement > 0.5:

        if matched_days >= 30:

            return {
                "status": "Promising improvement",
                "level": "positive",
                "message": (
                    "The operating-condition-"
                    "normalized analysis shows "
                    f"{improvement:.1f}% lower SFOC "
                    f"during dosing across "
                    f"{matched_days} matched "
                    "observations."
                ),
                "recommendation": (
                    "The result is promising, "
                    "but it should not yet be "
                    "treated as confirmed chemical "
                    "fuel saving. Continue collecting "
                    "matched observations and "
                    "validate across different "
                    "voyages, speeds and engine loads."
                ),
            }

        return {
            "status": "Potential improvement",
            "level": "positive",
            "message": (
                "The normalized analysis "
                f"indicates {improvement:.1f}% "
                "lower SFOC during dosing."
            ),
            "recommendation": (
                "The result suggests a possible "
                "positive chemical effect, but "
                "more matched observations are "
                "needed before considering the "
                "improvement reliable."
            ),
        }

    # =====================================================
    # NEUTRAL
    # =====================================================

    if improvement >= -0.5:

        return {
            "status": "No clear effect",
            "level": "neutral",
            "message": (
                "The normalized analysis shows "
                f"only {improvement:.1f}% SFOC "
                "improvement. This is too small "
                "to indicate a clear chemical "
                "performance effect."
            ),
            "recommendation": (
                "Continue monitoring before "
                "concluding that the chemical "
                "has no effect."
            ),
        }

    # =====================================================
    # NEGATIVE
    # =====================================================

    return {
        "status": "Possible deterioration",
        "level": "negative",
        "message": (
            "The operating-condition-normalized "
            "analysis shows "
            f"{improvement:.1f}% SFOC "
            "deterioration during dosing."
        ),
        "recommendation": (
            "The current data does not indicate "
            "a positive chemical effect. More "
            "matched observations should be "
            "collected before making a final decision."
        ),
    }


# =========================================================
# HELPER — PREPARE DAILY DATA FOR TEMPLATE
# =========================================================

def prepare_daily_data(daily_df):

    if daily_df is None:
        return []

    if not isinstance(daily_df, pd.DataFrame):
        return []

    if daily_df.empty:
        return []

    df = daily_df.copy()

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    if "date" not in df.columns:
        return []

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    df = (
        df
        .dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    # -----------------------------------------------------
    # REMOVE FUTURE DATA
    # -----------------------------------------------------

    today = pd.Timestamp.today().normalize()

    df = df[
        df["date"] <= today
    ].copy()

    daily_data = []

    # -----------------------------------------------------
    # ROWS
    # -----------------------------------------------------

    for _, row in df.iterrows():

        date_value = row.get("date")

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

        additive = safe_float(
            row.get("total_additive")
        )

        remark = row.get(
            "remarks",
            "",
        )

        if remark is None:
            remark = ""

        else:

            try:

                if pd.isna(remark):
                    remark = ""

            except (TypeError, ValueError):
                pass

        # -------------------------------------------------
        # DOSING STATUS
        # -------------------------------------------------

        dosing_status = row.get(
            "dosing_status",
            "No Dosing",
        )

        if dosing_status is None:
            dosing_status = "No Dosing"

        else:

            try:

                if pd.isna(dosing_status):
                    dosing_status = "No Dosing"

            except (TypeError, ValueError):
                dosing_status = "No Dosing"

        dosing_status = str(
            dosing_status
        ).strip()

        dosing_lower = dosing_status.lower()

        if (
            dosing_lower in {
                "dosing",
                "yes",
                "true",
                "1",
                "active",
            }
            or (
                "dosing" in dosing_lower
                and "no dosing" not in dosing_lower
            )
        ):

            dosing_status = "Dosing"

        else:

            dosing_status = "No Dosing"

        # -------------------------------------------------
        # VOYAGE
        # -----------------------------------------------------

        voyage = row.get(
            "voyage",
            "UNKNOWN",
        )

        if voyage is None:
            voyage = "UNKNOWN"

        else:

            try:

                if pd.isna(voyage):
                    voyage = "UNKNOWN"

            except (TypeError, ValueError):
                pass

        voyage = str(voyage).strip()

        if not voyage:
            voyage = "UNKNOWN"

        # -------------------------------------------------
        # DATE FORMATTING
        # -----------------------------------------------------

        if pd.notna(date_value):

            date_display = date_value.strftime(
                "%d %b"
            )

            full_date = date_value.strftime(
                "%d %b %Y"
            )

        else:

            date_display = ""
            full_date = ""

        # -------------------------------------------------
        # RECORD
        # -----------------------------------------------------

        daily_data.append(
            {
                "date": date_display,

                "full_date": full_date,

                "sfoc": (
                    round(sfoc, 2)
                    if sfoc is not None
                    else None
                ),

                "fuel": (
                    round(fuel, 2)
                    if fuel is not None
                    else None
                ),

                "speed": (
                    round(speed, 2)
                    if speed is not None
                    else None
                ),

                "power": (
                    round(power, 2)
                    if power is not None
                    else None
                ),

                "additive": (
                    round(additive, 2)
                    if additive is not None
                    else 0
                ),

                "status": dosing_status,

                "dosing_status": dosing_status,

                "voyage": voyage,

                "remarks": str(remark),
            }
        )

    return daily_data


# =========================================================
# HELPER — PREPARE NORMALIZED MATCHES
# =========================================================

def prepare_normalized_comparison(
    normalized_comparison
):

    if not isinstance(
        normalized_comparison,
        dict,
    ):

        return {}

    if not normalized_comparison:
        return {}

    comparison = normalized_comparison.copy()

    # -----------------------------------------------------
    # FIELD COMPATIBILITY
    # -----------------------------------------------------

    if "matched_days" not in comparison:

        comparison["matched_days"] = comparison.get(
            "matched_observations",
            0,
        )

    if "matched_observations" not in comparison:

        comparison["matched_observations"] = comparison.get(
            "matched_days",
            0,
        )

    if "matched_baseline_sfoc" not in comparison:

        comparison["matched_baseline_sfoc"] = comparison.get(
            "matched_non_dosing_sfoc"
        )

    if "matched_non_dosing_sfoc" not in comparison:

        comparison["matched_non_dosing_sfoc"] = comparison.get(
            "matched_baseline_sfoc"
        )

    # -----------------------------------------------------
    # MATCHES
    # -----------------------------------------------------

    matches = comparison.get(
        "matches",
        [],
    )

    if not isinstance(
        matches,
        list,
    ):

        matches = []

    prepared_matches = []

    for match in matches:

        if not isinstance(
            match,
            dict,
        ):

            continue

        match = match.copy()

        # -----------------------------------------------
        # NUMERIC VALUES
        # -----------------------------------------------

        numeric_fields = [

            "dosing_sfoc",

            "baseline_sfoc",

            "matched_non_dosing_sfoc",

            "sfoc_difference",

            "sfoc_improvement",

            "match_score",

            "power_difference",

            "speed_difference",

            "rpm_difference",

            "load_difference",

            "draft_difference",

            "date_difference",
        ]

        for field in numeric_fields:

            if field in match:

                value = safe_float(
                    match.get(field)
                )

                match[field] = (
                    round(value, 4)
                    if value is not None
                    else None
                )

        # -----------------------------------------------
        # DATES
        # -----------------------------------------------

        for field in [
            "dosing_date",
            "baseline_date",
        ]:

            if field not in match:
                continue

            value = match.get(field)

            if value is None:
                continue

            try:

                if pd.isna(value):
                    continue

            except (TypeError, ValueError):
                pass

            try:

                value = pd.to_datetime(
                    value
                )

                match[field] = value.strftime(
                    "%d %b %Y"
                )

            except (
                TypeError,
                ValueError,
            ):

                pass

        # -----------------------------------------------
        # VOYAGE
        # -----------------------------------------------

        voyage = match.get(
            "voyage",
            "UNKNOWN",
        )

        if voyage is None:
            voyage = "UNKNOWN"

        else:

            try:

                if pd.isna(voyage):
                    voyage = "UNKNOWN"

            except (TypeError, ValueError):
                pass

        match["voyage"] = str(
            voyage
        ).strip()

        if not match["voyage"]:
            match["voyage"] = "UNKNOWN"

        # -----------------------------------------------
        # QUALITY
        # -----------------------------------------------

        match["match_quality"] = str(
            match.get(
                "match_quality",
                "Unknown",
            )
        )

        prepared_matches.append(
            match
        )

    comparison["matches"] = prepared_matches

    comparison["matched_rows"] = prepared_matches

    # -----------------------------------------------------
    # ROUND SUMMARY VALUES
    # -----------------------------------------------------

    for field in [

        "dosing_sfoc",

        "matched_baseline_sfoc",

        "matched_non_dosing_sfoc",

        "mean_pair_difference",

        "median_pair_difference",

        "sfoc_improvement",

        "median_match_score",
    ]:

        if field in comparison:

            value = safe_float(
                comparison.get(field)
            )

            comparison[field] = (
                round(value, 4)
                if value is not None
                else None
            )

    comparison["matched_days"] = safe_int(
        comparison.get(
            "matched_days",
            comparison.get(
                "matched_observations",
                0,
            ),
        )
    )

    comparison["matched_observations"] = safe_int(
        comparison.get(
            "matched_observations",
            comparison.get(
                "matched_days",
                0,
            ),
        )
    )

    comparison["rejected_observations"] = safe_int(
        comparison.get(
            "rejected_observations",
            0,
        )
    )

    return comparison


# =========================================================
# CHEMICAL DASHBOARD
# =========================================================

def chemical_dashboard(request):

    # =====================================================
    # SELECT VESSEL
    # =====================================================

    vessel = normalise_vessel(
        request.GET.get(
            "vessel",
            "DANIEL N",
        )
    )

    # =====================================================
    # RUN ANALYSIS
    # =====================================================

    result = get_vessel_analysis(vessel)

    if not isinstance(result, dict):
        result = {
            "success": False,
            "message": "Analysis returned an invalid result.",
        }

    if not result.get("success", False):

        return render(
            request,
            "chemical_analysis/dashboard.html",
            {
                "error": result.get(
                    "message",
                    "Unable to analyse vessel data.",
                ),
                "vessel": vessel,
            },
        )

    # =====================================================
    # DAILY DATA
    # =====================================================

    daily_df = result.get("daily")

    daily_data = prepare_daily_data(
        daily_df
    )

    # =====================================================
    # PERFORMANCE SUMMARY
    # =====================================================

    try:

        performance_summary = (
            calculate_performance_summary(
                daily_df
            )
        )

    except Exception as exc:

        print(
            "Performance summary error:",
            exc,
        )

        performance_summary = {}

    if not isinstance(
        performance_summary,
        dict,
    ):

        performance_summary = {}

    # =====================================================
    # RAW COMPARISON
    # =====================================================

    comparison = result.get(
        "comparison",
        {},
    )

    if not isinstance(
        comparison,
        dict,
    ):

        comparison = {}

    comparison = calculate_sfoc_effect(
        comparison
    )

    comparison["sfoc_interpretation"] = (
        get_unadjusted_interpretation(
            comparison.get(
                "sfoc_improvement"
            )
        )
    )

    # =====================================================
    # NORMALIZED COMPARISON
    # =====================================================

    normalized_comparison = result.get(
        "normalized_comparison",
        {},
    )

    if not isinstance(
        normalized_comparison,
        dict,
    ):

        normalized_comparison = {}

    normalized_comparison = (
        prepare_normalized_comparison(
            normalized_comparison
        )
    )

    # =====================================================
    # CHEMICAL CONCLUSION
    # =====================================================

    chemical_conclusion = (
        get_chemical_conclusion(
            normalized_comparison
        )
    )

    # =====================================================
    # BEFORE / AFTER
    # =====================================================

    before_after = result.get(
        "before_after",
        {},
    )

    if not isinstance(
        before_after,
        dict,
    ):

        before_after = {}

    before_after = before_after.copy()

    dosing_analysis = result.get(
        "dosing_analysis",
        {},
    )

    if not isinstance(
        dosing_analysis,
        dict,
    ):

        dosing_analysis = {}

    data_quality = result.get(
        "data_quality",
        {},
    )

    if not isinstance(
        data_quality,
        dict,
    ):

        data_quality = {}

    # -----------------------------------------------------
    # NORMALISE BEFORE / AFTER NUMBERS
    # -----------------------------------------------------

    for field in [

        "before_sfoc",

        "after_sfoc",

        "difference",

        "improvement",

        "before_fuel_consumption",

        "after_fuel_consumption",

        "fuel_improvement",

        "before_power",

        "after_power",

        "before_speed",

        "after_speed",

        "before_rpm",

        "after_rpm",

        "annual_baseline_fuel_kg",

        "annual_fuel_impact_kg",

        "annual_fuel_impact_tonnes",

        "annual_cost_impact",
    ]:

        if field in before_after:

            value = safe_float(
                before_after.get(field)
            )

            before_after[field] = (
                round(value, 4)
                if value is not None
                else None
            )

    # =====================================================
    # KPI VALUES
    # =====================================================

    kpis = result.get(
        "kpis",
        {},
    )

    if not isinstance(
        kpis,
        dict,
    ):

        kpis = {}

    kpis = kpis.copy()

    # -----------------------------------------------------
    # FORMAT KPI NUMBERS
    # -----------------------------------------------------

    for field in [

        "total_fuel_kg",

        "average_speed",

        "average_power",

        "average_sfoc",

        "total_additive",
    ]:

        if field in kpis:

            value = safe_float(
                kpis.get(field)
            )

            kpis[field] = (
                round(value, 2)
                if value is not None
                else None
            )

    kpis["total_measurements"] = safe_int(
        kpis.get(
            "total_measurements",
            0,
        )
    )

    kpis["dosing_days"] = safe_int(
        kpis.get(
            "dosing_days",
            0,
        )
    )

    # =====================================================
    # DATE FORMATTING FOR KPI
    # =====================================================

    for field in [

        "start_date",

        "end_date",

        "first_dosing_date",
    ]:

        if field not in kpis:
            continue

        value = kpis.get(field)

        if value is None:
            continue

        try:

            if pd.isna(value):
                continue

        except (TypeError, ValueError):
            pass

        try:

            kpis[field] = pd.to_datetime(
                value
            ).strftime(
                "%d %b %Y"
            )

        except (
            TypeError,
            ValueError,
        ):

            pass

    # =====================================================
    # NORMALIZED SUMMARY
    # =====================================================

    normalized_improvement = safe_float(
        normalized_comparison.get(
            "sfoc_improvement"
        )
    )

    normalized_comparison[
        "sfoc_improvement_display"
    ] = (
        round(
            normalized_improvement,
            2,
        )
        if normalized_improvement is not None
        else None
    )

    # =====================================================
    # DEBUG
    # =====================================================

    print()
    print("=" * 70)
    print("CHEMICAL DASHBOARD")
    print("=" * 70)

    print("VESSEL:", vessel)

    print(
        "DAILY ROWS:",
        len(daily_data),
    )

    print(
        "RAW DOSING SFOC:",
        comparison.get("dosing_sfoc"),
    )

    print(
        "RAW NON-DOSING SFOC:",
        comparison.get("non_dosing_sfoc"),
    )

    print(
        "NORMALIZED DOSING SFOC:",
        normalized_comparison.get("dosing_sfoc"),
    )

    print(
        "NORMALIZED BASELINE SFOC:",
        normalized_comparison.get(
            "matched_baseline_sfoc"
        ),
    )

    print(
        "NORMALIZED IMPROVEMENT:",
        normalized_comparison.get(
            "sfoc_improvement"
        ),
    )

    print(
        "MATCHED OBSERVATIONS:",
        normalized_comparison.get(
            "matched_observations"
        ),
    )

    print(
        "MATCH QUALITY:",
        normalized_comparison.get(
            "overall_quality"
        ),
    )

    print("=" * 70)

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "chemical_analysis/dashboard.html",
        {
            "vessel": vessel,

            "kpis": kpis,

            "comparison": comparison,

            "normalized_comparison":
                normalized_comparison,

            "chemical_conclusion":
                chemical_conclusion,

            "before_after":
                before_after,

            "dosing_analysis":
                dosing_analysis,

            "data_quality":
                data_quality,

            "performance_summary":
                performance_summary,

            "daily_data":
                daily_data,
        },
    )


# =========================================================
# PERFORMANCE ANALYSIS PAGE
# =========================================================

def performance_analysis(request):

    # =====================================================
    # SELECT VESSEL
    # =====================================================

    vessel = normalise_vessel(
        request.GET.get(
            "vessel",
            "DANIEL N",
        )
    )

    # =====================================================
    # RUN EXISTING ANALYSIS
    # =====================================================

    result = get_vessel_analysis(vessel)

    if not isinstance(result, dict):
        result = {
            "success": False,
            "message": "Analysis returned an invalid result.",
        }

    if not result.get("success", False):

        return render(
            request,
            "chemical_analysis/performance_analysis.html",
            {
                "vessel": vessel,

                "error": result.get(
                    "message",
                    "Unable to analyse vessel data.",
                ),
            },
        )

    # =====================================================
    # DAILY DATA
    # =====================================================

    daily_df = result.get("daily")

    # =====================================================
    # COMPLETE PERFORMANCE ANALYSIS
    # =====================================================

    try:

        performance_result = (
            get_performance_analysis(
                daily_df
            )
        )

    except Exception as exc:

        print(
            "Performance analysis error:",
            exc,
        )

        performance_result = {}

    if not isinstance(
        performance_result,
        dict,
    ):

        performance_result = {}

    performance_summary = (
        performance_result.get(
            "performance_summary",
            {},
        )
    )

    if not isinstance(
        performance_summary,
        dict,
    ):

        performance_summary = {}

    daily_data = (
        performance_result.get(
            "daily_data",
            [],
        )
    )

    if not isinstance(
        daily_data,
        list,
    ):

        daily_data = []

    chart_data = (
        performance_result.get(
            "chart_data",
            {},
        )
    )

    # =====================================================
    # ROUND SUMMARY VALUES
    # =====================================================

    for field in [

        "average_sfoc",

        "average_fuel_consumption",

        "average_speed",

        "average_power",

        "normal_load_average_sfoc",

        "min_sfoc",

        "max_sfoc",
    ]:

        value = safe_float(
            performance_summary.get(field)
        )

        performance_summary[field] = (
            round(value, 2)
            if value is not None
            else None
        )

    # =====================================================
    # INTEGER SUMMARY VALUES
    # =====================================================

    for field in [

        "total_days",

        "usable_days",

        "low_load_days",
    ]:

        performance_summary[field] = safe_int(
            performance_summary.get(
                field,
                0,
            )
        )

    # =====================================================
    # CHART DATA SAFETY
    # =====================================================

    if not isinstance(
        chart_data,
        dict,
    ):

        chart_data = {}

    chart_data.setdefault(
        "dates",
        [],
    )

    chart_data.setdefault(
        "sfoc",
        [],
    )

    chart_data.setdefault(
        "fuel",
        [],
    )

    chart_data.setdefault(
        "speed",
        [],
    )

    chart_data.setdefault(
        "power",
        [],
    )

    # =====================================================
    # DEBUG
    # =====================================================

    print()
    print("=" * 70)
    print("PERFORMANCE ANALYSIS")
    print("=" * 70)

    print(
        "VESSEL:",
        vessel,
    )

    print(
        "TOTAL DAYS:",
        performance_summary.get(
            "total_days"
        ),
    )

    print(
        "USABLE DAYS:",
        performance_summary.get(
            "usable_days"
        ),
    )

    print(
        "LOW LOAD DAYS:",
        performance_summary.get(
            "low_load_days"
        ),
    )

    print(
        "AVERAGE SFOC:",
        performance_summary.get(
            "average_sfoc"
        ),
    )

    print(
        "AVERAGE FUEL:",
        performance_summary.get(
            "average_fuel_consumption"
        ),
    )

    print(
        "AVERAGE SPEED:",
        performance_summary.get(
            "average_speed"
        ),
    )

    print(
        "AVERAGE POWER:",
        performance_summary.get(
            "average_power"
        ),
    )

    print(
        "NORMAL LOAD SFOC:",
        performance_summary.get(
            "normal_load_average_sfoc"
        ),
    )

    print(
        "BEST SFOC:",
        performance_summary.get(
            "min_sfoc"
        ),
    )

    print(
        "BEST SFOC DATE:",
        performance_summary.get(
            "best_sfoc_date"
        ),
    )

    print(
        "WORST SFOC:",
        performance_summary.get(
            "max_sfoc"
        ),
    )

    print(
        "WORST SFOC DATE:",
        performance_summary.get(
            "worst_sfoc_date"
        ),
    )

    print(
        "CHART ROWS:",
        len(
            chart_data.get(
                "dates",
                [],
            )
        ),
    )

    print("=" * 70)

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "chemical_analysis/performance_analysis.html",
        {
            "vessel": vessel,

            "performance_summary":
                performance_summary,

            "daily_data":
                daily_data,

            "chart_data":
                chart_data,
        },
    )


# =========================================================
# UPLOAD DATA
# =========================================================

def upload_data(request):

    # =====================================================
    # POST
    # =====================================================

    if request.method == "POST":

        vessel = (
            request.POST.get(
                "vessel",
                "",
            )
            .strip()
            .upper()
        )

        measurement_file = request.FILES.get(
            "measurement_file"
        )

        dosing_file = request.FILES.get(
            "dosing_file"
        )

        # =================================================
        # VESSEL VALIDATION
        # =================================================

        if not vessel:

            messages.error(
                request,
                "Please select a vessel.",
            )

            return redirect(
                "chemical_analysis:upload"
            )

        if vessel not in VALID_VESSELS:

            messages.error(
                request,
                "Invalid vessel selected.",
            )

            return redirect(
                "chemical_analysis:upload"
            )

        # =================================================
        # FILE VALIDATION
        # =================================================

        if (
            not measurement_file
            and not dosing_file
        ):

            messages.error(
                request,
                "Please upload at least one file.",
            )

            return redirect(
                "chemical_analysis:upload"
            )

        # =================================================
        # MEASUREMENT IMPORT
        # =================================================

        if measurement_file:

            import_history = (
                ChemicalImportHistory.objects.create(
                    vessel=vessel,
                    import_type="Measurement",
                    filename=measurement_file.name,
                    status="Failed",
                    message="Import started.",
                )
            )

            # Keep vessel information available to importer
            measurement_file.vessel = vessel

            try:

                result = import_measurements(
                    measurement_file,
                    import_history=import_history,
                )

            except Exception as exc:

                print(
                    "Measurement import exception:",
                    exc,
                )

                result = {
                    "success": False,
                    "message": (
                        "Measurement import failed: "
                        f"{exc}"
                    ),
                }

            if not isinstance(
                result,
                dict,
            ):

                result = {
                    "success": False,
                    "message": (
                        "Measurement importer "
                        "returned an invalid result."
                    ),
                }

            if result.get(
                "success",
                False,
            ):

                new_rows = safe_int(
                    result.get(
                        "new_rows",
                        0,
                    )
                )

                skipped_rows = safe_int(
                    result.get(
                        "skipped_rows",
                        0,
                    )
                )

                sheets = result.get(
                    "sheets",
                    [],
                )

                if not isinstance(
                    sheets,
                    (list, tuple),
                ):

                    sheets = []

                import_history.new_rows = (
                    new_rows
                )

                import_history.skipped_rows = (
                    skipped_rows
                )

                import_history.status = (
                    "Success"
                )

                import_history.message = (
                    "Measurement data imported successfully."
                    +
                    (
                        " Sheets read: "
                        +
                        ", ".join(
                            map(
                                str,
                                sheets,
                            )
                        )
                        if sheets
                        else ""
                    )
                )

                import_history.save()

                messages.success(
                    request,
                    (
                        "Measurement data imported "
                        "successfully. "
                        f"{new_rows} new rows added, "
                        f"{skipped_rows} duplicates skipped."
                        +
                        (
                            " Sheets read: "
                            +
                            ", ".join(
                                map(
                                    str,
                                    sheets,
                                )
                            )
                            if sheets
                            else ""
                        )
                    ),
                )

            else:

                error_message = result.get(
                    "message",
                    "Measurement import failed.",
                )

                import_history.status = (
                    "Failed"
                )

                import_history.message = str(
                    error_message
                )

                import_history.new_rows = 0

                import_history.skipped_rows = 0

                import_history.save()

                messages.error(
                    request,
                    error_message,
                )

        # =================================================
        # DOSING IMPORT
        # =================================================

        if dosing_file:

            import_history = (
                ChemicalImportHistory.objects.create(
                    vessel=vessel,
                    import_type="Dosing Log",
                    filename=dosing_file.name,
                    status="Failed",
                    message="Import started.",
                )
            )

            try:

                result = import_dosing_log(
                    dosing_file,
                    vessel,
                    import_history=import_history,
                )

            except Exception as exc:

                print(
                    "Dosing import exception:",
                    exc,
                )

                result = {
                    "success": False,
                    "message": (
                        "Dosing import failed: "
                        f"{exc}"
                    ),
                }

            if not isinstance(
                result,
                dict,
            ):

                result = {
                    "success": False,
                    "message": (
                        "Dosing importer "
                        "returned an invalid result."
                    ),
                }

            if result.get(
                "success",
                False,
            ):

                new_rows = safe_int(
                    result.get(
                        "new_rows",
                        0,
                    )
                )

                updated_rows = safe_int(
                    result.get(
                        "updated_rows",
                        0,
                    )
                )

                import_history.new_rows = (
                    new_rows
                )

                import_history.skipped_rows = (
                    updated_rows
                )

                import_history.status = (
                    "Success"
                )

                import_history.message = (
                    "Dosing log processed successfully."
                )

                import_history.save()

                messages.success(
                    request,
                    (
                        "Dosing data processed "
                        "successfully. "
                        f"{new_rows} new dates added, "
                        f"{updated_rows} existing dates updated."
                    ),
                )

            else:

                error_message = result.get(
                    "message",
                    "Dosing log import failed.",
                )

                import_history.status = (
                    "Failed"
                )

                import_history.message = str(
                    error_message
                )

                import_history.new_rows = 0

                import_history.skipped_rows = 0

                import_history.save()

                messages.error(
                    request,
                    error_message,
                )

        # =================================================
        # RETURN
        # =================================================

        return redirect(
            f"/chemical_analysis/?vessel={vessel}"
        )

    # =====================================================
    # GET
    # =====================================================

    return render(
        request,
        "chemical_analysis/upload.html",
    )


# =========================================================
# IMPORT HISTORY
# =========================================================

def import_history(request):

    vessel = (
        request.GET.get(
            "vessel",
            "",
        )
        .strip()
        .upper()
    )

    history = (
        ChemicalImportHistory.objects.all()
    )

    if vessel in VALID_VESSELS:

        history = history.filter(
            vessel=vessel
        )

    history = history.order_by(
        "-created_at"
    )

    return render(
        request,
        "chemical_analysis/history.html",
        {
            "history": history,

            "selected_vessel": vessel,
        },
    )


# =========================================================
# DELETE IMPORT
# =========================================================

def delete_import(
    request,
    import_id,
):

    if request.method != "POST":

        messages.error(
            request,
            "Invalid delete request.",
        )

        return redirect(
            "chemical_analysis:history"
        )

    import_record = get_object_or_404(
        ChemicalImportHistory,
        id=import_id,
    )

    vessel = import_record.vessel

    filename = import_record.filename

    # =====================================================
    # DELETE RELATED DATA
    # =====================================================

    with transaction.atomic():

        measurement_count = (
            ChemicalMeasurement.objects
            .filter(
                import_history=import_record
            )
            .delete()[0]
        )

        dosing_count = (
            ChemicalDosing.objects
            .filter(
                import_history=import_record
            )
            .delete()[0]
        )

        import_record.delete()

    # =====================================================
    # MESSAGE
    # =====================================================

    messages.success(
        request,
        (
            f"Import '{filename}' deleted successfully. "
            f"{measurement_count} measurement records "
            f"and "
            f"{dosing_count} dosing records removed."
        ),
    )

    # =====================================================
    # RETURN
    # =====================================================

    return redirect(
        f"/chemical_analysis/history/"
        f"?vessel={vessel}"
    )
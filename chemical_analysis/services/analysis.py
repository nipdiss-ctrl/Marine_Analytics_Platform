import re

import numpy as np
import pandas as pd

from ..models import (
    ChemicalMeasurement,
    ChemicalDosing,
)

from .performance_analysis import (
    calculate_performance_summary,
)

from .dosing_analysis import (
    calculate_dosing_analysis,
)

from .data_quality import (
    calculate_data_quality,
)

# =========================================================
# HELPERS
# =========================================================

def _clean_text(value, default="UNKNOWN"):
    """Safely clean a text value."""

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    value = str(value).strip()

    if not value:
        return default

    if value.lower() in {
        "nan",
        "none",
        "null",
        "unknown",
        "nat",
    }:
        return default

    return value


def _normalise_voyage(value):
    """
    Normalise voyage / Excel sheet name.

    Examples:

        Voyage 1  -> VOYAGE 1
        voyage 1  -> VOYAGE 1
        V01       -> V01
        01        -> 01

    The actual voyage identity is preserved.
    """

    value = _clean_text(value)

    if value == "UNKNOWN":
        return "UNKNOWN"

    value = str(value).strip()

    # Remove repeated whitespace
    value = re.sub(r"\s+", " ", value)

    return value.upper()


def _voyage_match_key(value):
    """
    Create a comparison key for voyage names.

    This is used ONLY for matching.

    Examples:

        Voyage 01 -> VOYAGE01
        voyage-01 -> VOYAGE01
        Voyage_01 -> VOYAGE01

    This helps when Excel sheet naming differs only
    by spaces, hyphens or underscores.
    """

    value = _normalise_voyage(value)

    if value == "UNKNOWN":
        return "UNKNOWN"

    value = re.sub(
        r"[\s_\-]+",
        "",
        value,
    )

    return value


def _get_model_field_names(model):
    """Return actual Django model field names."""

    try:
        return {
            field.name
            for field in model._meta.get_fields()
            if hasattr(field, "name")
        }
    except Exception:
        return set()


def _find_voyage_field(model):
    """Find the field containing voyage / Excel sheet information."""

    available = _get_model_field_names(model)

    candidates = [
        "voyage",
        "voyage_name",
        "sheet_name",
        "source_sheet",
        "excel_sheet",
        "sheet",
        "sheetname",
        "source_voyage",
    ]

    for candidate in candidates:
        if candidate in available:
            return candidate

    return None


def _get_dosing_records(vessel):
    """
    Load ChemicalDosing records and dynamically detect
    voyage/sheet field.
    """

    model_fields = _get_model_field_names(
        ChemicalDosing
    )

    voyage_field = _find_voyage_field(
        ChemicalDosing
    )

    wanted_fields = [
        "date",
        "morning_additive",
        "evening_additive",
        "total_additive",
        "total_fuel_qty",
        "chemical_rob",
        "remarks",
    ]

    valid_fields = [
        field
        for field in wanted_fields
        if field in model_fields
    ]

    if voyage_field and voyage_field not in valid_fields:
        valid_fields.append(voyage_field)

    queryset = (
        ChemicalDosing.objects
        .filter(vessel=vessel)
        .values(*valid_fields)
    )

    records = list(queryset)

    for record in records:

        if voyage_field:

            record["voyage"] = _normalise_voyage(
                record.get(voyage_field)
            )

        else:

            record["voyage"] = "UNKNOWN"

    print("\nCHEMICAL DOSING VOYAGE FIELD:")
    print(
        f"Detected database field: "
        f"{voyage_field}"
    )

    if voyage_field:

        unique_voyages = sorted(
            {
                _normalise_voyage(
                    record.get(voyage_field)
                )
                for record in records
            }
        )

        print(
            "Detected voyage / sheet values:"
        )

        for voyage in unique_voyages:
            print(f"  - {voyage}")

    else:

        print(
            "WARNING: No voyage/sheet-name field "
            "exists in ChemicalDosing."
        )

    return records


def _get_measurement_voyage_field():
    """Detect whether ChemicalMeasurement contains a voyage field."""

    return _find_voyage_field(
        ChemicalMeasurement
    )


def _normalise_dosing_bool(value):
    """Convert common dosing representations into boolean."""

    if isinstance(value, bool):
        return value

    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except Exception:
        pass

    text = str(value).strip().lower()

    return text in {
        "yes",
        "true",
        "1",
        "dosing",
        "active",
    }


def _safe_float(value):
    """Safely convert a value to float."""

    try:

        value = pd.to_numeric(
            value,
            errors="coerce",
        )

        if pd.isna(value):
            return np.nan

        return float(value)

    except Exception:

        return np.nan


# =========================================================
# NORMALIZED SFOC
# =========================================================

def calculate_normalized_sfoc(daily_df):
    """
    Voyage-aware operating-condition normalized SFOC matching.

    Matching priority:

        1. Same voyage
        2. Opposite dosing status
        3. Similar engine load
        4. Similar power
        5. Similar speed
        6. Similar RPM
        7. Similar draft
        8. Reasonable date distance

    A baseline observation can only be used once.

    If the dosing voyage is UNKNOWN, known baseline voyages
    may be searched.

    Voyage matching uses a normalised comparison key so that
    differences such as:

        Voyage 01
        voyage-01
        Voyage_01

    do not prevent matching.

    Rejected matches are retained for debugging.
    """

    print("\n" + "=" * 70)
    print(
        "NORMALIZED SFOC - "
        "VOYAGE AWARE MATCHING"
    )
    print("=" * 70)

    # =========================================================
    # EMPTY RESULT
    # =========================================================

    def empty_result(
        quality="Insufficient Data",
        rejected=0,
        rejected_matches=None,
    ):

        if rejected_matches is None:
            rejected_matches = []

        return {

            "overall_quality":
                quality,

            "overall_match_quality":
                quality,

            "matched_observations":
                0,

            "matched_days":
                0,

            "rejected_observations":
                rejected,

            "dosing_sfoc":
                np.nan,

            "matched_baseline_sfoc":
                np.nan,

            "matched_non_dosing_sfoc":
                np.nan,

            "mean_pair_difference":
                np.nan,

            "median_pair_difference":
                np.nan,

            "sfoc_improvement":
                np.nan,

            "matches":
                [],

            "matched_rows":
                [],

            "median_match_score":
                np.nan,
        }

    # =========================================================
    # INPUT
    # =========================================================

    if daily_df is None or daily_df.empty:
        return empty_result()

    df = daily_df.copy()

    # =========================================================
    # COLUMN ALIASES
    # =========================================================

    aliases = {

        "date_only": [
            "date_only",
            "date",
            "Date",
            "DATE",
            "timestamp_date",
        ],

        "SFOC": [
            "SFOC",
            "sfoc",
            "avg_sfoc",
            "SFOC g/kWh",
            "Flowmeter SFOC",
            "ME - Flowmeter SFOC",
        ],

        "Power": [
            "Power",
            "power",
            "avg_power",
            "Power kW",
            "ME - Power",
            "ME - Power ",
        ],

        "RPM": [
            "RPM",
            "rpm",
            "avg_rpm",
            "ME - RPM",
            "ME - RPM ",
        ],

        "Speed": [
            "Speed",
            "speed",
            "avg_speed",
            "Speed knots",
            "GPS Speed",
            "GPS Speed ",
        ],

        "Engine Load": [
            "Engine Load",
            "engine_load",
            "avg_fuel_load",
            "Engine Load %",
            "Fuel Load %",
            "Fuel Load",
            "MCR",
            "ME - MCR",
            "ME - MCR ",
        ],

        "voyage": [
            "voyage",
            "Voyage",
            "VOYAGE",
            "Voy",
            "voyage_name",
            "sheet_name",
            "source_sheet",
            "excel_sheet",
            "sheet",
        ],

        "dosing_status": [
            "dosing_status",
            "Dosing Status",
            "Chemical Status",
            "chemical_status",
        ],

        "Draft FWD": [
            "Draft FWD",
            "Draft FWD ",
            "Draft_FWD",
            "draft_fwd",
        ],

        "Draft AFT": [
            "Draft AFT",
            "Draft AFT ",
            "Draft_AFT",
            "draft_aft",
        ],

        "Prop1 Slip": [
            "Prop1 Slip",
            "Propeller Slip",
            "Prop1_Slip",
        ],

        "Beaufort Scale": [
            "Beaufort Scale",
            "Beaufort",
            "Beaufort Scale ",
        ],
    }

    existing_columns = list(
        df.columns
    )

    rename_map = {}

    for standard_name, possible_names in aliases.items():

        if standard_name in existing_columns:
            continue

        for possible_name in possible_names:

            if possible_name in existing_columns:

                rename_map[
                    possible_name
                ] = standard_name

                break

    if rename_map:
        df = df.rename(
            columns=rename_map
        )

    # =========================================================
    # DATE
    # =========================================================

    if "date_only" not in df.columns:

        if "Timestamp" in df.columns:

            df["date_only"] = (
                pd.to_datetime(
                    df["Timestamp"],
                    errors="coerce",
                    utc=True,
                )
                .dt.date
            )

        else:

            print(
                "NORMALIZED SFOC ERROR: "
                "No date column available."
            )

            return empty_result()

    else:

        df["date_only"] = (
            pd.to_datetime(
                df["date_only"],
                errors="coerce",
            )
            .dt.date
        )

    # =========================================================
    # NUMERIC
    # =========================================================

    numeric_columns = [

        "SFOC",
        "Power",
        "RPM",
        "Speed",
        "Engine Load",
        "Draft FWD",
        "Draft AFT",
        "Prop1 Slip",
        "Beaufort Scale",
    ]

    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    # =========================================================
    # VOYAGE
    # =========================================================

    if "voyage" not in df.columns:

        df["voyage"] = "UNKNOWN"

    df["voyage"] = (
        df["voyage"]
        .apply(_normalise_voyage)
    )

    # Create comparison key.
    df["voyage_match_key"] = (
        df["voyage"]
        .apply(_voyage_match_key)
    )

    # =========================================================
    # DOSING STATUS
    # =========================================================

    if "dosing_status" not in df.columns:

        if "dosing" in df.columns:

            df["dosing_status"] = (
                df["dosing"]
                .apply(
                    _normalise_dosing_bool
                )
                .map({
                    True: "Dosing",
                    False: "No Dosing",
                })
            )

        else:

            df["dosing_status"] = (
                "No Dosing"
            )

    df["dosing_status"] = (
        df["dosing_status"]
        .fillna("No Dosing")
        .astype(str)
        .str.strip()
    )

    dosing_text = (
        df["dosing_status"]
        .str.lower()
        .str.strip()
    )

    df["is_dosing"] = (

        dosing_text.isin([
            "dosing",
            "yes",
            "true",
            "1",
            "active",
        ])

        |

        (
            dosing_text.str.contains(
                "dosing",
                na=False,
            )

            &

            ~dosing_text.str.contains(
                "no dosing",
                na=False,
            )
        )
    )

    # =========================================================
    # REQUIRED
    # =========================================================

    required = [

        "date_only",
        "SFOC",
        "Power",
        "RPM",
        "Speed",
        "Engine Load",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        print(
            "NORMALIZED SFOC ERROR - "
            f"missing columns: {missing}"
        )

        print(
            "Available columns:",
            list(df.columns),
        )

        return empty_result()

    # =========================================================
    # REMOVE INVALID
    # =========================================================

    df = df.dropna(
        subset=required
    ).copy()

    df = df[
        (df["SFOC"] > 0)
        &
        (df["Power"] > 0)
        &
        (df["RPM"] > 0)
        &
        (df["Speed"] >= 0)
        &
        (df["Engine Load"] >= 0)
    ].copy()

    if df.empty:
        return empty_result()

    # =========================================================
    # DAILY DUPLICATE CLEANUP
    # =========================================================

    df = (
        df
        .sort_values(
            [
                "date_only",
                "voyage",
            ]
        )
        .drop_duplicates(
            subset=[
                "date_only",
                "voyage",
            ],
            keep="first",
        )
        .reset_index(drop=True)
    )

    # =========================================================
    # DOSING / BASELINE
    # =========================================================

    dosing = df[
        df["is_dosing"]
    ].copy()

    baseline = df[
        ~df["is_dosing"]
    ].copy()

    print(
        f"TOTAL OBSERVATIONS: {len(df)}"
    )

    print(
        f"DOSING OBSERVATIONS: {len(dosing)}"
    )

    print(
        f"NON-DOSING OBSERVATIONS: {len(baseline)}"
    )

    # =========================================================
    # VOYAGE DEBUG
    # =========================================================

    print("\nAVAILABLE VOYAGES / SHEETS:")

    for voyage in sorted(
        df["voyage"].unique()
    ):

        count = (
            df["voyage"] == voyage
        ).sum()

        print(
            f"  {voyage}: "
            f"{count} observations"
        )

    # =========================================================
    # NEED BOTH
    # =========================================================

    if dosing.empty or baseline.empty:

        return empty_result(
            quality="Insufficient Data",
            rejected=len(dosing),
        )

    # =========================================================
    # MATCHING LIMITS
    # =========================================================

    MAX_POWER_DIFF = 250.0
    MAX_SPEED_DIFF = 1.00
    MAX_RPM_DIFF = 1.50
    MAX_LOAD_DIFF = 2.00
    MAX_DATE_DISTANCE = 21
    MAX_DRAFT_DIFF = 1.50

    # =========================================================
    # WEIGHTS
    # =========================================================

    WEIGHT_POWER = 0.27
    WEIGHT_SPEED = 0.18
    WEIGHT_RPM = 0.14
    WEIGHT_LOAD = 0.23
    WEIGHT_DRAFT = 0.09
    WEIGHT_DATE = 0.09

    # =========================================================
    # MATCH
    # =========================================================

    matches = []
    rejected = []

    used_baseline_indices = set()

    for _, dose in dosing.iterrows():

        dose_date = dose["date_only"]

        dose_voyage = _normalise_voyage(
            dose["voyage"]
        )

        dose_voyage_key = (
            _voyage_match_key(
                dose_voyage
            )
        )

        # -----------------------------------------------------
        # VOYAGE MATCHING
        # -----------------------------------------------------

        if dose_voyage_key != "UNKNOWN":

            candidates = baseline[
                baseline["voyage_match_key"]
                ==
                dose_voyage_key
            ].copy()

            voyage_restriction = (
                f"same voyage "
                f"({dose_voyage})"
            )

        else:

            # UNKNOWN voyage does not receive a
            # deliberate voyage match.

            candidates = baseline.copy()

            voyage_restriction = (
                "any known baseline voyage"
            )

        # -----------------------------------------------------
        # REMOVE USED BASELINES
        # -----------------------------------------------------

        if used_baseline_indices:

            candidates = candidates[
                ~candidates.index.isin(
                    used_baseline_indices
                )
            ].copy()

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        if not candidates.empty:

            candidates["date_distance"] = (
                pd.to_datetime(
                    candidates["date_only"]
                )
                -
                pd.Timestamp(
                    dose_date
                )
            ).abs().dt.days

            candidates = candidates[
                candidates["date_distance"]
                <= MAX_DATE_DISTANCE
            ].copy()

        # -----------------------------------------------------
        # OPERATING CONDITIONS
        # -----------------------------------------------------

        if not candidates.empty:

            dose_power = _safe_float(
                dose["Power"]
            )

            dose_speed = _safe_float(
                dose["Speed"]
            )

            dose_rpm = _safe_float(
                dose["RPM"]
            )

            dose_load = _safe_float(
                dose["Engine Load"]
            )

            candidates["power_diff"] = (
                candidates["Power"]
                -
                dose_power
            ).abs()

            candidates["speed_diff"] = (
                candidates["Speed"]
                -
                dose_speed
            ).abs()

            candidates["rpm_diff"] = (
                candidates["RPM"]
                -
                dose_rpm
            ).abs()

            candidates["load_diff"] = (
                candidates["Engine Load"]
                -
                dose_load
            ).abs()

            # -------------------------------------------------
            # DRAFT FWD
            # -------------------------------------------------

            if (
                "Draft FWD"
                in candidates.columns
                and
                "Draft FWD"
                in dose.index
                and
                pd.notna(
                    dose["Draft FWD"]
                )
            ):

                candidates[
                    "draft_fwd_diff"
                ] = (
                    candidates["Draft FWD"]
                    -
                    float(
                        dose["Draft FWD"]
                    )
                ).abs()

            else:

                candidates[
                    "draft_fwd_diff"
                ] = 0.0

            # -------------------------------------------------
            # DRAFT AFT
            # -------------------------------------------------

            if (
                "Draft AFT"
                in candidates.columns
                and
                "Draft AFT"
                in dose.index
                and
                pd.notna(
                    dose["Draft AFT"]
                )
            ):

                candidates[
                    "draft_aft_diff"
                ] = (
                    candidates["Draft AFT"]
                    -
                    float(
                        dose["Draft AFT"]
                    )
                ).abs()

            else:

                candidates[
                    "draft_aft_diff"
                ] = 0.0

            candidates["draft_diff"] = (
                candidates[
                    "draft_fwd_diff"
                ]
                +
                candidates[
                    "draft_aft_diff"
                ]
            ) / 2.0

            # -------------------------------------------------
            # HARD LIMITS
            # -------------------------------------------------

            candidates = candidates[
                (
                    candidates["power_diff"]
                    <= MAX_POWER_DIFF
                )
                &
                (
                    candidates["speed_diff"]
                    <= MAX_SPEED_DIFF
                )
                &
                (
                    candidates["rpm_diff"]
                    <= MAX_RPM_DIFF
                )
                &
                (
                    candidates["load_diff"]
                    <= MAX_LOAD_DIFF
                )
                &
                (
                    candidates["draft_diff"]
                    <= MAX_DRAFT_DIFF
                )
            ].copy()

        # =====================================================
        # NO MATCH
        # =====================================================

        if candidates.empty:

            if dose_voyage != "UNKNOWN":

                reason = (
                    "No unused baseline observation "
                    f"from {voyage_restriction} "
                    "passed the operating-condition "
                    "limits."
                )

            else:

                reason = (
                    "No unused baseline observation "
                    "passed the operating-condition "
                    "limits."
                )

            rejected_item = {

                "dosing_date":
                    dose_date,

                "voyage":
                    dose_voyage,

                "reason":
                    reason,
            }

            rejected.append(
                rejected_item
            )

            print(
                f"\nDosing date: {dose_date}"
            )

            print(
                f"Voyage: {dose_voyage}"
            )

            print(
                f"Reason: {reason}"
            )

            continue

        # =====================================================
        # SCORES
        # =====================================================

        candidates["power_score"] = (
            candidates["power_diff"]
            /
            MAX_POWER_DIFF
        )

        candidates["speed_score"] = (
            candidates["speed_diff"]
            /
            MAX_SPEED_DIFF
        )

        candidates["rpm_score"] = (
            candidates["rpm_diff"]
            /
            MAX_RPM_DIFF
        )

        candidates["load_score"] = (
            candidates["load_diff"]
            /
            MAX_LOAD_DIFF
        )

        candidates["draft_score"] = (
            candidates["draft_diff"]
            /
            MAX_DRAFT_DIFF
        )

        candidates["date_score"] = (
            candidates["date_distance"]
            /
            MAX_DATE_DISTANCE
        )

        # =====================================================
        # MATCH SCORE
        # =====================================================

        candidates["match_score"] = (

            WEIGHT_POWER
            *
            candidates["power_score"]

            +

            WEIGHT_SPEED
            *
            candidates["speed_score"]

            +

            WEIGHT_RPM
            *
            candidates["rpm_score"]

            +

            WEIGHT_LOAD
            *
            candidates["load_score"]

            +

            WEIGHT_DRAFT
            *
            candidates["draft_score"]

            +

            WEIGHT_DATE
            *
            candidates["date_score"]
        )

        # =====================================================
        # BEST MATCH
        # =====================================================

        best = (
            candidates
            .sort_values(
                [
                    "match_score",
                    "date_distance",
                ]
            )
            .iloc[0]
        )

        best_index = best.name

        used_baseline_indices.add(
            best_index
        )

        # =====================================================
        # QUALITY
        # =====================================================

        score = float(
            best["match_score"]
        )

        if score <= 0.25:

            quality = "Excellent"

        elif score <= 0.45:

            quality = "Good"

        elif score <= 0.65:

            quality = "Fair"

        else:

            quality = "Poor"

        # =====================================================
        # SFOC
        # =====================================================

        dosing_sfoc = float(
            dose["SFOC"]
        )

        baseline_sfoc = float(
            best["SFOC"]
        )

        difference = (
            baseline_sfoc
            -
            dosing_sfoc
        )

        if baseline_sfoc > 0:

            improvement = (
                difference
                /
                baseline_sfoc
                *
                100.0
            )

        else:

            improvement = np.nan

        # =====================================================
        # RECORD
        # =====================================================

        match = {

            "dosing_date":
                dose_date,

            "baseline_date":
                best["date_only"],

            "voyage":
                dose_voyage,

            "baseline_voyage":
                _normalise_voyage(
                    best["voyage"]
                ),

            "dosing_sfoc":
                dosing_sfoc,

            "baseline_sfoc":
                baseline_sfoc,

            "matched_non_dosing_sfoc":
                baseline_sfoc,

            "sfoc_difference":
                difference,

            "sfoc_improvement":
                improvement,

            "match_score":
                score,

            "match_quality":
                quality,

            "power_difference":
                float(
                    best["power_diff"]
                ),

            "speed_difference":
                float(
                    best["speed_diff"]
                ),

            "rpm_difference":
                float(
                    best["rpm_diff"]
                ),

            "load_difference":
                float(
                    best["load_diff"]
                ),

            "draft_difference":
                float(
                    best["draft_diff"]
                ),

            "date_difference":
                int(
                    best["date_distance"]
                ),

            "dosing_power":
                float(
                    dose["Power"]
                ),

            "baseline_power":
                float(
                    best["Power"]
                ),

            "dosing_speed":
                float(
                    dose["Speed"]
                ),

            "baseline_speed":
                float(
                    best["Speed"]
                ),

            "dosing_rpm":
                float(
                    dose["RPM"]
                ),

            "baseline_rpm":
                float(
                    best["RPM"]
                ),

            "dosing_load":
                float(
                    dose["Engine Load"]
                ),

            "baseline_load":
                float(
                    best["Engine Load"]
                ),
        }

        matches.append(
            match
        )

        # =====================================================
        # DEBUG
        # =====================================================

        print(
            f"\nDosing: {dose_date}"
        )

        print(
            f"Baseline: "
            f"{best['date_only']}"
        )

        print(
            f"Voyage: "
            f"{dose_voyage}"
        )

        print(
            f"Baseline voyage: "
            f"{best['voyage']}"
        )

        print(
            f"Dosing SFOC: "
            f"{dosing_sfoc:.3f}"
        )

        print(
            f"Baseline SFOC: "
            f"{baseline_sfoc:.3f}"
        )

        print(
            f"Power difference: "
            f"{best['power_diff']:.2f}"
        )

        print(
            f"Speed difference: "
            f"{best['speed_diff']:.2f}"
        )

        print(
            f"RPM difference: "
            f"{best['rpm_diff']:.2f}"
        )

        print(
            f"Load difference: "
            f"{best['load_diff']:.2f}"
        )

        print(
            f"Draft difference: "
            f"{best['draft_diff']:.2f}"
        )

        print(
            f"Date difference: "
            f"{int(best['date_distance'])} days"
        )

        print(
            f"Match score: "
            f"{score:.3f}"
        )

        print(
            f"Match quality: "
            f"{quality}"
        )

        print(
            f"SFOC improvement: "
            f"{improvement:.3f} %"
        )

    # =========================================================
    # NO MATCHES
    # =========================================================

    if not matches:

        print(
            "\nNO VALID NORMALIZED "
            "SFOC MATCHES."
        )

        return empty_result(
            quality="No Valid Matches",
            rejected=len(rejected),
            rejected_matches=rejected,
        )

    # =========================================================
    # MATCH DATAFRAME
    # =========================================================

    matches_df = pd.DataFrame(
        matches
    )

    # =========================================================
    # AGGREGATES
    # =========================================================

    dosing_sfoc = (
        matches_df[
            "dosing_sfoc"
        ]
        .dropna()
        .mean()
    )

    baseline_sfoc = (
        matches_df[
            "baseline_sfoc"
        ]
        .dropna()
        .mean()
    )

    mean_difference = (
        matches_df[
            "sfoc_difference"
        ]
        .dropna()
        .mean()
    )

    median_difference = (
        matches_df[
            "sfoc_difference"
        ]
        .dropna()
        .median()
    )

    if (
        pd.notna(
            baseline_sfoc
        )
        and
        baseline_sfoc > 0
        and
        pd.notna(
            mean_difference
        )
    ):

        improvement = (
            mean_difference
            /
            baseline_sfoc
            *
            100.0
        )

    else:

        improvement = np.nan

    # =========================================================
    # OVERALL QUALITY
    # =========================================================

    median_score = (
        matches_df[
            "match_score"
        ]
        .median()
    )

    if len(matches) < 3:

        overall_quality = (
            "Insufficient Matches"
        )

    elif median_score <= 0.25:

        overall_quality = "Excellent"

    elif median_score <= 0.45:

        overall_quality = "Very Good"

    elif median_score <= 0.65:

        overall_quality = "Good"

    else:

        overall_quality = "Fair"

    # =========================================================
    # ROUND
    # =========================================================

    numeric_match_keys = [

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
        "dosing_power",
        "baseline_power",
        "dosing_speed",
        "baseline_speed",
        "dosing_rpm",
        "baseline_rpm",
        "dosing_load",
        "baseline_load",
    ]

    for match in matches:

        for key in numeric_match_keys:

            if (
                key in match
                and
                pd.notna(
                    match[key]
                )
            ):

                match[key] = round(
                    float(
                        match[key]
                    ),
                    4,
                )

    # =========================================================
    # SUMMARY
    # =========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "NORMALIZED SFOC "
        "MATCHING SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        f"Total dosing observations: "
        f"{len(dosing)}"
    )

    print(
        f"Accepted matches: "
        f"{len(matches)}"
    )

    print(
        f"Rejected matches: "
        f"{len(rejected)}"
    )

    print(
        f"Overall match quality: "
        f"{overall_quality}"
    )

    print(
        f"Dosing SFOC: "
        f"{dosing_sfoc:.2f}"
    )

    print(
        f"Matched non-dosing SFOC: "
        f"{baseline_sfoc:.2f}"
    )

    print(
        f"Mean pair difference: "
        f"{mean_difference:.2f}"
    )

    print(
        f"Median pair difference: "
        f"{median_difference:.2f}"
    )

    print(
        f"SFOC improvement: "
        f"{improvement:.2f} %"
    )

    print(
        "=" * 70
    )

    return {

        "overall_quality":
            overall_quality,

        "overall_match_quality":
            overall_quality,

        "matched_observations":
            len(matches),

        "matched_days":
            len(matches),

        "rejected_observations":
            len(rejected),

        "dosing_sfoc":
            dosing_sfoc,

        "matched_baseline_sfoc":
            baseline_sfoc,

        "matched_non_dosing_sfoc":
            baseline_sfoc,

        "mean_pair_difference":
            mean_difference,

        "median_pair_difference":
            median_difference,

        "sfoc_improvement":
            improvement,

        "matches":
            matches,

        "matched_rows":
            matches,

        "median_match_score":
            median_score,
    }


# =========================================================
# VESSEL ANALYSIS
# =========================================================

def get_vessel_analysis(vessel):

    vessel = str(
        vessel
    ).strip().upper()

    ANALYSIS_START_DATE = pd.Timestamp(
        "2026-06-20"
    ).date()

    VALID_MIN_POWER = 500.0

    MAX_TIME_GAP_HOURS = 1.0

    # =========================================================
    # DETECT MEASUREMENT VOYAGE FIELD
    # =========================================================

    measurement_voyage_field = (
        _get_measurement_voyage_field()
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "VESSEL ANALYSIS"
    )

    print(
        "=" * 70
    )

    print(
        f"Vessel: {vessel}"
    )

    print(
        "ChemicalMeasurement "
        "voyage field:",
        measurement_voyage_field,
    )

    # =========================================================
    # LOAD MEASUREMENTS
    # =========================================================

    measurement_fields = [

        "timestamp",
        "fuel_load",
        "fuel_inlet",
        "fuel_outlet",
        "rpm",
        "speed",
        "power",
    ]

    if measurement_voyage_field:

        measurement_fields.append(
            measurement_voyage_field
        )

    measurements = list(
        ChemicalMeasurement.objects
        .filter(vessel=vessel)
        .values(*measurement_fields)
    )

    if not measurements:

        return {

            "success":
                False,

            "message":
                f"No measurement data "
                f"found for {vessel}.",
        }

    measurement_df = pd.DataFrame(
        measurements
    )

    # =========================================================
    # STANDARDISE VOYAGE COLUMN
    # =========================================================

    if measurement_voyage_field:

        if (
            measurement_voyage_field
            != "voyage"
        ):

            measurement_df = (
                measurement_df
                .rename(
                    columns={
                        measurement_voyage_field:
                            "voyage"
                    }
                )
            )

        measurement_df[
            "voyage"
        ] = (
            measurement_df[
                "voyage"
            ]
            .apply(
                _normalise_voyage
            )
        )

    else:

        measurement_df[
            "voyage"
        ] = "UNKNOWN"

    # =========================================================
    # REQUIRED
    # =========================================================

    required_columns = [

        "timestamp",
        "fuel_load",
        "fuel_inlet",
        "fuel_outlet",
        "rpm",
        "speed",
        "power",
        "voyage",
    ]

    for column in required_columns:

        if column not in measurement_df.columns:

            if column == "voyage":

                measurement_df[
                    column
                ] = "UNKNOWN"

            else:

                measurement_df[
                    column
                ] = np.nan

    # =========================================================
    # TIMESTAMP
    # =========================================================

    measurement_df[
        "timestamp"
    ] = pd.to_datetime(
        measurement_df[
            "timestamp"
        ],
        errors="coerce",
        utc=True,
    )

    measurement_df = (
        measurement_df
        .dropna(
            subset=["timestamp"]
        )
        .sort_values(
            "timestamp"
        )
        .reset_index(
            drop=True
        )
    )

    print(
        f"\nMeasurement data available: "
        f"{len(measurement_df)} rows"
    )

    if measurement_df.empty:

        return {

            "success":
                False,

            "message":
                f"No valid timestamps "
                f"found for {vessel}.",
        }

    print(
        f"Measurement start: "
        f"{measurement_df['timestamp'].min()}"
    )

    print(
        f"Measurement end: "
        f"{measurement_df['timestamp'].max()}"
    )

    # =========================================================
    # NUMERIC
    # =========================================================

    numeric_columns = [

        "fuel_load",
        "fuel_inlet",
        "fuel_outlet",
        "rpm",
        "speed",
        "power",
    ]

    for column in numeric_columns:

        measurement_df[
            column
        ] = pd.to_numeric(
            measurement_df[
                column
            ],
            errors="coerce",
        )

    measurement_df[
        numeric_columns
    ] = (
        measurement_df[
            numeric_columns
        ]
        .replace(
            [
                np.inf,
                -np.inf,
            ],
            np.nan,
        )
    )

    # =========================================================
    # FUEL CONSUMPTION
    # =========================================================

    measurement_df[
        "fuel_consumption"
    ] = (
        measurement_df[
            "fuel_inlet"
        ]
        -
        measurement_df[
            "fuel_outlet"
        ]
    )

    measurement_df.loc[
        measurement_df[
            "fuel_consumption"
        ] <= 0,
        "fuel_consumption",
    ] = np.nan

    # =========================================================
    # TIME
    # =========================================================

    measurement_df[
        "time_diff_hours"
    ] = (
        measurement_df[
            "timestamp"
        ]
        .diff()
        .dt.total_seconds()
        /
        3600.0
    )

    measurement_df.loc[
        measurement_df[
            "time_diff_hours"
        ] <= 0,
        "time_diff_hours",
    ] = np.nan

    measurement_df.loc[
        measurement_df[
            "time_diff_hours"
        ]
        >
        MAX_TIME_GAP_HOURS,
        "time_diff_hours",
    ] = np.nan

    # =========================================================
    # INTEGRATED FUEL
    # =========================================================

    measurement_df[
        "fuel_used_kg"
    ] = (
        measurement_df[
            "fuel_consumption"
        ]
        *
        measurement_df[
            "time_diff_hours"
        ]
    )

    measurement_df.loc[
        measurement_df[
            "fuel_used_kg"
        ] < 0,
        "fuel_used_kg",
    ] = np.nan

    # =========================================================
    # FUEL / NM
    # =========================================================

    measurement_df[
        "fuel_per_nm"
    ] = np.nan

    valid_fuel_nm = (

        measurement_df[
            "speed"
        ].notna()

        &

        measurement_df[
            "fuel_consumption"
        ].notna()

        &

        (
            measurement_df[
                "speed"
            ] > 0.5
        )
    )

    measurement_df.loc[
        valid_fuel_nm,
        "fuel_per_nm",
    ] = (

        measurement_df.loc[
            valid_fuel_nm,
            "fuel_consumption",
        ]

        /

        measurement_df.loc[
            valid_fuel_nm,
            "speed",
        ]
    )

    # =========================================================
    # SFOC
    # =========================================================

    measurement_df[
        "sfoc"
    ] = np.nan

    valid_sfoc = (

        measurement_df[
            "power"
        ].notna()

        &

        measurement_df[
            "fuel_consumption"
        ].notna()

        &

        (
            measurement_df[
                "power"
            ]
            >=
            VALID_MIN_POWER
        )

        &

        (
            measurement_df[
                "fuel_consumption"
            ] > 0
        )
    )

    measurement_df.loc[
        valid_sfoc,
        "sfoc",
    ] = (

        measurement_df.loc[
            valid_sfoc,
            "fuel_consumption",
        ]

        /

        measurement_df.loc[
            valid_sfoc,
            "power",
        ]

        *
        1000.0
    )

    # =========================================================
    # REALISTIC SFOC
    # =========================================================

    measurement_df.loc[
        (
            measurement_df[
                "sfoc"
            ] < 100
        )
        |
        (
            measurement_df[
                "sfoc"
            ] > 500
        ),
        "sfoc",
    ] = np.nan

    # =========================================================
    # DATE
    # =========================================================

    measurement_df[
        "date"
    ] = (
        measurement_df[
            "timestamp"
        ]
        .dt.date
    )

    # =========================================================
    # LOAD DOSING
    # =========================================================

    dosing_records = (
        _get_dosing_records(
            vessel
        )
    )

    if dosing_records:

        dosing_df = pd.DataFrame(
            dosing_records
        )

        required_dosing_columns = [

            "date",
            "voyage",
            "morning_additive",
            "evening_additive",
            "total_additive",
            "total_fuel_qty",
            "chemical_rob",
            "remarks",
        ]

        for column in required_dosing_columns:

            if column not in dosing_df.columns:

                dosing_df[column] = np.nan

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        dosing_df[
            "date"
        ] = (
            pd.to_datetime(
                dosing_df[
                    "date"
                ],
                errors="coerce",
            )
            .dt.date
        )

        # -----------------------------------------------------
        # REMOVE DOSING RECORDS BEFORE
        # 20 JUNE 2026
        # -----------------------------------------------------

        dosing_df = dosing_df[
            dosing_df[
                "date"
            ].notna()

            &

            (
                dosing_df[
                    "date"
                ]
                >=
                ANALYSIS_START_DATE
            )
        ].copy()

        # =====================================================
        # DOSING WITHOUT MEASUREMENT DATA
        # =====================================================

        if not dosing_df.empty:

            measurement_dates = set(
                measurement_df[
                    "date"
                ].dropna()
            )

            dosing_df[
                "measurement_available"
            ] = (
                dosing_df[
                    "date"
                ]
                .isin(
                    measurement_dates
                )
            )

            dosing_without_measurement = (
                dosing_df[
                    ~dosing_df[
                        "measurement_available"
                    ]
                ].copy()
            )

        else:

            dosing_without_measurement = (
                pd.DataFrame()
            )

        # =====================================================
        # DATA COVERAGE
        # =====================================================

        measurement_start = (
            measurement_df[
                "date"
            ].min()
            if not measurement_df.empty
            else None
        )

        measurement_end = (
            measurement_df[
                "date"
            ].max()
            if not measurement_df.empty
            else None
        )

        dosing_start = (
            dosing_df[
                "date"
            ].min()
            if not dosing_df.empty
            else None
        )

        dosing_end = (
            dosing_df[
                "date"
            ].max()
            if not dosing_df.empty
            else None
        )

        print(
            "\nDATA COVERAGE:"
        )

        print(
            f"Measurement data: "
            f"{measurement_start} → "
            f"{measurement_end}"
        )

        print(
            f"Dosing data: "
            f"{dosing_start} → "
            f"{dosing_end}"
        )

        print(
            f"Dosing records after "
            f"{ANALYSIS_START_DATE}: "
            f"{len(dosing_df)}"
        )

        # -----------------------------------------------------
        # VOYAGE
        # -----------------------------------------------------

        dosing_df[
            "voyage"
        ] = (
            dosing_df[
                "voyage"
            ]
            .apply(
                _normalise_voyage
            )
        )

        # -----------------------------------------------------
        # NUMERIC
        # -----------------------------------------------------

        for column in [

            "morning_additive",
            "evening_additive",
            "total_additive",
            "total_fuel_qty",
        ]:

            dosing_df[
                column
            ] = pd.to_numeric(
                dosing_df[
                    column
                ],
                errors="coerce",
            )

        # -----------------------------------------------------
        # TOTAL ADDITIVE
        # -----------------------------------------------------

        dosing_df[
            "total_additive"
        ] = (
            dosing_df[
                "total_additive"
            ]
            .fillna(0.0)
        )

        # -----------------------------------------------------
        # REMARKS
        # -----------------------------------------------------

        dosing_df[
            "remarks"
        ] = (
            dosing_df[
                "remarks"
            ]
            .fillna("")
            .astype(str)
        )

    else:

        dosing_df = pd.DataFrame(
            columns=[

                "date",
                "voyage",
                "morning_additive",
                "evening_additive",
                "total_additive",
                "total_fuel_qty",
                "chemical_rob",
                "remarks",
            ]
        )

        dosing_without_measurement = (
            pd.DataFrame()
        )
        # =========================================================
    # RECONCILE UNKNOWN MEASUREMENT VOYAGES
    # =========================================================
    #
    # ChemicalDosing already contains the correct voyage / sheet
    # information. Some ChemicalMeasurement records have voyage
    # stored as UNKNOWN, so they cannot match dosing records when
    # merging on [date, voyage].
    #
    # We therefore use the dosing records to infer the measurement
    # voyage by DATE.
    #
    # Rules:
    #   1. Keep an existing known measurement voyage.
    #   2. If measurement voyage is UNKNOWN and exactly one voyage
    #      exists in dosing records for that date, use that voyage.
    #   3. If multiple dosing voyages exist on the same date, do
    #      not guess; keep UNKNOWN.
    #
    # This preserves the existing June/July voyage information while
    # allowing August UNKNOWN measurements to become 103L.

    if not dosing_df.empty:

        # Ensure dosing voyage values are normalized.
        dosing_df["voyage"] = (
            dosing_df["voyage"]
            .apply(_normalise_voyage)
        )

        # -----------------------------------------------------
        # Build date -> unique voyage mapping
        # -----------------------------------------------------

        dosing_date_voyages = (
            dosing_df[
                [
                    "date",
                    "voyage",
                ]
            ]
            .dropna(
                subset=[
                    "date",
                ]
            )
            .copy()
        )

        dosing_date_voyages = (
            dosing_date_voyages[
                dosing_date_voyages["voyage"]
                != "UNKNOWN"
            ]
        )

        date_to_voyages = (
            dosing_date_voyages
            .groupby("date")["voyage"]
            .apply(
                lambda values:
                sorted(
                    set(values)
                )
            )
            .to_dict()
        )

        # -----------------------------------------------------
        # Count before reconciliation
        # -----------------------------------------------------

        unknown_before = int(
            (
                measurement_df["voyage"]
                == "UNKNOWN"
            ).sum()
        )

        print(
            "\nMEASUREMENT VOYAGE RECONCILIATION:"
        )

        print(
            "UNKNOWN measurement voyages before:",
            unknown_before,
        )

        # -----------------------------------------------------
        # Fill UNKNOWN measurements from dosing voyage
        # -----------------------------------------------------

        inferred_count = 0
        ambiguous_count = 0

        for index in measurement_df.index:

            current_voyage = (
                _normalise_voyage(
                    measurement_df.at[
                        index,
                        "voyage",
                    ]
                )
            )

            # Never overwrite an already known voyage.
            if current_voyage != "UNKNOWN":
                continue

            measurement_date = (
                measurement_df.at[
                    index,
                    "date",
                ]
            )

            voyages_for_date = (
                date_to_voyages.get(
                    measurement_date,
                    [],
                )
            )

            # Exactly one voyage for this date:
            # safe to assign.
            if len(voyages_for_date) == 1:

                inferred_voyage = (
                    voyages_for_date[0]
                )

                measurement_df.at[
                    index,
                    "voyage",
                ] = inferred_voyage

                inferred_count += 1

            # More than one voyage on the same date:
            # do not guess.
            elif len(voyages_for_date) > 1:

                ambiguous_count += 1

        # -----------------------------------------------------
        # Recreate matching key AFTER reconciliation
        # -----------------------------------------------------

        measurement_df[
            "voyage"
        ] = (
            measurement_df[
                "voyage"
            ]
            .apply(
                _normalise_voyage
            )
        )

        measurement_df[
            "voyage_match_key"
        ] = (
            measurement_df[
                "voyage"
            ]
            .apply(
                _voyage_match_key
            )
        )

        unknown_after = int(
            (
                measurement_df["voyage"]
                == "UNKNOWN"
            ).sum()
        )

        print(
            "Measurement voyages inferred:",
            inferred_count,
        )

        print(
            "Ambiguous measurement dates:",
            ambiguous_count,
        )

        print(
            "UNKNOWN measurement voyages after:",
            unknown_after,
        )

        # -----------------------------------------------------
        # Show inferred voyage distribution
        # -----------------------------------------------------

        print(
            "\nMEASUREMENT VOYAGES AFTER RECONCILIATION:"
        )

        voyage_counts = (
            measurement_df[
                "voyage"
            ]
            .value_counts()
            .sort_index()
        )

        for voyage, count in voyage_counts.items():

            print(
                f"  {voyage}: "
                f"{count} observations"
            )

        # -----------------------------------------------------
        # Show August specifically
        # -----------------------------------------------------

        august_measurements = (
            measurement_df[
                (
                    measurement_df["date"]
                    >= pd.Timestamp(
                        "2026-08-01"
                    ).date()
                )
                &
                (
                    measurement_df["date"]
                    <= pd.Timestamp(
                        "2026-08-31"
                    ).date()
                )
            ]
        )

        if not august_measurements.empty:

            print(
                "\nAUGUST MEASUREMENT VOYAGES:"
            )

            print(
                august_measurements[
                    [
                        "date",
                        "voyage",
                    ]
                ]
                .drop_duplicates()
                .sort_values(
                    [
                        "date",
                        "voyage",
                    ]
                )
                .to_string(
                    index=False
                )
            )

    else:

        # No dosing data available, so retain the
        # measurement voyage information as-is.

        measurement_df[
            "voyage"
        ] = (
            measurement_df[
                "voyage"
            ]
            .apply(
                _normalise_voyage
            )
        )

        measurement_df[
            "voyage_match_key"
        ] = (
            measurement_df[
                "voyage"
            ]
            .apply(
                _voyage_match_key
            )
        )

    # =========================================================
    # DOSING MAP
    # =========================================================

    if not dosing_df.empty:

        if measurement_voyage_field:

            dosing_map = (
                dosing_df
                .groupby(
                    [
                        "date",
                        "voyage",
                    ],
                    as_index=False,
                )
                .agg(
                    total_additive=(
                        "total_additive",
                        "sum",
                    )
                )
            )

            measurement_df = (
                measurement_df
                .drop(
                    columns=[
                        "total_additive"
                    ],
                    errors="ignore",
                )
                .merge(
                    dosing_map,
                    on=[
                        "date",
                        "voyage",
                    ],
                    how="left",
                )
            )

        else:

            dosing_map = (
                dosing_df
                .groupby(
                    "date",
                    as_index=False,
                )
                .agg(
                    total_additive=(
                        "total_additive",
                        "sum",
                    )
                )
            )

            measurement_df = (
                measurement_df
                .drop(
                    columns=[
                        "total_additive"
                    ],
                    errors="ignore",
                )
                .merge(
                    dosing_map,
                    on="date",
                    how="left",
                )
            )

    else:

        measurement_df[
            "total_additive"
        ] = 0.0

    # =========================================================
    # CLEAN ADDITIVE
    # =========================================================

    measurement_df[
        "total_additive"
    ] = (
        pd.to_numeric(
            measurement_df[
                "total_additive"
            ],
            errors="coerce",
        )
        .fillna(0.0)
    )

    measurement_df[
        "dosing_status"
    ] = np.where(
        measurement_df[
            "total_additive"
        ] > 0,
        "Dosing",
        "No Dosing",
    )

    # =========================================================
    # DAILY DATA
    # =========================================================

    daily = (
        measurement_df
        .groupby(
            [
                "date",
                "voyage",
            ],
            dropna=False,
        )
        .agg(

            fuel_used_kg=(
                "fuel_used_kg",
                "sum",
            ),

            avg_fuel_consumption=(
                "fuel_consumption",
                "mean",
            ),

            avg_sfoc=(
                "sfoc",
                "mean",
            ),

            avg_speed=(
                "speed",
                "mean",
            ),

            avg_power=(
                "power",
                "mean",
            ),

            avg_rpm=(
                "rpm",
                "mean",
            ),

            avg_fuel_load=(
                "fuel_load",
                "mean",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "date",
                "voyage",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # =========================================================
    # DAILY DOSING INFORMATION
    # =========================================================

    if not dosing_df.empty:

        if measurement_voyage_field:

            daily_dosing = (
                dosing_df
                .groupby(
                    [
                        "date",
                        "voyage",
                    ],
                    as_index=False,
                )
                .agg(

                    total_additive=(
                        "total_additive",
                        "sum",
                    ),

                    total_fuel_qty=(
                        "total_fuel_qty",
                        "sum",
                    ),

                    chemical_rob=(
                        "chemical_rob",
                        "first",
                    ),

                    remarks=(
                        "remarks",
                        lambda values:
                        " | ".join(
                            [
                                str(value).strip()
                                for value in values
                                if (
                                    pd.notna(
                                        value
                                    )
                                    and
                                    str(
                                        value
                                    ).strip()
                                    and
                                    str(
                                        value
                                    )
                                    .strip()
                                    .lower()
                                    not in {
                                        "nan",
                                        "none",
                                    }
                                )
                            ]
                        ),
                    ),
                )
            )

            daily = (
                daily
                .drop(
                    columns=[

                        "total_additive",
                        "total_fuel_qty",
                        "chemical_rob",
                        "remarks",
                    ],
                    errors="ignore",
                )
                .merge(
                    daily_dosing,
                    on=[
                        "date",
                        "voyage",
                    ],
                    how="left",
                )
            )

        else:

            daily_dosing = (
                dosing_df
                .groupby(
                    "date",
                    as_index=False,
                )
                .agg(

                    total_additive=(
                        "total_additive",
                        "sum",
                    ),

                    total_fuel_qty=(
                        "total_fuel_qty",
                        "sum",
                    ),

                    chemical_rob=(
                        "chemical_rob",
                        "first",
                    ),

                    remarks=(
                        "remarks",
                        lambda values:
                        " | ".join(
                            [
                                str(value).strip()
                                for value in values
                                if (
                                    pd.notna(
                                        value
                                    )
                                    and
                                    str(
                                        value
                                    ).strip()
                                    and
                                    str(
                                        value
                                    )
                                    .strip()
                                    .lower()
                                    not in {
                                        "nan",
                                        "none",
                                    }
                                )
                            ]
                        ),
                    ),
                )
            )

            daily = (
                daily
                .drop(
                    columns=[

                        "total_additive",
                        "total_fuel_qty",
                        "chemical_rob",
                        "remarks",
                    ],
                    errors="ignore",
                )
                .merge(
                    daily_dosing,
                    on="date",
                    how="left",
                )
            )

    else:

        daily[
            "total_additive"
        ] = 0.0

        daily[
            "total_fuel_qty"
        ] = np.nan

        daily[
            "chemical_rob"
        ] = np.nan

        daily[
            "remarks"
        ] = ""

    # =========================================================
    # CLEAN DAILY
    # =========================================================

    daily[
        "total_additive"
    ] = (
        pd.to_numeric(
            daily[
                "total_additive"
            ],
            errors="coerce",
        )
        .fillna(0.0)
    )

    daily[
        "remarks"
    ] = (
        daily[
            "remarks"
        ]
        .fillna("")
        .astype(str)
    )

    daily[
        "voyage"
    ] = (
        daily[
            "voyage"
        ]
        .apply(
            _normalise_voyage
        )
    )

    # =========================================================
    # DEBUG
    # =========================================================

    print(
        "\nDAILY VOYAGE INFORMATION:"
    )

    if not daily.empty:

        print(
            daily[
                [
                    "date",
                    "voyage",
                    "total_additive",
                ]
            ].to_string(
                index=False
            )
        )

    # =========================================================
    # DOSING STATUS
    # =========================================================

    daily[
        "dosing_status"
    ] = np.where(
        daily[
            "total_additive"
        ] > 0,
        "Dosing",
        "No Dosing",
    )

    # =========================================================
    # NEW ANALYTICS
    # =========================================================

    performance_summary = (
     calculate_performance_summary(
        daily
     )
    )

    dosing_analysis = (
     calculate_dosing_analysis(
        daily
     )
    )

    # =========================================================
    # RAW COMPARISON
    # =========================================================

    dosing_days = daily[
        daily[
            "total_additive"
        ] > 0
    ]

    non_dosing_days = daily[
        daily[
            "total_additive"
        ] <= 0
    ]

    dosing_sfoc_values = (
        dosing_days[
            "avg_sfoc"
        ]
        .dropna()
    )

    non_dosing_sfoc_values = (
        non_dosing_days[
            "avg_sfoc"
        ]
        .dropna()
    )

    dosing_sfoc = (
        dosing_sfoc_values.mean()
        if not dosing_sfoc_values.empty
        else np.nan
    )

    non_dosing_sfoc = (
        non_dosing_sfoc_values.mean()
        if not non_dosing_sfoc_values.empty
        else np.nan
    )

    if (
        pd.notna(dosing_sfoc)
        and
        pd.notna(non_dosing_sfoc)
        and
        non_dosing_sfoc > 0
    ):

        raw_sfoc_difference = (
            dosing_sfoc
            -
            non_dosing_sfoc
        )

        sfoc_improvement = (
            (
                non_dosing_sfoc
                -
                dosing_sfoc
            )
            /
            non_dosing_sfoc
            *
            100.0
        )

    else:

        raw_sfoc_difference = np.nan
        sfoc_improvement = np.nan

    # =========================================================
    # RAW FUEL
    # =========================================================

    dosing_fuel_values = (
        dosing_days[
            "avg_fuel_consumption"
        ]
        .dropna()
    )

    non_dosing_fuel_values = (
        non_dosing_days[
            "avg_fuel_consumption"
        ]
        .dropna()
    )

    dosing_fuel = (
        dosing_fuel_values.mean()
        if not dosing_fuel_values.empty
        else np.nan
    )

    non_dosing_fuel = (
        non_dosing_fuel_values.mean()
        if not non_dosing_fuel_values.empty
        else np.nan
    )

    if (
        pd.notna(dosing_fuel)
        and
        pd.notna(non_dosing_fuel)
        and
        non_dosing_fuel > 0
    ):

        fuel_difference = (
            (
                non_dosing_fuel
                -
                dosing_fuel
            )
            /
            non_dosing_fuel
            *
            100.0
        )

    else:

        fuel_difference = np.nan

    # =========================================================
    # NORMALIZED
    # =========================================================

    normalized_comparison = (
        calculate_normalized_sfoc(
            daily
        )
    )

    # =========================================================
    # DATA QUALITY
    # =========================================================

    data_quality = (
        calculate_data_quality(
            daily,
            normalized_comparison,
        )
    )


    # =========================================================
    # DEBUG MATCHES
    # =========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "NORMALIZED SFOC MATCHES"
    )

    print(
        "=" * 70
    )

    for row in normalized_comparison.get(
        "matches",
        [],
    ):

        print(row)

    print(
        "=" * 70
    )

    print(
        "Overall match quality:",
        normalized_comparison.get(
            "overall_quality"
        ),
    )

    print(
        "Mean pair difference:",
        normalized_comparison.get(
            "mean_pair_difference"
        ),
    )

    print(
        "Median pair difference:",
        normalized_comparison.get(
            "median_pair_difference"
        ),
    )

    print(
        "Matched observations:",
        normalized_comparison.get(
            "matched_observations"
        ),
    )

    print(
        "Rejected observations:",
        normalized_comparison.get(
            "rejected_observations"
        ),
    )

    print(
        "Adjusted SFOC effect:",
        normalized_comparison.get(
            "sfoc_improvement"
        ),
    )

    print(
        "=" * 70
    )

    # =========================================================
    # BEFORE / AFTER
    # =========================================================

    if not dosing_df.empty:

        valid_dosing_dates = (
            dosing_df.loc[
                dosing_df[
                    "total_additive"
                ] > 0,
                "date",
            ]
            .dropna()
        )

    else:

        valid_dosing_dates = pd.Series(
            dtype="object"
        )

    if not valid_dosing_dates.empty:

        first_dosing_date = (
            valid_dosing_dates.min()
        )

        before_measurements = (
            measurement_df[
                measurement_df[
                    "date"
                ]
                <
                first_dosing_date
            ]
        )

        after_measurements = (
            measurement_df[
                measurement_df[
                    "date"
                ]
                >=
                first_dosing_date
            ]
        )

    else:

        first_dosing_date = None

        before_measurements = (
            pd.DataFrame()
        )

        after_measurements = (
            pd.DataFrame()
        )

    # =========================================================
    # BEFORE / AFTER SFOC
    # =========================================================

    before_sfoc = (
        before_measurements[
            "sfoc"
        ]
        .dropna()
        .mean()
        if not before_measurements.empty
        else np.nan
    )

    after_sfoc = (
        after_measurements[
            "sfoc"
        ]
        .dropna()
        .mean()
        if not after_measurements.empty
        else np.nan
    )

    if (
        pd.notna(before_sfoc)
        and
        pd.notna(after_sfoc)
        and
        before_sfoc > 0
    ):

        before_after_difference = (
            after_sfoc
            -
            before_sfoc
        )

        before_after_improvement = (
            (
                before_sfoc
                -
                after_sfoc
            )
            /
            before_sfoc
            *
            100.0
        )

    else:

        before_after_difference = np.nan
        before_after_improvement = (
            np.nan
        )

    # =========================================================
    # OPERATING CONDITIONS
    # =========================================================

    before_power = (
        before_measurements[
            "power"
        ].mean()
        if not before_measurements.empty
        else np.nan
    )

    after_power = (
        after_measurements[
            "power"
        ].mean()
        if not after_measurements.empty
        else np.nan
    )

    before_speed = (
        before_measurements[
            "speed"
        ].mean()
        if not before_measurements.empty
        else np.nan
    )

    after_speed = (
        after_measurements[
            "speed"
        ].mean()
        if not after_measurements.empty
        else np.nan
    )

    before_rpm = (
        before_measurements[
            "rpm"
        ].mean()
        if not before_measurements.empty
        else np.nan
    )

    after_rpm = (
        after_measurements[
            "rpm"
        ].mean()
        if not after_measurements.empty
        else np.nan
    )

    # =========================================================
    # BEFORE / AFTER FUEL
    # =========================================================

    before_fuel_consumption = (
        before_measurements[
            "fuel_consumption"
        ]
        .dropna()
        .mean()
        if not before_measurements.empty
        else np.nan
    )

    after_fuel_consumption = (
        after_measurements[
            "fuel_consumption"
        ]
        .dropna()
        .mean()
        if not after_measurements.empty
        else np.nan
    )

    if (
        pd.notna(
            before_fuel_consumption
        )
        and
        pd.notna(
            after_fuel_consumption
        )
        and
        before_fuel_consumption > 0
    ):

        before_after_fuel_improvement = (
            (
                before_fuel_consumption
                -
                after_fuel_consumption
            )
            /
            before_fuel_consumption
            *
            100.0
        )

    else:

        before_after_fuel_improvement = (
            np.nan
        )

    # =========================================================
    # ANNUAL FUEL IMPACT
    # =========================================================

    if (
        pd.notna(
            before_after_fuel_improvement
        )
        and
        pd.notna(
            before_fuel_consumption
        )
        and
        before_fuel_consumption > 0
    ):

        annual_baseline_fuel_kg = (
            before_fuel_consumption
            *
            24
            *
            365
        )

        annual_fuel_impact_kg = (
            annual_baseline_fuel_kg
            *
            (
                before_after_fuel_improvement
                /
                100.0
            )
        )

        annual_fuel_impact_tonnes = (
            annual_fuel_impact_kg
            /
            1000.0
        )

    else:

        annual_baseline_fuel_kg = (
            np.nan
        )

        annual_fuel_impact_kg = (
            np.nan
        )

        annual_fuel_impact_tonnes = (
            np.nan
        )

    # =========================================================
    # IMPACT TYPE
    # =========================================================

    if pd.notna(
        annual_fuel_impact_tonnes
    ):

        if annual_fuel_impact_tonnes > 0:

            annual_fuel_impact_type = (
                "Estimated Saving"
            )

        elif annual_fuel_impact_tonnes < 0:

            annual_fuel_impact_type = (
                "Additional Consumption"
            )

        else:

            annual_fuel_impact_type = (
                "No Material Change"
            )

    else:

        annual_fuel_impact_type = (
            "Insufficient Data"
        )

    # =========================================================
    # KPIs
    # =========================================================

    total_measurements = len(
        measurement_df
    )

    start_date = (
        measurement_df[
            "timestamp"
        ].min()
    )

    end_date = (
        measurement_df[
            "timestamp"
        ].max()
    )

    total_fuel_kg = (
        measurement_df[
            "fuel_used_kg"
        ]
        .sum(
            min_count=1
        )
    )

    average_speed = (
        measurement_df[
            "speed"
        ].mean()
    )

    average_power = (
        measurement_df[
            "power"
        ].mean()
    )

    average_sfoc = (
        measurement_df[
            "sfoc"
        ]
        .dropna()
        .mean()
    )

    total_additive = (
        dosing_df[
            "total_additive"
        ].sum()
        if not dosing_df.empty
        else 0.0
    )

    dosing_days_count = (
        len(
            dosing_df[
                dosing_df[
                    "total_additive"
                ] > 0
            ]
        )
        if not dosing_df.empty
        else 0
    )

    # =========================================================
    # VOYAGE SUMMARY
    # =========================================================

    voyage_summary = []

    if not daily.empty:

        for voyage, voyage_df in (
            daily.groupby(
                "voyage",
                dropna=False,
            )
        ):

            voyage_summary.append(
                {

                    "voyage":
                        voyage,

                    "days":
                        len(
                            voyage_df
                        ),

                    "dosing_days":
                        int(
                            (
                                voyage_df[
                                    "total_additive"
                                ]
                                > 0
                            ).sum()
                        ),

                    "avg_sfoc":
                        voyage_df[
                            "avg_sfoc"
                        ]
                        .dropna()
                        .mean(),

                    "avg_power":
                        voyage_df[
                            "avg_power"
                        ]
                        .dropna()
                        .mean(),

                    "avg_speed":
                        voyage_df[
                            "avg_speed"
                        ]
                        .dropna()
                        .mean(),
                }
            )

    # =========================================================
    # RETURN
    # =========================================================

    return {

        "success":
            True,

        "vessel":
            vessel,

        "kpis": {

            "total_measurements":
                total_measurements,

            "start_date":
                start_date,

            "end_date":
                end_date,

            "total_fuel_kg":
                total_fuel_kg,

            "average_speed":
                average_speed,

            "average_power":
                average_power,

            "average_sfoc":
                average_sfoc,

            "total_additive":
                total_additive,

            "dosing_days":
                dosing_days_count,

            "first_dosing_date":
                first_dosing_date,
        },

        "comparison": {

            "dosing_sfoc":
                dosing_sfoc,

            "non_dosing_sfoc":
                non_dosing_sfoc,

            "sfoc_improvement":
                sfoc_improvement,

            "raw_sfoc_difference":
                raw_sfoc_difference,

            "dosing_fuel":
                dosing_fuel,

            "non_dosing_fuel":
                non_dosing_fuel,

            "fuel_difference":
                fuel_difference,
        },

        "normalized_comparison":
            normalized_comparison,

        "performance_summary":
                performance_summary,
        
        "dosing_analysis":
             dosing_analysis,
        
        "data_quality":
            data_quality,    

        "before_after": {

            "first_dosing_date":
                first_dosing_date,

            "before_sfoc":
                before_sfoc,

            "after_sfoc":
                after_sfoc,

            "difference":
                before_after_difference,

            "improvement":
                before_after_improvement,

            "before_fuel_consumption":
                before_fuel_consumption,

            "after_fuel_consumption":
                after_fuel_consumption,

            "fuel_improvement":
                before_after_fuel_improvement,

            "before_power":
                before_power,

            "after_power":
                after_power,

            "before_speed":
                before_speed,

            "after_speed":
                after_speed,

            "before_rpm":
                before_rpm,

            "after_rpm":
                after_rpm,

            "before_measurements":
                len(
                    before_measurements
                ),

            "after_measurements":
                len(
                    after_measurements
                ),

            "annual_baseline_fuel_kg":
                annual_baseline_fuel_kg,

            "annual_fuel_impact_kg":
                annual_fuel_impact_kg,

            "annual_fuel_impact_tonnes":
                annual_fuel_impact_tonnes,

            "annual_fuel_impact_type":
                annual_fuel_impact_type,

            "annual_cost_impact":
                np.nan,
        },

        "voyage_summary":
            voyage_summary,

        "daily":
            daily,

        "measurements":
            measurement_df,

        "dosing":
            dosing_df,

            
        }
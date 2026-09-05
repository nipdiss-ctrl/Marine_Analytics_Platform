
import re
from io import BytesIO

import pandas as pd
from django.db import transaction

from ..models import ChemicalDosing


# =========================================================
# TEXT HELPERS
# =========================================================

def _clean_text(value, default=""):
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
        "nat",
        "n/a",
        "na",
    }:
        return default

    return value


def _normalise_voyage(value):
    value = _clean_text(value, "UNKNOWN")

    if value == "UNKNOWN":
        return value

    value = re.sub(r"\s+", " ", value)

    return value.upper()


# =========================================================
# NUMERIC HELPER
# =========================================================

def _safe_float(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        value = str(value).strip()

        if not value:
            return None

        value = value.replace(",", "")

        return float(value)

    except (TypeError, ValueError):
        return None


# =========================================================
# COLUMN NORMALISATION
# =========================================================

def _normalise_column_name(value):
    value = _clean_text(value)

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _find_column(df, possible_names):
    if df is None or df.empty:
        return None

    normalised = {}

    for column in df.columns:

        key = _normalise_column_name(column)

        normalised[key] = column

    # Exact normalised match
    for name in possible_names:

        key = _normalise_column_name(name)

        if key in normalised:
            return normalised[key]

    # Partial match
    for column in df.columns:

        column_key = _normalise_column_name(column)

        for name in possible_names:

            name_key = _normalise_column_name(name)

            if (
                name_key
                and name_key in column_key
            ):
                return column

    return None


# =========================================================
# FIND HEADER ROW
# =========================================================

def _find_header_row(raw_df):
    """
    Find the actual table header.

    We deliberately inspect more rows because the dosing
    workbook may have title/information rows above the table.
    """

    if raw_df is None or raw_df.empty:
        return None

    date_words = {
        "date",
        "day",
        "report date",
        "dosing date",
    }

    additive_words = {
        "morning",
        "evening",
        "additive",
        "dosing",
        "chemical",
    }

    fuel_words = {
        "fuel",
        "quantity",
        "qty",
    }

    best_row = None
    best_score = -1

    max_rows = min(
        len(raw_df),
        60,
    )

    for index in range(max_rows):

        values = [
            _normalise_column_name(value)
            for value in raw_df.iloc[index].tolist()
        ]

        values = [
            value
            for value in values
            if value
        ]

        if not values:
            continue

        score = 0

        joined = " ".join(values)

        # Date
        if any(
            word in joined
            for word in date_words
        ):
            score += 5

        # Additive / dosing
        if any(
            word in joined
            for word in additive_words
        ):
            score += 3

        # Fuel
        if any(
            word in joined
            for word in fuel_words
        ):
            score += 2

        if score > best_score:

            best_score = score
            best_row = index

    return best_row


# =========================================================
# READ ONE SHEET
# =========================================================

def _read_dosing_sheet(
    excel_buffer,
    sheet_name,
):
    """
    Read one complete dosing worksheet.
    """

    try:
        excel_buffer.seek(0)

        raw_df = pd.read_excel(
            excel_buffer,
            sheet_name=sheet_name,
            header=None,
        )

    except Exception as exc:

        print(
            f"[DOSING] ERROR reading "
            f"sheet '{sheet_name}': {exc}"
        )

        return pd.DataFrame()

    if raw_df.empty:
        return pd.DataFrame()

    header_row = _find_header_row(
        raw_df
    )

    if header_row is None:

        print(
            f"[DOSING] WARNING: Could not "
            f"find header in '{sheet_name}'"
        )

        return pd.DataFrame()

    print(
        f"[DOSING] Sheet '{sheet_name}' "
        f"header row = {header_row}"
    )

    try:

        excel_buffer.seek(0)

        df = pd.read_excel(
            excel_buffer,
            sheet_name=sheet_name,
            header=header_row,
        )

    except Exception as exc:

        print(
            f"[DOSING] ERROR re-reading "
            f"'{sheet_name}': {exc}"
        )

        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Clean column names
    cleaned = []

    for column in df.columns:

        value = _clean_text(
            column
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        cleaned.append(
            value
        )

    df.columns = cleaned

    # Preserve source sheet
    df["_voyage"] = _normalise_voyage(
        sheet_name
    )

    return df


# =========================================================
# CONVERT ONE SHEET
# =========================================================

def _convert_sheet(
    df,
    sheet_name,
):
    """
    Convert one worksheet into standard dosing data.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    date_column = _find_column(
        df,
        [
            "date",
            "day",
            "report date",
            "dosing date",
            "date of dosing",
            "date/time",
            "datetime",
        ],
    )

    if date_column is None:

        print(
            f"[DOSING] WARNING: No date "
            f"column found in '{sheet_name}'."
        )

        print(
            "[DOSING] Columns:"
        )

        for column in df.columns:
            print(
                f"    {column}"
            )

        return pd.DataFrame()

    result = pd.DataFrame(
        index=df.index
    )

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    result["date"] = pd.to_datetime(
        df[date_column],
        errors="coerce",
        dayfirst=True,
    )

    result["date"] = (
        result["date"]
        .dt.normalize()
    )

    # -----------------------------------------------------
    # VOYAGE
    # -----------------------------------------------------

    result["voyage"] = (
        _normalise_voyage(
            sheet_name
        )
    )

    # -----------------------------------------------------
    # MORNING
    # -----------------------------------------------------

    morning_column = _find_column(
        df,
        [
            "morning additive",
            "morning dosing",
            "morning dose",
            "morning",
            "am additive",
            "am dosing",
            "am dose",
        ],
    )

    if morning_column is not None:

        result["morning_additive"] = (
            df[morning_column]
            .map(_safe_float)
        )

    else:

        result["morning_additive"] = None

    # -----------------------------------------------------
    # EVENING
    # -----------------------------------------------------

    evening_column = _find_column(
        df,
        [
            "evening additive",
            "evening dosing",
            "evening dose",
            "evening",
            "pm additive",
            "pm dosing",
            "pm dose",
        ],
    )

    if evening_column is not None:

        result["evening_additive"] = (
            df[evening_column]
            .map(_safe_float)
        )

    else:

        result["evening_additive"] = None

    # -----------------------------------------------------
    # TOTAL ADDITIVE
    # -----------------------------------------------------

    total_column = _find_column(
        df,
        [
            "total additive",
            "total dosing",
            "total dose",
            "total chemical",
            "chemical used",
            "additive used",
            "daily additive",
        ],
    )

    if total_column is not None:

        result["total_additive"] = (
            df[total_column]
            .map(_safe_float)
        )

    else:

        morning = pd.to_numeric(
            result["morning_additive"],
            errors="coerce",
        ).fillna(0)

        evening = pd.to_numeric(
            result["evening_additive"],
            errors="coerce",
        ).fillna(0)

        result["total_additive"] = (
            morning + evening
        )

    # -----------------------------------------------------
    # FUEL
    # -----------------------------------------------------

    fuel_column = _find_column(
        df,
        [
            "total fuel qty",
            "total fuel quantity",
            "fuel quantity",
            "fuel qty",
            "total fuel",
            "fuel consumption",
            "fuel",
        ],
    )

    if fuel_column is not None:

        result["total_fuel_qty"] = (
            df[fuel_column]
            .map(_safe_float)
        )

    else:

        result["total_fuel_qty"] = None

    # -----------------------------------------------------
    # CHEMICAL ROB
    # -----------------------------------------------------

    rob_column = _find_column(
        df,
        [
            "chemical rob",
            "chemical r.o.b",
            "chemical remaining",
            "chemical balance",
            "remaining chemical",
            "rob",
        ],
    )

    if rob_column is not None:

        result["chemical_rob"] = (
            df[rob_column]
            .map(_safe_float)
        )

    else:

        result["chemical_rob"] = None

    # -----------------------------------------------------
    # REMARKS
    # -----------------------------------------------------

    remarks_column = _find_column(
        df,
        [
            "remarks",
            "remark",
            "comments",
            "comment",
            "notes",
        ],
    )

    if remarks_column is not None:

        result["remarks"] = (
            df[remarks_column]
            .map(
                lambda value:
                _clean_text(value)
            )
        )

    else:

        result["remarks"] = ""

    # -----------------------------------------------------
    # REMOVE INVALID DATES
    # -----------------------------------------------------

    result = result.dropna(
        subset=["date"]
    ).copy()

    if result.empty:
        return pd.DataFrame()

    # -----------------------------------------------------
    # REMOVE FUTURE DATES
    # -----------------------------------------------------

    today = (
        pd.Timestamp.today()
        .normalize()
    )

    result = result[
        result["date"] <= today
    ].copy()

    if result.empty:
        return pd.DataFrame()

    # -----------------------------------------------------
    # DEBUG AUGUST
    # -----------------------------------------------------

    august = result[
        result["date"].dt.month == 8
    ]

    if not august.empty:

        print(
            f"[DOSING] {sheet_name}: "
            f"{len(august)} August rows detected."
        )

        print(
            august[
                [
                    "date",
                    "morning_additive",
                    "evening_additive",
                    "total_additive",
                ]
            ].tail(10).to_string(
                index=False
            )
        )

    return result


# =========================================================
# GET MODEL FIELDS
# =========================================================

def _get_model_fields():
    return {
        field.name
        for field in ChemicalDosing._meta.get_fields()
        if hasattr(field, "name")
    }


# =========================================================
# IMPORT DOSING LOG
# =========================================================

def import_dosing_log(
    dosing_file,
    vessel,
    import_history=None,
):
    """
    Import ALL sheets from the dosing workbook.

    The important behaviour is:

        workbook
          |
          +-- voyage sheet 1
          |
          +-- voyage sheet 2
          |
          +-- voyage sheet 3
          |
          +-- ...
          |
          +-- all converted to common format
          |
          +-- database update

    If the database has a voyage field, records are kept
    separately by:

        vessel + date + voyage

    If the database DOES NOT have a voyage field, records
    are combined by date because the model can only store
    one dosing row per vessel/date.
    """

    try:

        # =================================================
        # VESSEL
        # =================================================

        vessel = _clean_text(
            vessel
        ).upper()

        if not vessel:

            return {
                "success": False,
                "message":
                    "Vessel was not provided.",
            }

        # =================================================
        # FILE
        # =================================================

        if hasattr(
            dosing_file,
            "seek",
        ):
            dosing_file.seek(0)

        if hasattr(
            dosing_file,
            "read",
        ):

            file_bytes = (
                dosing_file.read()
            )

        else:

            file_bytes = dosing_file

        if not file_bytes:

            return {
                "success": False,
                "message":
                    "Empty dosing file.",
            }

        excel_buffer = BytesIO(
            file_bytes
        )

        # =================================================
        # WORKBOOK
        # =================================================

        workbook = pd.ExcelFile(
            excel_buffer
        )

        sheet_names = (
            workbook.sheet_names
        )

        print("\n")
        print("=" * 80)
        print("DOSING WORKBOOK IMPORT")
        print("=" * 80)
        print(
            f"Vessel: {vessel}"
        )
        print(
            f"Sheets found: {len(sheet_names)}"
        )

        for sheet in sheet_names:
            print(
                f"  -> {sheet}"
            )

        # =================================================
        # READ ALL SHEETS
        # =================================================

        all_frames = []
        sheets_read = []

        for sheet_name in sheet_names:

            print("\n" + "-" * 70)
            print(
                f"PROCESSING SHEET: {sheet_name}"
            )
            print("-" * 70)

            raw_df = _read_dosing_sheet(
                excel_buffer,
                sheet_name,
            )

            if raw_df.empty:

                print(
                    "  No usable table found."
                )

                continue

            converted = _convert_sheet(
                raw_df,
                sheet_name,
            )

            if converted.empty:

                print(
                    "  No valid dated rows."
                )

                continue

            all_frames.append(
                converted
            )

            sheets_read.append(
                sheet_name
            )

            print(
                f"  Valid rows: "
                f"{len(converted)}"
            )

        # =================================================
        # NO DATA
        # =================================================

        if not all_frames:

            return {
                "success": False,
                "message": (
                    "No valid dosing records "
                    "were found in any sheet."
                ),
                "all_sheets":
                    sheet_names,
            }

        # =================================================
        # COMBINE SHEETS
        # =================================================

        df = pd.concat(
            all_frames,
            ignore_index=True,
        )

        df = df.sort_values(
            [
                "date",
                "voyage",
            ]
        ).reset_index(
            drop=True
        )

        print("\n")
        print(
            f"TOTAL ROWS FROM ALL SHEETS: "
            f"{len(df)}"
        )

        # =================================================
        # MODEL FIELDS
        # =================================================

        model_fields = (
            _get_model_fields()
        )

        print(
            "\nChemicalDosing fields:"
        )

        print(
            sorted(model_fields)
        )

        # =================================================
        # VOYAGE FIELD
        # =================================================

        voyage_field = None

        for candidate in [
            "voyage",
            "voyage_name",
            "sheet_name",
            "source_sheet",
            "excel_sheet",
            "sheet",
            "sheetname",
            "source_voyage",
        ]:

            if candidate in model_fields:

                voyage_field = candidate
                break

        print(
            f"Voyage field: {voyage_field}"
        )

        # =================================================
        # CRITICAL CASE:
        #
        # NO VOYAGE FIELD
        #
        # If the model is unique by vessel/date,
        # two sheets cannot create two rows for one day.
        #
        # Therefore combine the sheets by date.
        # =================================================

        if voyage_field is None:

            print(
                "\n[DOSING] Model has no voyage field."
            )

            print(
                "[DOSING] Combining all sheets by date."
            )

            numeric_columns = [
                "morning_additive",
                "evening_additive",
                "total_additive",
                "total_fuel_qty",
            ]

            grouped_rows = []

            for date_value, group in df.groupby(
                "date",
                sort=True,
            ):

                row = {
                    "date":
                        date_value,
                    "voyage":
                        "MULTI-SHEET",
                }

                # -------------------------------------------------
                # ADDITIVE
                # -------------------------------------------------

                for column in [
                    "morning_additive",
                    "evening_additive",
                    "total_additive",
                ]:

                    values = pd.to_numeric(
                        group[column],
                        errors="coerce",
                    ).dropna()

                    if not values.empty:
                        row[column] = float(
                            values.sum()
                        )
                    else:
                        row[column] = None

                # -------------------------------------------------
                # FUEL
                # -------------------------------------------------

                fuel_values = pd.to_numeric(
                    group["total_fuel_qty"],
                    errors="coerce",
                ).dropna()

                if not fuel_values.empty:

                    row["total_fuel_qty"] = float(
                        fuel_values.sum()
                    )

                else:

                    row["total_fuel_qty"] = None

                # -------------------------------------------------
                # ROB
                #
                # For ROB, use the last available value.
                # -------------------------------------------------

                rob_values = group[
                    "chemical_rob"
                ].dropna()

                if not rob_values.empty:

                    row["chemical_rob"] = (
                        _safe_float(
                            rob_values.iloc[-1]
                        )
                    )

                else:

                    row["chemical_rob"] = None

                # -------------------------------------------------
                # REMARKS
                # -------------------------------------------------

                remarks = []

                for value in group[
                    "remarks"
                ]:

                    text = _clean_text(
                        value
                    )

                    if text:
                        remarks.append(
                            text
                        )

                row["remarks"] = (
                    " | ".join(
                        dict.fromkeys(
                            remarks
                        )
                    )
                )

                grouped_rows.append(
                    row
                )

            df = pd.DataFrame(
                grouped_rows
            )

            print(
                f"[DOSING] After date "
                f"combination: {len(df)} rows"
            )

        # =================================================
        # UPDATE / CREATE
        # =================================================

        created = 0
        updated = 0
        failed = 0

        august_created = 0
        august_updated = 0

        with transaction.atomic():

            for _, row in df.iterrows():

                date_value = row.get(
                    "date"
                )

                if pd.isna(
                    date_value
                ):
                    continue

                date_value = (
                    pd.Timestamp(
                        date_value
                    ).date()
                )

                field_data = {
                    "vessel": vessel,
                    "date": date_value,
                }

                # -------------------------------------------------
                # VOYAGE
                # -------------------------------------------------

                if voyage_field:

                    field_data[
                        voyage_field
                    ] = _normalise_voyage(
                        row.get(
                            "voyage"
                        )
                    )

                # -------------------------------------------------
                # OPTIONAL FIELDS
                # -------------------------------------------------

                optional = {

                    "morning_additive":
                        row.get(
                            "morning_additive"
                        ),

                    "evening_additive":
                        row.get(
                            "evening_additive"
                        ),

                    "total_additive":
                        row.get(
                            "total_additive"
                        ),

                    "total_fuel_qty":
                        row.get(
                            "total_fuel_qty"
                        ),

                    "chemical_rob":
                        row.get(
                            "chemical_rob"
                        ),

                    "remarks":
                        row.get(
                            "remarks"
                        ),
                }

                for field_name, value in optional.items():

                    if field_name not in model_fields:
                        continue

                    # Convert NaN to None
                    if isinstance(
                        value,
                        float,
                    ) and pd.isna(value):

                        value = None

                    field_data[
                        field_name
                    ] = value

                # -------------------------------------------------
                # IMPORT HISTORY
                # -------------------------------------------------

                if (
                    import_history is not None
                    and
                    "import_history"
                    in model_fields
                ):

                    field_data[
                        "import_history"
                    ] = import_history

                # -------------------------------------------------
                # LOOKUP
                # -------------------------------------------------

                lookup = {
                    "vessel":
                        vessel,
                    "date":
                        date_value,
                }

                if voyage_field:

                    lookup[
                        voyage_field
                    ] = field_data[
                        voyage_field
                    ]

                # -------------------------------------------------
                # CREATE OR UPDATE
                # -------------------------------------------------

                try:

                    obj, was_created = (
                        ChemicalDosing.objects
                        .update_or_create(
                            **lookup,
                            defaults={
                                key: value
                                for key, value
                                in field_data.items()
                                if key not in lookup
                            },
                        )
                    )

                    if was_created:

                        created += 1

                        if date_value.month == 8:

                            august_created += 1

                    else:

                        updated += 1

                        if date_value.month == 8:

                            august_updated += 1

                except Exception as exc:

                    failed += 1

                    print(
                        "[DOSING] FAILED:"
                        f" {date_value} "
                        f"{row.get('voyage')}: "
                        f"{exc}"
                    )

        # =================================================
        # AUGUST CHECK
        # =================================================

        august_df = df[
            pd.to_datetime(
                df["date"],
                errors="coerce",
            ).dt.month == 8
        ]

        print("\n")
        print("=" * 80)
        print("AUGUST DOSING CHECK")
        print("=" * 80)

        print(
            f"August rows processed: "
            f"{len(august_df)}"
        )

        if not august_df.empty:

            print(
                august_df[
                    [
                        "date",
                        "voyage",
                        "morning_additive",
                        "evening_additive",
                        "total_additive",
                    ]
                ].tail(20).to_string(
                    index=False
                )
            )

        # =================================================
        # DATABASE CHECK
        # =================================================

        db_count = (
            ChemicalDosing.objects
            .filter(
                vessel=vessel,
                date__month=8,
            )
            .count()
        )

        print(
            f"\nAugust records currently "
            f"in database for {vessel}: "
            f"{db_count}"
        )

        # =================================================
        # RESULT
        # =================================================

        print("\n")
        print("=" * 80)
        print("DOSING IMPORT COMPLETE")
        print("=" * 80)

        print(
            f"Sheets found: "
            f"{len(sheet_names)}"
        )

        print(
            f"Sheets read: "
            f"{len(sheets_read)}"
        )

        print(
            f"Rows processed: "
            f"{len(df)}"
        )

        print(
            f"Created: "
            f"{created}"
        )

        print(
            f"Updated: "
            f"{updated}"
        )

        print(
            f"Failed: "
            f"{failed}"
        )

        print(
            f"August created: "
            f"{august_created}"
        )

        print(
            f"August updated: "
            f"{august_updated}"
        )

        print(
            f"August DB records: "
            f"{db_count}"
        )

        print(
            "=" * 80
        )

        return {

            "success":
                True,

            "vessel":
                vessel,

            "total_rows":
                len(df),

            "new_rows":
                created,

            "created_rows":
                created,

            "updated_rows":
                updated,

            "failed_rows":
                failed,

            "august_rows":
                len(august_df),

            "august_created":
                august_created,

            "august_updated":
                august_updated,

            "august_database_rows":
                db_count,

            "sheets":
                sheets_read,

            "all_sheets":
                sheet_names,

            "voyage_field":
                voyage_field,

            "voyages":
                sorted(
                    {
                        _normalise_voyage(
                            value
                        )
                        for value in df[
                            "voyage"
                        ].dropna()
                    }
                ),

            "start":
                df["date"].min(),

            "end":
                df["date"].max(),

            "message": (
                "Dosing workbook imported. "
                f"Processed {len(sheets_read)} "
                f"of {len(sheet_names)} sheets. "
                f"Created {created}, "
                f"updated {updated}."
            ),
        }

    except Exception as exc:

        print("\n")
        print("=" * 80)
        print("DOSING IMPORT ERROR")
        print("=" * 80)
        print(
            repr(exc)
        )
        print("=" * 80)

        return {
            "success":
                False,

            "message": (
                "Error importing dosing "
                f"data: {exc}"
            ),
        }


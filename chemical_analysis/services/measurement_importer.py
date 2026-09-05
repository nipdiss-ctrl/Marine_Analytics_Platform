
import pandas as pd

from django.db import transaction

from chemical_analysis.models import ChemicalMeasurement


# =========================================================
# HELPERS
# =========================================================

def _normalise_voyage(value):
    """
    Convert an Excel worksheet name into a clean voyage name.
    """
    if value is None:
        return "UNKNOWN"

    voyage = str(value).strip()

    if not voyage or voyage.lower() == "nan":
        return "UNKNOWN"

    return voyage.upper()


def _safe_float(row, column):
    """
    Safely convert a dataframe value to float.
    """
    if column not in row.index:
        return None

    value = row.get(column)

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_columns(df):
    """
    Normalise column whitespace/case so METIS column names
    remain compatible even when Excel contains extra spaces.
    """

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    return df


# =========================================================
# IMPORT METIS MEASUREMENTS
# =========================================================

def import_measurements(
    file,
    import_history=None,
):
    """
    Import METIS measurement data.

    Excel:
        ALL worksheets are read.

        Worksheet name = voyage.

        Example:
            Sheet '103B2' -> voyage '103B2'
            Sheet '103L'  -> voyage '103L'

    CSV:
        Single CSV file.
        Voyage defaults to UNKNOWN.

    Database identity:
        vessel + timestamp

    Important:
        Voyage is metadata attached to the measurement.
        We do NOT change the existing database uniqueness rule
        yet.
    """

    try:

        # =====================================================
        # FILE INFORMATION
        # =====================================================

        filename = getattr(
            file,
            "name",
            "",
        ).lower()

        sheet_names = []
        dataframes = []

        # =====================================================
        # EXCEL
        # =====================================================

        if filename.endswith(
            (".xlsx", ".xls")
        ):

            # -------------------------------------------------
            # IMPORTANT:
            # Create ExcelFile once.
            # -------------------------------------------------

            try:
                file.seek(0)
            except Exception:
                pass

            excel_file = pd.ExcelFile(file)

            sheet_names = list(
                excel_file.sheet_names
            )

            print()
            print("=" * 80)
            print("METIS MEASUREMENT IMPORT")
            print("=" * 80)
            print(
                "Workbook:",
                getattr(file, "name", "unknown"),
            )
            print(
                "Sheets found:",
                sheet_names,
            )
            print("=" * 80)

            # -------------------------------------------------
            # READ EVERY SHEET
            # -------------------------------------------------

            for sheet_name in sheet_names:

                voyage = _normalise_voyage(
                    sheet_name
                )

                try:

                    print()
                    print(
                        f"Reading sheet: "
                        f"'{sheet_name}'"
                    )

                    sheet_df = pd.read_excel(
                        excel_file,
                        sheet_name=sheet_name,
                    )

                    if sheet_df is None:
                        print(
                            "  -> Empty result"
                        )
                        continue

                    if sheet_df.empty:
                        print(
                            "  -> Empty sheet"
                        )
                        continue

                    sheet_df = _normalise_columns(
                        sheet_df
                    )

                    # -----------------------------------------
                    # STORE SOURCE INFORMATION
                    # -----------------------------------------

                    sheet_df["_source_sheet"] = (
                        str(sheet_name)
                    )

                    sheet_df["_voyage"] = voyage

                    dataframes.append(
                        sheet_df
                    )

                    print(
                        f"  -> Voyage: {voyage}"
                    )

                    print(
                        f"  -> Rows: "
                        f"{len(sheet_df)}"
                    )

                    print(
                        f"  -> Columns: "
                        f"{len(sheet_df.columns)}"
                    )

                except Exception as exc:

                    print(
                        f"  -> ERROR reading "
                        f"'{sheet_name}': "
                        f"{exc}"
                    )

            print()
            print("-" * 80)
            print("SHEET SUMMARY")

            for df_sheet in dataframes:

                voyage = (
                    df_sheet["_voyage"]
                    .iloc[0]
                )

                print(
                    f"Voyage {voyage}: "
                    f"{len(df_sheet)} rows"
                )

            print("-" * 80)

        # =====================================================
        # CSV
        # =====================================================

        elif filename.endswith(".csv"):

            try:
                file.seek(0)
            except Exception:
                pass

            df = pd.read_csv(file)

            if not df.empty:

                df = _normalise_columns(df)

                df["_source_sheet"] = ""
                df["_voyage"] = "UNKNOWN"

                dataframes.append(df)

        # =====================================================
        # UNSUPPORTED
        # =====================================================

        else:

            return {
                "success": False,
                "message": (
                    "Unsupported file type. "
                    "Please upload CSV or Excel."
                ),
            }

        # =====================================================
        # NO DATA
        # =====================================================

        if not dataframes:

            return {
                "success": False,
                "message": (
                    "The uploaded file contains "
                    "no readable measurement data."
                ),
            }

        # =====================================================
        # COMBINE ALL SHEETS
        # =====================================================

        df = pd.concat(
            dataframes,
            ignore_index=True,
        )

        if df.empty:

            return {
                "success": False,
                "message": (
                    "No measurement data was found "
                    "in the uploaded worksheets."
                ),
            }

        df = _normalise_columns(df)

        # =====================================================
        # EXPECTED METIS COLUMNS
        # =====================================================

        column_map = {

            "Timestamp (UTC)": "timestamp",

            "Main Engine Fuel Load % - Instant (%)":
                "fuel_load",

            "Main Engine Fuel Oil Inlet Mass Flow -   Instant (kg/hr)":
                "fuel_inlet",

            "Main Engine Fuel Oil Outlet Mass Flow -   Instant (kg/hr)":
                "fuel_outlet",

            "Main Engine Rotational Speed - Instant (rpm)":
                "rpm",

            "Vessel Hull Through Water Longitudinal Speed   - Instant (knots)":
                "speed",

            "Vessel   Propeller Shaft Mechanical Power - Instant (KW)":
                "power",
        }

        # =====================================================
        # NORMALISE COLUMN NAMES
        # =====================================================

        normalized_columns = {}

        for column in df.columns:

            normalized = (
                " ".join(
                    str(column).split()
                )
                .strip()
                .lower()
            )

            normalized_columns[
                normalized
            ] = column

        rename_map = {}

        for expected, new_name in column_map.items():

            normalized_expected = (
                " ".join(
                    expected.split()
                )
                .strip()
                .lower()
            )

            original_column = (
                normalized_columns.get(
                    normalized_expected
                )
            )

            if original_column is not None:

                rename_map[
                    original_column
                ] = new_name

        df = df.rename(
            columns=rename_map
        )

        # =====================================================
        # TIMESTAMP
        # =====================================================

        if "timestamp" not in df.columns:

            return {
                "success": False,
                "message": (
                    "Could not find the METIS Timestamp "
                    "column.\n\n"
                    f"Columns found: "
                    f"{list(df.columns)}"
                ),
            }

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            errors="coerce",
            utc=True,
        )

        df = df.dropna(
            subset=["timestamp"]
        )

        if df.empty:

            return {
                "success": False,
                "message": (
                    "No valid METIS timestamps "
                    "were found."
                ),
            }

        # =====================================================
        # VESSEL
        # =====================================================

        vessel = getattr(
            file,
            "vessel",
            None,
        )

        if not vessel:

            return {
                "success": False,
                "message": (
                    "Vessel name is required."
                ),
            }

        vessel = (
            str(vessel)
            .strip()
            .upper()
        )

        # =====================================================
        # VOYAGE
        # =====================================================

        if "_voyage" not in df.columns:

            df["_voyage"] = "UNKNOWN"

        df["_voyage"] = (
            df["_voyage"]
            .fillna("UNKNOWN")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        df.loc[
            df["_voyage"].isin(
                ["", "NAN", "NONE"]
            ),
            "_voyage",
        ] = "UNKNOWN"

        # =====================================================
        # NUMERIC COLUMNS
        # =====================================================

        numeric_columns = [
            "fuel_load",
            "fuel_inlet",
            "fuel_outlet",
            "rpm",
            "speed",
            "power",
        ]

        for column in numeric_columns:

            if column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        # =====================================================
        # DUPLICATES INSIDE THE UPLOAD
        # =====================================================

        # Same timestamp within the same voyage
        # = duplicate.
        #
        # We deliberately keep voyage here so that
        # different worksheet/voyage records are not
        # accidentally removed during dataframe cleaning.

        df = df.drop_duplicates(
            subset=[
                "timestamp",
                "_voyage",
            ],
            keep="last",
        )

        # =====================================================
        # VOYAGE SUMMARY
        # =====================================================

        voyage_summary = (
            df.groupby(
                "_voyage",
                dropna=False,
            )
            .size()
            .to_dict()
        )

        print()
        print("=" * 80)
        print("COMBINED METIS DATA")
        print("=" * 80)
        print(
            "Total rows after cleaning:",
            len(df),
        )

        print(
            "Voyages:"
        )

        for voyage, count in sorted(
            voyage_summary.items(),
            key=lambda item: str(item[0]),
        ):

            print(
                f"  {voyage}: {count} rows"
            )

        print("=" * 80)

        # =====================================================
        # EXISTING DATABASE RECORDS
        # =====================================================

        timestamps = (
            df["timestamp"]
            .tolist()
        )

        existing_records = {}

        chunk_size = 500

        for i in range(
            0,
            len(timestamps),
            chunk_size,
        ):

            timestamp_chunk = (
                timestamps[
                    i:i + chunk_size
                ]
            )

            rows = (
                ChemicalMeasurement.objects
                .filter(
                    vessel=vessel,
                    timestamp__in=timestamp_chunk,
                )
                .values(
                    "timestamp",
                    "voyage",
                )
            )

            for row in rows:

                existing_records[
                    row["timestamp"]
                ] = row["voyage"]

        # =====================================================
        # SPLIT NEW / EXISTING
        # =====================================================

        new_rows = []
        update_rows = []

        skipped_count = 0

        for _, row in df.iterrows():

            timestamp = (
                row["timestamp"]
            )

            voyage = _normalise_voyage(
                row["_voyage"]
            )

            existing_voyage = (
                existing_records.get(
                    timestamp
                )
            )

            # -------------------------------------------------
            # NEW
            # -------------------------------------------------

            if existing_voyage is None:

                new_rows.append(row)

                continue

            # -------------------------------------------------
            # EXISTING UNKNOWN -> KNOWN VOYAGE
            # -------------------------------------------------

            if (
                str(existing_voyage)
                .strip()
                .upper()
                == "UNKNOWN"
                and voyage != "UNKNOWN"
            ):

                update_rows.append(
                    (
                        timestamp,
                        voyage,
                    )
                )

                continue

            # -------------------------------------------------
            # EXISTING KNOWN
            # -------------------------------------------------

            skipped_count += 1

        # =====================================================
        # CREATE NEW OBJECTS
        # =====================================================

        objects = []

        for row in new_rows:

            objects.append(
                ChemicalMeasurement(
                    vessel=vessel,

                    voyage=_normalise_voyage(
                        row["_voyage"]
                    ),

                    timestamp=(
                        row["timestamp"]
                        .to_pydatetime()
                    ),

                    fuel_load=_safe_float(
                        row,
                        "fuel_load",
                    ),

                    fuel_inlet=_safe_float(
                        row,
                        "fuel_inlet",
                    ),

                    fuel_outlet=_safe_float(
                        row,
                        "fuel_outlet",
                    ),

                    rpm=_safe_float(
                        row,
                        "rpm",
                    ),

                    speed=_safe_float(
                        row,
                        "speed",
                    ),

                    power=_safe_float(
                        row,
                        "power",
                    ),

                    import_history=(
                        import_history
                    ),
                )
            )

        # =====================================================
        # INSERT / UPDATE
        # =====================================================

        with transaction.atomic():

            # -------------------------------------------------
            # INSERT NEW RECORDS
            # -------------------------------------------------

            if objects:

                ChemicalMeasurement.objects.bulk_create(
                    objects,
                    batch_size=1000,
                    ignore_conflicts=True,
                )

            # -------------------------------------------------
            # UPDATE UNKNOWN VOYAGES
            # -------------------------------------------------

            updated_count = 0

            for timestamp, voyage in update_rows:

                updated = (
                    ChemicalMeasurement.objects
                    .filter(
                        vessel=vessel,
                        timestamp=timestamp,
                        voyage="UNKNOWN",
                    )
                    .update(
                        voyage=voyage,
                        import_history=import_history,
                    )
                )

                updated_count += updated

        # =====================================================
        # FINAL COUNTS
        # =====================================================

        inserted_count = len(objects)

        # Some bulk_create records may have been ignored
        # because another process inserted them meanwhile.
        #
        # The database remains protected by the unique
        # vessel + timestamp constraint.

        total_processed = (
            inserted_count
            + updated_count
            + skipped_count
        )

        print()
        print("=" * 80)
        print("IMPORT RESULT")
        print("=" * 80)
        print(
            "Rows processed:",
            len(df),
        )
        print(
            "New rows:",
            inserted_count,
        )
        print(
            "Voyage corrections:",
            updated_count,
        )
        print(
            "Skipped existing:",
            skipped_count,
        )
        print()
        print(
            "Voyages in uploaded file:"
        )

        for voyage, count in sorted(
            voyage_summary.items(),
            key=lambda item: str(item[0]),
        ):

            print(
                f"  {voyage}: {count}"
            )

        print("=" * 80)

        # =====================================================
        # RESULT
        # =====================================================

        return {

            "success": True,

            "vessel": vessel,

            "total_rows": len(df),

            "new_rows": inserted_count,

            "updated_rows": updated_count,

            "skipped_rows": skipped_count,

            "start": df[
                "timestamp"
            ].min(),

            "end": df[
                "timestamp"
            ].max(),

            "sheets": sheet_names,

            "voyages": {
                str(k): int(v)
                for k, v
                in voyage_summary.items()
            },

            "message": (
                "Measurement data imported successfully. "
                f"Sheets read: {', '.join(sheet_names)}. "
                f"Voyages found: "
                f"{', '.join(map(str, voyage_summary.keys()))}."
            ),
        }

    except Exception as exc:

        print()
        print("=" * 80)
        print("METIS IMPORT ERROR")
        print("=" * 80)
        print(
            repr(exc)
        )
        print("=" * 80)

        return {

            "success": False,

            "message": (
                "Error importing measurement "
                f"data: {exc}"
            ),
        }


from datetime import datetime
from pathlib import Path
import re

import pandas as pd

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from scoc_monitoring.models import (
    VoyageLeg,
    VoyageObservation,
)


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None or pd.isna(value):
        return ""

    return " ".join(
        str(value).strip().split()
    )


def clean_number(value):
    """
    Convert Excel numeric values to float.

    Handles:
        12
        12.5
        "12.5"
        "12,5"
        empty / NaN
    """
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    text = text.replace(",", ".")

    # Remove common units if they appear in text.
    text = re.sub(
        r"(kn|kt|kts|mt/day|mt|kw|rpm|nm|m)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    """
    Convert Excel timestamp to timezone-aware datetime.
    """

    if value is None or pd.isna(value):
        return None

    dt = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(dt):
        return None

    dt = dt.to_pydatetime()

    if timezone.is_naive(dt):
        dt = timezone.make_aware(
            dt,
            timezone.get_current_timezone(),
        )

    return dt


def normalise(value):
    return clean_text(value).upper()


def get_column(df, name):
    """
    Find a column case-insensitively.
    """

    wanted = normalise(name)

    for column in df.columns:

        if normalise(column) == wanted:
            return column

    return None


def get_first_column(df, names):
    """
    Return the first matching column from a list of alternatives.
    """

    for name in names:

        column = get_column(
            df,
            name,
        )

        if column is not None:
            return column

    return None


def parse_pasted_message(message):
    """
    Basic extraction from a pasted noon report.

    The Excel remains the primary source.

    This function is deliberately tolerant because noon
    messages can have different formats.
    """

    if not message:
        return {}

    result = {}

    patterns = {

        "distance_to_go": [
            r"distance\s*(?:to\s*)?go\s*[:=]\s*([\d.,]+)",
            r"dtg\s*[:=]\s*([\d.,]+)",
            r"distance\s*to\s*go\s*[:=]?\s*([\d.,]+)",
        ],

        "hsfo_rob": [
            r"hsfo\s*(?:rob|on\s*board)?\s*[:=]\s*([\d.,]+)",
        ],

        "lsfo_rob": [
            r"lsfo\s*(?:rob|on\s*board)?\s*[:=]\s*([\d.,]+)",
        ],

        "mgo_rob": [
            r"mgo\s*(?:rob|on\s*board)?\s*[:=]\s*([\d.,]+)",
        ],

        "power_kw": [
            r"(?:me\s*)?power\s*[:=]\s*([\d.,]+)",
            r"power\s*\(kw\)\s*[:=]\s*([\d.,]+)",
        ],

        "rpm": [
            r"rpm\s*[:=]\s*([\d.,]+)",
        ],

        "cylinder_oil_consumption_l": [
            r"(?:cylinder\s*)?oil\s*(?:consumption|cons)\s*[:=]\s*([\d.,]+)",
            r"cyl(?:inder)?\s*oil\s*[:=]\s*([\d.,]+)",
        ],

        "running_hours": [
            r"running\s*hours\s*[:=]\s*([\d.,]+)",
            r"me\s*running\s*hours\s*[:=]\s*([\d.,]+)",
        ],
    }

    for field, field_patterns in patterns.items():

        for pattern in field_patterns:

            match = re.search(
                pattern,
                message,
                flags=re.IGNORECASE,
            )

            if match:

                result[field] = clean_number(
                    match.group(1)
                )

                break

    return result


def find_spire_header(file_path):
    """
    Locate the actual header row.

    The Spire workbook currently has:

        row 1 = copyright
        rows 2-3 = blank
        row 4 = actual headers

    Therefore pandas header=3.

    We still detect it dynamically so the importer is
    not unnecessarily dependent on exactly four rows.
    """

    preview = pd.read_excel(
        file_path,
        sheet_name="weatherNoonReport",
        header=None,
        nrows=15,
    )

    for index, row in preview.iterrows():

        values = [
            normalise(value)
            for value in row.tolist()
            if clean_text(value)
        ]

        required = {
            "REPORTED TIME (UTC)",
            "LOAD",
            "DEPARTURE",
            "DESTINATION",
        }

        if required.issubset(set(values)):

            return index

    return None


def calculate_scoc(
    oil_consumption_l,
    power_kw,
    running_hours,
    density_kg_l=0.93,
):
    """
    SCoC = cylinder oil g/kWh.
    """

    if (
        oil_consumption_l is None
        or power_kw is None
        or running_hours is None
    ):
        return None

    if power_kw <= 0 or running_hours <= 0:
        return None

    return (
        oil_consumption_l
        * density_kg_l
        * 1000
        / (power_kw * running_hours)
    )


# ============================================================
# COMMAND
# ============================================================

class Command(BaseCommand):

    help = (
        "Import SCoC monitoring data from an Excel workbook "
        "into VoyageLeg and VoyageObservation."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "file_path",
            type=str,
            help=(
                "Full path to the SCoC monitoring Excel file."
            ),
        )

        parser.add_argument(
            "--message",
            type=str,
            default="",
            help=(
                "Optional pasted noon report/message. "
                "Use this when route or other values are "
                "available in the message."
            ),
        )

    # ========================================================
    # HANDLE
    # ========================================================

    def handle(self, *args, **options):

        file_path = Path(
            options["file_path"]
        )

        pasted_message = (
            options.get("message")
            or ""
        )

        if not file_path.exists():

            raise CommandError(
                f"Excel file does not exist:\n{file_path}"
            )

        if file_path.suffix.lower() not in (
            ".xlsx",
            ".xls",
            ".xlsm",
        ):

            raise CommandError(
                "The supplied file is not an Excel workbook."
            )

        self.stdout.write("")

        self.stdout.write(
            self.style.WARNING(
                f"Importing SCoC monitoring file: "
                f"{file_path.name}"
            )
        )

        self.stdout.write("")

        # ----------------------------------------------------
        # PARSE MESSAGE
        # ----------------------------------------------------

        message_values = parse_pasted_message(
            pasted_message
        )

        if pasted_message:

            self.stdout.write(
                "Pasted message supplied: YES"
            )

        else:

            self.stdout.write(
                "Pasted message supplied: NO"
            )

        # ----------------------------------------------------
        # SHEETS
        # ----------------------------------------------------

        try:

            excel = pd.ExcelFile(
                file_path
            )

        except Exception as exc:

            raise CommandError(
                f"Could not open Excel file: {exc}"
            )

        sheet_names = excel.sheet_names

        self.stdout.write(
            f"Sheets found: {', '.join(sheet_names)}"
        )

        if "weatherNoonReport" not in sheet_names:

            raise CommandError(
                "Expected sheet 'weatherNoonReport' "
                "was not found."
            )

        # ----------------------------------------------------
        # FIND HEADER
        # ----------------------------------------------------

        header_row = find_spire_header(
            file_path
        )

        if header_row is None:

            raise CommandError(
                "Could not locate the weatherNoonReport "
                "header row."
            )

        self.stdout.write(
            f"Detected header row: "
            f"Excel row {header_row + 1} "
            f"(pandas header={header_row})"
        )

        # ----------------------------------------------------
        # READ DATA
        # ----------------------------------------------------

        try:

            df = pd.read_excel(
                file_path,
                sheet_name="weatherNoonReport",
                header=header_row,
            )

        except Exception as exc:

            raise CommandError(
                f"Could not read weatherNoonReport: {exc}"
            )

        # Remove completely empty rows.

        df = df.dropna(
            how="all"
        ).copy()

        rows_read = len(df)

        self.stdout.write(
            f"Rows read: {rows_read}"
        )

        if df.empty:

            self.stdout.write(
                self.style.WARNING(
                    "No data rows found."
                )
            )

            return

        # ----------------------------------------------------
        # IDENTIFY COLUMNS
        # ----------------------------------------------------

        reported_time_col = get_first_column(
            df,
            [
                "Reported Time (UTC)",
                "Reported Time",
            ],
        )

        load_col = get_column(
            df,
            "Load",
        )

        departure_col = get_column(
            df,
            "Departure",
        )

        destination_col = get_column(
            df,
            "Destination",
        )

        speed_col = get_first_column(
            df,
            [
                "Reported STW (kn)",
                "STW used in fuel model (kn)",
                "Reported SOG (kn)",
                "SOG used in fuel model (kn)",
            ],
        )

        consumption_col = get_first_column(
            df,
            [
                "ME Cons / 24 hrs (MT/d)",
                "Reported ME Cons (mt)",
            ],
        )

        distance_col = get_column(
            df,
            "Dist (nm)",
        )

        power_col = get_column(
            df,
            "Power (kw)",
        )

        rpm_col = get_column(
            df,
            "RPM",
        )

        sfoc_col = get_column(
            df,
            "SFOC (g/kWh)",
        )

        # ----------------------------------------------------
        # REQUIRED COLUMNS
        # ----------------------------------------------------

        required_columns = {
            "Reported Time": reported_time_col,
            "Load": load_col,
            "Departure": departure_col,
            "Destination": destination_col,
        }

        missing = [
            name
            for name, column in required_columns.items()
            if column is None
        ]

        if missing:

            raise CommandError(
                "Required columns missing from Excel: "
                + ", ".join(missing)
            )

        self.stdout.write("")

        self.stdout.write(
            "Column mapping:"
        )

        self.stdout.write(
            f"  Time:        {reported_time_col}"
        )

        self.stdout.write(
            f"  Load:        {load_col}"
        )

        self.stdout.write(
            f"  Departure:   {departure_col}"
        )

        self.stdout.write(
            f"  Destination: {destination_col}"
        )

        self.stdout.write(
            f"  Speed:       {speed_col}"
        )

        self.stdout.write(
            f"  Consumption: {consumption_col}"
        )

        self.stdout.write(
            f"  Distance:    {distance_col}"
        )

        self.stdout.write(
            f"  Power:       {power_col}"
        )

        self.stdout.write(
            f"  RPM:         {rpm_col}"
        )

        self.stdout.write("")

        # ----------------------------------------------------
        # STATISTICS
        # ----------------------------------------------------

        observations_created = 0
        observations_updated = 0

        legs_created = 0
        legs_reused = 0

        rows_skipped = 0

        # ----------------------------------------------------
        # IMPORT
        # ----------------------------------------------------

        with transaction.atomic():

            for index, row in df.iterrows():

                # --------------------------------------------
                # BASIC ROUTE INFORMATION
                # --------------------------------------------

                reported_time = parse_datetime(
                    row.get(
                        reported_time_col
                    )
                )

                if reported_time is None:

                    rows_skipped += 1

                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping row {index + 2}: "
                            "invalid Reported Time."
                        )
                    )

                    continue

                load_type = clean_text(
                    row.get(load_col)
                )

                departure = clean_text(
                    row.get(departure_col)
                )

                destination = clean_text(
                    row.get(destination_col)
                )

                if not load_type:

                    load_type = "Unknown"

                # Normalise load choice.

                if normalise(load_type) == "LADEN":

                    load_type = "Laden"

                elif normalise(load_type) == "BALLAST":

                    load_type = "Ballast"

                else:

                    load_type = "Unknown"

                # --------------------------------------------
                # VALUES FROM EXCEL
                # --------------------------------------------

                speed = (
                    clean_number(
                        row.get(speed_col)
                    )
                    if speed_col
                    else None
                )

                consumption = (
                    clean_number(
                        row.get(consumption_col)
                    )
                    if consumption_col
                    else None
                )

                distance = (
                    clean_number(
                        row.get(distance_col)
                    )
                    if distance_col
                    else None
                )

                power_kw = (
                    clean_number(
                        row.get(power_col)
                    )
                    if power_col
                    else None
                )

                rpm = (
                    clean_number(
                        row.get(rpm_col)
                    )
                    if rpm_col
                    else None
                )

                # Spire's SFOC column is NOT SCoC.
                #
                # Therefore do NOT put it into observation.scoc.

                # --------------------------------------------
                # PASTED MESSAGE VALUES
                # --------------------------------------------

                distance_to_go = (
                    message_values.get(
                        "distance_to_go"
                    )
                )

                hsfo_rob = (
                    message_values.get(
                        "hsfo_rob"
                    )
                )

                lsfo_rob = (
                    message_values.get(
                        "lsfo_rob"
                    )
                )

                mgo_rob = (
                    message_values.get(
                        "mgo_rob"
                    )
                )

                message_power = (
                    message_values.get(
                        "power_kw"
                    )
                )

                message_rpm = (
                    message_values.get(
                        "rpm"
                    )
                )

                running_hours = (
                    message_values.get(
                        "running_hours"
                    )
                )

                cylinder_oil = (
                    message_values.get(
                        "cylinder_oil_consumption_l"
                    )
                )

                # Only use message values when Excel doesn't
                # already contain the value.

                if power_kw is None:

                    power_kw = message_power

                if rpm is None:

                    rpm = message_rpm

                # --------------------------------------------
                # SCoC
                # --------------------------------------------

                scoc = calculate_scoc(
                    cylinder_oil,
                    power_kw,
                    running_hours,
                )

                # --------------------------------------------
                # LEG IDENTIFICATION
                # --------------------------------------------

                leg = (
                    VoyageLeg.objects
                    .filter(
                        load_type=load_type,
                        departure=departure,
                        destination=destination,
                    )
                    .order_by(
                        "start_date",
                        "id",
                    )
                    .first()
                )

                if leg is None:

                    leg = VoyageLeg.objects.create(
                        load_type=load_type,
                        voyage_reference="",
                        departure=departure,
                        destination=destination,
                        start_date=reported_time,
                        end_date=reported_time,
                    )

                    legs_created += 1

                else:

                    legs_reused += 1

                    # Expand date range.

                    if (
                        leg.start_date is None
                        or reported_time < leg.start_date
                    ):

                        leg.start_date = reported_time

                    if (
                        leg.end_date is None
                        or reported_time > leg.end_date
                    ):

                        leg.end_date = reported_time

                    leg.save(
                        update_fields=[
                            "start_date",
                            "end_date",
                            "updated_at",
                        ]
                    )

                # --------------------------------------------
                # OBSERVATION
                # --------------------------------------------

                observation, created = (
                    VoyageObservation.objects
                    .get_or_create(
                        leg=leg,
                        reported_time=reported_time,
                        defaults={
                            "speed": speed,
                            "consumption": consumption,
                            "distance": distance,
                            "distance_to_go": distance_to_go,
                            "duration_days": (
                                (
                                    1.0
                                    if running_hours is not None
                                    and running_hours > 0
                                    else None
                                )
                            ),
                            "running_hours": running_hours,
                            "hsfo_rob": hsfo_rob,
                            "lsfo_rob": lsfo_rob,
                            "mgo_rob": mgo_rob,
                            "power_kw": power_kw,
                            "rpm": rpm,
                            "load_percent": None,
                            "scoc": scoc,
                            "cylinder_oil_consumption_l": (
                                cylinder_oil
                            ),
                            "source_file": file_path.name,
                            "source_message": pasted_message,
                        },
                    )
                )

                if created:

                    observations_created += 1

                else:

                    observations_updated += 1

                    # Update existing record with the
                    # newly imported values.

                    fields_to_update = []

                    if speed is not None:

                        observation.speed = speed

                        fields_to_update.append(
                            "speed"
                        )

                    if consumption is not None:

                        observation.consumption = (
                            consumption
                        )

                        fields_to_update.append(
                            "consumption"
                        )

                    if distance is not None:

                        observation.distance = distance

                        fields_to_update.append(
                            "distance"
                        )

                    if distance_to_go is not None:

                        observation.distance_to_go = (
                            distance_to_go
                        )

                        fields_to_update.append(
                            "distance_to_go"
                        )

                    if running_hours is not None:

                        observation.running_hours = (
                            running_hours
                        )

                        fields_to_update.append(
                            "running_hours"
                        )

                    if hsfo_rob is not None:

                        observation.hsfo_rob = hsfo_rob

                        fields_to_update.append(
                            "hsfo_rob"
                        )

                    if lsfo_rob is not None:

                        observation.lsfo_rob = lsfo_rob

                        fields_to_update.append(
                            "lsfo_rob"
                        )

                    if mgo_rob is not None:

                        observation.mgo_rob = mgo_rob

                        fields_to_update.append(
                            "mgo_rob"
                        )

                    if power_kw is not None:

                        observation.power_kw = power_kw

                        fields_to_update.append(
                            "power_kw"
                        )

                    if rpm is not None:

                        observation.rpm = rpm

                        fields_to_update.append(
                            "rpm"
                        )

                    if cylinder_oil is not None:

                        observation.cylinder_oil_consumption_l = (
                            cylinder_oil
                        )

                        fields_to_update.append(
                            "cylinder_oil_consumption_l"
                        )

                    if scoc is not None:

                        observation.scoc = scoc

                        fields_to_update.append(
                            "scoc"
                        )

                    observation.source_file = (
                        file_path.name
                    )

                    observation.source_message = (
                        pasted_message
                    )

                    fields_to_update.extend(
                        [
                            "source_file",
                            "source_message",
                            "updated_at",
                        ]
                    )

                    observation.save(
                        update_fields=fields_to_update
                    )

                # --------------------------------------------
                # LOAD PERCENT
                # --------------------------------------------

                if (
                    observation.power_kw is not None
                    and observation.power_kw > 0
                ):

                    ENGINE_MCR_KW = 22700.0

                    observation.load_percent = (
                        observation.power_kw
                        / ENGINE_MCR_KW
                        * 100.0
                    )

                    observation.save(
                        update_fields=[
                            "load_percent",
                            "updated_at",
                        ]
                    )

                # --------------------------------------------
                # UPDATE LEG RUNNING AVERAGES
                # --------------------------------------------

                observations = (
                    VoyageObservation.objects
                    .filter(leg=leg)
                )

                speeds = [
                    x.speed
                    for x in observations
                    if x.speed is not None
                ]

                consumptions = [
                    x.consumption
                    for x in observations
                    if x.consumption is not None
                ]

                if speeds:

                    leg.average_speed = (
                        sum(speeds)
                        / len(speeds)
                    )

                if consumptions:

                    leg.average_consumption = (
                        sum(consumptions)
                        / len(consumptions)
                    )

                # Distance-to-go should represent the
                # latest known value.

                dtg_values = [
                    x.distance_to_go
                    for x in observations
                    if x.distance_to_go is not None
                ]

                if dtg_values:

                    leg.distance_to_go = (
                        dtg_values[-1]
                    )

                leg.save(
                    update_fields=[
                        "average_speed",
                        "average_consumption",
                        "distance_to_go",
                        "updated_at",
                    ]
                )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                "SCoC monitoring import completed."
            )
        )

        self.stdout.write("")

        self.stdout.write(
            f"File: {file_path.name}"
        )

        self.stdout.write(
            "Sheets processed: weatherNoonReport"
        )

        self.stdout.write(
            f"Rows read: {rows_read}"
        )

        self.stdout.write(
            f"Observations created: "
            f"{observations_created}"
        )

        self.stdout.write(
            f"Observations updated: "
            f"{observations_updated}"
        )

        self.stdout.write(
            f"Voyage legs created: "
            f"{legs_created}"
        )

        self.stdout.write(
            f"Voyage legs reused: "
            f"{legs_reused}"
        )

        self.stdout.write(
            f"Rows skipped: "
            f"{rows_skipped}"
        )

        self.stdout.write("")
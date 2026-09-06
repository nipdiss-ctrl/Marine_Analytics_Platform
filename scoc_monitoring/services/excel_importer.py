# scoc_monitoring/services/excel_importer.py

import re
from datetime import datetime, date, time
from pathlib import Path

import pandas as pd
from django.db import transaction
from django.utils import timezone

from scoc_monitoring.models import (
    VoyageLeg,
    VoyageObservation,
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    """
    Convert Excel values to clean strings.
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def normalize_text(value):
    """
    Normalize text for comparisons.
    """
    text = clean_text(value)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()


def number(value):
    """
    Safely convert an Excel value to float.

    Supports:
        123
        123.4
        "123.4"
        "123,4"
        "1,234.5"
        "1 234.5"
        "-"
        "N/A"
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        return float(value)

    text = clean_text(value)

    if not text:
        return None

    # Common empty Excel values
    if normalize_text(text) in {
        "-",
        "n/a",
        "na",
        "none",
        "null",
        "nan",
    }:
        return None

    text = text.replace(" ", "")

    # European decimal format
    if "," in text and "." not in text:
        text = text.replace(",", ".")

    # 1,234.5
    elif "," in text and "." in text:
        text = text.replace(",", "")

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    """
    Convert Excel date/time into timezone-aware datetime.
    """

    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None

        dt = value.to_pydatetime()

    elif isinstance(value, datetime):
        dt = value

    elif isinstance(value, date):
        dt = datetime.combine(
            value,
            time.min,
        )

    else:
        text = clean_text(value)

        if not text:
            return None

        dt = pd.to_datetime(
            text,
            errors="coerce",
            dayfirst=True,
        )

        if pd.isna(dt):
            return None

        dt = dt.to_pydatetime()

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    return dt


def first_number(text):
    """
    Return the first numeric value found in text.
    """

    if not text:
        return None

    match = re.search(
        r"-?\d+(?:[.,]\d+)?",
        clean_text(text),
    )

    if not match:
        return None

    return number(match.group(0))


# ============================================================
# REGEX HELPERS
# ============================================================

NUMBER_PATTERN = r"(-?\d+(?:[.,]\d+)?)"


def extract_number(text, patterns):
    """
    Try several regex patterns and return the first number.
    """

    text = clean_text(text)

    if not text:
        return None

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        if match.groups():

            for group in match.groups():

                if group is None:
                    continue

                value = number(group)

                if value is not None:
                    return value

        value = first_number(
            match.group(0)
        )

        if value is not None:
            return value

    return None


# ============================================================
# NOON MESSAGE PARSER
# ============================================================

def parse_noon_message(message):
    """
    Parse a pasted noon report/message.

    This is kept compatible with the existing importer.
    """

    message = clean_text(message)

    result = {
        "reported_time": None,

        "voyage_reference": "",
        "departure": "",
        "destination": "",
        "load_type": "Unknown",

        "speed": None,
        "consumption": None,
        "distance": None,
        "distance_to_go": None,

        "running_hours": None,

        "hsfo_rob": None,
        "lsfo_rob": None,
        "mgo_rob": None,

        "power_kw": None,
        "rpm": None,
        "load_percent": None,

        "scoc": None,
        "cylinder_oil_consumption_l": None,

        "target_speed": None,
        "target_consumption": None,
    }

    if not message:
        return result

    # --------------------------------------------------------
    # DATE / TIME
    # --------------------------------------------------------

    date_patterns = [
        r"\bDATE\s*[:=-]\s*([0-9./-]+)",
        r"\bREPORT(?:ING)?\s+DATE\s*[:=-]\s*([0-9./-]+)",
        r"\bNOON\s+DATE\s*[:=-]\s*([0-9./-]+)",
        r"\bTIME\s*[:=-]\s*([0-9./-]+\s+[0-9:]+)",
    ]

    for pattern in date_patterns:

        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE,
        )

        if match:

            dt = parse_datetime(
                match.group(1)
            )

            if dt:
                result["reported_time"] = dt
                break

    # --------------------------------------------------------
    # VOYAGE REFERENCE
    # --------------------------------------------------------

    voyage_patterns = [
        r"\bVOYAGE\s*(?:NO|NUMBER|REF|REFERENCE)?\s*[:=-]\s*([A-Z0-9./_-]+)",
        r"\bVOY\s*(?:NO|NUMBER)?\s*[:=-]\s*([A-Z0-9./_-]+)",
    ]

    for pattern in voyage_patterns:

        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE,
        )

        if match:

            result["voyage_reference"] = clean_text(
                match.group(1)
            )

            break

    # --------------------------------------------------------
    # LOAD TYPE
    # --------------------------------------------------------

    if re.search(
        r"\bBALLAST\b",
        message,
        flags=re.IGNORECASE,
    ):
        result["load_type"] = "Ballast"

    elif re.search(
        r"\bLADEN\b",
        message,
        flags=re.IGNORECASE,
    ):
        result["load_type"] = "Laden"

    # --------------------------------------------------------
    # DEPARTURE
    # --------------------------------------------------------

    departure_patterns = [
        r"\bDEPARTURE\s*[:=-]\s*([^\n,;]+)",
        r"\bFROM\s*[:=-]\s*([^\n,;]+)",
        r"\bFROM\s+([A-Z][A-Z .'-]{2,})\s+(?:TO|DESTINATION)\b",
    ]

    for pattern in departure_patterns:

        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE,
        )

        if match:

            result["departure"] = clean_text(
                match.group(1)
            )

            break

    # --------------------------------------------------------
    # DESTINATION
    # --------------------------------------------------------

    destination_patterns = [
        r"\bDESTINATION\s*[:=-]\s*([^\n,;]+)",
        r"\bTO\s*[:=-]\s*([^\n,;]+)",
    ]

    for pattern in destination_patterns:

        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE,
        )

        if match:

            result["destination"] = clean_text(
                match.group(1)
            )

            break

    # --------------------------------------------------------
    # SPEED
    # --------------------------------------------------------

    result["speed"] = extract_number(
        message,
        [
            rf"\bAVERAGE\s+SPEED\s*(?:\(\s*KN\s*\))?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bSPEED\s*(?:\(\s*KN\s*\))?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bSPEED\s*{NUMBER_PATTERN}\s*KN\b",
        ],
    )

    # --------------------------------------------------------
    # CONSUMPTION
    # --------------------------------------------------------

    result["consumption"] = extract_number(
        message,
        [
            rf"\bAVERAGE\s+CONSUMPTION\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bFUEL\s+CONSUMPTION\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bTOTAL\s+CONSUMPTION\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bCONSUMPTION\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bCONS(?:UMPTION)?\.?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # DISTANCE
    # --------------------------------------------------------

    result["distance"] = extract_number(
        message,
        [
            rf"\bDISTANCE\s+(?:RUN|MADE|SAILED)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bDISTANCE\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bDIST(?:ANCE)?\.?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # DISTANCE TO GO
    # --------------------------------------------------------

    result["distance_to_go"] = extract_number(
        message,
        [
            rf"\bDISTANCE\s+TO\s+GO\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bDTG\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bD\.T\.G\.?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # RUNNING HOURS
    # --------------------------------------------------------

    result["running_hours"] = extract_number(
        message,
        [
            rf"\bRUNNING\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bRUN\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bME\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # FUEL ROB
    # --------------------------------------------------------

    result["hsfo_rob"] = extract_number(
        message,
        [
            rf"\bHSFO\s+(?:ROB|ON\s+BOARD|ONBOARD)\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bHSFO\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["lsfo_rob"] = extract_number(
        message,
        [
            rf"\bLSFO\s+(?:ROB|ON\s+BOARD|ONBOARD)\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bLSFO\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["mgo_rob"] = extract_number(
        message,
        [
            rf"\bMGO\s+(?:ROB|ON\s+BOARD|ONBOARD)\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bMGO\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # POWER
    # --------------------------------------------------------

    result["power_kw"] = extract_number(
        message,
        [
            rf"\bPOWER\s*(?:KW|KWH)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bME\s+POWER\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # RPM
    # --------------------------------------------------------

    result["rpm"] = extract_number(
        message,
        [
            rf"\bRPM\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bENGINE\s+RPM\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # LOAD %
    # --------------------------------------------------------

    result["load_percent"] = extract_number(
        message,
        [
            rf"\bLOAD\s*(?:%|PERCENT)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bENGINE\s+LOAD\s*(?:%|PERCENT)?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # SCoC
    # --------------------------------------------------------

    result["scoc"] = extract_number(
        message,
        [
            rf"\bSCOC\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bS\.C\.O\.C\.?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # CYLINDER OIL
    # --------------------------------------------------------

    result["cylinder_oil_consumption_l"] = extract_number(
        message,
        [
            rf"\bCYLINDER\s+OIL\s+(?:CONSUMPTION)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bCYL\s+OIL\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # TARGET SPEED
    # --------------------------------------------------------

    result["target_speed"] = extract_number(
        message,
        [
            rf"\bTARGET\s+SPEED\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bSPEED\s+TARGET\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # TARGET CONSUMPTION
    # --------------------------------------------------------

    result["target_consumption"] = extract_number(
        message,
        [
            rf"\bTARGET\s+CONSUMPTION\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bCONSUMPTION\s+TARGET\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    return result


# ============================================================
# EXCEL COLUMN DETECTION
# ============================================================

def find_column(df, names):
    """
    Find an Excel column using exact and fuzzy matching.
    """

    normalized_columns = {
        normalize_text(column): column
        for column in df.columns
    }

    # --------------------------------------------------------
    # Exact match
    # --------------------------------------------------------

    for name in names:

        normalized = normalize_text(name)

        if normalized in normalized_columns:
            return normalized_columns[normalized]

    # --------------------------------------------------------
    # Partial match
    # --------------------------------------------------------

    for column in df.columns:

        normalized_column = normalize_text(column)

        for name in names:

            normalized_name = normalize_text(name)

            if normalized_name in normalized_column:
                return column

    return None


def detect_columns(df):
    """
    Detect columns from the Spire Excel and common
    noon-report workbooks.

    IMPORTANT:
    The Spire Excel supplied by the user contains:

        Reported Time (UTC)
        Type
        Voy
        Load
        Departure
        Destination
        Steaming Time (hrs)
        Dist (nm)
        STW used in fuel model (kn)
        Reported STW (kn)
        Reported ME Cons (mt)
        ME Cons / 24 hrs (MT/d)
        Reported Aux Engine Cons (mt)
        Aux Engine Cons / 24 hrs (MT/d)
        Reported Total Cons (mt)
    """

    return {

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        "date": find_column(
            df,
            [
                "Reported Time (UTC)",
                "Reported Time",
                "Date",
                "Report Date",
                "Noon Date",
                "Reporting Date",
                "Timestamp",
                "DATE",
            ],
        ),

        # ----------------------------------------------------
        # VOYAGE
        # ----------------------------------------------------

        "voyage": find_column(
            df,
            [
                "Voy",
                "Voyage",
                "Voyage No",
                "Voyage Number",
                "Voyage Reference",
                "Voy No",
            ],
        ),

        # ----------------------------------------------------
        # LOAD TYPE
        # ----------------------------------------------------

        "load_type": find_column(
            df,
            [
                "Load",
                "Load Type",
                "Loading Condition",
                "Condition",
                "Laden/Ballast",
                "Laden Ballast",
            ],
        ),

        # ----------------------------------------------------
        # DEPARTURE
        # ----------------------------------------------------

        "departure": find_column(
            df,
            [
                "Departure",
                "From",
                "Port of Departure",
                "Loading Port",
            ],
        ),

        # ----------------------------------------------------
        # DESTINATION
        # ----------------------------------------------------

        "destination": find_column(
            df,
            [
                "Destination",
                "To",
                "Port of Destination",
                "Discharge Port",
            ],
        ),

        # ----------------------------------------------------
        # STEAMING / RUNNING HOURS
        # ----------------------------------------------------

        "running_hours": find_column(
            df,
            [
                "Steaming Time (hrs)",
                "Steaming Time",
                "Running Hours",
                "Run Hours",
                "ME Hours",
                "Engine Hours",
            ],
        ),

        # ----------------------------------------------------
        # DISTANCE
        # ----------------------------------------------------

        "distance": find_column(
            df,
            [
                "Dist (nm)",
                "Distance (nm)",
                "Distance",
                "Distance Run",
                "Distance Made",
                "Distance Sailed",
            ],
        ),

        # ----------------------------------------------------
        # SOURCE SPEED
        #
        # IMPORTANT FOR XH ATOP:
        # The uploaded source Excel provides the speed in
        # COLUMN N. This is the value that must be used by
        # the application and it corresponds to column L in
        # the manually prepared Speed and Cons workbook.
        #
        # Excel column N = pandas column index 13.
        # ----------------------------------------------------

        "source_speed": (
            df.columns[13]
            if len(df.columns) > 13
            else None
        ),

        # ----------------------------------------------------
        # REPORTED ME CONSUMPTION
        # ----------------------------------------------------

        "me_consumption": find_column(
            df,
            [
                "Reported ME Cons (mt)",
                "ME Consumption",
                "Reported ME Consumption",
            ],
        ),

        # ----------------------------------------------------
        # ME / 24 HOURS
        # ----------------------------------------------------

        "me_consumption_24": find_column(
            df,
            [
                "ME Cons / 24 hrs (MT/d)",
                "ME Cons / 24 hrs",
                "ME Consumption / 24 hrs",
            ],
        ),

        # ----------------------------------------------------
        # AUX CONSUMPTION
        # ----------------------------------------------------

        "aux_consumption": find_column(
            df,
            [
                "Reported Aux Engine Cons (mt)",
                "Aux Engine Consumption",
                "Reported Aux Cons",
            ],
        ),

        # ----------------------------------------------------
        # AUX / 24 HOURS
        # ----------------------------------------------------

        "aux_consumption_24": find_column(
            df,
            [
                "Aux Engine Cons / 24 hrs (MT/d)",
                "Aux Engine Cons / 24 hrs",
                "Aux Consumption / 24 hrs",
            ],
        ),

        # ----------------------------------------------------
        # TOTAL CONSUMPTION
        #
        # THIS IS THE IMPORTANT SOURCE FOR P
        # when ROB data is unavailable.
        # ----------------------------------------------------

        "total_consumption": find_column(
            df,
            [
                "Reported Total Cons (mt)",
                "Reported Total Consumption (mt)",
                "Total Consumption",
                "Total Cons",
            ],
        ),

        # ----------------------------------------------------
        # OLD GENERIC CONSUMPTION
        # ----------------------------------------------------

        "consumption": find_column(
            df,
            [
                "Consumption",
                "Average Consumption",
                "Fuel Consumption",
                "Daily Consumption",
                "Cons",
            ],
        ),

        # ----------------------------------------------------
        # DISTANCE TO GO
        # ----------------------------------------------------

        "distance_to_go": find_column(
            df,
            [
                "Distance to Go",
                "DTG",
                "Dist to Go",
                "Distance To Go",
            ],
        ),

        # ----------------------------------------------------
        # FUEL ROB
        # ----------------------------------------------------

        "hsfo_rob": find_column(
            df,
            [
                "HSFO ROB",
                "HSFO Onboard",
                "HSFO On Board",
                "HSFO",
            ],
        ),

        "lsfo_rob": find_column(
            df,
            [
                "LSFO ROB",
                "LSFO Onboard",
                "LSFO On Board",
                "LSFO",
            ],
        ),

        "mgo_rob": find_column(
            df,
            [
                "MGO ROB",
                "MGO Onboard",
                "MGO On Board",
                "MGO",
            ],
        ),

        # ----------------------------------------------------
        # POWER
        # ----------------------------------------------------

        "power_kw": find_column(
            df,
            [
                "Power (kw)",
                "Power (kW)",
                "Power KW",
                "Power",
                "ME Power",
            ],
        ),

        # ----------------------------------------------------
        # RPM
        # ----------------------------------------------------

        "rpm": find_column(
            df,
            [
                "RPM",
                "Engine RPM",
                "ME RPM",
            ],
        ),

        # ----------------------------------------------------
        # LOAD %
        # ----------------------------------------------------

        "load_percent": find_column(
            df,
            [
                "Load %",
                "Load Percent",
                "Engine Load",
                "Load Percentage",
            ],
        ),

        # ----------------------------------------------------
        # SCOC
        # ----------------------------------------------------

        "scoc": find_column(
            df,
            [
                "SCoC",
                "SCOC",
                "S.C.O.C.",
                "Specific Consumption",
            ],
        ),

        # ----------------------------------------------------
        # CYLINDER OIL
        # ----------------------------------------------------

        "cylinder_oil": find_column(
            df,
            [
                "Cylinder Oil",
                "Cylinder Oil Consumption",
                "Cylinder Oil Consumption (L)",
                "Cyl Oil",
            ],
        ),

        # ----------------------------------------------------
        # TARGET SPEED
        # ----------------------------------------------------

        "target_speed": find_column(
            df,
            [
                "Target Speed",
                "Speed Target",
                "Target Speed (kn)",
            ],
        ),

        # ----------------------------------------------------
        # TARGET CONSUMPTION
        # ----------------------------------------------------

        "target_consumption": find_column(
            df,
            [
                "Target Consumption",
                "Consumption Target",
            ],
        ),
    }


# ============================================================
# LEG KEY
# ============================================================

def normalize_port(value):
    """
    Normalize port names for route matching.
    """

    text = normalize_text(value)

    text = text.replace(",", "")
    text = text.replace(".", "")

    return text


def leg_identity(
    voyage_reference,
    departure,
    destination,
    load_type,
):
    """
    Create the identity used to find an existing VoyageLeg.

    Date is deliberately NOT included.
    """

    return (
        normalize_text(voyage_reference),
        normalize_port(departure),
        normalize_port(destination),
        normalize_text(load_type),
    )


def same_leg(
    leg,
    voyage_reference,
    departure,
    destination,
    load_type,
):
    """
    Determine whether an existing VoyageLeg represents
    the same actual voyage.
    """

    existing = leg_identity(
        leg.voyage_reference,
        leg.departure,
        leg.destination,
        leg.load_type,
    )

    incoming = leg_identity(
        voyage_reference,
        departure,
        destination,
        load_type,
    )

    # --------------------------------------------------------
    # Strong match
    # --------------------------------------------------------

    if existing == incoming:
        return True

    (
        existing_voyage,
        existing_dep,
        existing_dest,
        existing_load,
    ) = existing

    (
        incoming_voyage,
        incoming_dep,
        incoming_dest,
        incoming_load,
    ) = incoming

    # --------------------------------------------------------
    # Route + load condition match
    # --------------------------------------------------------

    if (
        existing_dep
        and existing_dest
        and incoming_dep
        and incoming_dest
        and existing_dep == incoming_dep
        and existing_dest == incoming_dest
        and existing_load == incoming_load
    ):

        # Both voyage references exist and conflict.
        if (
            existing_voyage
            and incoming_voyage
            and existing_voyage != incoming_voyage
        ):
            return False

        return True

    return False


# ============================================================
# FIND OR CREATE LEG
# ============================================================

# ============================================================
# FIND OR CREATE LEG
# ============================================================

def get_or_create_leg(
    voyage_reference="",
    departure="",
    destination="",
    load_type="Unknown",
    start_date=None,
    target_speed=None,
    target_consumption=None,
    vessel=None,
):
    """
    Find an existing voyage leg for the SELECTED VESSEL
    or create a new one.

    IMPORTANT:

    A voyage belonging to Vessel A must never be reused
    for Vessel B.

    Leg identity is therefore:

        Vessel
        +
        Voyage Reference
        +
        Departure
        +
        Destination
        +
        Load Type
    """

    voyage_reference = clean_text(
        voyage_reference
    )

    departure = clean_text(
        departure
    )

    destination = clean_text(
        destination
    )

    load_type = clean_text(
        load_type
    ) or "Unknown"

    vessel_id = getattr(
        vessel,
        "id",
        None,
    )

    # --------------------------------------------------------
    # VESSEL IS REQUIRED
    # --------------------------------------------------------

    if vessel_id is None:

        raise ValueError(
            "A vessel is required when importing SCoC data."
        )

    # --------------------------------------------------------
    # ONLY SEARCH LEGS BELONGING TO THIS VESSEL
    # --------------------------------------------------------

    candidates = (
        VoyageLeg.objects
        .filter(
            vessel_id=vessel_id
        )
        .order_by("id")
    )

    # --------------------------------------------------------
    # FIND EXISTING LEG
    # --------------------------------------------------------

    for leg in candidates:

        if same_leg(
            leg,
            voyage_reference,
            departure,
            destination,
            load_type,
        ):

            changed = False

            # ------------------------------------------------
            # FILL MISSING FIELDS
            # ------------------------------------------------

            if (
                not leg.voyage_reference
                and voyage_reference
            ):

                leg.voyage_reference = (
                    voyage_reference
                )

                changed = True

            if (
                not leg.departure
                and departure
            ):

                leg.departure = departure

                changed = True

            if (
                not leg.destination
                and destination
            ):

                leg.destination = destination

                changed = True

            if (
                leg.load_type == "Unknown"
                and load_type != "Unknown"
            ):

                leg.load_type = load_type

                changed = True

            # ------------------------------------------------
            # EARLIEST START DATE
            # ------------------------------------------------

            if start_date:

                if (
                    leg.start_date is None
                    or start_date < leg.start_date
                ):

                    leg.start_date = start_date

                    changed = True

            # ------------------------------------------------
            # TARGET SPEED
            # ------------------------------------------------

            if (
                leg.target_speed is None
                and target_speed is not None
            ):

                leg.target_speed = (
                    target_speed
                )

                changed = True

            # ------------------------------------------------
            # TARGET CONSUMPTION
            # ------------------------------------------------

            if (
                leg.target_consumption is None
                and target_consumption is not None
            ):

                leg.target_consumption = (
                    target_consumption
                )

                changed = True

            if changed:

                leg.save()

            return leg, False

    # --------------------------------------------------------
    # CREATE NEW LEG
    # --------------------------------------------------------

    leg = VoyageLeg.objects.create(

        voyage_reference=(
            voyage_reference
        ),

        departure=(
            departure
        ),

        destination=(
            destination
        ),

        load_type=(
            load_type
        ),

        start_date=(
            start_date
        ),

        target_speed=(
            target_speed
        ),

        target_consumption=(
            target_consumption
        ),

        vessel=(
            vessel
        ),
    )

    return leg, True
# ============================================================
# EXCEL ROW VALUE
# ============================================================

def row_value(row, column):
    """
    Safely get a value from a pandas row.
    """

    if column is None:
        return None

    try:
        return row[column]
    except (KeyError, IndexError):
        return None


# ============================================================
# EXCEL ROW PARSER
# ============================================================

def parse_excel_row(row, columns):
    """
    Convert one Excel row into our database fields.

    IMPORTANT:
    The manual Speed and Cons workbook calculates the daily
    duration from the difference between consecutive
    Reported Time values.

    Therefore this function only reads source values.
    Duration, calculated speed and normalized consumption are
    recalculated later in update_leg_statistics(), where the
    previous observation is available.
    """

    reported_time = parse_datetime(
        row_value(
            row,
            columns["date"],
        )
    )

    # --------------------------------------------------------
    # BASIC SOURCE VALUES
    # --------------------------------------------------------

    voyage_reference = clean_text(
        row_value(
            row,
            columns["voyage"],
        )
    )

    departure = clean_text(
        row_value(
            row,
            columns["departure"],
        )
    )

    destination = clean_text(
        row_value(
            row,
            columns["destination"],
        )
    )

    load_type = clean_text(
        row_value(
            row,
            columns["load_type"],
        )
    )

    running_hours = number(
        row_value(
            row,
            columns["running_hours"],
        )
    )

    distance = number(
        row_value(
            row,
            columns["distance"],
        )
    )

    # --------------------------------------------------------
    # ROB
    # --------------------------------------------------------

    hsfo_rob = number(
        row_value(
            row,
            columns["hsfo_rob"],
        )
    )

    lsfo_rob = number(
        row_value(
            row,
            columns["lsfo_rob"],
        )
    )

    mgo_rob = number(
        row_value(
            row,
            columns["mgo_rob"],
        )
    )

    # --------------------------------------------------------
    # REPORTED TOTAL CONSUMPTION
    # --------------------------------------------------------

    total_consumption = number(
        row_value(
            row,
            columns["total_consumption"],
        )
    )

    # --------------------------------------------------------
    # FALLBACK GENERIC CONSUMPTION
    # --------------------------------------------------------

    generic_consumption = number(
        row_value(
            row,
            columns["consumption"],
        )
    )

    # --------------------------------------------------------
    # FALLBACK ME CONSUMPTION
    # --------------------------------------------------------

    me_consumption = number(
        row_value(
            row,
            columns["me_consumption"],
        )
    )

    # --------------------------------------------------------
    # SOURCE SPEED
    # --------------------------------------------------------

    source_speed = number(
        row_value(
            row,
            columns["source_speed"],
        )
    )

    # --------------------------------------------------------
    # DISTANCE TO GO
    # --------------------------------------------------------

    distance_to_go = number(
        row_value(
            row,
            columns["distance_to_go"],
        )
    )

    # --------------------------------------------------------
    # OTHER VALUES
    # --------------------------------------------------------

    power_kw = number(
        row_value(
            row,
            columns["power_kw"],
        )
    )

    rpm = number(
        row_value(
            row,
            columns["rpm"],
        )
    )

    load_percent = number(
        row_value(
            row,
            columns["load_percent"],
        )
    )

    scoc = number(
        row_value(
            row,
            columns["scoc"],
        )
    )

    cylinder_oil = number(
        row_value(
            row,
            columns["cylinder_oil"],
        )
    )

        # ----------------------------------------------------
    # STANDARD TARGET SPEED
    # ----------------------------------------------------
    #
    # XH ATOP standard performance:
    # Ballast = 13.00 kn
    # Laden   = 12.00 kn
    # ----------------------------------------------------

    normalized_load = normalize_text(load_type)

    if "ballast" in normalized_load:
        target_speed = 13.0

    elif "laden" in normalized_load:
        target_speed = 12.0

    else:
        target_speed = None


        

    target_consumption = number(
        row_value(
            row,
            columns["target_consumption"],
        )
    )

    # --------------------------------------------------------
    # LOAD TYPE NORMALIZATION
    # --------------------------------------------------------

    normalized_load = normalize_text(
        load_type
    )

    if "ballast" in normalized_load:
        load_type = "Ballast"

    elif "laden" in normalized_load:
        load_type = "Laden"

    else:
        load_type = "Unknown"

    # --------------------------------------------------------
    # DO NOT CALCULATE DURATION HERE
    # --------------------------------------------------------
    #
    # The Excel uses:
    #
    # D7 = C7 - C6
    #
    # so duration depends on the PREVIOUS row.
    #
    # It is calculated in update_leg_statistics().
    # --------------------------------------------------------

    duration_days = None

    # --------------------------------------------------------
    # SPEED FROM SOURCE EXCEL COLUMN N
    # --------------------------------------------------------
    #
    # The XH ATOP source Excel already contains the speed
    # required by the application in column N.
    # This is the same speed represented by column L in the
    # manually prepared Speed and Cons workbook.
    #
    # Therefore speed is imported directly and is NOT
    # recalculated from distance / duration.
    # --------------------------------------------------------

    calculated_speed = source_speed

    # --------------------------------------------------------
    # REPORTED PERIOD CONSUMPTION
    # --------------------------------------------------------
    #
    # Priority:
    #
    # 1. Total consumption
    # 2. Generic consumption
    # 3. ME consumption
    #
    # This is only the source fallback. When ROB values are
    # available, update_leg_statistics() calculates the period
    # consumption from previous ROB - current ROB.
    # --------------------------------------------------------

    reported_period_consumption = None

    if total_consumption is not None:
        reported_period_consumption = total_consumption

    elif generic_consumption is not None:
        reported_period_consumption = generic_consumption

    elif me_consumption is not None:
        reported_period_consumption = me_consumption

    return {
        "reported_time": reported_time,

        "voyage_reference": voyage_reference,
        "departure": departure,
        "destination": destination,
        "load_type": load_type,

        "speed": source_speed,

        "consumption": reported_period_consumption,

        "distance": distance,
        "distance_to_go": distance_to_go,

        "running_hours": running_hours,

        "duration_days": duration_days,

        "hsfo_rob": hsfo_rob,
        "lsfo_rob": lsfo_rob,
        "mgo_rob": mgo_rob,

        "power_kw": power_kw,
        "rpm": rpm,
        "load_percent": load_percent,

        "scoc": scoc,
        "cylinder_oil_consumption_l": cylinder_oil,

        "target_speed": target_speed,
        "target_consumption": target_consumption,
    }


# ============================================================
# UPDATE OBSERVATION
# ============================================================

def update_observation(
    observation,
    data,
):
    """
    Update available observation values.

    None values do not overwrite existing values.
    """

    fields = [
        "speed",
        "consumption",
        "distance",
        "distance_to_go",
        "duration_days",
        "running_hours",
        "hsfo_rob",
        "lsfo_rob",
        "mgo_rob",
        "power_kw",
        "rpm",
        "load_percent",
        "scoc",
        "cylinder_oil_consumption_l",
    ]

    changed = False

    for field in fields:

        value = data.get(field)

        if value is None:
            continue

        if getattr(
            observation,
            field,
        ) != value:

            setattr(
                observation,
                field,
                value,
            )

            changed = True

    # --------------------------------------------------------
    # SOURCE INFORMATION
    # --------------------------------------------------------

    source_file = clean_text(
        data.get("source_file")
    )

    source_message = clean_text(
        data.get("source_message")
    )

    if source_file:

        if observation.source_file != source_file:

            observation.source_file = source_file
            changed = True

    if source_message:

        if observation.source_message != source_message:

            observation.source_message = source_message
            changed = True

    if changed:
        observation.save()

    return observation


# ============================================================
# CONSUMPTION CALCULATION
# ============================================================

def calculate_period_consumption(
    previous,
    current,
):
    """
    Calculate period fuel consumption.

    SECOND EXCEL LOGIC:

        P =
            Previous HSFO
          + Previous LSFO
          + Previous MGO
          - Current HSFO
          - Current LSFO
          - Current MGO

    If complete ROB values are not available, return
    the current observation's reported consumption.

    This is important for the Spire Excel because the
    supplied Spire columns contain Reported Total Cons
    but do not contain fuel ROB columns.
    """

    if previous is not None:

        previous_rob_values = [
            previous.hsfo_rob,
            previous.lsfo_rob,
            previous.mgo_rob,
        ]

        current_rob_values = [
            current.hsfo_rob,
            current.lsfo_rob,
            current.mgo_rob,
        ]

        # Only use ROB formula if all six values exist.
        if all(
            value is not None
            for value in (
                previous_rob_values
                + current_rob_values
            )
        ):

            previous_total = sum(
                previous_rob_values
            )

            current_total = sum(
                current_rob_values
            )

            consumption = (
                previous_total
                - current_total
            )

            # Prevent negative consumption caused
            # by bunker stem / ROB corrections.
            return consumption

    # --------------------------------------------------------
    # Spire fallback
    # --------------------------------------------------------

    return current.consumption


# ============================================================
# NORMALIZED 24-HOUR CONSUMPTION
# ============================================================

def calculate_consumption_per_day(
    observation,
    period_consumption=None,
):
    """
    Equivalent to second Excel:

        Q = P / D * 1

    where:

        P = period consumption
        D = duration days
    """

    if period_consumption is None:
        period_consumption = observation.consumption

    if period_consumption is None:
        return None

    duration_days = observation.duration_days

    if (
        duration_days is None
        or duration_days <= 0
    ):
        return None

    return (
        period_consumption
        / duration_days
    )


# ============================================================
# CALCULATE LEG STATISTICS
# ============================================================

def update_leg_statistics(leg):
    """
    Recalculate voyage-level statistics to match the manually
    prepared Speed and Cons Excel.

    DAILY SPEED
        Duration (days)
            = Current Reported Time - Previous Reported Time

        Hours
            = Duration (days) * 24

        Speed
            = Distance / Duration / 24

    DAILY CONSUMPTION
        Period consumption
            = Previous total ROB - Current total ROB

        If ROB is unavailable:
            use the source Reported Total Cons (mt)

        Consumption / 24h
            = Period consumption / Duration (days)

    LEG AVERAGES
        Average Speed
            = arithmetic average of valid daily speeds

        Average Consumption
            = arithmetic average of valid daily
              normalized consumption values

    This matches the formulas used in the manually prepared
    workbook, where speed is based on Distance / Duration / 24
    and consumption is Period Consumption / Duration.
    """

    observations = list(
        leg.observations.order_by(
            "reported_time",
            "id",
        )
    )

    if not observations:
        return leg

    speed_values = []
    consumption_per_day_values = []

    previous = None

    for observation in observations:

        # ----------------------------------------------------
        # DURATION
        # ----------------------------------------------------
        #
        # Manual Excel:
        #
        # D7 = C7 - C6
        # D8 = C8 - C7
        #
        # Therefore duration MUST use the timestamp difference.
        # ----------------------------------------------------

        duration_days = None

        if (
            previous is not None
            and previous.reported_time is not None
            and observation.reported_time is not None
        ):

            delta = (
                observation.reported_time
                - previous.reported_time
            )

            duration_days = (
                delta.total_seconds()
                / 86400.0
            )

        # ----------------------------------------------------
        # FIRST OBSERVATION
        # ----------------------------------------------------
        #
        # There is no previous timestamp, so the first row
        # cannot have an Excel-style period duration.
        # ----------------------------------------------------

        if (
            duration_days is None
            or duration_days <= 0
        ):

            observation.duration_days = None

            observation.save(
                update_fields=[
                    "duration_days",
                    "updated_at",
                ]
            )

            previous = observation
            continue

        # ----------------------------------------------------
        # SAVE DURATION
        # ----------------------------------------------------

        observation.duration_days = duration_days

        # ----------------------------------------------------
        # SPEED FROM SOURCE EXCEL COLUMN N
        # ----------------------------------------------------
        #
        # IMPORTANT:
        # Do not recalculate speed from distance / duration.
        # The source Excel already provides the required speed
        # in column N.
        #
        # Source Excel column N == manual workbook column L.
        # The imported observation.speed is therefore the
        # value used for the voyage average.
        # ----------------------------------------------------

        calculated_speed = observation.speed

        # ----------------------------------------------------
        # PERIOD CONSUMPTION
        # ----------------------------------------------------

        period_consumption = (
            calculate_period_consumption(
                previous,
                observation,
            )
        )

        if period_consumption is not None:

            observation.consumption = (
                period_consumption
            )

        # ----------------------------------------------------
        # NORMALIZED CONSUMPTION
        # ----------------------------------------------------
        #
        # Excel:
        #
        # Q = P / D
        #
        # P = period consumption
        # D = duration days
        # ----------------------------------------------------

        consumption_per_day = (
            calculate_consumption_per_day(
                observation,
                period_consumption,
            )
        )

        # ----------------------------------------------------
        # SAVE ALL CALCULATED DAILY VALUES
        # ----------------------------------------------------

        observation.save(
            update_fields=[
                "duration_days",
                "speed",
                "consumption",
                "updated_at",
            ]
        )

        # ----------------------------------------------------
        # COLLECT SPEED FOR AVERAGE
        # ----------------------------------------------------

        if (
            calculated_speed is not None
            and calculated_speed >= 0
        ):

            speed_values.append(
                calculated_speed
            )

        # ----------------------------------------------------
        # COLLECT CONSUMPTION FOR AVERAGE
        # ----------------------------------------------------

        if (
            consumption_per_day is not None
            and consumption_per_day >= 0
        ):

            consumption_per_day_values.append(
                consumption_per_day
            )

        previous = observation

    # --------------------------------------------------------
    # AVERAGE SPEED
    # --------------------------------------------------------
    #
    # Excel:
    #
    # W = AVERAGE(L6:L...)
    #
    # --------------------------------------------------------

    if speed_values:

        leg.average_speed = (
            sum(speed_values)
            / len(speed_values)
        )

    else:

        leg.average_speed = None

    # --------------------------------------------------------
    # AVERAGE CONSUMPTION
    # --------------------------------------------------------
    #
    # Excel:
    #
    # AB = AVERAGE(Q6:Q...)
    #
    # --------------------------------------------------------

    if consumption_per_day_values:

        leg.average_consumption = (
            sum(consumption_per_day_values)
            / len(consumption_per_day_values)
        )

    else:

        leg.average_consumption = None

    # --------------------------------------------------------
    # START / END DATE
    # --------------------------------------------------------

    first_observation = observations[0]
    latest_observation = observations[-1]

    if first_observation.reported_time is not None:

        leg.start_date = (
            first_observation.reported_time
        )

    if latest_observation.reported_time is not None:

        leg.end_date = (
            latest_observation.reported_time
        )

    leg.save()

    return leg



# ============================================================
# EXCEL HEADER DETECTION
# ============================================================

def detect_excel_header_row(file_path, sheet_name, max_rows=20):
    """
    Detect the real table header row.

    Spire workbooks can contain copyright/blank rows above the
    actual table. For the supplied weatherNoonReport workbook,
    the real header is the row containing 'Reported Time (UTC)'.

    Returns a zero-based pandas header row index.
    """
    preview = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=None,
        nrows=max_rows,
    )

    required_headers = {
        "reported time (utc)",
        "reported time",
        "date",
    }

    best_row = None
    best_score = -1

    for row_index in range(len(preview)):
        values = [
            normalize_text(value)
            for value in preview.iloc[row_index].tolist()
        ]

        score = 0

        if "reported time (utc)" in values:
            score += 100

        if "reported time" in values:
            score += 80

        if "date" in values:
            score += 60

        # These are strong indicators that this is the Spire
        # weatherNoonReport data header.
        for expected in (
            "type",
            "voy",
            "load",
            "departure",
            "destination",
            "dist (nm)",
            "reported stw (kn)",
            "reported total cons (mt)",
        ):
            if expected in values:
                score += 10

        if score > best_score:
            best_score = score
            best_row = row_index

    if best_row is None or best_score < 60:
        # Fall back to the normal Excel header.
        return 0

    return best_row


# ============================================================
# IMPORT EXCEL
# ============================================================

@transaction.atomic
def import_excel(
    file_path,
    source_message="",
    vessel=None,
):
    """
    Main Excel importer.

    Supports:

        .xlsx
        .xls
        .xlsm

    The importer is designed to reproduce the
    calculation methodology from the manually
    prepared second Excel.
    """

    file_path = Path(file_path)

    if not file_path.exists():

        raise FileNotFoundError(
            f"Excel file not found: {file_path}"
        )

    # --------------------------------------------------------
    # READ WORKBOOK
    # --------------------------------------------------------

    workbook = pd.ExcelFile(
        file_path
    )

    summary = {
        "file": file_path.name,
        "sheets": [],

        "rows_read": 0,
        "observations_created": 0,
        "observations_updated": 0,

        "legs_created": 0,
        "legs_reused": 0,

        "rows_skipped": 0,
    }

    # --------------------------------------------------------
    # PARSE NOON MESSAGE
    # --------------------------------------------------------

    message_data = parse_noon_message(
        source_message
    )

    # --------------------------------------------------------
    # PROCESS EACH SHEET
    # --------------------------------------------------------

    for sheet_name in workbook.sheet_names:

        try:

            # Spire exports contain metadata/blank rows above the
            # real table header. Detect the header instead of
            # assuming row 1 contains column names.
            header_row = detect_excel_header_row(
                file_path,
                sheet_name,
            )

            print(
                f"[SCoC importer] sheet={sheet_name!r} "
                f"header_row={header_row}",
                flush=True,
            )

            df = pd.read_excel(
                file_path,
                sheet_name=sheet_name,
                header=header_row,
            )

            print(
                f"[SCoC importer] columns={list(df.columns)!r}",
                flush=True,
            )

        except Exception as exc:
            print(
                f"[SCoC importer] failed reading "
                f"{sheet_name!r}: {exc}",
                flush=True,
            )
            continue

        if df.empty:
            continue

        summary["sheets"].append(
            sheet_name
        )

        columns = detect_columns(
            df
        )

        # ----------------------------------------------------
        # DATE REQUIRED
        # ----------------------------------------------------

        if columns["date"] is None:
            continue

        # ----------------------------------------------------
        # PROCESS ROWS
        # ----------------------------------------------------

        for _, row in df.iterrows():

            data = parse_excel_row(
                row,
                columns,
            )

            summary["rows_read"] += 1

            # ------------------------------------------------
            # MERGE MESSAGE VALUES
            #
            # Excel takes priority.
            # Message fills missing values.
            # ------------------------------------------------

            message_fields = [
                "voyage_reference",
                "departure",
                "destination",
                "load_type",
                "speed",
                "consumption",
                "distance",
                "distance_to_go",
                "running_hours",
                "hsfo_rob",
                "lsfo_rob",
                "mgo_rob",
                "power_kw",
                "rpm",
                "load_percent",
                "scoc",
                "cylinder_oil_consumption_l",
                "target_speed",
                "target_consumption",
            ]

            for field in message_fields:

                current = data.get(
                    field
                )

                message_value = (
                    message_data.get(field)
                )

                if (
                    (
                        current is None
                        or current == ""
                        or current == "Unknown"
                    )
                    and message_value not in (
                        None,
                        "",
                        "Unknown",
                    )
                ):

                    data[field] = (
                        message_value
                    )

            # ------------------------------------------------
            # DATE REQUIRED
            # ------------------------------------------------

            reported_time = data[
                "reported_time"
            ]

            if reported_time is None:

                summary[
                    "rows_skipped"
                ] += 1

                continue

            # ------------------------------------------------
            # ROUTE
            # ------------------------------------------------

            voyage_reference = data[
                "voyage_reference"
            ]

            departure = data[
                "departure"
            ]

            destination = data[
                "destination"
            ]

            load_type = data[
                "load_type"
            ]

            # ------------------------------------------------
            # FALLBACK TO MESSAGE ROUTE
            # ------------------------------------------------

            if not departure:

                departure = (
                    message_data[
                        "departure"
                    ]
                )

            if not destination:

                destination = (
                    message_data[
                        "destination"
                    ]
                )

            if not voyage_reference:

                voyage_reference = (
                    message_data[
                        "voyage_reference"
                    ]
                )

            if (
                load_type == "Unknown"
                and message_data[
                    "load_type"
                ] != "Unknown"
            ):

                load_type = (
                    message_data[
                        "load_type"
                    ]
                )

            # ------------------------------------------------
            # REQUIRE ROUTE INFORMATION
            # ------------------------------------------------

            if (
                not departure
                and not destination
                and not voyage_reference
            ):

                summary[
                    "rows_skipped"
                ] += 1

                continue

            # ------------------------------------------------
            # CREATE / REUSE LEG
            # ------------------------------------------------

            leg, created = get_or_create_leg(
                voyage_reference=(
                    voyage_reference
                ),
                departure=departure,
                destination=destination,
                load_type=load_type,
                start_date=reported_time,
                target_speed=data[
                    "target_speed"
                ],
                target_consumption=data[
                    "target_consumption"
                ],
                vessel=vessel,
            )

            if created:

                summary[
                    "legs_created"
                ] += 1

            else:

                summary[
                    "legs_reused"
                ] += 1

            # ------------------------------------------------
            # DAILY OBSERVATION
            # ------------------------------------------------

            observation_data = {
                field: data.get(field)
                for field in [
                    "speed",
                    "consumption",
                    "distance",
                    "distance_to_go",
                    "duration_days",
                    "running_hours",
                    "hsfo_rob",
                    "lsfo_rob",
                    "mgo_rob",
                    "power_kw",
                    "rpm",
                    "load_percent",
                    "scoc",
                    "cylinder_oil_consumption_l",
                ]
            }

            observation_data[
                "source_file"
            ] = file_path.name

            observation_data[
                "source_message"
            ] = source_message

            # ------------------------------------------------
            # CREATE / UPDATE OBSERVATION
            # ------------------------------------------------

            observation, obs_created = (
                VoyageObservation.objects.get_or_create(
                    leg=leg,
                    reported_time=reported_time,
                    defaults=observation_data,
                )
            )

            if obs_created:

                summary[
                    "observations_created"
                ] += 1

            else:

                update_observation(
                    observation,
                    observation_data,
                )

                summary[
                    "observations_updated"
                ] += 1

            # ------------------------------------------------
            # TARGET VALUES
            # ------------------------------------------------

            changed = False

            target_speed = data[
                "target_speed"
            ]

            target_consumption = data[
                "target_consumption"
            ]

            if (
                leg.target_speed is None
                and target_speed is not None
            ):

                leg.target_speed = (
                    target_speed
                )

                changed = True

            if (
                leg.target_consumption is None
                and target_consumption is not None
            ):

                leg.target_consumption = (
                    target_consumption
                )

                changed = True

            if changed:
                leg.save()

    # ========================================================
    # MESSAGE-ONLY IMPORT
    # ========================================================

    if (
        source_message
        and message_data[
            "reported_time"
        ] is not None
    ):

        reported_time = (
            message_data[
                "reported_time"
            ]
        )

        leg, created = get_or_create_leg(
            voyage_reference=(
                message_data[
                    "voyage_reference"
                ]
            ),
            departure=(
                message_data[
                    "departure"
                ]
            ),
            destination=(
                message_data[
                    "destination"
                ]
            ),
            load_type=(
                message_data[
                    "load_type"
                ]
            ),
            start_date=reported_time,
            target_speed=(
                message_data[
                    "target_speed"
                ]
            ),
            target_consumption=(
                message_data[
                    "target_consumption"
                ]
            ),
        )

        if created:

            summary[
                "legs_created"
            ] += 1

        else:

            summary[
                "legs_reused"
            ] += 1

        observation_data = {
            field: message_data.get(field)
            for field in [
                "speed",
                "consumption",
                "distance",
                "distance_to_go",
                "running_hours",
                "hsfo_rob",
                "lsfo_rob",
                "mgo_rob",
                "power_kw",
                "rpm",
                "load_percent",
                "scoc",
                "cylinder_oil_consumption_l",
            ]
        }

        # ----------------------------------------------------
        # Message duration
        # ----------------------------------------------------
        #
        # Do not calculate duration from running hours here.
        # The Excel methodology uses the difference between
        # consecutive Reported Time values.
        # update_leg_statistics() will calculate it after the
        # observation has been stored.
        # ----------------------------------------------------

        observation_data[
            "duration_days"
        ] = None

        observation_data[
            "source_file"
        ] = file_path.name

        observation_data[
            "source_message"
        ] = source_message

        observation, obs_created = (
            VoyageObservation.objects.get_or_create(
                leg=leg,
                reported_time=reported_time,
                defaults=observation_data,
            )
        )

        if obs_created:

            summary[
                "observations_created"
            ] += 1

        else:

            update_observation(
                observation,
                observation_data,
            )

            summary[
                "observations_updated"
            ] += 1

    # ========================================================
    # RE-CALCULATE ALL LEG STATISTICS
    #
    # This is important.
    #
    # We calculate after ALL rows have been imported,
    # because consumption may require the previous
    # observation's ROB.
    # ========================================================

    for leg in VoyageLeg.objects.all():

        update_leg_statistics(
            leg
        )

    try:
        workbook.close()
    except Exception:
        pass

    del workbook

    return summary


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def import_noon_report_excel(
    file_path,
    source_message="",
):
    """
    Compatibility alias.

    Existing views can continue to call:

        import_noon_report_excel(...)
    """

    return import_excel(
        file_path=file_path,
        source_message=source_message,
    )


# ============================================================
# SCoC MONITORING IMPORT
# ============================================================

def import_scoc_monitoring_row(
    report_date,
    vessel_name="",
    me_power=None,
    running_hours=None,
    cylinder_oil_consumption_l=None,
    load_percent=None,
    scoc=None,
):
    """
    Create or update the daily SCoC monitoring record.
    """

    from scoc_monitoring.models import (
        ScocDailyData
    )

    # --------------------------------------------------------
    # NORMALIZE DATE
    # --------------------------------------------------------

    if isinstance(
        report_date,
        datetime,
    ):

        report_date = (
            report_date.date()
        )

    elif isinstance(
        report_date,
        pd.Timestamp,
    ):

        report_date = (
            report_date.date()
        )

    elif isinstance(
        report_date,
        str,
    ):

        parsed = pd.to_datetime(
            report_date,
            errors="coerce",
            dayfirst=True,
        )

        if pd.isna(parsed):

            raise ValueError(
                f"Invalid report date: {report_date}"
            )

        report_date = (
            parsed.date()
        )

    if not report_date:

        raise ValueError(
            "report_date is required"
        )

    vessel_name = clean_text(
        vessel_name
    )

    # --------------------------------------------------------
    # FIND EXISTING RECORD
    # --------------------------------------------------------

    filters = {
        "report_date": report_date,
    }

    if vessel_name:

        filters[
            "vessel_name"
        ] = vessel_name

    record = (
        ScocDailyData.objects
        .filter(**filters)
        .first()
    )

    # --------------------------------------------------------
    # CREATE
    # --------------------------------------------------------

    if record is None:

        record = (
            ScocDailyData.objects.create(
                report_date=report_date,
                vessel_name=vessel_name,

                me_power=number(
                    me_power
                ),

                running_hours=number(
                    running_hours
                ),

                cylinder_oil_consumption_l=(
                    number(
                        cylinder_oil_consumption_l
                    )
                ),

                load_percent=number(
                    load_percent
                ),

                scoc=number(
                    scoc
                ),
            )
        )

        return record, True

    # --------------------------------------------------------
    # UPDATE ONLY AVAILABLE VALUES
    # --------------------------------------------------------

    changed = False

    values = {
        "me_power": me_power,

        "running_hours": running_hours,

        "cylinder_oil_consumption_l":
            cylinder_oil_consumption_l,

        "load_percent":
            load_percent,

        "scoc":
            scoc,
    }

    for field, value in values.items():

        value = number(value)

        if value is None:
            continue

        if getattr(
            record,
            field,
            None,
        ) != value:

            setattr(
                record,
                field,
                value,
            )

            changed = True

    if vessel_name:

        if (
            getattr(
                record,
                "vessel_name",
                "",
            )
            != vessel_name
        ):

            record.vessel_name = (
                vessel_name
            )

            changed = True

    if changed:
        record.save()

    return record, False


# ============================================================
# IMPORT SCoC MONITOR DATA FROM EXCEL
# ============================================================

def import_scoc_monitoring_excel(
    file_path,
    vessel_name="",
):
    """
    Import daily SCoC monitoring data from Excel.
    """

    file_path = Path(
        file_path
    )

    if not file_path.exists():

        raise FileNotFoundError(
            f"SCoC Excel file not found: {file_path}"
        )

    workbook = pd.ExcelFile(
        file_path
    )

    summary = {
        "file": file_path.name,
        "sheets": [],
        "rows_read": 0,
        "records_created": 0,
        "records_updated": 0,
        "rows_skipped": 0,
    }

    for sheet_name in workbook.sheet_names:

        try:

            df = pd.read_excel(
                file_path,
                sheet_name=sheet_name,
            )

        except Exception:
            continue

        if df.empty:
            continue

        columns = {

            "date": find_column(
                df,
                [
                    "Date",
                    "Report Date",
                    "Noon Date",
                    "Reporting Date",
                    "Timestamp",
                ],
            ),

            "vessel": find_column(
                df,
                [
                    "Vessel",
                    "Vessel Name",
                    "Ship",
                    "Ship Name",
                ],
            ),

            "me_power": find_column(
                df,
                [
                    "ME Power",
                    "Main Engine Power",
                    "Power",
                    "Power (kW)",
                    "Power KW",
                ],
            ),

            "running_hours": find_column(
                df,
                [
                    "Running Hours",
                    "Run Hours",
                    "ME Hours",
                    "Engine Hours",
                ],
            ),

            "cylinder_oil": find_column(
                df,
                [
                    "Cylinder Oil",
                    "Cylinder Oil Consumption",
                    "Cylinder Oil Consumption (L)",
                    "Cyl Oil",
                ],
            ),

            "load_percent": find_column(
                df,
                [
                    "Load %",
                    "Load Percent",
                    "Engine Load",
                    "Load",
                ],
            ),

            "scoc": find_column(
                df,
                [
                    "SCoC",
                    "SCOC",
                    "S.C.O.C.",
                    "Specific Consumption",
                ],
            ),
        }

        # ----------------------------------------------------
        # DATE REQUIRED
        # ----------------------------------------------------

        if columns["date"] is None:
            continue

        summary[
            "sheets"
        ].append(
            sheet_name
        )

        # ----------------------------------------------------
        # PROCESS ROWS
        # ----------------------------------------------------

        for _, row in df.iterrows():

            summary[
                "rows_read"
            ] += 1

            report_date = parse_datetime(
                row_value(
                    row,
                    columns["date"],
                )
            )

            if report_date is None:

                summary[
                    "rows_skipped"
                ] += 1

                continue

            # ------------------------------------------------
            # VESSEL
            # ------------------------------------------------

            row_vessel = clean_text(
                row_value(
                    row,
                    columns["vessel"],
                )
            )

            if not row_vessel:

                row_vessel = clean_text(
                    vessel_name
                )

            # ------------------------------------------------
            # VALUES
            # ------------------------------------------------

            me_power = number(
                row_value(
                    row,
                    columns["me_power"],
                )
            )

            running_hours = number(
                row_value(
                    row,
                    columns["running_hours"],
                )
            )

            cylinder_oil = number(
                row_value(
                    row,
                    columns["cylinder_oil"],
                )
            )

            load_percent = number(
                row_value(
                    row,
                    columns["load_percent"],
                )
            )

            scoc = number(
                row_value(
                    row,
                    columns["scoc"],
                )
            )

            # ------------------------------------------------
            # CREATE / UPDATE
            # ------------------------------------------------

            record, created = (
                import_scoc_monitoring_row(
                    report_date=report_date,
                    vessel_name=row_vessel,
                    me_power=me_power,
                    running_hours=running_hours,
                    cylinder_oil_consumption_l=(
                        cylinder_oil
                    ),
                    load_percent=load_percent,
                    scoc=scoc,
                )
            )

            if created:

                summary[
                    "records_created"
                ] += 1

            else:

                summary[
                    "records_updated"
                ] += 1

    return summary
import re
from datetime import datetime, date, time
from pathlib import Path

import pandas as pd
from django.db import transaction
from django.utils import timezone

from scoc_monitoring.models import (
    ScocVessel,
    VoyageLeg,
    VoyageObservation,
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def normalize_text(value):
    text = clean_text(value)
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def number(value):
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

    if "," in text and "." not in text:
        text = text.replace(",", ".")
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
    Safely parse Excel dates.

    ISO:
        2026-06-01 -> 1 June 2026

    Human/date-report:
        01/06/2026 -> 1 June 2026
        27-Aug-2026 -> 27 August 2026
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
        dt = datetime.combine(value, time.min)

    else:
        text = clean_text(value)

        if not text:
            return None

        iso_date = re.match(
            r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}",
            text,
        )

        try:
            dt = pd.to_datetime(
                text,
                errors="coerce",
                dayfirst=not bool(iso_date),
            )
        except Exception:
            return None

        if pd.isna(dt):
            return None

        dt = dt.to_pydatetime()

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    return dt


def first_number(text):
    if not text:
        return None

    match = re.search(
        r"-?\d+(?:[.,]\d+)?",
        clean_text(text),
    )

    if not match:
        return None

    return number(match.group(0))


NUMBER_PATTERN = r"(-?\d+(?:[.,]\d+)?)"


def extract_number(text, patterns):
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

        for group in match.groups():
            if group is None:
                continue

            value = number(group)

            if value is not None:
                return value

        value = first_number(match.group(0))

        if value is not None:
            return value

    return None


# ============================================================
# NOON MESSAGE PARSER
# ============================================================

def parse_noon_message(message):
    result = {
        "reported_time": None,
        "voyage_reference": "",
        "departure": "",
        "destination": "",
        "load_type": "Unknown",
        "speed": None,
        "consumption": None,
        "me_consumption_24": None,
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

    message = clean_text(message)

    if not message:
        return result

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date_patterns = [
        r"\bDATE\s*[:=-]\s*("
        r"\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{4}"
        r"|"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r")",

        r"\bREPORT(?:ING)?\s+DATE\s*[:=-]\s*("
        r"\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{4}"
        r"|"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r")",

        r"\bNOON\s+DATE\s*[:=-]\s*("
        r"\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{4}"
        r"|"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r")",

        r"\bTIME\s*[:=-]\s*("
        r"\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{4}"
        r"|"
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|"
        r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
        r")"
        r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?",
    ]

    for pattern in date_patterns:
        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE,
        )

        if match:
            dt = parse_datetime(match.group(1))

            if dt:
                result["reported_time"] = dt
                break

    # --------------------------------------------------------
    # VOYAGE
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

    if re.search(r"\bBALLAST\b", message, re.I):
        result["load_type"] = "Ballast"
    elif re.search(r"\bLADEN\b", message, re.I):
        result["load_type"] = "Laden"

    # --------------------------------------------------------
    # ROUTE
    # --------------------------------------------------------

    for pattern in [
        r"\bDEPARTURE\s*[:=-]\s*([^\n,;]+)",
        r"\bFROM\s*[:=-]\s*([^\n,;]+)",
    ]:
        match = re.search(pattern, message, re.I)

        if match:
            result["departure"] = clean_text(match.group(1))
            break

    for pattern in [
        r"\bDESTINATION\s*[:=-]\s*([^\n,;]+)",
        r"\bTO\s*[:=-]\s*([^\n,;]+)",
    ]:
        match = re.search(pattern, message, re.I)

        if match:
            result["destination"] = clean_text(match.group(1))
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
    # ME / 24 HRS
    # --------------------------------------------------------

    result["me_consumption_24"] = extract_number(
        message,
        [
            rf"\bME\s+CONS(?:UMPTION)?\s*/?\s*24\s*HRS?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bME\s+CONS(?:UMPTION)?\s*24\s*HRS?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    # --------------------------------------------------------
    # OTHER VALUES
    # --------------------------------------------------------

    result["distance"] = extract_number(
        message,
        [
            rf"\bDISTANCE\s+(?:RUN|MADE|SAILED)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bDISTANCE\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["distance_to_go"] = extract_number(
        message,
        [
            rf"\bDISTANCE\s+TO\s+GO\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bDTG\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["running_hours"] = extract_number(
        message,
        [
            rf"\bRUNNING\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bRUN\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bME\s+HOURS?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

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

    result["power_kw"] = extract_number(
        message,
        [
            rf"\bPOWER\s*(?:KW|KWH)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bME\s+POWER\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["rpm"] = extract_number(
        message,
        [
            rf"\bRPM\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bENGINE\s+RPM\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["load_percent"] = extract_number(
        message,
        [
            rf"\bLOAD\s*(?:%|PERCENT)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bENGINE\s+LOAD\s*(?:%|PERCENT)?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["scoc"] = extract_number(
        message,
        [
            rf"\bSCOC\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bS\.C\.O\.C\.?\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["cylinder_oil_consumption_l"] = extract_number(
        message,
        [
            rf"\bCYLINDER\s+OIL\s+(?:CONSUMPTION)?\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bCYL\s+OIL\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

    result["target_speed"] = extract_number(
        message,
        [
            rf"\bTARGET\s+SPEED\s*[:=-]\s*{NUMBER_PATTERN}",
            rf"\bSPEED\s+TARGET\s*[:=-]\s*{NUMBER_PATTERN}",
        ],
    )

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
    normalized_columns = {
        normalize_text(column): column
        for column in df.columns
    }

    # Exact first
    for name in names:
        normalized = normalize_text(name)

        if normalized in normalized_columns:
            return normalized_columns[normalized]

    # Then fuzzy
    for column in df.columns:
        normalized_column = normalize_text(column)

        for name in names:
            normalized_name = normalize_text(name)

            if normalized_name in normalized_column:
                return column

    return None


def detect_columns(df):
    """
    IMPORTANT:
    Never use a fixed Excel column number for speed.
    """

    return {
        "date": find_column(
            df,
            [
                "Reported Time (UTC)",
                "Reported Time",
                "Timestamp",
                "Date",
                "Report Date",
                "Noon Date",
                "Reporting Date",
            ],
        ),

        "type": find_column(
            df,
            [
                "Type",
                "Report Type",
                "Event Type",
                "Status",
            ],
        ),

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

        "departure": find_column(
            df,
            [
                "Departure",
                "From",
                "Port of Departure",
                "Loading Port",
            ],
        ),

        "destination": find_column(
            df,
            [
                "Destination",
                "To",
                "Port of Destination",
                "Discharge Port",
            ],
        ),

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
        # SPEED
        #
        # Explicitly detect the source field.
        # DO NOT use df.columns[13].
        # ----------------------------------------------------

        "source_speed": find_column(
            df,
            [
                "Reported SOG (kn)",
                "Reported SOG",
                "SOG (kn)",
                "SOG",
                "Reported STW (kn)",
                "Reported STW",
                "STW (kn)",
                "STW",
                "Speed (kn)",
                "Speed",
            ],
        ),

        "me_consumption": find_column(
            df,
            [
                "Reported ME Cons (mt)",
                "Reported ME Consumption",
                "ME Consumption",
                "ME Cons",
            ],
        ),

        "me_consumption_24": find_column(
            df,
            [
                "ME Cons / 24 hrs (MT/d)",
                "ME Cons / 24 hrs",
                "ME Consumption / 24 hrs",
                "ME Consumption / 24h",
            ],
        ),

        "aux_consumption": find_column(
            df,
            [
                "Reported Aux Engine Cons (mt)",
                "Aux Engine Consumption",
                "Reported Aux Cons",
            ],
        ),

        "total_consumption": find_column(
            df,
            [
                "Reported Total Cons (mt)",
                "Reported Total Consumption (mt)",
                "Total Consumption",
                "Total Cons",
            ],
        ),

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

        "distance_to_go": find_column(
            df,
            [
                "Distance to Go",
                "DTG",
                "Dist to Go",
                "Distance To Go",
            ],
        ),

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

        "rpm": find_column(
            df,
            [
                "RPM",
                "Engine RPM",
                "ME RPM",
            ],
        ),

        "load_percent": find_column(
            df,
            [
                "Load %",
                "Load Percent",
                "Engine Load",
                "Load Percentage",
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

        "cylinder_oil": find_column(
            df,
            [
                "Cylinder Oil",
                "Cylinder Oil Consumption",
                "Cylinder Oil Consumption (L)",
                "Cyl Oil",
            ],
        ),

        "target_speed": find_column(
            df,
            [
                "Target Speed",
                "Speed Target",
                "Target Speed (kn)",
            ],
        ),

        "target_consumption": find_column(
            df,
            [
                "Target Consumption",
                "Consumption Target",
            ],
        ),
    }


# ============================================================
# ROUTE HELPERS
# ============================================================

def normalize_port(value):
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
    return (
        normalize_text(voyage_reference),
        normalize_port(departure),
        normalize_port(destination),
        normalize_text(load_type),
    )


def same_route(
    leg,
    voyage_reference,
    departure,
    destination,
    load_type,
):
    return leg_identity(
        leg.voyage_reference,
        leg.departure,
        leg.destination,
        leg.load_type,
    ) == leg_identity(
        voyage_reference,
        departure,
        destination,
        load_type,
    )


def _leg_is_continuation(
    leg,
    reported_time,
    voyage_reference,
):
    """
    Decide whether an existing route is the same physical voyage.

    A same route occurring months later must NOT be merged.

    A normal daily-report gap is acceptable.
    A gap of more than 3 days starts a new leg unless the
    explicit voyage reference confirms the same voyage.
    """

    if leg.end_date is None:
        return True

    if (
        voyage_reference
        and leg.voyage_reference
        and normalize_text(voyage_reference)
        == normalize_text(leg.voyage_reference)
    ):
        return True

    gap = reported_time - leg.end_date

    return gap.total_seconds() <= 3 * 86400


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
    if vessel is None:
        raise ValueError(
            "A vessel is required when importing SCoC data."
        )

    voyage_reference = clean_text(voyage_reference)
    departure = clean_text(departure)
    destination = clean_text(destination)
    load_type = clean_text(load_type) or "Unknown"

    candidates = (
        VoyageLeg.objects
        .filter(vessel=vessel)
        .order_by("-start_date", "-id")
    )

    # --------------------------------------------------------
    # Find a CONTINUING leg, not merely a matching route.
    # --------------------------------------------------------

    for leg in candidates:

        if not same_route(
            leg,
            voyage_reference,
            departure,
            destination,
            load_type,
        ):
            continue

        if start_date is not None:
            if not _leg_is_continuation(
                leg,
                start_date,
                voyage_reference,
            ):
                continue

        changed = False

        if not leg.voyage_reference and voyage_reference:
            leg.voyage_reference = voyage_reference
            changed = True

        if not leg.departure and departure:
            leg.departure = departure
            changed = True

        if not leg.destination and destination:
            leg.destination = destination
            changed = True

        if leg.load_type == "Unknown" and load_type != "Unknown":
            leg.load_type = load_type
            changed = True

        if changed:
            leg.save()

        return leg, False

    # --------------------------------------------------------
    # No continuation found -> NEW VOYAGE LEG
    # --------------------------------------------------------

    leg = VoyageLeg.objects.create(
        voyage_reference=voyage_reference,
        departure=departure,
        destination=destination,
        load_type=load_type,
        start_date=start_date,
        target_speed=target_speed,
        target_consumption=target_consumption,
        vessel=vessel,
    )

    return leg, True


# ============================================================
# ROW HELPERS
# ============================================================

def row_value(row, column):
    if column is None:
        return None

    try:
        return row[column]
    except (KeyError, IndexError):
        return None


def normalize_load_type(value):
    text = normalize_text(value)

    if "ballast" in text:
        return "Ballast"

    if "laden" in text:
        return "Laden"

    return "Unknown"


def normalize_event_type(value):
    text = normalize_text(value)

    if not text:
        return ""

    return text.replace("-", "_").replace(" ", "_")


def is_performance_row(row, columns):
    """
    Determine whether a source row represents a performance
    observation rather than a transition/event row.

    Transition rows should not influence route averages.
    """

    event_type = normalize_event_type(
        row_value(row, columns.get("type"))
    )

    if event_type in {
        "departure",
        "arrival",
        "in_port",
        "inport",
        "port",
        "anchorage",
        "bunkering",
        "drifting",
    }:
        return False

    return True


# ============================================================
# EXCEL ROW PARSER
# ============================================================

def parse_excel_row(
    row,
    columns,
    vessel=None,
):
    reported_time = parse_datetime(
        row_value(row, columns["date"])
    )

    voyage_reference = clean_text(
        row_value(row, columns["voyage"])
    )

    departure = clean_text(
        row_value(row, columns["departure"])
    )

    destination = clean_text(
        row_value(row, columns["destination"])
    )

    load_type = normalize_load_type(
        row_value(row, columns["load_type"])
    )

    running_hours = number(
        row_value(row, columns["running_hours"])
    )

    distance = number(
        row_value(row, columns["distance"])
    )

    hsfo_rob = number(
        row_value(row, columns["hsfo_rob"])
    )

    lsfo_rob = number(
        row_value(row, columns["lsfo_rob"])
    )

    mgo_rob = number(
        row_value(row, columns["mgo_rob"])
    )

    total_consumption = number(
        row_value(row, columns["total_consumption"])
    )

    generic_consumption = number(
        row_value(row, columns["consumption"])
    )

    me_consumption = number(
        row_value(row, columns["me_consumption"])
    )

    me_consumption_24 = number(
        row_value(row, columns["me_consumption_24"])
    )

    # --------------------------------------------------------
    # EXPLICIT SOURCE SPEED
    # --------------------------------------------------------

    source_speed = number(
        row_value(row, columns["source_speed"])
    )

    distance_to_go = number(
        row_value(row, columns["distance_to_go"])
    )

    power_kw = number(
        row_value(row, columns["power_kw"])
    )

    rpm = number(
        row_value(row, columns["rpm"])
    )

    load_percent = number(
        row_value(row, columns["load_percent"])
    )

    scoc = number(
        row_value(row, columns["scoc"])
    )

    cylinder_oil = number(
        row_value(row, columns["cylinder_oil"])
    )

    source_target_speed = number(
        row_value(row, columns["target_speed"])
    )

    source_target_consumption = number(
        row_value(row, columns["target_consumption"])
    )

    target_speed = None
    target_consumption = None

    if vessel and load_type in {"Ballast", "Laden"}:
        target_speed = vessel.get_target_speed(load_type)
        target_consumption = vessel.get_target_consumption(load_type)

    if target_speed is None:
        target_speed = source_target_speed

    if target_consumption is None:
        target_consumption = source_target_consumption

    # --------------------------------------------------------
    # SOURCE PERIOD CONSUMPTION
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
        "me_consumption_24": me_consumption_24,

        "distance": distance,
        "distance_to_go": distance_to_go,

        "running_hours": running_hours,
        "duration_days": None,

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
# OBSERVATION UPDATE
# ============================================================

def update_observation(
    observation,
    data,
):
    fields = [
        "speed",
        "consumption",
        "me_consumption_24",
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

        if getattr(observation, field) != value:
            setattr(observation, field, value)
            changed = True

    source_file = clean_text(
        data.get("source_file")
    )

    source_message = clean_text(
        data.get("source_message")
    )

    if source_file and observation.source_file != source_file:
        observation.source_file = source_file
        changed = True

    if source_message and observation.source_message != source_message:
        observation.source_message = source_message
        changed = True

    if changed:
        observation.save()

    return observation


# ============================================================
# CONSUMPTION
# ============================================================

def calculate_period_consumption(
    previous,
    current,
):
    """
    ROB difference is only used when all six ROB values exist.
    Otherwise retain the source-reported consumption.
    """

    if previous is None:
        return current.consumption

    previous_values = [
        previous.hsfo_rob,
        previous.lsfo_rob,
        previous.mgo_rob,
    ]

    current_values = [
        current.hsfo_rob,
        current.lsfo_rob,
        current.mgo_rob,
    ]

    if all(
        value is not None
        for value in previous_values + current_values
    ):
        result = (
            sum(previous_values)
            - sum(current_values)
        )

        # Never turn a normal source value into a negative
        # consumption because of a ROB correction.
        if result >= 0:
            return result

    return current.consumption


def calculate_consumption_per_day(
    observation,
    period_consumption=None,
):
    if period_consumption is None:
        period_consumption = observation.consumption

    if period_consumption is None:
        return None

    duration_days = observation.duration_days

    if duration_days is None or duration_days <= 0:
        return None

    return period_consumption / duration_days


# ============================================================
# LEG STATISTICS
# ============================================================

def update_leg_statistics(leg):
    """
    Calculate route statistics from actual performance
    observations.

    IMPORTANT:
    - transition/event rows are excluded
    - explicit ME / 24h values take priority
    - source speed is not overwritten
    """

    observations = list(
        leg.observations.order_by(
            "reported_time",
            "id",
        )
    )

    if not observations:
        leg.average_speed = None
        leg.average_consumption = None
        leg.save(
            update_fields=[
                "average_speed",
                "average_consumption",
                "updated_at",
            ]
        )
        return leg

    speed_values = []
    consumption_values = []

    previous_performance = None

    for observation in observations:

        # ----------------------------------------------------
        # Determine whether this is a real performance row.
        #
        # We don't have event_type stored in the model, so
        # transition rows are recognized using source_message
        # where available.
        # ----------------------------------------------------

        source_text = normalize_text(
            observation.source_message
        )

        is_transition = any(
            word in source_text
            for word in [
                "departure",
                "arrival",
                "in port",
                "in_port",
            ]
        )

        # ----------------------------------------------------
        # Duration between performance observations
        # ----------------------------------------------------

        if previous_performance is not None:
            delta = (
                observation.reported_time
                - previous_performance.reported_time
            )

            duration_days = (
                delta.total_seconds()
                / 86400.0
            )

            if duration_days > 0:
                observation.duration_days = duration_days

        # ----------------------------------------------------
        # Consumption
        # ----------------------------------------------------

        period_consumption = calculate_period_consumption(
            previous_performance,
            observation,
        )

        if period_consumption is not None:
            observation.consumption = period_consumption

        # ----------------------------------------------------
        # Explicit ME / 24h has priority.
        # ----------------------------------------------------

        daily_consumption = number(
            observation.me_consumption_24
        )

        if daily_consumption is None:
            daily_consumption = (
                calculate_consumption_per_day(
                    observation,
                    period_consumption,
                )
            )

        observation.save(
            update_fields=[
                "consumption",
                "duration_days",
                "updated_at",
            ]
        )

        # ----------------------------------------------------
        # Exclude transition rows from averages.
        # ----------------------------------------------------

        if not is_transition:

            speed = number(
                observation.speed
            )

            if speed is not None and speed > 0:
                speed_values.append(speed)

            if (
                daily_consumption is not None
                and daily_consumption >= 0
            ):
                consumption_values.append(
                    daily_consumption
                )

            previous_performance = observation

    # --------------------------------------------------------
    # AVERAGES
    # --------------------------------------------------------

    leg.average_speed = (
        sum(speed_values) / len(speed_values)
        if speed_values
        else None
    )

    leg.average_consumption = (
        sum(consumption_values) / len(consumption_values)
        if consumption_values
        else None
    )

    # --------------------------------------------------------
    # DATES
    # --------------------------------------------------------

    leg.start_date = observations[0].reported_time
    leg.end_date = observations[-1].reported_time

    latest_distance_to_go = observations[-1].distance_to_go

    if latest_distance_to_go is not None:
        leg.distance_to_go = latest_distance_to_go

    leg.save()

    return leg


# ============================================================
# HEADER DETECTION
# ============================================================

def detect_excel_header_row(
    file_path,
    sheet_name,
    max_rows=25,
):
    preview = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=None,
        nrows=max_rows,
    )

    best_row = 0
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
            score += 90

        if "date" in values:
            score += 70

        if "type" in values:
            score += 20

        if "voy" in values:
            score += 20

        if "load" in values:
            score += 20

        if "departure" in values:
            score += 20

        if "destination" in values:
            score += 20

        if "reported sog (kn)" in values:
            score += 20

        if "reported total cons (mt)" in values:
            score += 20

        if score > best_score:
            best_score = score
            best_row = row_index

    return best_row


# ============================================================
# IMPORT EXCEL
# ============================================================

@transaction.atomic
def import_excel(
    file_path=None,
    source_message="",
    vessel=None,
):
    if vessel is None:
        raise ValueError(
            "A vessel is required when importing SCoC data."
        )

    source_message = clean_text(source_message)

    file_name = ""

    if file_path:
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Excel file not found: {file_path}"
            )

        file_name = file_path.name

    if not file_path and not source_message:
        raise ValueError(
            "Please provide an Excel file or a noon report message."
        )

    message_data = parse_noon_message(
        source_message
    )

    summary = {
        "file": file_name,
        "sheets": [],
        "rows_read": 0,
        "observations_created": 0,
        "observations_updated": 0,
        "legs_created": 0,
        "legs_reused": 0,
        "rows_skipped": 0,
        "errors": [],
    }

    # ========================================================
    # EXCEL
    # ========================================================

    if file_path:

        workbook = pd.ExcelFile(file_path)

        try:

            for sheet_name in workbook.sheet_names:

                try:

                    header_row = detect_excel_header_row(
                        file_path,
                        sheet_name,
                    )

                    df = pd.read_excel(
                        file_path,
                        sheet_name=sheet_name,
                        header=header_row,
                    )

                except Exception as exc:

                    summary["errors"].append(
                        f"{sheet_name}: {exc}"
                    )

                    continue

                if df.empty:
                    continue

                summary["sheets"].append(
                    sheet_name
                )

                columns = detect_columns(df)

                print(
                    f"\n[SCoC importer] {sheet_name}"
                )
                print(
                    f"Header row: {header_row}"
                )
                print(
                    f"Date column: {columns['date']}"
                )
                print(
                    f"Speed column: {columns['source_speed']}"
                )
                print(
                    f"Load column: {columns['load_type']}"
                )
                print(
                    f"Departure column: {columns['departure']}"
                )
                print(
                    f"Destination column: {columns['destination']}"
                )
                print(
                    f"ME/24 column: {columns['me_consumption_24']}"
                )

                if columns["date"] is None:
                    summary["errors"].append(
                        f"{sheet_name}: no date column detected"
                    )
                    continue

                # ------------------------------------------------
                # PROCESS IN CHRONOLOGICAL ORDER
                # ------------------------------------------------

                rows = []

                for _, row in df.iterrows():

                    data = parse_excel_row(
                        row,
                        columns,
                        vessel=vessel,
                    )

                    summary["rows_read"] += 1

                    if data["reported_time"] is None:
                        summary["rows_skipped"] += 1
                        continue

                    rows.append(data)

                rows.sort(
                    key=lambda item: item["reported_time"]
                )

                # ------------------------------------------------
                # PROCESS VALID ROWS
                # ------------------------------------------------

                for data in rows:

                    reported_time = data[
                        "reported_time"
                    ]

                    # --------------------------------------------
                    # MESSAGE FALLBACK
                    # --------------------------------------------

                    for field in [
                        "voyage_reference",
                        "departure",
                        "destination",
                        "load_type",
                        "speed",
                        "consumption",
                        "me_consumption_24",
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
                    ]:

                        current = data.get(field)
                        message_value = message_data.get(field)

                        if (
                            (
                                current is None
                                or current == ""
                                or current == "Unknown"
                            )
                            and message_value
                            not in (
                                None,
                                "",
                                "Unknown",
                            )
                        ):
                            data[field] = message_value

                    # --------------------------------------------
                    # ROUTE
                    # --------------------------------------------

                    voyage_reference = clean_text(
                        data["voyage_reference"]
                    )

                    departure = clean_text(
                        data["departure"]
                    )

                    destination = clean_text(
                        data["destination"]
                    )

                    load_type = normalize_load_type(
                        data["load_type"]
                    )

                    # --------------------------------------------
                    # If the row has no route information at all,
                    # don't invent a route.
                    # --------------------------------------------

                    if (
                        not voyage_reference
                        and not departure
                        and not destination
                    ):
                        summary["rows_skipped"] += 1
                        continue

                    # --------------------------------------------
                    # LEG
                    # --------------------------------------------

                    leg, created = get_or_create_leg(
                        voyage_reference=voyage_reference,
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
                        summary["legs_created"] += 1
                    else:
                        summary["legs_reused"] += 1

                    # --------------------------------------------
                    # OBSERVATION
                    # --------------------------------------------

                    observation_data = {
                        field: data.get(field)
                        for field in [
                            "speed",
                            "consumption",
                            "me_consumption_24",
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

                    observation_data["source_file"] = (
                        file_name
                    )

                    observation_data["source_message"] = (
                        source_message
                    )

                    (
                        observation,
                        obs_created,
                    ) = VoyageObservation.objects.get_or_create(
                        leg=leg,
                        reported_time=reported_time,
                        defaults=observation_data,
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

        finally:

            try:
                workbook.close()
            except Exception:
                pass

    # ========================================================
    # MESSAGE ONLY
    # ========================================================

    if (
        source_message
        and message_data["reported_time"] is not None
    ):

        reported_time = (
            message_data["reported_time"]
        )

        load_type = normalize_load_type(
            message_data["load_type"]
        )

        target_speed = None
        target_consumption = None

        if load_type in {"Ballast", "Laden"}:

            target_speed = vessel.get_target_speed(
                load_type
            )

            target_consumption = vessel.get_target_consumption(
                load_type
            )

        if target_speed is None:
            target_speed = message_data.get(
                "target_speed"
            )

        if target_consumption is None:
            target_consumption = message_data.get(
                "target_consumption"
            )

        leg, created = get_or_create_leg(
            voyage_reference=message_data[
                "voyage_reference"
            ],
            departure=message_data[
                "departure"
            ],
            destination=message_data[
                "destination"
            ],
            load_type=load_type,
            start_date=reported_time,
            target_speed=target_speed,
            target_consumption=target_consumption,
            vessel=vessel,
        )

        if created:
            summary["legs_created"] += 1
        else:
            summary["legs_reused"] += 1

        observation_data = {
            field: message_data.get(field)
            for field in [
                "speed",
                "consumption",
                "me_consumption_24",
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

        observation_data["duration_days"] = None
        observation_data["source_file"] = file_name
        observation_data["source_message"] = source_message

        (
            observation,
            obs_created,
        ) = VoyageObservation.objects.get_or_create(
            leg=leg,
            reported_time=reported_time,
            defaults=observation_data,
        )

        if obs_created:
            summary["observations_created"] += 1
        else:
            update_observation(
                observation,
                observation_data,
            )
            summary["observations_updated"] += 1

    # ========================================================
    # RECALCULATE ONLY AFFECTED VESSEL LEGS
    # ========================================================

    for leg in (
        VoyageLeg.objects
        .filter(vessel=vessel)
        .prefetch_related("observations")
    ):
        update_leg_statistics(leg)

    return summary


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def import_noon_report_excel(
    file_path=None,
    source_message="",
    vessel=None,
):
    return import_excel(
        file_path=file_path,
        source_message=source_message,
        vessel=vessel,
    )


# ============================================================
# SCoC MONITORING
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
    from scoc_monitoring.models import ScocDailyData

    if isinstance(report_date, datetime):
        report_date = report_date.date()

    elif isinstance(report_date, pd.Timestamp):

        if pd.isna(report_date):
            raise ValueError(
                f"Invalid report date: {report_date}"
            )

        report_date = report_date.date()

    elif isinstance(report_date, date):
        pass

    elif isinstance(report_date, str):

        parsed = parse_datetime(report_date)

        if parsed is None:
            raise ValueError(
                f"Invalid report date: {report_date}"
            )

        report_date = parsed.date()

    if not report_date:
        raise ValueError(
            "report_date is required"
        )

    vessel_name = clean_text(vessel_name)

    filters = {
        "report_date": report_date,
    }

    if vessel_name:
        filters["vessel_name"] = vessel_name

    record = (
        ScocDailyData.objects
        .filter(**filters)
        .first()
    )

    if record is None:

        record = ScocDailyData.objects.create(
            report_date=report_date,
            vessel_name=vessel_name,
            me_power=number(me_power),
            running_hours=number(running_hours),
            cylinder_oil_consumption_l=number(
                cylinder_oil_consumption_l
            ),
            load_percent=number(load_percent),
            scoc=number(scoc),
        )

        return record, True

    changed = False

    values = {
        "me_power": me_power,
        "running_hours": running_hours,
        "cylinder_oil_consumption_l":
            cylinder_oil_consumption_l,
        "load_percent": load_percent,
        "scoc": scoc,
    }

    for field, value in values.items():

        value = number(value)

        if value is None:
            continue

        if getattr(record, field, None) != value:
            setattr(record, field, value)
            changed = True

    if vessel_name and record.vessel_name != vessel_name:
        record.vessel_name = vessel_name
        changed = True

    if changed:
        record.save()

    return record, False


def import_scoc_monitoring_excel(
    file_path,
    vessel_name="",
):
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"SCoC Excel file not found: {file_path}"
        )

    workbook = pd.ExcelFile(file_path)

    summary = {
        "file": file_path.name,
        "sheets": [],
        "rows_read": 0,
        "records_created": 0,
        "records_updated": 0,
        "rows_skipped": 0,
    }

    try:

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

            if columns["date"] is None:
                continue

            summary["sheets"].append(sheet_name)

            for _, row in df.iterrows():

                summary["rows_read"] += 1

                report_date = parse_datetime(
                    row_value(
                        row,
                        columns["date"],
                    )
                )

                if report_date is None:
                    summary["rows_skipped"] += 1
                    continue

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

                record, created = (
                    import_scoc_monitoring_row(
                        report_date=report_date,
                        vessel_name=row_vessel,
                        me_power=number(
                            row_value(
                                row,
                                columns["me_power"],
                            )
                        ),
                        running_hours=number(
                            row_value(
                                row,
                                columns["running_hours"],
                            )
                        ),
                        cylinder_oil_consumption_l=number(
                            row_value(
                                row,
                                columns["cylinder_oil"],
                            )
                        ),
                        load_percent=number(
                            row_value(
                                row,
                                columns["load_percent"],
                            )
                        ),
                        scoc=number(
                            row_value(
                                row,
                                columns["scoc"],
                            )
                        ),
                    )
                )

                if created:
                    summary["records_created"] += 1
                else:
                    summary["records_updated"] += 1

    finally:

        try:
            workbook.close()
        except Exception:
            pass

    return summary
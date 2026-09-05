
import re
from datetime import datetime


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize text copied from Outlook, HTML email, Word, etc.

    Important:
    - Keeps line breaks because this report has labels on one
      line and values on the following line.
    """

    text = str(text or "")

    replacements = {
        "\xa0": " ",
        "\u200b": " ",
        "\r\n": "\n",
        "\r": "\n",
        "–": "-",
        "—": "-",
        "−": "-",
        "’": "'",
        "“": '"',
        "”": '"',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"&#160;", " ", text, flags=re.I)

    # Normalize spaces but KEEP newlines.
    lines = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def clean_value(value):
    if value is None:
        return None

    value = re.sub(r"\s+", " ", str(value)).strip()

    return value or None


def extract_float(patterns, text):
    """
    Try several regex patterns.
    Return the first valid floating-point number.
    """

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I | re.M | re.S,
        )

        if not match:
            continue

        try:
            value = match.group(1)

            value = value.replace(",", "").strip()

            return float(value)

        except (ValueError, TypeError, IndexError):
            continue

    return None


# ============================================================
# DATE
# ============================================================

def parse_report_date(text):
    """
    Parse the report date.

    Helen N example:

        Date / Time (LT / UTC)

        01-Sep-2026 / 1200 LT / 0400 Z

    Returns:

        datetime(2026, 9, 1)
    """

    patterns = [

        # ----------------------------------------------------
        # Date / Time followed by date
        # ----------------------------------------------------

        r"Date\s*/?\s*Time"
        r".{0,200}?"
        r"(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4})",

        # ----------------------------------------------------
        # Date - 01-SEP-2026
        # ----------------------------------------------------

        r"\bDate\s*[-:]\s*"
        r"(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4})",

        # ----------------------------------------------------
        # Numeric date
        # ----------------------------------------------------

        r"\bDate\s*[-:]\s*"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",

        # ----------------------------------------------------
        # Standalone date
        # ----------------------------------------------------

        r"\b(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4})"
        r"\s*/\s*\d{3,4}",
    ]

    formats = [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%b/%Y",
        "%d/%b/%y",
        "%d-%B-%Y",
        "%d-%B-%y",
        "%d/%B/%Y",
        "%d/%B/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d/%m/%Y",
        "%d/%m/%y",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I | re.M | re.S,
        )

        if not match:
            continue

        value = match.group(1).strip()

        # Normalize month to title case.
        value = value.title()

        for fmt in formats:

            try:
                return datetime.strptime(value, fmt)

            except ValueError:
                continue

    return None


# ============================================================
# VESSEL
# ============================================================

def parse_vessel_name(text):
    """
    Helen N example:

        M.V. HELEN N

    Also supports:

        M/V HELEN N
        Vessel Name - HELEN N
        Vessel Name: HELEN N
    """

    patterns = [

        # ----------------------------------------------------
        # Vessel Name - HELEN N
        # ----------------------------------------------------

        r"\bVessel\s+Name\s*[-:]\s*([^\n]+)",

        # ----------------------------------------------------
        # Vessel Name
        # HELEN N
        # ----------------------------------------------------

        r"\bVessel\s+Name\s*\n\s*([^\n]+)",

        # ----------------------------------------------------
        # M.V. HELEN N
        # ----------------------------------------------------

        r"\bM\.?\s*V\.?\s+([A-Za-z0-9][^\n]+)",

        # ----------------------------------------------------
        # M/V HELEN N
        # ----------------------------------------------------

        r"\bM/V\s+([A-Za-z0-9][^\n]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.I | re.M,
        )

        if not match:
            continue

        value = clean_value(match.group(1))

        if not value:
            continue

        # Remove contact information if captured.
        value = re.split(
            r"\b(?:TEL|TELEPHONE|EMAIL|TLX)\b",
            value,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        if value:
            return value

    return None


# ============================================================
# ROUTE
# ============================================================

def parse_route(text):
    """
    Extract the destination from:

        ETA / Port

        02-SEPT-2026, 2300 LT AGW WP / SHULANGHU, CHINA

    Returns:

        SHULANGHU, CHINA

    Also supports older formats such as:

        Port & ETA - KRISHNAPATNAM

        Destination - KRISHNAPATNAM

        To - KRISHNAPATNAM
    """

    # ========================================================
    # 1. NEW HELEN N FORMAT
    #
    # ETA / Port
    #
    # 02-SEPT-2026, 2300 LT AGW WP / SHULANGHU, CHINA
    # ========================================================

    match = re.search(
        r"\bETA\s*/?\s*Port\b"
        r".{0,500}?"
        r"\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}"
        r"[^ \n]*"
        r".{0,100}?"
        r"/\s*"
        r"([A-Za-z0-9][^\n]+)",
        text,
        flags=re.I | re.M | re.S,
    )

    if match:

        value = clean_value(match.group(1))

        if value:

            # Remove any accidental text after the port.
            value = re.split(
                r"\b(?:Remarks|Additional\s+Information|Thanks|Brgds)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0]

            value = value.strip(" -:;,/")

            if value:
                return value

    # ========================================================
    # 2. ETA / Port where date and port are on same line
    # ========================================================

    match = re.search(
        r"\bETA\s*/?\s*Port\b"
        r"\s*[-:]?\s*"
        r".{0,300}?"
        r"/\s*"
        r"([A-Za-z][A-Za-z0-9 .,'&/-]+)",
        text,
        flags=re.I | re.M | re.S,
    )

    if match:

        value = clean_value(match.group(1))

        if value:

            value = re.split(
                r"\b(?:Remarks|Additional\s+Information)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" -:;,/")

            if value:
                return value

    # ========================================================
    # 3. Port & ETA - KRISHNAPATNAM
    # ========================================================

    match = re.search(
        r"\bPort\s*(?:&|and)\s*ETA\s*[-:]\s*([^\n]+)",
        text,
        flags=re.I | re.M,
    )

    if match:

        value = clean_value(match.group(1))

        if value:

            # Remove ETA date if it is on same line.
            value = re.split(
                r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0]

            value = value.strip(" -:;,/")

            if value:
                return value

    # ========================================================
    # 4. Port & ETA on separate lines
    # ========================================================

    match = re.search(
        r"\bPort\s*(?:&|and)\s*ETA\s*\n\s*([^\n]+)",
        text,
        flags=re.I | re.M,
    )

    if match:

        value = clean_value(match.group(1))

        if value:
            return value

    # ========================================================
    # 5. Destination
    # ========================================================

    match = re.search(
        r"\bDestination\s*[-:]\s*([^\n]+)",
        text,
        flags=re.I | re.M,
    )

    if match:

        value = clean_value(match.group(1))

        if value:
            return value

    # ========================================================
    # 6. To
    # ========================================================

    match = re.search(
        r"\bTo\s*[-:]\s*([^\n]+)",
        text,
        flags=re.I | re.M,
    )

    if match:

        value = clean_value(match.group(1))

        if value:
            return value

    return None


# ============================================================
# SPEED
# ============================================================

def parse_speed(text):
    """
    Helen N format:

        Average
        Speed

        12.88 Knots

    Also supports:

        Average Speed - 12.88 Knots
        Avg Spd last 24 hrs - 12.88 kts
    """

    # ========================================================
    # 1. NEW HELEN N FORMAT
    #
    # Average Speed
    #
    # 12.88 Knots
    # ========================================================

    match = re.search(
        r"\bAverage\s+Speed\b"
        r"\s*"
        r"(?:[-:=]\s*)?"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*(?:Knots?|KTS?|KT)\b",
        text,
        flags=re.I | re.M | re.S,
    )

    if match:

        try:
            return float(match.group(1))
        except ValueError:
            pass

    # ========================================================
    # 2. Average Speed - 12.88 Knots
    # ========================================================

    patterns = [

        r"\bAverage\s+Speed\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*(?:Knots?|KTS?|KT)\b",

        # Avg Speed last 24 hrs
        r"\bAvg\.?\s*Spd\.?\s+"
        r"last\s+24(?:\.0)?\s*hrs?"
        r"\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*(?:Knots?|KTS?|KT)\b",

        # Avg Speed
        r"\bAvg\.?\s*Speed\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*(?:Knots?|KTS?|KT)\b",

        # Avg Spd
        r"\bAvg\.?\s*Spd\.?\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*(?:Knots?|KTS?|KT)\b",
    ]

    return extract_float(patterns, text)


# ============================================================
# FUEL CONSUMPTION
# ============================================================

def parse_consumption(text):
    """
    We need the MAIN ENGINE 3.5% FO consumption.

    Helen N format:

        F O
        3.5 % Consumption

        M / E

        59.1 MT

        A / E

        2.8 MT

        Boiler

        0 MT

    Therefore:

        consumption = 59.1 MT

    IMPORTANT:
    We deliberately do NOT use:
        - A/E consumption
        - Boiler consumption
        - 48-hour Avg.Cons/day
        - SOP consumption
        - ROB

    because the voyage calculation needs the daily M/E
    consumption.
    """

    # ========================================================
    # 1. NEW HELEN N FORMAT
    #
    # F O 3.5 % Consumption
    #
    # M / E
    #
    # 59.1 MT
    # ========================================================

    match = re.search(
        r"\bF\s*O\s*"
        r"3\.5\s*%\s*Consumption\b"
        r".{0,300}?"
        r"\bM\s*/\s*E\b"
        r".{0,100}?"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",
        text,
        flags=re.I | re.M | re.S,
    )

    if match:

        try:
            return float(match.group(1))
        except ValueError:
            pass

    # ========================================================
    # 2. F.O. 3.5% Consumption
    # Same-line variations
    # ========================================================

    match = re.search(
        r"\bF\.?\s*O\.?\s*"
        r"3\.5\s*%\s*Consumption\b"
        r".{0,200}?"
        r"\bM\s*/\s*E\b"
        r".{0,100}?"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",
        text,
        flags=re.I | re.M | re.S,
    )

    if match:

        try:
            return float(match.group(1))
        except ValueError:
            pass

    # ========================================================
    # 3. Older format:
    #
    # F. F.O Cons Last 24.0hrs - 43.0MT
    # ========================================================

    patterns = [

        r"\bF\.?\s*O\.?\s*Cons"
        r"\s+(?:last\s+)?24(?:\.0)?\s*hrs?"
        r"\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",

        r"\bFO\s+Cons"
        r"\s+(?:last\s+)?24(?:\.0)?\s*hrs?"
        r"\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",

        r"\bFuel\s+Consumption"
        r"\s+(?:last\s+)?24(?:\.0)?\s*hrs?"
        r"\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",
    ]

    value = extract_float(patterns, text)

    if value is not None:
        return value

    # ========================================================
    # 4. Old fallback:
    #
    # (ME-43.0MT- AE-0.0MT...)
    # ========================================================

    match = re.search(
        r"\bME\s*[-:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MT\b",
        text,
        flags=re.I,
    )

    if match:

        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


# ============================================================
# MAIN PARSER
# ============================================================

def parse_noon_report(text):
    """
    Parse the noon report.

    For the voyage calculation we only need:

        reported_time
        vessel_name
        voyage_route
        speed
        consumption

    """

    text = normalize_text(text)

    reported_time = parse_report_date(text)

    vessel_name = parse_vessel_name(text)

    voyage_route = parse_route(text)

    speed = parse_speed(text)

    consumption = parse_consumption(text)

    return {
        "reported_time": reported_time,

        "vessel_name": vessel_name,

        "voyage_route": voyage_route,

        "speed": speed,

        "consumption": consumption,

        # Kept for compatibility with the existing view.
        "destination": voyage_route,

        "eta": None,
    }


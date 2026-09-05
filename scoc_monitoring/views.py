
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.db import transaction
from scoc_monitoring.models import (
    VoyageLeg,
    VoyageObservation,
)

from pathlib import Path
from django.conf import settings

from scoc_monitoring.services.excel_importer import (
    import_excel,
)
from scoc_monitoring.services.noon_report_parser import (
    parse_noon_report,
)

# ============================================================
# HELPERS
# ============================================================

def safe_float(value):
    """
    Safely convert a value to float.
    """

    try:
        if value is None:
            return None

        value = float(value)

        if value != value:
            return None

        return value

    except (TypeError, ValueError):
        return None


def normalize_load_type(value):
    """
    Convert all common representations into one
    consistent value.

    Examples:
        ballast -> Ballast
        BALLAST -> Ballast
        laden -> Laden
        LADEN -> Laden
    """

    if value is None:
        return None

    value = str(value).strip().lower()

    if value == "ballast":
        return "Ballast"

    if value == "laden":
        return "Laden"

    if value == "unknown":
        return "Unknown"

    return str(value).strip().title()


def calculate_status(
    average_speed,
    average_consumption,
    target_speed,
    target_consumption,
):
    """
    Calculate overall voyage status.

    Both speed and consumption targets must be available
    before an overall status can be calculated.
    """

    if (
        average_speed is None
        or average_consumption is None
        or target_speed is None
        or target_consumption is None
    ):
        return "Target Not Available"

    if (
        average_speed >= target_speed
        and average_consumption <= target_consumption
    ):
        return "Achieved"

    return "Not Achieved"


def calculate_observation_status(
    speed,
    consumption,
    target_speed,
    target_consumption,
):
    """
    Calculate status for an individual daily observation.
    """

    speed_ok = (
        speed is not None
        and speed > 0
        and target_speed is not None
        and speed >= target_speed
    )

    consumption_ok = (
        consumption is not None
        and consumption > 0
        and target_consumption is not None
        and consumption <= target_consumption
    )

    target_available = (
        target_speed is not None
        and target_consumption is not None
    )

    return {
        "speed_ok": speed_ok,
        "consumption_ok": consumption_ok,
        "target_available": target_available,
        "achieved": (
            target_available
            and speed_ok
            and consumption_ok
        ),
    }


def format_value(
    value,
    decimals=2,
):
    """
    Format numeric values for display.
    """

    value = safe_float(value)

    if value is None:
        return "—"

    return f"{value:.{decimals}f}"



# ============================================================
# UPLOAD
# ============================================================

def upload_excel(request):

    # ========================================================
    # AVAILABLE VESSELS
    # ========================================================

    vessel_names = (
        VoyageObservation.objects
        .exclude(vessel_name="")
        .exclude(vessel_name__isnull=True)
        .values_list("vessel_name", flat=True)
        .distinct()
        .order_by("vessel_name")
    )

    vessel_names = list(vessel_names)

    # Also include vessels stored on VoyageLeg
    leg_vessels = (
        VoyageLeg.objects
        .exclude(vessel_name="")
        .exclude(vessel_name__isnull=True)
        .values_list("vessel_name", flat=True)
        .distinct()
        .order_by("vessel_name")
    )

    for vessel in leg_vessels:
        if vessel and vessel not in vessel_names:
            vessel_names.append(vessel)

    vessel_names = sorted(
        set(
            str(v).strip()
            for v in vessel_names
            if v
        )
    )

    # ========================================================
    # GET
    # ========================================================

    if request.method != "POST":

        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "vessels": vessel_names,
            },
        )

    print("\n" + "=" * 70)
    print("SCOC IMPORT STARTED")
    print("=" * 70, flush=True)

    # ========================================================
    # FILE
    # ========================================================

    uploaded_file = request.FILES.get("file")

    # ========================================================
    # NOON REPORT MESSAGE
    # ========================================================

    noon_report_message = (
        request.POST.get(
            "noon_report_message",
            "",
        ).strip()
    )

    if not uploaded_file:

        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "error": "Please select an Excel file.",
                "vessels": vessel_names,
            },
        )

    if not noon_report_message:

        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "error": (
                    "Please paste the noon report message."
                ),
                "vessels": vessel_names,
            },
        )

    temp_file = None

    try:

        # ====================================================
        # TEMP FILE
        # ====================================================

        temp_dir = (
            Path(settings.BASE_DIR)
            / "temp_uploads"
        )

        temp_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_file = (
            temp_dir
            / uploaded_file.name
        )

        with open(
            temp_file,
            "wb+",
        ) as destination:

            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        # ====================================================
        # PARSE NOON REPORT
        # ====================================================

        print(
            "Parsing noon report...",
            flush=True,
        )

        noon_data = parse_noon_report(
            noon_report_message
        )

        print(
            "NOON REPORT DATA:",
            noon_data,
            flush=True,
        )

        # ====================================================
        # BASIC DATA
        # ====================================================

        reported_time = noon_data.get(
            "reported_time"
        )

        vessel_name = (
            noon_data.get(
                "vessel_name"
            )
            or ""
        ).strip()

        destination = (
            noon_data.get(
                "destination"
            )
            or ""
        ).strip()

        voyage_route = (
            noon_data.get(
                "voyage_route"
            )
            or destination
            or ""
        ).strip()

        if not reported_time:

            raise ValueError(
                "Could not determine the noon report date/time."
            )

        if not vessel_name:

            raise ValueError(
                "Could not determine the vessel name "
                "from the noon report."
            )

        # ====================================================
        # NORMALIZE VESSEL
        # ====================================================

        vessel_name = " ".join(
            vessel_name.split()
        ).upper()

        print(
            "VESSEL:",
            vessel_name,
            flush=True,
        )

        print(
            "DESTINATION:",
            destination,
            flush=True,
        )

        # ====================================================
        # IMPORT
        # ====================================================

        with transaction.atomic():

            result = import_excel(
                temp_file,
                source_message=noon_report_message,
            )

            if not isinstance(result, dict):

                result = {
                    "rows_read": 0,
                    "observations_created": 0,
                    "observations_updated": 0,
                    "legs_created": 0,
                    "legs_reused": 0,
                    "rows_skipped": 0,
                    "errors": [
                        "Excel importer returned invalid result."
                    ],
                }

            # ==================================================
            # FIND CORRECT VOYAGE LEG
            # ==================================================

            leg = None

            # --------------------------------------------------
            # 1. SAME VESSEL + SAME REPORT TIME
            # --------------------------------------------------

            existing_observation = (
                VoyageObservation.objects
                .filter(
                    reported_time=reported_time,
                    vessel_name__iexact=vessel_name,
                )
                .select_related("leg")
                .first()
            )

            if existing_observation:

                leg = existing_observation.leg

                print(
                    "FOUND LEG FROM EXISTING OBSERVATION:",
                    leg.id,
                    flush=True,
                )

            # --------------------------------------------------
            # 2. SAME VESSEL + SAME DESTINATION
            # --------------------------------------------------

            if leg is None and destination:

                candidate_legs = (
                    VoyageLeg.objects
                    .filter(
                        vessel_name__iexact=vessel_name,
                        destination__icontains=destination,
                    )
                    .order_by(
                        "-start_date",
                        "-id",
                    )
                )

                if candidate_legs.exists():

                    leg = candidate_legs.first()

                    print(
                        "FOUND LEG FROM VESSEL + DESTINATION:",
                        leg.id,
                        flush=True,
                    )

            # --------------------------------------------------
            # 3. SAME VESSEL + ROUTE
            # --------------------------------------------------

            if leg is None and voyage_route:

                candidate_legs = (
                    VoyageLeg.objects
                    .filter(
                        vessel_name__iexact=vessel_name,
                        voyage_route__icontains=voyage_route,
                    )
                    .order_by(
                        "-start_date",
                        "-id",
                    )
                )

                if candidate_legs.exists():

                    leg = candidate_legs.first()

                    print(
                        "FOUND LEG FROM VESSEL + ROUTE:",
                        leg.id,
                        flush=True,
                    )

            # --------------------------------------------------
            # 4. SAME VESSEL FROM SOURCE MESSAGE
            # --------------------------------------------------

            if leg is None:

                candidate_legs = (
                    VoyageLeg.objects
                    .filter(
                        vessel_name__iexact=vessel_name,
                    )
                    .order_by(
                        "-start_date",
                        "-id",
                    )
                )

                if candidate_legs.exists():

                    leg = candidate_legs.first()

                    print(
                        "FOUND LEG FROM VESSEL:",
                        leg.id,
                        flush=True,
                    )

            # ==================================================
            # CREATE NEW LEG
            # ==================================================

            if leg is None:

                leg = VoyageLeg.objects.create(

                    # IMPORTANT:
                    # Save vessel on the VoyageLeg itself.
                    vessel_name=vessel_name,

                    load_type="UNKNOWN",

                    departure="",

                    destination=destination,

                    voyage_route=(
                        voyage_route
                        or destination
                    ),

                    start_date=reported_time,

                    source_message=(
                        noon_report_message
                    ),
                )

                print(
                    "CREATED NEW VOYAGE LEG:",
                    {
                        "id": leg.id,
                        "vessel": leg.vessel_name,
                        "destination": leg.destination,
                        "route": leg.voyage_route,
                    },
                    flush=True,
                )

            # ==================================================
            # UPDATE EXISTING LEG
            # ==================================================

            else:

                print(
                    "USING EXISTING VOYAGE LEG:",
                    {
                        "id": leg.id,
                        "old_vessel": leg.vessel_name,
                        "new_vessel": vessel_name,
                    },
                    flush=True,
                )

                # IMPORTANT:
                # Always ensure the leg has the correct vessel.
                leg.vessel_name = vessel_name

                if destination:
                    leg.destination = destination

                if voyage_route:
                    leg.voyage_route = voyage_route

                if not leg.start_date:
                    leg.start_date = reported_time

                leg.source_message = noon_report_message

            # ==================================================
            # CREATE / UPDATE OBSERVATION
            # ==================================================

            observation, created = (
                VoyageObservation.objects
                .update_or_create(

                    leg=leg,

                    reported_time=reported_time,

                    defaults={

                        # --------------------------------------
                        # Identification
                        # --------------------------------------

                        "vessel_name":
                            vessel_name,

                        "position":
                            noon_data.get(
                                "position"
                            ) or "",

                        # --------------------------------------
                        # Navigation
                        # --------------------------------------

                        "course":
                            safe_float(
                                noon_data.get(
                                    "course"
                                )
                            ),

                        "speed":
                            safe_float(
                                noon_data.get(
                                    "speed"
                                )
                            ),

                        "distance_run":
                            safe_float(
                                noon_data.get(
                                    "distance_run"
                                )
                            ),

                        "distance":
                            safe_float(
                                noon_data.get(
                                    "distance_run"
                                )
                            ),

                        "distance_to_go":
                            safe_float(
                                noon_data.get(
                                    "distance_to_go"
                                )
                            ),

                        "eta":
                            noon_data.get(
                                "eta"
                            ) or "",

                        # --------------------------------------
                        # Engine
                        # --------------------------------------

                        "rpm":
                            safe_float(
                                noon_data.get(
                                    "rpm"
                                )
                            ),

                        "slip":
                            safe_float(
                                noon_data.get(
                                    "slip"
                                )
                            ),

                        "shaft_power_kw":
                            safe_float(
                                noon_data.get(
                                    "shaft_power_kw"
                                )
                            ),

                        "engine_power_kw":
                            safe_float(
                                noon_data.get(
                                    "engine_power_kw"
                                )
                            ),

                        "power_kw":
                            safe_float(
                                noon_data.get(
                                    "power_kw"
                                )
                            ),

                        "engine_load_percent":
                            safe_float(
                                noon_data.get(
                                    "engine_load_percent"
                                )
                            ),

                        "load_percent":
                            safe_float(
                                noon_data.get(
                                    "engine_load_percent"
                                )
                            ),

                        # --------------------------------------
                        # Fuel
                        # --------------------------------------

                        "hsfo_consumption_mt":
                            safe_float(
                                noon_data.get(
                                    "hsfo_consumption_mt"
                                )
                            ),

                        "consumption":
                            safe_float(
                                noon_data.get(
                                    "hsfo_consumption_mt"
                                )
                            ),

                        "hsfo_rob_mt":
                            safe_float(
                                noon_data.get(
                                    "hsfo_rob_mt"
                                )
                            ),

                        "hsfo_rob":
                            safe_float(
                                noon_data.get(
                                    "hsfo_rob_mt"
                                )
                            ),

                        "lsfo_consumption_mt":
                            safe_float(
                                noon_data.get(
                                    "lsfo_consumption_mt"
                                )
                            ),

                        "lsfo_rob":
                            safe_float(
                                noon_data.get(
                                    "lsfo_rob"
                                )
                            ),

                        "lsmgo_consumption_mt":
                            safe_float(
                                noon_data.get(
                                    "lsmgo_consumption_mt"
                                )
                            ),

                        "lsmgo_rob_mt":
                            safe_float(
                                noon_data.get(
                                    "lsmgo_rob_mt"
                                )
                            ),

                        "lsmgo_rob":
                            safe_float(
                                noon_data.get(
                                    "lsmgo_rob_mt"
                                )
                            ),

                        # --------------------------------------
                        # Cylinder oil
                        # --------------------------------------

                        "cylinder_oil_consumption_l":
                            safe_float(
                                noon_data.get(
                                    "cylinder_oil_consumption_l"
                                )
                            ),

                        # --------------------------------------
                        # SCoC
                        # --------------------------------------

                        "scoc":
                            safe_float(
                                noon_data.get(
                                    "scoc"
                                )
                            ),

                        # --------------------------------------
                        # Running
                        # --------------------------------------

                        "running_hours":
                            safe_float(
                                noon_data.get(
                                    "running_hours"
                                )
                            ),

                        "duration_days":
                            safe_float(
                                noon_data.get(
                                    "duration_days"
                                )
                            ),

                        # --------------------------------------
                        # Weather
                        # --------------------------------------

                        "wind":
                            noon_data.get(
                                "wind"
                            ) or "",

                        "swell":
                            noon_data.get(
                                "swell"
                            ) or "",

                        "current":
                            noon_data.get(
                                "current"
                            ) or "",

                        # --------------------------------------
                        # Remarks
                        # --------------------------------------

                        "remarks":
                            noon_data.get(
                                "remarks"
                            ) or "",

                        # --------------------------------------
                        # Source
                        # --------------------------------------

                        "source_message":
                            noon_report_message,

                        "source_file":
                            uploaded_file.name,
                    },
                )
            )

            # ==================================================
            # MAKE SURE LEG VESSEL IS CORRECT
            # ==================================================

            leg.vessel_name = vessel_name

            # ==================================================
            # RECALCULATE LEG
            # ==================================================

            observations = (
                VoyageObservation.objects
                .filter(
                    leg=leg
                )
                .order_by(
                    "reported_time",
                    "id",
                )
            )

            # --------------------------------------------------
            # SPEED
            # --------------------------------------------------

            speeds = []

            for observation_item in observations:

                value = safe_float(
                    observation_item.speed
                )

                if (
                    value is not None
                    and value >= 0
                ):

                    speeds.append(value)

            # --------------------------------------------------
            # CONSUMPTION
            # --------------------------------------------------

            consumptions = []

            for observation_item in observations:

                value = safe_float(
                    observation_item.consumption
                )

                if value is None:
                    continue

                duration_days = safe_float(
                    observation_item.duration_days
                )

                if (
                    duration_days is not None
                    and duration_days > 0
                ):

                    daily_consumption = (
                        value / duration_days
                    )

                else:

                    daily_consumption = value

                if daily_consumption >= 0:

                    consumptions.append(
                        daily_consumption
                    )

            # --------------------------------------------------
            # AVERAGES
            # --------------------------------------------------

            if speeds:

                leg.average_speed = (
                    sum(speeds)
                    / len(speeds)
                )

            else:

                leg.average_speed = None

            if consumptions:

                leg.average_consumption = (
                    sum(consumptions)
                    / len(consumptions)
                )

            else:

                leg.average_consumption = None

            # --------------------------------------------------
            # LATEST
            # --------------------------------------------------

            latest = observations.last()

            if latest:

                leg.distance_to_go = (
                    latest.distance_to_go
                )

                leg.end_date = (
                    latest.reported_time
                )

            # --------------------------------------------------
            # COUNT
            # --------------------------------------------------

            leg.observation_count = (
                observations.count()
            )

            # --------------------------------------------------
            # SAVE
            # --------------------------------------------------

            leg.save()

            print(
                "VOYAGE LEG UPDATED:",
                {
                    "leg_id": leg.id,
                    "vessel": leg.vessel_name,
                    "average_speed":
                        leg.average_speed,
                    "average_consumption":
                        leg.average_consumption,
                    "observation_count":
                        leg.observation_count,
                },
                flush=True,
            )

        # ====================================================
        # CLEANUP
        # ====================================================

        try:

            if temp_file:
                temp_file.unlink()

        except Exception:
            pass

        # ====================================================
        # SESSION RESULT
        # ====================================================

        request.session[
            "scoc_import_result"
        ] = {

            "rows_read":
                int(
                    result.get(
                        "rows_read",
                        0,
                    )
                ),

            "observations_created":
                int(
                    result.get(
                        "observations_created",
                        0,
                    )
                ),

            "observations_updated":
                int(
                    result.get(
                        "observations_updated",
                        0,
                    )
                ),

            "legs_created":
                int(
                    result.get(
                        "legs_created",
                        0,
                    )
                ),

            "legs_updated":
                int(
                    result.get(
                        "legs_reused",
                        0,
                    )
                ),

            "rows_skipped":
                int(
                    result.get(
                        "rows_skipped",
                        0,
                    )
                ),

            "errors":
                result.get(
                    "errors",
                    [],
                ),

            "noon_report":
                noon_data,

            "vessel":
                vessel_name,
        }

        return redirect(
            "scoc_monitoring:import_result"
        )

    except Exception as exc:

        import traceback

        traceback.print_exc()

        try:

            if temp_file:
                temp_file.unlink()

        except Exception:
            pass

        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "error": str(exc),
                "vessels": vessel_names,
            },
        )

# ============================================================
# OVERVIEW
# ============================================================

def import_result(request):
    """
    Main SCoC overview/dashboard.

    Actual performance is calculated from the daily
    observations.

    Average Speed:
        AVERAGE(all valid daily speeds)

    Average Consumption:
        AVERAGE(all valid daily consumption/day)
    """

def import_result(request):
    """
    Main SCoC overview/dashboard.

    All vessels are included.
    """

    # ========================================================
    # ALL VESSELS
    # ========================================================

    observation_vessels = (
        VoyageObservation.objects
        .exclude(vessel_name="")
        .exclude(vessel_name__isnull=True)
        .values_list(
            "vessel_name",
            flat=True,
        )
        .distinct()
    )

    leg_vessels = (
        VoyageLeg.objects
        .exclude(vessel_name="")
        .exclude(vessel_name__isnull=True)
        .values_list(
            "vessel_name",
            flat=True,
        )
        .distinct()
    )

    vessels = sorted(
        set(
            list(observation_vessels)
            + list(leg_vessels)
        )
    )

    # ========================================================
    # ALL LEGS
    # ========================================================

    all_legs = (
        VoyageLeg.objects
        .all()
        .order_by(
            "vessel_name",
            "-start_date",
            "-id",
        )
    )

    # ========================================================
    # GROUP BY LOAD TYPE
    # ========================================================

    grouped_legs = {}

    for leg in all_legs:

        normalized_type = normalize_load_type(
            leg.load_type
        )

        if not normalized_type:
            normalized_type = "Unknown"

        if normalized_type not in grouped_legs:
            grouped_legs[normalized_type] = []

        grouped_legs[normalized_type].append(
            leg
        )

    preferred_order = [
        "Ballast",
        "Laden",
        "Unknown",
    ]

    ordered_load_types = []

    for load_type in preferred_order:

        if load_type in grouped_legs:

            ordered_load_types.append(
                load_type
            )

    for load_type in grouped_legs:

        if load_type not in ordered_load_types:

            ordered_load_types.append(
                load_type
            )

    summaries = []

    # ========================================================
    # SUMMARY
    # ========================================================

    for load_type in ordered_load_types:

        legs = grouped_legs[
            load_type
        ]

        speeds = []
        consumptions = []
        target_speeds = []
        target_consumptions = []

        for leg in legs:

            observations = (
                VoyageObservation.objects
                .filter(
                    leg=leg
                )
                .order_by(
                    "reported_time",
                    "id",
                )
            )

            for observation in observations:

                speed = safe_float(
                    observation.speed
                )

                duration_days = safe_float(
                    observation.duration_days
                )

                period_consumption = safe_float(
                    observation.consumption
                )

                if (
                    speed is not None
                    and speed >= 0
                ):
                    speeds.append(speed)

                if (
                    period_consumption is not None
                ):

                    if (
                        duration_days is not None
                        and duration_days > 0
                    ):

                        consumption_per_day = (
                            period_consumption
                            / duration_days
                        )

                    else:

                        consumption_per_day = (
                            period_consumption
                        )

                    if consumption_per_day >= 0:

                        consumptions.append(
                            consumption_per_day
                        )

            target_speed = safe_float(
                leg.target_speed
            )

            target_consumption = safe_float(
                leg.target_consumption
            )

            if target_speed is not None:

                target_speeds.append(
                    target_speed
                )

            if target_consumption is not None:

                target_consumptions.append(
                    target_consumption
                )

        average_speed = (
            sum(speeds) / len(speeds)
            if speeds
            else None
        )

        average_consumption = (
            sum(consumptions)
            / len(consumptions)
            if consumptions
            else None
        )

        target_speed = (
            sum(target_speeds)
            / len(target_speeds)
            if target_speeds
            else None
        )

        target_consumption = (
            sum(target_consumptions)
            / len(target_consumptions)
            if target_consumptions
            else None
        )

        status = calculate_status(
            average_speed,
            average_consumption,
            target_speed,
            target_consumption,
        )

        summaries.append(
            {
                "load_type":
                    load_type,

                "average_speed":
                    average_speed,

                "average_consumption":
                    average_consumption,

                "target_speed":
                    target_speed,

                "target_consumption":
                    target_consumption,

                "status":
                    status,

                "route_count":
                    len(legs),

                "observation_count":
                    len(speeds),
            }
        )

    # ========================================================
    # IMPORT RESULT
    # ========================================================

    result = request.session.pop(
        "scoc_import_result",
        {
            "rows_read": 0,
            "observations_created": 0,
            "observations_updated": 0,
            "legs_created": 0,
            "legs_updated": 0,
            "rows_skipped": 0,
            "errors": [],
        },
    )

    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "scoc_monitoring/import_result.html",
        {
            "result":
                result,

            "summaries":
                summaries,

            "vessels":
                vessels,

            "all_legs":
                all_legs,
        },
    )

# ============================================================
# ROUTES / VOYAGE LEGS
# ============================================================

def voyage_legs(
    request,
    load_type,
    performance_type="speed",
):
    """
    Display voyage legs for Ballast/Laden.

    performance_type:
        speed
        consumption

    The selected performance type is also passed to the
    detail page so that the detail page only displays the
    relevant daily column.
    """

    # ========================================================
    # NORMALIZE LOAD TYPE
    # ========================================================

    load_type_key = str(
        load_type
    ).strip().lower()

    if load_type_key == "ballast":

        display_load_type = "Ballast"

    elif load_type_key == "laden":

        display_load_type = "Laden"

    elif load_type_key == "unknown":

        display_load_type = "Unknown"

    else:

        display_load_type = normalize_load_type(
            load_type
        )

    # ========================================================
    # NORMALIZE PERFORMANCE TYPE
    # ========================================================

    performance_type = str(
        performance_type
    ).strip().lower()

    if performance_type not in [
        "speed",
        "consumption",
    ]:

        performance_type = "speed"

    # ========================================================
    # GET LEGS
    # ========================================================

    all_legs = (
        VoyageLeg.objects
        .all()
        .order_by(
            "-start_date",
            "-id",
        )
    )

    legs = []

    for leg in all_legs:

        database_load_type = normalize_load_type(
            leg.load_type
        )

        if database_load_type == display_load_type:
            legs.append(leg)

    # ========================================================
    # BUILD TABLE ROWS
    # ========================================================

    leg_rows = []

    for leg in legs:

        average_speed = safe_float(
            leg.average_speed
        )

        average_consumption = safe_float(
            leg.average_consumption
        )

        target_speed = safe_float(
            leg.target_speed
        )

        target_consumption = safe_float(
            leg.target_consumption
        )

        status = calculate_status(
            average_speed,
            average_consumption,
            target_speed,
            target_consumption,
        )

        observation_count = (
            VoyageObservation.objects
            .filter(leg=leg)
            .count()
        )

        leg_rows.append(
            {
                "leg":
                    leg,

                "average_speed":
                    average_speed,

                "average_consumption":
                    average_consumption,

                "target_speed":
                    target_speed,

                "target_consumption":
                    target_consumption,

                "status":
                    status,

                "observation_count":
                    observation_count,
            }
        )

    # ========================================================
    # TEMPLATE
    # ========================================================

    if performance_type == "speed":

        template_name = (
            "scoc_monitoring/"
            "voyage_legs_speed.html"
        )

    else:

        template_name = (
            "scoc_monitoring/"
            "voyage_legs_consumption.html"
        )

    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        template_name,
        {
            "load_type":
                display_load_type,

            "performance_type":
                performance_type,

            "leg_rows":
                leg_rows,
        },
    )


# ============================================================
# VOYAGE DETAIL / DAILY DATA
# ============================================================

def voyage_detail(
    request,
    leg_id,
    performance_type="speed",
):
    """
    Display and edit daily data for one voyage leg.

    Speed page:
        Edit VoyageObservation.speed

    Consumption page:
        Edit VoyageObservation.consumption

    After editing, the VoyageLeg averages are recalculated.
    """

    # ========================================================
    # GET LEG
    # ========================================================

    leg = get_object_or_404(
        VoyageLeg,
        id=leg_id,
    )

    # ========================================================
    # NORMALIZE PERFORMANCE TYPE
    # ========================================================

    performance_type = str(
        performance_type
    ).strip().lower()

    if performance_type not in [
        "speed",
        "consumption",
    ]:
        performance_type = "speed"

    # ========================================================
    # EDIT DAILY VALUE
    # ========================================================

    if request.method == "POST":

        observation_id = request.POST.get(
            "observation_id"
        )

        new_value = request.POST.get(
            "value"
        )

        # ----------------------------------------------------
        # Validate observation
        # ----------------------------------------------------

        observation = get_object_or_404(
            VoyageObservation,
            id=observation_id,
            leg=leg,
        )

        # ----------------------------------------------------
        # Convert value
        # ----------------------------------------------------

        try:

            if new_value is None or not new_value.strip():

                raise ValueError(
                    "Value cannot be empty."
                )

            value = float(
                new_value.strip()
            )

            if value < 0:

                raise ValueError(
                    "Value cannot be negative."
                )

        except (ValueError, TypeError):

            return redirect(
                "scoc_monitoring:voyage_detail",
                leg_id=leg.id,
                performance_type=performance_type,
            )

        # ----------------------------------------------------
        # Update selected field
        # ----------------------------------------------------

        if performance_type == "speed":

            observation.speed = value

        else:

            # IMPORTANT:
            #
            # The database stores the original period
            # consumption.
            #
            # The page displays consumption/day.
            #
            # Therefore, when editing the displayed MT/day
            # value, convert it back to the stored period
            # consumption using duration_days.

            duration_days = safe_float(
                observation.duration_days
            )

            if (
                duration_days is not None
                and duration_days > 0
            ):

                observation.consumption = (
                    value * duration_days
                )

            else:

                observation.consumption = value

        observation.save()

        # ====================================================
        # RECALCULATE VOYAGE LEG
        # ====================================================

        observations = (
            VoyageObservation.objects
            .filter(
                leg=leg
            )
            .order_by(
                "reported_time",
                "id",
            )
        )

        # ----------------------------------------------------
        # SPEED AVERAGE
        # ----------------------------------------------------

        speeds = []

        for observation_item in observations:

            speed = safe_float(
                observation_item.speed
            )

            if (
                speed is not None
                and speed >= 0
            ):

                speeds.append(
                    speed
                )

        if speeds:

            leg.average_speed = (
                sum(speeds)
                / len(speeds)
            )

        else:

            leg.average_speed = None

        # ----------------------------------------------------
        # CONSUMPTION AVERAGE
        # ----------------------------------------------------

        consumptions = []

        for observation_item in observations:

            period_consumption = safe_float(
                observation_item.consumption
            )

            if period_consumption is None:
                continue

            duration_days = safe_float(
                observation_item.duration_days
            )

            if (
                duration_days is not None
                and duration_days > 0
            ):

                consumption_per_day = (
                    period_consumption
                    / duration_days
                )

            else:

                consumption_per_day = (
                    period_consumption
                )

            if consumption_per_day >= 0:

                consumptions.append(
                    consumption_per_day
                )

        if consumptions:

            leg.average_consumption = (
                sum(consumptions)
                / len(consumptions)
            )

        else:

            leg.average_consumption = None

        # ----------------------------------------------------
        # Update latest observation information
        # ----------------------------------------------------

        latest = observations.last()

        if latest:

            leg.distance_to_go = (
                latest.distance_to_go
            )

            leg.end_date = (
                latest.reported_time
            )

        # ----------------------------------------------------
        # Count observations
        # ----------------------------------------------------

        leg.observation_count = (
            observations.count()
        )

        leg.save()

        # ----------------------------------------------------
        # Return to same route page
        # ----------------------------------------------------

        return redirect(
            "scoc_monitoring:voyage_detail",
            leg_id=leg.id,
            performance_type=performance_type,
        )

    # ========================================================
    # TARGETS
    # ========================================================

    target_speed = safe_float(
        leg.target_speed
    )

    target_consumption = safe_float(
        leg.target_consumption
    )

    # ========================================================
    # OBSERVATIONS
    # ========================================================

    observations = (
        VoyageObservation.objects
        .filter(
            leg=leg
        )
        .order_by(
            "reported_time",
            "id",
        )
    )

    daily_rows = []

    # ========================================================
    # BUILD DAILY DATA
    # ========================================================

    for observation in observations:

        speed = safe_float(
            observation.speed
        )

        period_consumption = safe_float(
            observation.consumption
        )

        duration_days = safe_float(
            observation.duration_days
        )

        running_hours = safe_float(
            observation.running_hours
        )

        distance = safe_float(
            observation.distance
        )

        # ----------------------------------------------------
        # NORMALIZED DAILY CONSUMPTION
        # ----------------------------------------------------

        consumption_per_day = None

        if (
            period_consumption is not None
            and duration_days is not None
            and duration_days > 0
        ):

            consumption_per_day = (
                period_consumption
                / duration_days
            )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        status = calculate_observation_status(
            speed,
            consumption_per_day,
            target_speed,
            target_consumption,
        )

        daily_rows.append(
            {
                "observation":
                    observation,

                "report_date":
                    observation.reported_time,

                "speed":
                    speed,

                "period_consumption":
                    period_consumption,

                "consumption":
                    consumption_per_day,

                "duration_days":
                    duration_days,

                "running_hours":
                    running_hours,

                "distance":
                    distance,

                "distance_to_go":
                    safe_float(
                        observation.distance_to_go
                    ),

                "hsfo_rob":
                    safe_float(
                        observation.hsfo_rob
                    ),

                "lsmgo_rob":
                    safe_float(
                        observation.lsmgo_rob
                    ),

                "power_kw":
                    safe_float(
                        observation.power_kw
                    ),

                "rpm":
                    safe_float(
                        observation.rpm
                    ),

                "load_percent":
                    safe_float(
                        observation.load_percent
                    ),

                "scoc":
                    safe_float(
                        observation.scoc
                    ),

                "cylinder_oil":
                    safe_float(
                        observation.cylinder_oil_consumption_l
                    ),

                "speed_ok":
                    status["speed_ok"],

                "consumption_ok":
                    status["consumption_ok"],

                "target_available":
                    status["target_available"],

                "status":
                    (
                        "Achieved"
                        if status["achieved"]
                        else (
                            "Not Achieved"
                            if status["target_available"]
                            else "Target Not Available"
                        )
                    ),
            }
        )

    # ========================================================
    # OVERALL VOYAGE STATUS
    # ========================================================

    voyage_status = calculate_status(
        safe_float(
            leg.average_speed
        ),
        safe_float(
            leg.average_consumption
        ),
        target_speed,
        target_consumption,
    )

    # ========================================================
    # COUNTS
    # ========================================================

    valid_speeds = [
        row["speed"]
        for row in daily_rows
        if row["speed"] is not None
    ]

    valid_consumptions = [
        row["consumption"]
        for row in daily_rows
        if row["consumption"] is not None
    ]

    latest = (
        daily_rows[-1]
        if daily_rows
        else None
    )

    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "scoc_monitoring/voyage_detail.html",
        {
            "leg":
                leg,

            "daily_rows":
                daily_rows,

            "performance_type":
                performance_type,

            "target_speed":
                target_speed,

            "target_consumption":
                target_consumption,

            "voyage_status":
                voyage_status,

            "latest":
                latest,

            "observation_count":
                len(
                    daily_rows
                ),

            "valid_speed_count":
                len(
                    valid_speeds
                ),

            "valid_consumption_count":
                len(
                    valid_consumptions
                ),
        },
    )

# ============================================================
# OLD OBSERVATION URL
# ============================================================

def observation_detail(
    request,
    observation_id,
):

    observation = get_object_or_404(
        VoyageObservation,
        id=observation_id,
    )

    return redirect(
        "scoc_monitoring:voyage_detail",
        leg_id=observation.leg_id,
    )


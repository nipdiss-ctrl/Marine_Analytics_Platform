from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)
from inspections.models import Vessel

from scoc_monitoring.models import (
    VoyageLeg,
    VoyageObservation,
    
)
from pathlib import Path
from django.conf import settings
from scoc_monitoring.services.excel_importer import (
    import_excel,
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

    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_load_type(value):
    """
    Convert all common representations into one
    consistent value.

    Examples:
        ballast -> Ballast
        BALLAST -> Ballast
        Ballast -> Ballast
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
    # LOAD ACTIVE VESSELS
    # ========================================================

    vessels = (
        Vessel.objects
        .filter(active=True)
        .order_by("vessel_name")
    )

    if request.method == "POST":

        print("\n" + "=" * 70)
        print("SCOC EXCEL UPLOAD STARTED")
        print("=" * 70, flush=True)

        uploaded_file = request.FILES.get("file")

        noon_report_message = (
            request.POST.get(
                "noon_report_message",
                "",
            ).strip()
        )

        vessel_id = request.POST.get("vessel")

        # ====================================================
        # VALIDATE VESSEL
        # ====================================================

        if not vessel_id:

            return render(
                request,
                "scoc_monitoring/upload.html",
                {
                    "error": "Please select a vessel.",
                    "vessels": vessels,
                },
            )

        vessel = get_object_or_404(
            Vessel,
            id=vessel_id,
            active=True,
        )

        print(
            "Selected vessel:",
            vessel.vessel_name,
            flush=True,
        )
        
        if not uploaded_file:

            print(
                "ERROR: No file received",
                flush=True,
            )

            return render(
                request,
                "scoc_monitoring/upload.html",
                {
                    "error": (
                        "Please select an Excel file."
                    )
                },
            )

        print(
            "Uploaded file:",
            uploaded_file.name,
            flush=True,
        )

        print(
            "File size:",
            uploaded_file.size,
            flush=True,
        )

        try:

            # ==================================================
            # SAVE UPLOADED FILE TEMPORARILY
            # ==================================================

            temp_dir = Path(
                settings.BASE_DIR
            ) / "temp_uploads"

            temp_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            temp_file = (
                temp_dir
                / uploaded_file.name
            )

            print(
                "Saving temporary file:",
                temp_file,
                flush=True,
            )

            with open(
                temp_file,
                "wb+",
            ) as destination:

                for chunk in uploaded_file.chunks():

                    destination.write(chunk)

            print(
                "Temporary file saved.",
                flush=True,
            )

            # ==================================================
            # CALL IMPORTER WITH PATH
            # ==================================================

            print(
                ">>> CALLING import_excel() <<<",
                flush=True,
            )

            # ==================================================
            # REPLACE OLD SCoC DATA
            # ==================================================
            # This upload is treated as a full replacement import.
            # Delete the old observations first, then the old legs.
            # If the import fails, the transaction rolls back.
            # ==================================================
            from django.db import transaction

            with transaction.atomic():

                ####VoyageObservation.objects.all().delete()
                ####VoyageLeg.objects.all().delete()

                result = import_excel(
                    temp_file,
                    source_message=noon_report_message,
                    vessel=vessel,
                )

            print(
                ">>> IMPORT FINISHED <<<",
                flush=True,
            )

            print(
                "IMPORT RESULT:",
                result,
                flush=True,
            )

            # ==================================================
            # DELETE TEMPORARY FILE
            # ==================================================

            try:

                temp_file.unlink()

                print(
                    "Temporary file deleted.",
                    flush=True,
                )

            except Exception as cleanup_error:

                print(
                    "Temporary file cleanup error:",
                    cleanup_error,
                    flush=True,
                )

            # ==================================================
            # STORE RESULT
            # ==================================================

            request.session[
                "scoc_import_result"
            ] = {

                "rows_read": int(
                    result.get(
                        "rows_read",
                        0,
                    )
                ),

                "observations_created": int(
                    result.get(
                        "observations_created",
                        0,
                    )
                ),

                "observations_updated": int(
                    result.get(
                        "observations_updated",
                        0,
                    )
                ),

                "legs_created": int(
                    result.get(
                        "legs_created",
                        0,
                    )
                ),

                "legs_updated": int(
                    result.get(
                        "legs_reused",
                        0,
                    )
                ),

                "rows_skipped": int(
                    result.get(
                        "rows_skipped",
                        0,
                    )
                ),

                "errors": result.get(
                    "errors",
                    [],
                ),
            }
            request.session["scoc_import_vessel_id"] = vessel.id

            return redirect(
                "scoc_monitoring:import_result"
            )

        except Exception as exc:

            print(
                "=" * 70,
                flush=True,
            )

            print(
                "IMPORT ERROR",
                flush=True,
            )

            print(
                "ERROR TYPE:",
                type(exc).__name__,
                flush=True,
            )

            print(
                "ERROR:",
                str(exc),
                flush=True,
            )

            import traceback

            traceback.print_exc()

            return render(
                request,
                "scoc_monitoring/upload.html",
                {
                    "error": str(exc),
                },
            )

    return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "vessels": vessels,
            },
    )

# ============================================================
# OVERVIEW
# ============================================================

# ============================================================
# OVERVIEW
# ============================================================

def import_result(request, vessel_id):
    """
    Main SCoC overview/dashboard for one vessel.

    Dashboard actuals are calculated from the DAILY observations,
    not by averaging already-averaged VoyageLeg values.

    This matches the manual Speed and Cons workbook:

        Average Speed
            = AVERAGE(all valid daily speeds)

        Average Consumption
            = AVERAGE(all valid daily consumption / 24h)

    The importer calculates and stores the daily values.

    IMPORTANT:
    Only data belonging to the selected vessel is displayed.
    """

    # ========================================================
    # LOAD SELECTED VESSEL
    # ========================================================

    vessel = get_object_or_404(
        Vessel,
        id=vessel_id,
        active=True,
        scoc_active=True,
    )

    print(
        "SCoC Overview Vessel:",
        vessel.vessel_name,
        flush=True,
    )

    # ========================================================
    # LOAD ONLY THIS VESSEL'S LEGS
    # ========================================================

    all_legs = (
        VoyageLeg.objects
        .filter(
            vessel=vessel,
        )
        .order_by("id")
    )

    grouped_legs = {}

    # ========================================================
    # GROUP LEGS BY LOAD TYPE
    # ========================================================

    for leg in all_legs:

        normalized_type = normalize_load_type(
            leg.load_type
        )

        if not normalized_type:
            continue

        if normalized_type not in grouped_legs:

            grouped_legs[normalized_type] = []

        grouped_legs[normalized_type].append(
            leg
        )

    # ========================================================
    # NORMAL ORDER
    # ========================================================

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
    # SUMMARY BY LOAD TYPE
    # ========================================================

    for load_type in ordered_load_types:

        legs = grouped_legs[
            load_type
        ]

        speeds = []

        consumptions = []

        target_speeds = []

        target_consumptions = []

        # ====================================================
        # DAILY ACTUAL PERFORMANCE
        # ====================================================

        for leg in legs:

            observations = (
                VoyageObservation.objects
                .filter(
                    leg=leg,
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

                # =================================================
                # SPEED
                # =================================================
                #
                # Use the daily observation speed.
                #
                # Do NOT average VoyageLeg.average_speed here.
                # =================================================

                if (
                    speed is not None
                    and speed >= 0
                    and duration_days is not None
                    and duration_days > 0
                ):

                    speeds.append(
                        speed
                    )

                # =================================================
                # CONSUMPTION
                # =================================================
                #
                # Period Consumption / Duration(days)
                # =================================================

                if (
                    period_consumption is not None
                    and duration_days is not None
                    and duration_days > 0
                ):

                    consumption_per_day = (
                        period_consumption
                        / duration_days
                    )

                    if consumption_per_day >= 0:

                        consumptions.append(
                            consumption_per_day
                        )

        # ========================================================
        # AVERAGE SPEED
        # ========================================================

        average_speed = (
            sum(speeds) / len(speeds)
            if speeds
            else None
        )

        # ========================================================
        # AVERAGE CONSUMPTION
        # ========================================================

        average_consumption = (
            sum(consumptions)
            / len(consumptions)
            if consumptions
            else None
        )

        # ========================================================
        # TARGETS
        # ========================================================

        for leg in legs:

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

        # ========================================================
        # AVERAGE TARGET SPEED
        # ========================================================

        target_speed = (
            sum(target_speeds)
            / len(target_speeds)
            if target_speeds
            else None
        )

        # ========================================================
        # AVERAGE TARGET CONSUMPTION
        # ========================================================

        target_consumption = (
            sum(target_consumptions)
            / len(target_consumptions)
            if target_consumptions
            else None
        )

        # ========================================================
        # STATUS
        # ========================================================

        status = calculate_status(
            average_speed,
            average_consumption,
            target_speed,
            target_consumption,
        )

        # ========================================================
        # ADD SUMMARY
        # ========================================================

        summaries.append(
            {
                "load_type": load_type,

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
    # RENDER OVERVIEW
    # ========================================================

    return render(
        request,
        "scoc_monitoring/import_result.html",
        {
            "result": result,

            "summaries": summaries,

            "vessel": vessel,
        },
    )
# ============================================================
# ROUTES / VOYAGE LEGS
# ============================================================

def voyage_legs(
    request,
    vessel_id,
    load_type,
    performance_type="speed",
    
):
    """
    Display voyage legs for Ballast/Laden.

    load_type:
        ballast
        laden
        unknown

    performance_type:
        speed
        consumption

    If performance_type is omitted,
    speed is used.

    Therefore:

        /routes/ballast/

    is equivalent to:

        /routes/ballast/speed/
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

    # ========================================================
    # VALIDATE PERFORMANCE TYPE
    # ========================================================

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
    .filter(
        vessel_id=vessel_id,
    )
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

            legs.append(
                leg
            )

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
            .filter(
                leg=leg
            )
            .count()
        )

        # ----------------------------------------------------
        # APPEND
        # ----------------------------------------------------

        leg_rows.append(
            {
                "leg": leg,

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

             "vessel_id":
                vessel_id,
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
):
    """
    Display daily data for one voyage leg.

    Daily speed and duration come from the corrected importer,
    which follows the manual Excel calculation:

        Duration = current report time - previous report time

        Speed = Distance / Duration(days) / 24

        Consumption / 24h
            = Period Consumption / Duration(days)
    """

    leg = get_object_or_404(
        VoyageLeg,
        id=leg_id,
    )

    target_speed = safe_float(
        leg.target_speed
    )

    target_consumption = safe_float(
        leg.target_consumption
    )

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
    # DAILY OBSERVATIONS
    # ========================================================

    for observation in observations:

        # ----------------------------------------------------
        # VALUES CALCULATED BY IMPORTER
        # ----------------------------------------------------

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
        # EXCEL-STYLE NORMALIZED CONSUMPTION
        #
        # Q = P / D
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
        # DO NOT RECALCULATE SPEED FROM RUNNING HOURS
        # ----------------------------------------------------
        #
        # The corrected importer uses:
        #
        # L = Distance / Duration(days) / 24
        #
        # Therefore use observation.speed directly.
        # ----------------------------------------------------

        calculated_speed = speed

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        status = calculate_observation_status(
            calculated_speed,
            consumption_per_day,
            target_speed,
            target_consumption,
        )

        # ----------------------------------------------------
        # REPORT DATE
        # ----------------------------------------------------

        report_date = (
            observation.reported_time
        )

        # ----------------------------------------------------
        # DAILY ROW
        # ----------------------------------------------------

        daily_rows.append(
            {
                "observation":
                    observation,

                "report_date":
                    report_date,

                # Excel columns

                "duration_days":
                    duration_days,

                "running_hours":
                    running_hours,

                "distance":
                    distance,

                "speed":
                    calculated_speed,

                "period_consumption":
                    period_consumption,

                "consumption":
                    consumption_per_day,

                # Other fields

                "distance_to_go":
                    safe_float(
                        observation.distance_to_go
                    ),

                "hsfo_rob":
                    safe_float(
                        observation.hsfo_rob
                    ),

                "lsfo_rob":
                    safe_float(
                        observation.lsfo_rob
                    ),

                "mgo_rob":
                    safe_float(
                        observation.mgo_rob
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

                # Status

                "speed_ok":
                    status[
                        "speed_ok"
                    ],

                "consumption_ok":
                    status[
                        "consumption_ok"
                    ],

                "target_available":
                    status[
                        "target_available"
                    ],

                "status":
                    (
                        "Achieved"
                        if status[
                            "achieved"
                        ]
                        else (
                            "Not Achieved"
                            if status[
                                "target_available"
                            ]
                            else
                            "Target Not Available"
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




############################################################################


# ============================================================
# SCoC VESSEL DASHBOARD
# ============================================================

def dashboard(request):

    vessels = (
        Vessel.objects
        .filter(
            active=True,
            scoc_active=True,
        )
        .order_by("vessel_name")
    )

    return render(
        request,
        "scoc_monitoring/dashboard.html",
        {
            "vessels": vessels,
        },
    )

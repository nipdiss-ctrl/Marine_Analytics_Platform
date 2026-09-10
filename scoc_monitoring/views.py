from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from scoc_monitoring.models import (
    ScocVessel,
    VoyageLeg,
    VoyageObservation,
)
from scoc_monitoring.services.excel_importer import import_excel


def safe_float(value):
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
    """Overall status requires both speed and consumption targets."""
    if (
        average_speed is None
        or average_consumption is None
        or target_speed is None
        or target_consumption is None
    ):
        return "Target Not Available"

    if average_speed >= target_speed and average_consumption <= target_consumption:
        return "Achieved"

    return "Not Achieved"


def calculate_performance_status(actual, target, performance_type):
    """
    Compare actual performance against the current vessel target.

    Speed:
        actual >= target  -> achieved

    Consumption:
        actual <= target  -> achieved
    """
    if actual is None or target is None:
        return {
            "status": "Target Not Available",
            "class": "secondary",
        }

    if performance_type == "speed":
        achieved = actual >= target
    else:
        achieved = actual <= target

    if achieved:
        return {
            "status": "Target Achieved",
            "class": "success",
        }

    return {
        "status": "Target Not Achieved",
        "class": "danger",
    }

def calculate_observation_status(
    speed,
    consumption,
    target_speed,
    target_consumption,
):
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
        "achieved": target_available and speed_ok and consumption_ok,
    }


def _latest_leg(legs):
    """Return the latest leg by completed/end date, then start date, then id."""
    if not legs:
        return None

    return max(
        legs,
        key=lambda leg: (
            leg.end_date or leg.start_date or datetime.min,
            leg.id,
        ),
    )


def _leg_consumption_average(leg):
    """Average authoritative daily ME consumption for one leg."""
    values = []

    for observation in leg.observations.all().order_by("reported_time", "id"):
        value = safe_float(observation.me_consumption_24)

        # Legacy rows may not yet have the explicit ME / 24h field.
        if value is None:
            period = safe_float(observation.consumption)
            duration = safe_float(observation.duration_days)
            if period is not None:
                if duration is not None and duration > 0:
                    value = period / duration
                else:
                    value = period

        if value is not None and value >= 0:
            values.append(value)

    if not values:
        return None

    return sum(values) / len(values)


def _recalculate_leg(leg):
    """Recalculate cached leg averages after a manual observation edit."""
    observations = list(
        leg.observations.all().order_by("reported_time", "id")
    )

    speeds = [
        safe_float(observation.speed)
        for observation in observations
        if safe_float(observation.speed) is not None
        and safe_float(observation.speed) >= 0
    ]

    consumptions = []
    for observation in observations:
        value = safe_float(observation.me_consumption_24)

        if value is None:
            period = safe_float(observation.consumption)
            duration = safe_float(observation.duration_days)
            if period is not None:
                value = period / duration if duration and duration > 0 else period

        if value is not None and value >= 0:
            consumptions.append(value)

    leg.average_speed = sum(speeds) / len(speeds) if speeds else None
    leg.average_consumption = (
        sum(consumptions) / len(consumptions)
        if consumptions
        else None
    )

    if observations:
        leg.start_date = observations[0].reported_time
        leg.end_date = observations[-1].reported_time
        leg.distance_to_go = observations[-1].distance_to_go

    leg.save()


# ============================================================
# UPLOAD
# ============================================================

def upload_excel(request):
    vessels = (
        ScocVessel.objects
        .filter(active=True)
        .order_by("vessel_name", "id")
    )

    if request.method != "POST":
        return render(
            request,
            "scoc_monitoring/upload.html",
            {"vessels": vessels},
        )

    uploaded_file = request.FILES.get("file")
    vessel_id = request.POST.get("vessel")

    if not vessel_id:
        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "vessels": vessels,
                "error": "Please select a vessel.",
            },
        )

    vessel = get_object_or_404(
        ScocVessel,
        id=vessel_id,
        active=True,
    )

    # --------------------------------------------------------
    # Excel is currently the only required input.
    #
    # Noon report messages are intentionally not required here.
    # The importer/backend can still support them later when
    # Outlook/API automation is added.
    # --------------------------------------------------------
    if not uploaded_file:
        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "vessels": vessels,
                "error": "Please select an Excel file.",
            },
        )

    temp_file = None

    try:
        temp_dir = Path(settings.BASE_DIR) / "temp_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_file = temp_dir / uploaded_file.name

        with open(temp_file, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        print("\n" + "=" * 70, flush=True)
        print("SCOC EXCEL UPLOAD STARTED", flush=True)
        print("Selected vessel:", vessel.vessel_name, flush=True)
        print("Uploaded file:", uploaded_file.name, flush=True)
        print("=" * 70, flush=True)

        # ----------------------------------------------------
        # Import Excel only.
        #
        # source_message is deliberately omitted for now.
        # This keeps the current workflow simple.
        # ----------------------------------------------------
        with transaction.atomic():
            result = import_excel(
                temp_file,
                vessel=vessel,
            )

        request.session["scoc_import_result"] = {
            "rows_read": int(result.get("rows_read", 0)),
            "observations_created": int(
                result.get("observations_created", 0)
            ),
            "observations_updated": int(
                result.get("observations_updated", 0)
            ),
            "legs_created": int(
                result.get("legs_created", 0)
            ),
            "legs_updated": int(
                result.get("legs_reused", 0)
            ),
            "rows_skipped": int(
                result.get("rows_skipped", 0)
            ),
            "errors": result.get("errors", []),
        }

        request.session["scoc_import_vessel_id"] = vessel.id

        return redirect(
            "scoc_monitoring:import_result",
            vessel_id=vessel.id,
        )

    except Exception as exc:
        import traceback
        traceback.print_exc()

        return render(
            request,
            "scoc_monitoring/upload.html",
            {
                "vessels": vessels,
                "error": str(exc),
            },
        )

    finally:
        if temp_file is not None:
            try:
                temp_file.unlink()
            except Exception:
                pass


# ============================================================
# OVERVIEW
# ============================================================

def import_result(request, vessel_id):
    """
    SCoC Voyage Overview.

    IMPORTANT:
    - Overview uses the vessel's CURRENT persistent targets.
    - Individual VoyageLeg records keep their historical target snapshots.
    """

    vessel = get_object_or_404(
        ScocVessel,
        pk=vessel_id,
    )

    legs = list(
        VoyageLeg.objects
        .filter(vessel=vessel)
        .prefetch_related("observations")
    )

    summaries = []

    for load_type in ["Ballast", "Laden"]:
        load_legs = [
            leg for leg in legs
            if normalize_load_type(leg.load_type) == load_type
        ]

        if not load_legs:
            continue

        # ---------------------------------------------------------
        # Only the LATEST leg is used for the overview average.
        # ---------------------------------------------------------
        latest_leg = _latest_leg(load_legs)

        observations = list(
            latest_leg.observations.all()
        )

        speeds = [
            safe_float(obs.speed)
            for obs in observations
            if safe_float(obs.speed) is not None
        ]

        consumptions = [
            safe_float(
                obs.me_consumption_24
                if obs.me_consumption_24 is not None
                else obs.consumption
            )
            for obs in observations
        ]

        consumptions = [
            value for value in consumptions
            if value is not None
        ]

        average_speed = (
            sum(speeds) / len(speeds)
            if speeds
            else safe_float(latest_leg.average_speed)
        )

        average_consumption = (
            sum(consumptions) / len(consumptions)
            if consumptions
            else _leg_consumption_average(latest_leg)
        )

        # ---------------------------------------------------------
        # CURRENT persistent vessel targets.
        #
        # These come from ScocVessel and therefore immediately
        # reflect changes made in Vessels -> Edit.
        # ---------------------------------------------------------
        target_speed = vessel.get_target_speed(load_type)
        target_consumption = vessel.get_target_consumption(load_type)

        target_speed = safe_float(target_speed)
        target_consumption = safe_float(target_consumption)

        # ---------------------------------------------------------
        # Performance status is calculated independently for
        # speed and consumption.
        # ---------------------------------------------------------
        speed_status = calculate_performance_status(
            average_speed,
            target_speed,
            performance_type="speed",
        )

        consumption_status = calculate_performance_status(
            average_consumption,
            target_consumption,
            performance_type="consumption",
        )

        summaries.append(
            {
                "load_type": load_type,
                "route_count": len(load_legs),

                "average_speed": average_speed,
                "target_speed": target_speed,
                "speed_status": speed_status,

                "average_consumption": average_consumption,
                "target_consumption": target_consumption,
                "consumption_status": consumption_status,

                "latest_leg": latest_leg,
            }
        )

    context = {
        "vessel": vessel,
        "summaries": summaries,
    }

    return render(
        request,
        "scoc_monitoring/import_result.html",
        context,
    )

# ============================================================
# ROUTES / VOYAGE LEGS
# ============================================================

def routes_home(request):
    """Route selector used by the SCoC navbar."""
    vessels = (
        ScocVessel.objects
        .filter(active=True)
        .order_by("vessel_name", "id")
    )
    return render(
        request,
        "scoc_monitoring/routes_home.html",
        {"vessels": vessels},
    )


def voyage_legs(request, vessel_id, load_type, performance_type):
    vessel = get_object_or_404(
        ScocVessel,
        pk=vessel_id,
    )

    load_type = normalize_load_type(load_type)

    performance_type = str(performance_type).strip().lower()

    if performance_type not in {"speed", "consumption"}:
        performance_type = "speed"

    legs = (
        VoyageLeg.objects
        .filter(
            vessel=vessel,
            load_type=load_type,
        )
        .prefetch_related("observations")
        .order_by("-start_date", "-id")
    )

    # =========================================================
    # CURRENT PERSISTENT VESSEL TARGETS
    #
    # These come from Vessels -> Edit.
    # They are NOT the historical VoyageLeg target fields.
    # =========================================================
    target_speed = safe_float(
        vessel.get_target_speed(load_type)
    )

    target_consumption = safe_float(
        vessel.get_target_consumption(load_type)
    )

    leg_rows = []

    for leg in legs:

        observations = list(
            leg.observations.all().order_by(
                "reported_time",
                "id",
            )
        )

        # =====================================================
        # AVERAGE SPEED
        # =====================================================
        speed_values = []

        for observation in observations:
            value = safe_float(observation.speed)

            if value is not None and value >= 0:
                speed_values.append(value)

        average_speed = (
            sum(speed_values) / len(speed_values)
            if speed_values
            else None
        )

        # =====================================================
        # AVERAGE CONSUMPTION
        #
        # Use the same authoritative calculation used by the
        # individual route page.
        # =====================================================
        average_consumption = _leg_consumption_average(leg)

        # =====================================================
        # SELECT PERFORMANCE TYPE
        # =====================================================
        if performance_type == "speed":
            actual_value = average_speed
            target_value = target_speed
        else:
            actual_value = average_consumption
            target_value = target_consumption

        # =====================================================
        # STATUS
        #
        # Speed:
        #   Actual >= Target = Achieved
        #
        # Consumption:
        #   Actual <= Target = Achieved
        # =====================================================
        if actual_value is None or target_value is None:
            status = "Target Not Available"

        elif performance_type == "speed":
            status = (
                "Achieved"
                if actual_value >= target_value
                else "Not Achieved"
            )

        else:
            status = (
                "Achieved"
                if actual_value <= target_value
                else "Not Achieved"
            )

        leg_rows.append(
            {
                "leg": leg,

                "average_speed": average_speed,
                "target_speed": target_speed,

                "average_consumption": average_consumption,
                "target_consumption": target_consumption,

                "observation_count": len(observations),

                "status": status,
            }
        )

    context = {
        "vessel": vessel,
        "vessel_id": vessel.id,

        "load_type": load_type,
        "performance_type": performance_type,

        "target_speed": target_speed,
        "target_consumption": target_consumption,

        "leg_rows": leg_rows,
    }

    return render(
        request,
        (
            "scoc_monitoring/voyage_legs_speed.html"
            if performance_type == "speed"
            else "scoc_monitoring/voyage_legs_consumption.html"
        ),
        context,
    )


# ============================================================
# VOYAGE DETAIL / DAILY DATA
# ============================================================

def voyage_detail(request, leg_id):
    leg = get_object_or_404(
        VoyageLeg.objects.select_related("vessel"),
        id=leg_id,
    )

    performance_type = request.POST.get("performance_type") or request.GET.get(
        "performance_type", "speed"
    )
    performance_type = str(performance_type).strip().lower()
    if performance_type not in {"speed", "consumption"}:
        performance_type = "speed"

    if leg.vessel:
        target_speed = safe_float(
            leg.vessel.get_target_speed(leg.load_type)
    )
        target_consumption = safe_float(
            leg.vessel.get_target_consumption(leg.load_type)
    )
    else:
        target_speed = None
        target_consumption = None

    observations = list(
        VoyageObservation.objects
        .filter(leg=leg)
        .order_by("reported_time", "id")
    )

    if request.method == "POST":
        observation_id = request.POST.get("observation_id")
        new_value = request.POST.get("value")

        observation = get_object_or_404(
            VoyageObservation,
            id=observation_id,
            leg=leg,
        )

        try:
            if new_value is None or not new_value.strip():
                raise ValueError("Value cannot be empty.")

            value = float(new_value.strip())
            if value < 0:
                raise ValueError("Value cannot be negative.")
        except (ValueError, TypeError):
            return redirect(
                "scoc_monitoring:voyage_detail",
                leg_id=leg.id,
            ) + f"?performance_type={performance_type}"

        if performance_type == "speed":
            observation.speed = value
        else:
            # The page edits the displayed authoritative ME / 24h value.
            observation.me_consumption_24 = value

        observation.save()
        _recalculate_leg(leg)

        return redirect(
            "scoc_monitoring:voyage_detail",
            leg_id=leg.id,
        ) + f"?performance_type={performance_type}"

    daily_rows = []

    for observation in observations:
        speed = safe_float(observation.speed)
        consumption = safe_float(observation.me_consumption_24)

        # Legacy fallback for records imported before me_consumption_24 existed.
        if consumption is None:
            period = safe_float(observation.consumption)
            duration = safe_float(observation.duration_days)
            if period is not None:
                consumption = period / duration if duration and duration > 0 else period

        status = calculate_observation_status(
            speed,
            consumption,
            target_speed,
            target_consumption,
        )

        daily_rows.append(
            {
                "observation": observation,
                "report_date": observation.reported_time,
                "speed": speed,
                "consumption": consumption,
                "duration_days": safe_float(observation.duration_days),
                "running_hours": safe_float(observation.running_hours),
                "distance": safe_float(observation.distance),
                "distance_to_go": safe_float(observation.distance_to_go),
                "hsfo_rob": safe_float(observation.hsfo_rob),
                "lsfo_rob": safe_float(observation.lsfo_rob),
                "mgo_rob": safe_float(observation.mgo_rob),
                "power_kw": safe_float(observation.power_kw),
                "rpm": safe_float(observation.rpm),
                "load_percent": safe_float(observation.load_percent),
                "scoc": safe_float(observation.scoc),
                "cylinder_oil": safe_float(observation.cylinder_oil_consumption_l),
                "speed_ok": status["speed_ok"],
                "consumption_ok": status["consumption_ok"],
                "target_available": status["target_available"],
                "status": (
                    calculate_performance_status(
                        speed,
                        target_speed,
                        "speed",
                    )
                    if performance_type == "speed"
                    else calculate_performance_status(
                        consumption,
                        target_consumption,
                        "consumption",
                    )
                ),
            }
        )

    average_speed = safe_float(leg.average_speed)
    average_consumption = _leg_consumption_average(leg)

    selected_value = (
        average_speed if performance_type == "speed" else average_consumption
    )
    selected_target = (
        target_speed if performance_type == "speed" else target_consumption
    )

    voyage_status = calculate_performance_status(
        selected_value,
        selected_target,
        performance_type,
    )

    return render(
        request,
        "scoc_monitoring/voyage_detail.html",
        {
            "leg": leg,
            "daily_rows": daily_rows,
            "target_speed": target_speed,
            "target_consumption": target_consumption,
            "voyage_status": voyage_status,
            "observation_count": len(daily_rows),
            "valid_speed_count": sum(1 for row in daily_rows if row["speed"] is not None),
            "valid_consumption_count": sum(
                1 for row in daily_rows if row["consumption"] is not None
            ),
            "performance_type": performance_type,
        },
    )


# ============================================================
# OLD OBSERVATION URL
# ============================================================

def observation_detail(request, observation_id):
    observation = get_object_or_404(
        VoyageObservation,
        id=observation_id,
    )

    return redirect(
        "scoc_monitoring:voyage_detail",
        leg_id=observation.leg_id,
    )


# ============================================================
# VESSEL MANAGEMENT
# ============================================================

def vessel_list(request):
    vessels = ScocVessel.objects.order_by("vessel_name", "id")
    return render(
        request,
        "scoc_monitoring/vessels.html",
        {"vessels": vessels},
    )


def vessel_create(request):
    from scoc_monitoring.forms import ScocVesselForm

    if request.method == "POST":
        form = ScocVesselForm(request.POST)
        if form.is_valid():
            vessel = form.save()
            return redirect(
                "scoc_monitoring:vessel_edit",
                vessel_id=vessel.id,
            )
    else:
        form = ScocVesselForm()

    return render(
        request,
        "scoc_monitoring/vessel_form.html",
        {
            "form": form,
            "page_title": "Add SCoC Vessel",
            "submit_label": "Save Vessel",
            "vessel": None,
        },
    )


def vessel_edit(request, vessel_id):
    from scoc_monitoring.forms import ScocVesselForm

    vessel = get_object_or_404(ScocVessel, id=vessel_id)

    if request.method == "POST":
        form = ScocVesselForm(request.POST, instance=vessel)
        if form.is_valid():
            form.save()
            return redirect("scoc_monitoring:vessel_list")
    else:
        form = ScocVesselForm(instance=vessel)

    return render(
        request,
        "scoc_monitoring/vessel_form.html",
        {
            "form": form,
            "page_title": f"Edit SCoC Vessel - {vessel.vessel_name}",
            "submit_label": "Save Changes",
            "vessel": vessel,
        },
    )


# ============================================================
# SCoC VESSEL DASHBOARD
# ============================================================

def dashboard(request):
    vessels = (
        ScocVessel.objects
        .filter(active=True)
        .order_by("vessel_name", "id")
    )

    return render(
        request,
        "scoc_monitoring/dashboard.html",
        {"vessels": vessels},
    )

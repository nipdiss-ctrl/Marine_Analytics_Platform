import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from inspections.models import (
    Inspection,
    InspectionFinding,
    Vessel,
)


@login_required
def dashboard(request):

    # =========================================================
    # LOAD INSPECTIONS
    # =========================================================

    inspections = (
        Inspection.objects
        .select_related("vessel")
        .prefetch_related("findings")
        .order_by("-inspection_date", "-id")
    )

    # =========================================================
    # INITIALISE DASHBOARD DATA
    # =========================================================

    inspection_register = []

    chart_labels = []
    high_data = []
    medium_data = []
    low_data = []
    total_data = []
    severity_data = []
    validity_data = []

    # =========================================================
    # PROCESS EACH INSPECTION
    # =========================================================

    for inspection in inspections:

        # -----------------------------------------------------
        # FINDINGS BY RISK
        # -----------------------------------------------------

        high = inspection.findings.filter(
            risk_level="HIGH"
        ).count()

        medium = inspection.findings.filter(
            risk_level="MEDIUM"
        ).count()

        low = inspection.findings.filter(
            risk_level="LOW"
        ).count()

        # -----------------------------------------------------
        # TOTAL FINDINGS
        # -----------------------------------------------------

        total = high + medium + low

        # -----------------------------------------------------
        # SEVERITY SCORE
        #
        # HIGH   = 3
        # MEDIUM = 2
        # LOW    = 1
        # -----------------------------------------------------

        severity = (
            (high * 3)
            + (medium * 2)
            + (low * 1)
        )

        # -----------------------------------------------------
        # DATE
        # -----------------------------------------------------

        inspection_date = inspection.inspection_date

        if inspection_date:

            date_label = inspection_date.strftime(
                "%d-%b-%y"
            )

        else:

            date_label = "No Date"

        # -----------------------------------------------------
        # CHART LABEL
        # -----------------------------------------------------

        chart_labels.append(
            f"{inspection.vessel.vessel_name} - {date_label}"
        )

        # -----------------------------------------------------
        # CHART DATA
        # -----------------------------------------------------

        high_data.append(high)
        medium_data.append(medium)
        low_data.append(low)
        total_data.append(total)
        severity_data.append(severity)

        validity_data.append(
            inspection.validity_months or 0
        )

        # -----------------------------------------------------
        # INSPECTION REGISTER
        # -----------------------------------------------------

        inspection_register.append(
            {
                "inspection": inspection,
                "vessel": inspection.vessel.vessel_name,
                "date": inspection.inspection_date,
                "high": high,
                "medium": medium,
                "low": low,
                "total": total,
                "severity": severity,
                "validity": inspection.validity_months,
            }
        )

    # =========================================================
    # KPI COUNTS
    # =========================================================

    total_vessels = Vessel.objects.count()

    total_inspections = Inspection.objects.count()

    total_findings = InspectionFinding.objects.count()

    high_risk = InspectionFinding.objects.filter(
        risk_level="HIGH"
    ).count()

    medium_risk = InspectionFinding.objects.filter(
        risk_level="MEDIUM"
    ).count()

    low_risk = InspectionFinding.objects.filter(
        risk_level="LOW"
    ).count()

    # =========================================================
    # DASHBOARD CONTEXT
    # =========================================================

    context = {

        # =====================================================
        # KPI
        # =====================================================

        "total_vessels": total_vessels,

        "total_inspections": total_inspections,

        "total_findings": total_findings,

        "high_risk": high_risk,

        "medium_risk": medium_risk,

        "low_risk": low_risk,

        # =====================================================
        # INSPECTION REGISTER
        # =====================================================

        "inspection_register": inspection_register,

        # =====================================================
        # CHART DATA
        # =====================================================

        "chart_labels": json.dumps(
            chart_labels
        ),

        "high_data": json.dumps(
            high_data
        ),

        "medium_data": json.dumps(
            medium_data
        ),

        "low_data": json.dumps(
            low_data
        ),

        "total_data": json.dumps(
            total_data
        ),

        "severity_data": json.dumps(
            severity_data
        ),

        "validity_data": json.dumps(
            validity_data
        ),
    }

    # =========================================================
    # RENDER RIGHTSHIP DASHBOARD
    # =========================================================

    return render(
        request,
        "dashboard/dashboard.html",
        context,
    )
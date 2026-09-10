import re
from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from openpyxl import load_workbook

from .forms import (
    VesselForm,
    InspectionForm,
    InspectionFindingForm,
    ChecklistItemForm,
    InspectionFindingRiskForm,
)

from .models import (
    Vessel,
    Inspection,
    ChecklistItem,
    InspectionFinding,
    RightShipRegisterRecord,
)


# =========================================================
# RIGHTSHIP RISK COLOUR DETECTION
# =========================================================

def get_excel_colour(cell):
    """
    Return the actual Excel colour information from a cell.

    Supports:
        RGB
        ARGB
        indexed
        theme
    """

    if cell is None:
        return None

    fill = cell.fill

    if fill is None:
        return None

    if fill.fill_type != "solid":
        return None

    color = fill.fgColor

    if color is None:
        return None

    if color.type == "rgb":

        rgb = color.rgb

        if rgb:

            rgb = str(rgb).upper().replace("#", "")

            if len(rgb) == 8:
                rgb = rgb[-6:]

            return rgb

    if color.type == "indexed":

        indexed = color.indexed

        if indexed is not None:
            return f"INDEXED:{indexed}"

    if color.type == "theme":

        theme = color.theme

        if theme is not None:
            return f"THEME:{theme}"

    return None


def get_risk_from_excel_cell(cell):
    """
    Detect RightShip risk from the Excel fill colour.

    RightShip convention:

        RED     -> HIGH
        ORANGE  -> MEDIUM
        YELLOW  -> LOW
    """

    if cell is None:
        return None

    fill = cell.fill

    if not fill:
        return None

    if fill.fill_type != "solid":
        return None

    color = fill.fgColor

    if color is None:
        return None

    # =====================================================
    # RGB / ARGB
    # =====================================================

    if color.type == "rgb" and color.rgb:

        rgb = str(color.rgb).upper().replace("#", "")

        if len(rgb) == 8:
            rgb = rgb[-6:]

        yellow_values = {
            "FFFF00",
            "FFF200",
            "FFD966",
            "FFE699",
            "FFFF99",
        }

        orange_values = {
            "FFC000",
            "F4B183",
            "ED7D31",
            "FF9900",
            "F39C12",
        }

        red_values = {
            "FF0000",
            "C00000",
            "FF5050",
            "E74C3C",
            "D9534F",
        }

        if rgb in yellow_values:
            return "LOW"

        if rgb in orange_values:
            return "MEDIUM"

        if rgb in red_values:
            return "HIGH"

    # =====================================================
    # INDEXED COLOURS
    # =====================================================

    if color.type == "indexed":

        indexed = color.indexed

        if indexed in {6, 13}:
            return "LOW"

        if indexed in {45, 52}:
            return "MEDIUM"

        if indexed in {9, 10}:
            return "HIGH"

    return None


# =========================================================
# DEBUG HELPER
# =========================================================

def inspect_excel_colour(cell):

    fill = cell.fill
    color = fill.fgColor if fill else None

    return {
        "coordinate": cell.coordinate,
        "fill_type": fill.fill_type if fill else None,
        "color_type": color.type if color else None,
        "rgb": color.rgb if color else None,
        "indexed": color.indexed if color else None,
        "theme": color.theme if color else None,
    }


# =========================================================
# VESSEL LIST
# =========================================================

@login_required
def vessel_list(request):

    vessels = (
        Vessel.objects
        .all()
        .order_by("vessel_name")
    )

    return render(
        request,
        "inspections/vessel_list.html",
        {
            "vessels": vessels,
        },
    )


# =========================================================
# CREATE VESSEL
# =========================================================

@login_required
def vessel_create(request):

    if request.method == "POST":

        form = VesselForm(request.POST)

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Vessel created successfully.",
            )

            return redirect("vessel_list")

    else:

        form = VesselForm()

    return render(
        request,
        "inspections/vessel_form.html",
        {
            "form": form,
        },
    )


# =========================================================
# EDIT VESSEL
# =========================================================

@login_required
def vessel_edit(request, pk):

    vessel = get_object_or_404(
        Vessel,
        pk=pk,
    )

    if request.method == "POST":

        form = VesselForm(
            request.POST,
            instance=vessel,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Vessel updated successfully.",
            )

            return redirect("vessel_list")

    else:

        form = VesselForm(
            instance=vessel,
        )

    return render(
        request,
        "inspections/vessel_form.html",
        {
            "form": form,
            "vessel": vessel,
        },
    )


# =========================================================
# DELETE VESSEL
# =========================================================

@login_required
def vessel_delete(request, pk):

    vessel = get_object_or_404(
        Vessel,
        pk=pk,
    )

    if request.method == "POST":

        vessel.delete()

        messages.success(
            request,
            "Vessel deleted successfully.",
        )

        return redirect("vessel_list")

    return render(
        request,
        "inspections/vessel_confirm_delete.html",
        {
            "vessel": vessel,
        },
    )


# =========================================================
# INSPECTION LIST
# =========================================================

@login_required
def inspection_list(request):

    inspections = (
        Inspection.objects
        .select_related("vessel")
        .prefetch_related("findings")
        .order_by(
            "-inspection_date",
            "-id",
        )
    )

    total_inspections = inspections.count()

    open_inspections = inspections.filter(
        status="OPEN"
    ).count()

    completed_inspections = inspections.filter(
        status="COMPLETED"
    ).count()

    total_vessels = Vessel.objects.count()

    high_risk = InspectionFinding.objects.filter(
        risk_level="HIGH"
    ).count()

    medium_risk = InspectionFinding.objects.filter(
        risk_level="MEDIUM"
    ).count()

    low_risk = InspectionFinding.objects.filter(
        risk_level="LOW"
    ).count()

    return render(
        request,
        "inspections/inspection_list.html",
        {
            "inspections": inspections,

            "total_inspections":
                total_inspections,

            "open_inspections":
                open_inspections,

            "completed_inspections":
                completed_inspections,

            "total_vessels":
                total_vessels,

            "high_risk":
                high_risk,

            "medium_risk":
                medium_risk,

            "low_risk":
                low_risk,
        },
    )


# =========================================================
# CREATE INSPECTION
# =========================================================

@login_required
def inspection_create(request):

    if request.method == "POST":

        form = InspectionForm(request.POST)

        if form.is_valid():

            inspection = form.save(
                commit=False
            )

            year = timezone.now().year

            last = (
                Inspection.objects
                .filter(
                    inspection_no__startswith=(
                        f"INS-{year}-"
                    )
                )
                .order_by("-id")
                .first()
            )

            if last:

                last_no = int(
                    last.inspection_no
                    .split("-")[-1]
                )

                next_no = last_no + 1

            else:

                next_no = 1

            inspection.inspection_no = (
                f"INS-{year}-{next_no:05d}"
            )

            inspection.save()

            messages.success(
                request,
                "Inspection created successfully.",
            )

            return redirect(
                "inspection_list"
            )

    else:

        form = InspectionForm()

    return render(
        request,
        "inspections/inspection_form.html",
        {
            "form": form,
        },
    )


# =========================================================
# INSPECTION FINDINGS
# =========================================================

@login_required
def inspection_findings(request, pk):

    inspection = get_object_or_404(
        Inspection.objects.select_related(
            "vessel"
        ),
        pk=pk,
    )

    findings = (
        inspection.findings
        .select_related("checklist_item")
        .order_by(
            "checklist_item__ref_no"
        )
    )

    total_findings = findings.count()

    high_risk = findings.filter(
        risk_level="HIGH"
    ).count()

    medium_risk = findings.filter(
        risk_level="MEDIUM"
    ).count()

    low_risk = findings.filter(
        risk_level="LOW"
    ).count()

    severity_score = (
        high_risk * 3
        + medium_risk * 2
        + low_risk
    )

    return render(
        request,
        "inspections/inspection_findings.html",
        {
            "inspection":
                inspection,

            "findings":
                findings,

            "total_findings":
                total_findings,

            "high_risk":
                high_risk,

            "medium_risk":
                medium_risk,

            "low_risk":
                low_risk,

            "severity_score":
                severity_score,
        },
    )


# =========================================================
# CREATE FINDING
# =========================================================

@login_required
def finding_create(
    request,
    inspection_id,
):

    inspection = get_object_or_404(
        Inspection,
        pk=inspection_id,
    )

    used_items = (
        InspectionFinding.objects
        .filter(
            inspection=inspection,
        )
        .values_list(
            "checklist_item_id",
            flat=True,
        )
    )

    if request.method == "POST":

        form = InspectionFindingForm(
            request.POST,
            inspection=inspection,
        )

        form.fields[
            "checklist_item"
        ].queryset = (
            ChecklistItem.objects
            .exclude(
                id__in=used_items,
            )
            .order_by("ref_no")
        )

        if form.is_valid():

            finding = form.save(
                commit=False
            )

            finding.inspection = inspection

            finding.save()

            messages.success(
                request,
                "Finding added successfully.",
            )

            return redirect(
                "finding_create",
                inspection_id=inspection.id,
            )

    else:

        form = InspectionFindingForm(
            inspection=inspection,
        )

        form.fields[
            "checklist_item"
        ].queryset = (
            ChecklistItem.objects
            .exclude(
                id__in=used_items,
            )
            .order_by("ref_no")
        )

    findings = (
        InspectionFinding.objects
        .filter(
            inspection=inspection,
        )
        .select_related(
            "checklist_item",
        )
        .order_by(
            "checklist_item__ref_no",
        )
    )

    return render(
        request,
        "inspections/finding_form.html",
        {
            "inspection":
                inspection,

            "form":
                form,

            "findings":
                findings,
        },
    )


# =========================================================
# EDIT FINDING RISK
# =========================================================

@login_required
def finding_edit_risk(request, pk):

    finding = get_object_or_404(
        InspectionFinding,
        pk=pk,
    )

    if request.method == "POST":

        form = InspectionFindingRiskForm(
            request.POST,
            instance=finding,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Risk level updated successfully.",
            )

            return redirect(
                "finding_create",
                inspection_id=finding.inspection.id,
            )

    else:

        form = InspectionFindingRiskForm(
            instance=finding,
        )

    return render(
        request,
        "inspections/finding_edit_risk.html",
        {
            "finding":
                finding,

            "form":
                form,
        },
    )


# =========================================================
# DELETE FINDING
# =========================================================

@login_required
def finding_delete(request, pk):

    finding = get_object_or_404(
        InspectionFinding,
        pk=pk,
    )

    inspection_id = (
        finding.inspection.id
    )

    if request.method == "POST":

        finding.delete()

        messages.success(
            request,
            "Finding deleted successfully.",
        )

    return redirect(
        "inspection_findings",
        pk=inspection_id,
    )


# =========================================================
# CHECKLIST ITEM CREATE
# =========================================================

@login_required
def checklistitem_create(request):

    if request.method == "POST":

        form = ChecklistItemForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Checklist item created successfully.",
            )

            return redirect(
                "checklistitem_list"
            )

    else:

        form = ChecklistItemForm()

    return render(
        request,
        "inspections/checklistitem_form.html",
        {
            "form":
                form,
        },
    )


# =========================================================
# CHECKLIST ITEM LIST
# =========================================================

@login_required
def checklistitem_list(request):

    items = (
        ChecklistItem.objects
        .all()
        .order_by("ref_no")
    )

    return render(
        request,
        "inspections/checklistitem_list.html",
        {
            "items":
                items,
        },
    )


# =========================================================
# RIGHTSHIP GRAPH IMPORT
# =========================================================

def import_graph_register(workbook):
    """
    Import the authoritative GRAPH worksheet.

    GRAPH headers are located around row 42:

        C = Vessel Name
        D = Inspection Date
        E = High Risk
        F = Medium Risk
        G = Low Risk
        H = Total Findings
        I = Severity Score
        J = Validity (Months)

    This stores both 2025 and 2026 records in
    RightShipRegisterRecord.

    The GRAPH data is deliberately kept separate from
    InspectionFinding because the GRAPH sheet is the
    authoritative historical register.
    """

    if "GRAPH" not in workbook.sheetnames:
        return 0, 0

    ws = workbook["GRAPH"]

    header_row = None

    # Search for the actual header instead of assuming
    # the exact row number.
    for row in range(1, min(ws.max_row, 60) + 1):

        values = []

        for col in range(1, ws.max_column + 1):

            value = ws.cell(
                row=row,
                column=col,
            ).value

            if value is not None:

                values.append(
                    str(value).strip().casefold()
                )

        if (
            "vessel name" in values
            and "inspection date" in values
            and "high risk" in values
            and "medium risk" in values
            and "low risk" in values
        ):

            header_row = row
            break

    if header_row is None:
        return 0, 0

    # -----------------------------------------------------
    # Header mapping
    # -----------------------------------------------------

    headers = {}

    for col in range(
        1,
        ws.max_column + 1,
    ):

        value = ws.cell(
            row=header_row,
            column=col,
        ).value

        if value is None:
            continue

        key = str(
            value
        ).strip().casefold()

        headers[key] = col

    vessel_col = headers.get(
        "vessel name"
    )

    date_col = headers.get(
        "inspection date"
    )

    high_col = headers.get(
        "high risk"
    )

    medium_col = headers.get(
        "medium risk"
    )

    low_col = headers.get(
        "low risk"
    )

    total_col = headers.get(
        "total findings"
    )

    severity_col = headers.get(
        "severity score"
    )

    validity_col = headers.get(
        "validity (months)"
    )

    required_columns = [
        vessel_col,
        date_col,
        high_col,
        medium_col,
        low_col,
    ]

    if any(
        column is None
        for column in required_columns
    ):
        return 0, 0

    created = 0
    updated = 0

    # -----------------------------------------------------
    # Import rows
    # -----------------------------------------------------

    for row_number in range(
        header_row + 1,
        ws.max_row + 1,
    ):

        vessel_value = ws.cell(
            row=row_number,
            column=vessel_col,
        ).value

        inspection_date = ws.cell(
            row=row_number,
            column=date_col,
        ).value

        if (
            vessel_value is None
            or inspection_date is None
        ):
            continue

        vessel_name = str(
            vessel_value
        ).strip()

        if not vessel_name:
            continue

        # -------------------------------------------------
        # Date
        # -------------------------------------------------

        if not hasattr(
            inspection_date,
            "year",
        ):
            continue

        # -------------------------------------------------
        # Numeric values
        # -------------------------------------------------

        def graph_int(value):

            if value is None:
                return 0

            try:
                return int(
                    float(value)
                )
            except (
                ValueError,
                TypeError,
            ):
                return 0

        high = graph_int(
            ws.cell(
                row=row_number,
                column=high_col,
            ).value
        )

        medium = graph_int(
            ws.cell(
                row=row_number,
                column=medium_col,
            ).value
        )

        low = graph_int(
            ws.cell(
                row=row_number,
                column=low_col,
            ).value
        )

        calculated_total = (
            high
            + medium
            + low
        )

        if total_col is not None:

            total_value = graph_int(
                ws.cell(
                    row=row_number,
                    column=total_col,
                ).value
            )

            total = (
                total_value
                if total_value
                else calculated_total
            )

        else:

            total = calculated_total

        calculated_severity = (
            high * 3
            + medium * 2
            + low
        )

        if severity_col is not None:

            severity_value = graph_int(
                ws.cell(
                    row=row_number,
                    column=severity_col,
                ).value
            )

            severity = (
                severity_value
                if severity_value
                else calculated_severity
            )

        else:

            severity = calculated_severity

        validity = 0

        if validity_col is not None:

            validity = graph_int(
                ws.cell(
                    row=row_number,
                    column=validity_col,
                ).value
            )

        # -------------------------------------------------
        # Vessel
        # -------------------------------------------------

        vessel, _ = (
            Vessel.objects.get_or_create(
                vessel_name=vessel_name,
            )
        )

        # -------------------------------------------------
        # Register record
        # -------------------------------------------------

        register_record, record_created = (
            RightShipRegisterRecord.objects.update_or_create(

                vessel=vessel,

                inspection_date=(
                    inspection_date
                ),

                defaults={

                    "high_risk":
                        high,

                    "medium_risk":
                        medium,

                    "low_risk":
                        low,

                    "total_findings":
                        total,

                    "severity_score":
                        severity,

                    "validity_months":
                        validity,

                    "source_row":
                        row_number,
                },
            )
        )

        if record_created:
            created += 1
        else:
            updated += 1

    return created, updated


# =========================================================
# RIGHTSHIP EXCEL IMPORT
# =========================================================

@login_required
@transaction.atomic
def inspection_import(request):

    sheet_data = []

    if request.method != "POST":

        return render(
            request,
            "inspections/inspection_import.html",
            {
                "sheet_data":
                    sheet_data,
            },
        )

    excel_file = request.FILES.get(
        "excel_file"
    )

    if not excel_file:

        messages.error(
            request,
            "Please select an Excel workbook.",
        )

        return render(
            request,
            "inspections/inspection_import.html",
            {
                "sheet_data":
                    sheet_data,
            },
        )

    try:

        workbook = load_workbook(
            excel_file,
            data_only=True,
        )

    except Exception as exc:

        messages.error(
            request,
            f"Could not read Excel workbook: {exc}",
        )

        return render(
            request,
            "inspections/inspection_import.html",
            {
                "sheet_data":
                    sheet_data,
            },
        )

    # =====================================================
    # GRAPH WORKSHEET
    # =====================================================

    graph_created, graph_updated = (
        import_graph_register(
            workbook
        )
    )

    if graph_created or graph_updated:

        messages.success(
            request,
            (
                f"GRAPH register imported: "
                f"{graph_created} new record(s), "
                f"{graph_updated} updated record(s)."
            ),
        )

    # =====================================================
    # DETAILED SHEETS
    # =====================================================

    skip_sheets = {
        "Index",
        "GRAPH",
        "Sheet1",
    }

    total_created = 0
    total_updated = 0
    total_skipped = 0

    total_low = 0
    total_medium = 0
    total_high = 0
    total_unclassified = 0

    # =====================================================
    # EACH VESSEL SHEET
    # =====================================================

    for ws in workbook.worksheets:

        if ws.title in skip_sheets:
            continue

        vessel_name = str(
            ws.title
        ).strip()

        if not vessel_name:
            continue

        # =================================================
        # HEADER
        # =================================================

        port = ws["D3"].value
        inspection_date = ws["D4"].value
        inspector = ws["D5"].value
        findings = ws["D6"].value
        validity_text = ws["D7"].value

        # =================================================
        # VALIDITY
        # =================================================

        validity = 6

        if validity_text:

            try:

                validity = int(
                    str(
                        validity_text
                    ).split()[0]
                )

            except (
                ValueError,
                TypeError,
            ):

                validity = 6

        # =================================================
        # VESSEL
        # =================================================

        vessel, vessel_created = (
            Vessel.objects.get_or_create(
                vessel_name=vessel_name,
            )
        )

        # =================================================
        # INSPECTION
        # =================================================

        inspection = (
            Inspection.objects
            .filter(
                vessel=vessel,
                inspection_date=inspection_date,
            )
            .first()
        )

        inspection_created = False

        if inspection is None:

            if hasattr(
                inspection_date,
                "year",
            ):

                year = (
                    inspection_date.year
                )

            else:

                year = timezone.now().year

            last = (
                Inspection.objects
                .filter(
                    inspection_no__startswith=(
                        f"INS-{year}-"
                    )
                )
                .order_by("-id")
                .first()
            )

            if last:

                next_no = (
                    int(
                        last.inspection_no
                        .split("-")[-1]
                    )
                    + 1
                )

            else:

                next_no = 1

            inspection = (
                Inspection.objects.create(

                    inspection_no=(
                        f"INS-{year}-{next_no:05d}"
                    ),

                    vessel=vessel,

                    port=port or "",

                    inspection_date=(
                        inspection_date
                    ),

                    inspector=(
                        inspector or ""
                    ),

                    validity_months=(
                        validity
                    ),

                    status="OPEN",

                    remarks=(
                        "Imported from RightShip Excel"
                    ),
                )
            )

            inspection_created = True

        else:

            inspection.port = (
                port or ""
            )

            inspection.inspector = (
                inspector or ""
            )

            inspection.validity_months = (
                validity
            )

            inspection.save(
                update_fields=[
                    "port",
                    "inspector",
                    "validity_months",
                ]
            )

        # =================================================
        # COUNTERS
        # =================================================

        findings_created = 0
        findings_updated = 0
        findings_skipped = 0

        low_count = 0
        medium_count = 0
        high_count = 0
        unclassified_count = 0

        # =================================================
        # FINDINGS
        # =================================================

        for row in range(
            9,
            ws.max_row + 1,
        ):

            ref_cell = ws[f"B{row}"]

            ref_no = ref_cell.value

            inspected_item = (
                ws[f"C{row}"].value
            )

            finding_description = (
                ws[f"D{row}"].value
            )

            # ---------------------------------------------
            # Skip empty rows
            # ---------------------------------------------

            if ref_no is None:
                continue

            ref_no = str(
                ref_no
            ).strip()

            if not ref_no:
                continue

            inspected_item = (
                str(
                    inspected_item
                ).strip()
                if inspected_item is not None
                else ""
            )

            finding_description = (
                str(
                    finding_description
                ).strip()
                if finding_description is not None
                else ""
            )

            # ---------------------------------------------
            # Risk from Excel colour
            # ---------------------------------------------

            risk_level = (
                get_risk_from_excel_cell(
                    ref_cell
                )
            )

            # ---------------------------------------------
            # Checklist item
            # ---------------------------------------------

            checklist_item, _ = (
                ChecklistItem.objects.get_or_create(

                    ref_no=ref_no,

                    defaults={
                        "inspected_item":
                            inspected_item,
                    },
                )
            )

            if (
                inspected_item
                and
                checklist_item.inspected_item
                != inspected_item
            ):

                checklist_item.inspected_item = (
                    inspected_item
                )

                checklist_item.save(
                    update_fields=[
                        "inspected_item"
                    ]
                )

            # ---------------------------------------------
            # Existing finding
            # ---------------------------------------------

            finding = (
                InspectionFinding.objects
                .filter(
                    inspection=inspection,
                    checklist_item=checklist_item,
                )
                .first()
            )

            # ---------------------------------------------
            # Unclassified
            # ---------------------------------------------

            if risk_level is None:

                unclassified_count += 1
                total_unclassified += 1

                if finding:

                    changed = False

                    if (
                        finding.finding_description
                        != finding_description
                    ):

                        finding.finding_description = (
                            finding_description
                        )

                        changed = True

                    if changed:

                        finding.save(
                            update_fields=[
                                "finding_description"
                            ]
                        )

                        findings_updated += 1
                        total_updated += 1

                continue

            # ---------------------------------------------
            # CREATE
            # ---------------------------------------------

            if finding is None:

                InspectionFinding.objects.create(

                    inspection=inspection,

                    checklist_item=(
                        checklist_item
                    ),

                    finding_description=(
                        finding_description
                    ),

                    risk_level=risk_level,
                )

                findings_created += 1
                total_created += 1

            # ---------------------------------------------
            # UPDATE
            # ---------------------------------------------

            else:

                changed = False

                if (
                    finding.finding_description
                    != finding_description
                ):

                    finding.finding_description = (
                        finding_description
                    )

                    changed = True

                if (
                    finding.risk_level
                    != risk_level
                ):

                    finding.risk_level = (
                        risk_level
                    )

                    changed = True

                if changed:

                    finding.save()

                    findings_updated += 1
                    total_updated += 1

                else:

                    findings_skipped += 1
                    total_skipped += 1

            # ---------------------------------------------
            # Risk counts
            # ---------------------------------------------

            if risk_level == "LOW":

                low_count += 1
                total_low += 1

            elif risk_level == "MEDIUM":

                medium_count += 1
                total_medium += 1

            elif risk_level == "HIGH":

                high_count += 1
                total_high += 1

        # =================================================
        # SHEET SUMMARY
        # =================================================

        sheet_data.append({

            "inspection_no":
                inspection.inspection_no,

            "vessel":
                vessel_name,

            "port":
                port,

            "inspection_date":
                inspection_date,

            "inspector":
                inspector,

            "findings":
                findings,

            "validity":
                validity,

            "vessel_created":
                vessel_created,

            "inspection_created":
                inspection_created,

            "findings_created":
                findings_created,

            "findings_updated":
                findings_updated,

            "findings_skipped":
                findings_skipped,

            "low_count":
                low_count,

            "medium_count":
                medium_count,

            "high_count":
                high_count,

            "unclassified_count":
                unclassified_count,
        })

    # =====================================================
    # MESSAGES
    # =====================================================

    messages.success(
        request,
        (
            f"Import completed: "
            f"{len(sheet_data)} inspection sheet(s), "
            f"{total_created} new finding(s), "
            f"{total_updated} updated finding(s)."
        ),
    )

    messages.info(
        request,
        (
            f"Risk distribution: "
            f"{total_high} High / "
            f"{total_medium} Medium / "
            f"{total_low} Low."
        ),
    )

    if total_unclassified:

        messages.warning(
            request,
            (
                f"{total_unclassified} row(s) "
                f"could not be classified from "
                f"the Excel colour."
            ),
        )

    return render(
        request,
        "inspections/inspection_import.html",
        {
            "sheet_data":
                sheet_data,
        },
    )


# =========================================================
# RIGHTSHIP VESSEL NAME NORMALISATION
# =========================================================

def build_vessel_alias_map(vessel_names):

    cleaned_names = {
        " ".join(
            str(name).split()
        ).strip()

        for name in vessel_names

        if name
    }

    lookup = {
        name.casefold(): name
        for name in cleaned_names
    }

    aliases = {}

    for name in cleaned_names:

        match = re.match(
            r"^(.*?)(?:\s+\d+)$",
            name,
        )

        if match:

            base_name = (
                match.group(1)
                .strip()
            )

            real_base_name = (
                lookup.get(
                    base_name.casefold()
                )
            )

            if real_base_name:

                aliases[name] = (
                    real_base_name
                )

                continue

        aliases[name] = name

    return aliases


# =========================================================
# RIGHTSHIP PREFERRED VESSEL ORDER
# =========================================================

PREFERRED_VESSEL_ORDER = [

    "Edward N",
    "Julia N",
    "Daniel N",
    "Saar N",
    "Helen N",
    "Mosel N",
    "Hugo N",
    "Steven N",
    "Abigail N",
]


# =========================================================
# RIGHTSHIP VESSEL SORT KEY
# =========================================================

def rightship_vessel_sort_key(
    vessel_name
):

    preferred_position = {
        name.casefold(): index

        for index, name

        in enumerate(
            PREFERRED_VESSEL_ORDER
        )
    }

    return (

        preferred_position.get(
            vessel_name.casefold(),
            9999,
        ),

        vessel_name.casefold(),

    )


# =========================================================
# BUILD RIGHTSHIP INSPECTION ROWS
# =========================================================

def build_rightship_rows():

    # =====================================================
    # AUTHORITATIVE GRAPH RECORDS
    # =====================================================

    graph_records = list(
        RightShipRegisterRecord.objects
        .select_related("vessel")
        .order_by(
            "source_row"
        )
    )

    actual_vessel_names = [

        record.vessel.vessel_name

        for record in graph_records

        if record.vessel
    ]

    # Also include detailed inspection vessels
    # so existing detailed records continue to work.
    detailed_inspections = list(

        Inspection.objects
        .select_related("vessel")
        .prefetch_related(
            "findings__checklist_item"
        )
    )

    actual_vessel_names.extend([

        inspection.vessel.vessel_name

        for inspection in detailed_inspections

        if inspection.vessel
    ])

    vessel_aliases = (
        build_vessel_alias_map(
            actual_vessel_names
        )
    )

    grouped = defaultdict(list)

    # =====================================================
    # GRAPH ROWS
    # =====================================================

    graph_dates = set()

    for record in graph_records:

        if not record.vessel:
            continue

        raw_vessel_name = (
            record.vessel.vessel_name
        )

        vessel_name = (
            vessel_aliases.get(
                raw_vessel_name,
                raw_vessel_name,
            )
        )

        graph_dates.add(
            (
                record.vessel_id,
                record.inspection_date,
            )
        )

        # Try to find corresponding detailed inspection.
        detailed_inspection = (
            Inspection.objects
            .filter(
                vessel=record.vessel,
                inspection_date=record.inspection_date,
            )
            .first()
        )

        report_url = None

        if detailed_inspection:

            report_url = reverse(
                "rightship_report_detail",
                args=[
                    detailed_inspection.id
                ],
            )

        year = (
            record.inspection_date.year
            if record.inspection_date
            else None
        )

        row = {

            "inspection":
                detailed_inspection,

            "register_record":
                record,

            "vessel":
                vessel_name,

            "original_vessel":
                raw_vessel_name,

            "date":
                record.inspection_date,

            "year":
                year,

            "high":
                record.high_risk,

            "medium":
                record.medium_risk,

            "low":
                record.low_risk,

            "total":
                record.total_findings,

            "severity":
                record.severity_score,

            "validity":
                record.validity_months,

            "port":
                (
                    detailed_inspection.port
                    if detailed_inspection
                    else ""
                ),

            "inspector":
                (
                    detailed_inspection.inspector
                    if detailed_inspection
                    else ""
                ),

            "status":
                (
                    detailed_inspection.status
                    if detailed_inspection
                    else ""
                ),

            "report_url":
                report_url,
        }

        grouped[
            vessel_name
        ].append(row)

    # =====================================================
    # DETAILED INSPECTIONS NOT PRESENT IN GRAPH
    #
    # This preserves the existing application behaviour.
    # =====================================================

    for inspection in detailed_inspections:

        if not inspection.vessel:
            continue

        key = (
            inspection.vessel_id,
            inspection.inspection_date,
        )

        if key in graph_dates:
            continue

        raw_vessel_name = (
            inspection.vessel.vessel_name
        )

        vessel_name = (
            vessel_aliases.get(
                raw_vessel_name,
                raw_vessel_name,
            )
        )

        findings = list(
            inspection.findings.all()
        )

        high = sum(

            1

            for finding in findings

            if str(
                finding.risk_level
            ).upper() == "HIGH"

        )

        medium = sum(

            1

            for finding in findings

            if str(
                finding.risk_level
            ).upper() == "MEDIUM"

        )

        low = sum(

            1

            for finding in findings

            if str(
                finding.risk_level
            ).upper() == "LOW"

        )

        total = (
            high
            + medium
            + low
        )

        severity = (
            high * 3
            + medium * 2
            + low
        )

        inspection_date = (
            inspection.inspection_date
        )

        year = (

            inspection_date.year

            if inspection_date

            else None

        )

        report_url = reverse(
            "rightship_report_detail",
            args=[
                inspection.id
            ],
        )

        row = {

            "inspection":
                inspection,

            "register_record":
                None,

            "vessel":
                vessel_name,

            "original_vessel":
                raw_vessel_name,

            "date":
                inspection_date,

            "year":
                year,

            "high":
                high,

            "medium":
                medium,

            "low":
                low,

            "total":
                total,

            "severity":
                severity,

            "validity":
                inspection.validity_months,

            "port":
                inspection.port,

            "inspector":
                inspection.inspector,

            "status":
                inspection.status,

            "report_url":
                report_url,
        }

        grouped[
            vessel_name
        ].append(row)

    # =====================================================
    # SORT EACH VESSEL
    # Latest inspection FIRST
    # =====================================================

    for vessel_name in grouped:

        grouped[
            vessel_name
        ].sort(

            key=lambda row: (

                row["date"]
                or date.min,

                (
                    row["inspection"].id
                    if row["inspection"]
                    else 0
                ),

            ),

            reverse=True,
        )

    # =====================================================
    # SORT VESSELS
    # =====================================================

    ordered_vessels = sorted(

        grouped.keys(),

        key=rightship_vessel_sort_key,

    )

    # =====================================================
    # FLATTEN
    # =====================================================

    rows = []

    for vessel_name in ordered_vessels:

        rows.extend(
            grouped[vessel_name]
        )

    return rows


# =========================================================
# RIGHTSHIP DASHBOARD
# =========================================================

@login_required
def rightship_dashboard(request):

    rows = build_rightship_rows()

    # =====================================================
    # GRAPH DATA
    # =====================================================

    chart_data = []

    for row in rows:

        chart_data.append({

            "vessel":
                row["vessel"],

            "date":
                (
                    row["date"].strftime(
                        "%d-%b-%Y"
                    )

                    if row["date"]

                    else ""
                ),

            "year":
                row["year"],

            "high":
                row["high"],

            "medium":
                row["medium"],

            "low":
                row["low"],

            "total":
                row["total"],

            "severity":
                row["severity"],

            "validity":
                row["validity"] or 0,

            "report_url":
                row["report_url"],
        })

    # =====================================================
    # VESSEL GROUP POSITIONS
    # =====================================================

    vessel_groups = []

    current_vessel = None
    start_index = 0

    for index, row in enumerate(rows):

        if row["vessel"] != current_vessel:

            if current_vessel is not None:

                vessel_groups.append({

                    "vessel":
                        current_vessel,

                    "start":
                        start_index,

                    "end":
                        index - 1,
                })

            current_vessel = (
                row["vessel"]
            )

            start_index = index

    if current_vessel is not None:

        vessel_groups.append({

            "vessel":
                current_vessel,

            "start":
                start_index,

            "end":
                len(rows) - 1,
        })

    # =====================================================
    # YEAR KPI DATA
    # =====================================================

    year_kpis = {}

    for year in [2026, 2025]:

        year_rows = [

            row

            for row in rows

            if row["year"] == year

        ]

        completed = len(
            year_rows
        )

        total_findings = sum(

            row["total"]

            for row in year_rows

        )

        high_findings = sum(

            row["high"]

            for row in year_rows

        )

        average_severity = (

            round(

                sum(
                    row["severity"]
                    for row in year_rows
                )
                / completed,

                1,

            )

            if completed

            else 0

        )

        average_validity = (

            round(

                sum(
                    row["validity"] or 0
                    for row in year_rows
                )
                / completed,

                1,

            )

            if completed

            else 0

        )

        year_kpis[year] = {

            "completed":
                completed,

            "total_findings":
                total_findings,

            "high_findings":
                high_findings,

            "average_severity":
                average_severity,

            "average_validity":
                average_validity,
        }

    # =====================================================
    # REPORTS
    # =====================================================

    reports = rows.copy()

    # =====================================================
    # GLOBAL COUNTS
    #
    # Dashboard register totals come from GRAPH.
    # =====================================================

    graph_records = list(
        RightShipRegisterRecord.objects.all()
    )

    total_vessels = (
        Vessel.objects.count()
    )

    total_inspections = (
        len(graph_records)
        if graph_records
        else Inspection.objects.count()
    )

    total_findings = sum(
        record.total_findings
        for record in graph_records
    )

    high_risk = sum(
        record.high_risk
        for record in graph_records
    )

    medium_risk = sum(
        record.medium_risk
        for record in graph_records
    )

    low_risk = sum(
        record.low_risk
        for record in graph_records
    )

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        "rows":
            rows,

        "chart_data":
            chart_data,

        "vessel_groups":
            vessel_groups,

        "year_kpis":
            year_kpis,

        "reports":
            reports,

        "total_vessels":
            total_vessels,

        "total_inspections":
            total_inspections,

        "total_findings":
            total_findings,

        "high_risk":
            high_risk,

        "medium_risk":
            medium_risk,

        "low_risk":
            low_risk,
    }

    return render(

        request,

        "inspections/dashboard.html",

        context,

    )


# =========================================================
# RIGHTSHIP REPORT LIST
# =========================================================

@login_required
def rightship_reports(request):

    rows = build_rightship_rows()

    report_groups = {}

    for row in rows:

        vessel_name = (
            row["vessel"]
        )

        if vessel_name not in report_groups:

            report_groups[
                vessel_name
            ] = []

        report_groups[
            vessel_name
        ].append(row)

    return render(

        request,

        "inspections/reports.html",

        {
            "report_groups":
                report_groups,
        },

    )


# =========================================================
# RIGHTSHIP INDIVIDUAL REPORT
# =========================================================

@login_required
def rightship_report_detail(
    request,
    pk,
):

    inspection = get_object_or_404(

        Inspection.objects
        .select_related("vessel")
        .prefetch_related(
            "findings__checklist_item"
        ),

        pk=pk,

    )

    findings = list(
        inspection.findings.all()
    )

    # =====================================================
    # RISK COUNTS
    # =====================================================

    high = sum(

        1

        for finding in findings

        if str(
            finding.risk_level
        ).upper() == "HIGH"

    )

    medium = sum(

        1

        for finding in findings

        if str(
            finding.risk_level
        ).upper() == "MEDIUM"

    )

    low = sum(

        1

        for finding in findings

        if str(
            finding.risk_level
        ).upper() == "LOW"

    )

    # =====================================================
    # TOTAL
    # =====================================================

    total = (
        high
        + medium
        + low
    )

    # =====================================================
    # SEVERITY
    # =====================================================

    severity = (
        high * 3
        + medium * 2
        + low
    )

    return render(

        request,

        "inspections/report_detail.html",

        {
            "inspection":
                inspection,

            "findings":
                findings,

            "high":
                high,

            "medium":
                medium,

            "low":
                low,

            "total":
                total,

            "severity":
                severity,
        },

    )
from django.db import models


# ============================================================
# VESSEL
# ============================================================

class Vessel(models.Model):

    vessel_name = models.CharField(
        max_length=150
    )

    active = models.BooleanField(
        default=True
    )

    scoc_active = models.BooleanField(
        default=False
    )

    def __str__(self):
        return self.vessel_name


# ============================================================
# INSPECTION
# ============================================================

class Inspection(models.Model):

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("COMPLETED", "Completed"),
    ]

    inspection_no = models.CharField(
        max_length=20,
        unique=True
    )

    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.PROTECT
    )

    port = models.CharField(
        max_length=100
    )

    inspection_date = models.DateField()

    inspector = models.CharField(
        max_length=100
    )

    validity_months = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPEN"
    )

    remarks = models.TextField(
        blank=True
    )

    def __str__(self):
        return self.inspection_no


# ============================================================
# CHECKLIST ITEM
# ============================================================

class ChecklistItem(models.Model):

    ref_no = models.CharField(
        max_length=20,
        unique=True
    )

    inspected_item = models.TextField()

    def __str__(self):
        return f"{self.ref_no} - {self.inspected_item[:50]}"


# ============================================================
# INSPECTION FINDING
# ============================================================

class InspectionFinding(models.Model):

    RISK_CHOICES = [
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]

    inspection = models.ForeignKey(
        Inspection,
        on_delete=models.CASCADE,
        related_name="findings"
    )

    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.PROTECT,
        related_name="findings"
    )

    finding_description = models.TextField()

    risk_level = models.CharField(
        max_length=10,
        choices=RISK_CHOICES
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "inspection",
                    "checklist_item"
                ],
                name="unique_checklist_per_inspection",
            )
        ]

    def __str__(self):
        return (
            f"{self.checklist_item.ref_no} - "
            f"{self.risk_level}"
        )


# ============================================================
# RIGHTSHIP GRAPH / REGISTER RECORD
# ============================================================

class RightShipRegisterRecord(models.Model):

    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.PROTECT,
        related_name="rightship_register_records",
    )

    inspection_date = models.DateField()

    high_risk = models.PositiveIntegerField(
        default=0
    )

    medium_risk = models.PositiveIntegerField(
        default=0
    )

    low_risk = models.PositiveIntegerField(
        default=0
    )

    total_findings = models.PositiveIntegerField(
        default=0
    )

    severity_score = models.PositiveIntegerField(
        default=0
    )

    validity_months = models.PositiveIntegerField(
        default=0
    )

    # Excel GRAPH row number.
    # Used to preserve the order from the workbook.
    source_row = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vessel",
                    "inspection_date"
                ],
                name="unique_rightship_register_vessel_date",
            )
        ]

        ordering = [
            "source_row"
        ]

    def __str__(self):
        return (
            f"{self.vessel.vessel_name} - "
            f"{self.inspection_date}"
        )
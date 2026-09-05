from django.db import models


class Vessel(models.Model):

    vessel_name = models.CharField(max_length=150)

    active = models.BooleanField(default=True)

    def __str__(self):
        return self.vessel_name


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

    port = models.CharField(max_length=100)

    inspection_date = models.DateField()

    inspector = models.CharField(max_length=100)

    validity_months = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPEN"
    )

    remarks = models.TextField(blank=True)

    def __str__(self):
        return self.inspection_no





################## check list
class ChecklistItem(models.Model):
    ref_no = models.CharField(max_length=20, unique=True)
    inspected_item = models.TextField()

    def __str__(self):
        return f"{self.ref_no} - {self.inspected_item[:50]}"



##################


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
                fields=["inspection", "checklist_item"],
                name="unique_checklist_per_inspection",
            )
        ]
        
    def __str__(self):
        return f"{self.checklist_item.ref_no} - {self.risk_level}"

    
from django.db import models


# =========================================================
# IMPORT HISTORY
# =========================================================

class ChemicalImportHistory(models.Model):

    """
    Records every chemical-analysis data import.

    Each measurement/dosing record can be linked back to
    the import that created it. This allows a complete import
    to be safely deleted from the History page.
    """

    IMPORT_TYPES = [
        ("Measurement", "Measurement"),
        ("Dosing Log", "Dosing Log"),
    ]

    STATUS_CHOICES = [
        ("Success", "Success"),
        ("Failed", "Failed"),
    ]

    vessel = models.CharField(
        max_length=100
    )

    import_type = models.CharField(
        max_length=50,
        choices=IMPORT_TYPES
    )

    filename = models.CharField(
        max_length=255
    )

    new_rows = models.PositiveIntegerField(
        default=0
    )

    skipped_rows = models.PositiveIntegerField(
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    message = models.TextField(
        blank=True,
        default=""
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.vessel} - "
            f"{self.import_type} - "
            f"{self.filename}"
        )


# =========================================================
# CHEMICAL MEASUREMENT
# =========================================================

class ChemicalMeasurement(models.Model):

    """
    Raw/processed METIS measurement data.

    One record per vessel + timestamp.

    import_history identifies the upload that created the row.
    """

    vessel = models.CharField(
        max_length=100
    )

    voyage = models.CharField(
        max_length=50,
        blank=True,
        default="UNKNOWN",
    )
    
    timestamp = models.DateTimeField()

    fuel_load = models.FloatField(
        null=True,
        blank=True
    )

    fuel_inlet = models.FloatField(
        null=True,
        blank=True
    )

    fuel_outlet = models.FloatField(
        null=True,
        blank=True
    )

    rpm = models.FloatField(
        null=True,
        blank=True
    )

    speed = models.FloatField(
        null=True,
        blank=True
    )

    power = models.FloatField(
        null=True,
        blank=True
    )

    import_history = models.ForeignKey(
        ChemicalImportHistory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurement_records"
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vessel",
                    "timestamp"
                ],
                name="unique_chemical_measurement"
            )
        ]

        ordering = [
            "vessel",
            "timestamp"
        ]

    def __str__(self):

        return (
            f"{self.vessel} - "
            f"{self.timestamp}"
        )


# =========================================================
# CHEMICAL DOSING
# =========================================================

class ChemicalDosing(models.Model):

    """
    Daily chemical dosing information.

    One record per vessel + date.

    import_history identifies the most recent upload that
    created/updated the record.
    """

    vessel = models.CharField(
        max_length=100
    )

    date = models.DateField()

    voyage = models.CharField(
    max_length=50,
    blank=True,
    default="UNKNOWN",
)

    morning_time = models.TimeField(
        null=True,
        blank=True
    )

    morning_additive = models.FloatField(
        null=True,
        blank=True
    )

    morning_fuel_qty = models.FloatField(
        null=True,
        blank=True
    )

    evening_time = models.TimeField(
        null=True,
        blank=True
    )

    evening_additive = models.FloatField(
        null=True,
        blank=True
    )

    evening_fuel_qty = models.FloatField(
        null=True,
        blank=True
    )

    total_additive = models.FloatField(
        null=True,
        blank=True
    )

    total_fuel_qty = models.FloatField(
        null=True,
        blank=True
    )

    chemical_rob = models.FloatField(
        null=True,
        blank=True
    )

    remarks = models.TextField(
        blank=True,
        default=""
    )

    import_history = models.ForeignKey(
        ChemicalImportHistory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dosing_records"
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vessel",
                    "date"
                ],
                name="unique_chemical_dosing"
            )
        ]

        ordering = [
            "vessel",
            "date"
        ]

    def __str__(self):

        return (
            f"{self.vessel} - "
            f"{self.date}"
        )
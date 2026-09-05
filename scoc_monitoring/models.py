from django.db import models


# ============================================================
# VOYAGE LEG
# ============================================================

class VoyageLeg(models.Model):

    LOAD_TYPE_CHOICES = [
        ("LADEN", "Laden"),
        ("BALLAST", "Ballast"),
        ("UNKNOWN", "Unknown"),
    ]

    # ---------------------------------------------------------
    # VESSEL
    # ---------------------------------------------------------

    vessel_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    # ---------------------------------------------------------
    # VOYAGE IDENTIFICATION
    # ---------------------------------------------------------

    voyage_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    departure = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    destination = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    voyage_route = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Example: Singapore → Krishnapatnam",
    )

    # ---------------------------------------------------------
    # LOAD TYPE
    # ---------------------------------------------------------

    load_type = models.CharField(
        max_length=20,
        choices=LOAD_TYPE_CHOICES,
        default="UNKNOWN",
    )

    # ---------------------------------------------------------
    # DATES
    # ---------------------------------------------------------

    start_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # TARGETS
    # ---------------------------------------------------------

    target_speed = models.FloatField(
        null=True,
        blank=True,
    )

    target_consumption = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # CALCULATED VOYAGE PERFORMANCE
    # ---------------------------------------------------------

    average_speed = models.FloatField(
        null=True,
        blank=True,
    )

    average_consumption = models.FloatField(
        null=True,
        blank=True,
    )

    distance_to_go = models.FloatField(
        null=True,
        blank=True,
    )

    observation_count = models.PositiveIntegerField(
        default=0,
    )

    # ---------------------------------------------------------
    # SOURCE
    # ---------------------------------------------------------

    source_message = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "vessel_name",
            "start_date",
            "id",
        ]

    def __str__(self):

        vessel = self.vessel_name or "Unknown Vessel"

        if self.voyage_route:
            return f"{vessel} - {self.voyage_route}"

        if self.departure or self.destination:
            return (
                f"{vessel} - "
                f"{self.departure or ''} → "
                f"{self.destination or ''}"
            )

        if self.voyage_reference:
            return (
                f"{vessel} - "
                f"{self.voyage_reference}"
            )

        return (
            f"{vessel} - "
            f"{self.get_load_type_display()} "
            f"Voyage Leg #{self.pk}"
        )


# ============================================================
# VOYAGE OBSERVATION
# ============================================================

class VoyageObservation(models.Model):

    leg = models.ForeignKey(
        VoyageLeg,
        on_delete=models.CASCADE,
        related_name="observations",
    )

    reported_time = models.DateTimeField()

    # ---------------------------------------------------------
    # BASIC
    # ---------------------------------------------------------

    vessel_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    position = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    course = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # PERFORMANCE
    # ---------------------------------------------------------

    speed = models.FloatField(
        null=True,
        blank=True,
    )

    consumption = models.FloatField(
        null=True,
        blank=True,
    )

    distance = models.FloatField(
        null=True,
        blank=True,
    )

    distance_run = models.FloatField(
        null=True,
        blank=True,
    )

    distance_to_go = models.FloatField(
        null=True,
        blank=True,
    )

    duration_days = models.FloatField(
        null=True,
        blank=True,
    )

    running_hours = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # ENGINE
    # ---------------------------------------------------------

    rpm = models.FloatField(
        null=True,
        blank=True,
    )

    power_kw = models.FloatField(
        null=True,
        blank=True,
    )

    engine_power_kw = models.FloatField(
        null=True,
        blank=True,
    )

    shaft_power_kw = models.FloatField(
        null=True,
        blank=True,
    )

    load_percent = models.FloatField(
        null=True,
        blank=True,
    )

    engine_load_percent = models.FloatField(
        null=True,
        blank=True,
    )

    slip = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # FUEL CONSUMPTION
    # ---------------------------------------------------------

    hsfo_consumption_mt = models.FloatField(
        null=True,
        blank=True,
    )

    hsfo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    hsfo_rob_mt = models.FloatField(
        null=True,
        blank=True,
    )

    lsfo_consumption_mt = models.FloatField(
        null=True,
        blank=True,
    )

    lsfo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    lsmgo_consumption_mt = models.FloatField(
        null=True,
        blank=True,
    )

    lsmgo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    lsmgo_rob_mt = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # SCoC / CYLINDER OIL
    # ---------------------------------------------------------

    cylinder_oil_consumption_l = models.FloatField(
        null=True,
        blank=True,
    )

    scoc = models.FloatField(
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # WEATHER / NAVIGATION
    # ---------------------------------------------------------

    wind = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    swell = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    current = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    # ---------------------------------------------------------
    # ETA
    # ---------------------------------------------------------

    eta = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    # ---------------------------------------------------------
    # REMARKS
    # ---------------------------------------------------------

    remarks = models.TextField(
        blank=True,
        default="",
    )

    # ---------------------------------------------------------
    # SOURCE
    # ---------------------------------------------------------

    source_file = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    source_message = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "reported_time",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "leg",
                    "reported_time",
                ],
                name="unique_voyage_observation_time",
            ),
        ]

    def __str__(self):

        vessel = (
            self.vessel_name
            or self.leg.vessel_name
            or "Unknown Vessel"
        )

        return (
            f"{vessel} - "
            f"{self.leg} - "
            f"{self.reported_time:%d-%b-%Y %H:%M}"
        )
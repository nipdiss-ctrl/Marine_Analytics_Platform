
from django.db import models
from inspections.models import Vessel

class Ship(models.Model):

    name = models.CharField(
        max_length=255,
        unique=True,
    )


    def __str__(self):
        return self.name
# ============================================================
# VOYAGE LEG
# ============================================================

class VoyageLeg(models.Model):

    LOAD_TYPE_CHOICES = [
        ("Laden", "Laden"),
        ("Ballast", "Ballast"),
        ("Unknown", "Unknown"),
    ]

    load_type = models.CharField(
        max_length=20,
        choices=LOAD_TYPE_CHOICES,
        default="Unknown",
    )

    # A source voyage / leg identifier when the Excel or
    # noon report provides one.
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

    start_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    # These are source values.
    # They are NOT automatically replaced with arbitrary
    # Laden/Ballast defaults.
    target_speed = models.FloatField(
        null=True,
        blank=True,
    )

    target_consumption = models.FloatField(
        null=True,
        blank=True,
    )

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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.PROTECT,
        related_name="voyage_legs",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "start_date",
            "id",
        ]

    def __str__(self):

        route = ""

        if self.departure or self.destination:
            route = (
                f"{self.departure} → "
                f"{self.destination}"
            )

        if route and self.voyage_reference:
            return (
                f"{route} - "
                f"{self.voyage_reference} "
                f"({self.load_type})"
            )

        if route:
            return (
                f"{route} "
                f"({self.load_type})"
            )

        if self.voyage_reference:
            return (
                f"{self.voyage_reference} "
                f"({self.load_type})"
            )

        return (
            f"{self.load_type} "
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

    hsfo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    lsfo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    mgo_rob = models.FloatField(
        null=True,
        blank=True,
    )

    power_kw = models.FloatField(
        null=True,
        blank=True,
    )

    rpm = models.FloatField(
        null=True,
        blank=True,
    )

    load_percent = models.FloatField(
        null=True,
        blank=True,
    )

    scoc = models.FloatField(
        null=True,
        blank=True,
    )

    cylinder_oil_consumption_l = models.FloatField(
        null=True,
        blank=True,
    )

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
                name="unique_observation_per_leg_time",
            ),
        ]

    def __str__(self):

        return (
            f"{self.leg} - "
            f"{self.reported_time:%d-%b-%Y %H:%M}"
        )

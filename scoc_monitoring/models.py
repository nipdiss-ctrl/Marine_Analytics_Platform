from django.db import models


# ============================================================
# SCoC VESSEL
# ============================================================

class ScocVessel(models.Model):
    """
    Vessel managed specifically by the SCoC Monitoring module.

    Existing SCoC configuration fields are preserved because they
    already exist in the database.

    The four target speed/consumption values are persistent
    vessel settings used for future imports.

    Historical VoyageLeg records retain their own target snapshots.
    """

    # --------------------------------------------------------
    # EXISTING SCoC VESSEL FIELDS
    # --------------------------------------------------------

    vessel_name = models.CharField(
        max_length=100,
        unique=True,
    )

    vessel_type = models.CharField(
        max_length=30,
        choices=[
            ("Bulk Carrier", "Bulk Carrier"),
            ("Ore Carrier", "Ore Carrier"),
        ],
        default="Bulk Carrier",
    )

    engine_mcr_kw = models.FloatField(default=0)
    ...
    engine_mcr_kw = models.FloatField(
        default=0,
    )

    cylinder_oil_density = models.FloatField(
        default=0.93,
    )

    target_scoc = models.FloatField(
        default=0.9,
    )

    high_alarm_threshold = models.FloatField(
        default=10,
    )

    low_alarm_threshold = models.FloatField(
        default=-10,
    )

    # --------------------------------------------------------
    # PERSISTENT PERFORMANCE TARGETS
    # --------------------------------------------------------

    target_speed_laden = models.FloatField(
        null=True,
        blank=True,
    )

    target_consumption_laden = models.FloatField(
        null=True,
        blank=True,
    )

    target_speed_ballast = models.FloatField(
        null=True,
        blank=True,
    )

    target_consumption_ballast = models.FloatField(
        null=True,
        blank=True,
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    active = models.BooleanField(
        default=True,
    )

    # --------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "vessel_name",
            "id",
        ]

    def __str__(self):
        return self.vessel_name

    # ========================================================
    # TARGET HELPERS
    # ========================================================

    def get_target_speed(self, load_type):
        if load_type == "Laden":
            return self.target_speed_laden

        if load_type == "Ballast":
            return self.target_speed_ballast

        return None

    def get_target_consumption(self, load_type):
        if load_type == "Laden":
            return self.target_consumption_laden

        if load_type == "Ballast":
            return self.target_consumption_ballast

        return None

# ============================================================
# SHIP
# ============================================================

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

    # ========================================================
    # TARGET SNAPSHOTS
    # ========================================================
    #
    # These values are copied from ScocVessel when the voyage
    # leg is imported.
    #
    # They MUST NOT be dynamically linked to ScocVessel.
    #
    # This means changing the vessel's current targets does
    # not alter historical voyages.
    #

    target_speed = models.FloatField(
        null=True,
        blank=True,
    )

    target_consumption = models.FloatField(
        null=True,
        blank=True,
    )

    # ========================================================
    # CALCULATED PERFORMANCE
    # ========================================================

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

    # ========================================================
    # VESSEL
    # ========================================================

    vessel = models.ForeignKey(
        ScocVessel,
        on_delete=models.PROTECT,
        related_name="voyage_legs",
        null=True,
        blank=True,
    )

    # ========================================================
    # AUDIT
    # ========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
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

    # ========================================================
    # PERFORMANCE
    # ========================================================

    speed = models.FloatField(
        null=True,
        blank=True,
    )

    # Display/application consumption value.
    #
    # For the Spire/XH ATOP workbook this is the same value as:
    #
    # ME Cons / 24 hrs (MT/d)
    #
    consumption = models.FloatField(
        null=True,
        blank=True,
    )

    # Raw/explicit authoritative daily ME consumption field.
    #
    # This preserves the actual:
    #
    # ME Cons / 24 hrs (MT/d)
    #
    # value separately.
    me_consumption_24 = models.FloatField(
        null=True,
        blank=True,
    )

    # ========================================================
    # NAVIGATION / VOYAGE
    # ========================================================

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

    # ========================================================
    # FUEL ROB
    # ========================================================

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

    # ========================================================
    # ENGINE
    # ========================================================

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

    # ========================================================
    # SCoC
    # ========================================================

    scoc = models.FloatField(
        null=True,
        blank=True,
    )

    cylinder_oil_consumption_l = models.FloatField(
        null=True,
        blank=True,
    )

    # ========================================================
    # SOURCE
    # ========================================================

    source_file = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    source_message = models.TextField(
        blank=True,
        default="",
    )

    # ========================================================
    # AUDIT
    # ========================================================

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


# ============================================================
# DAILY SCoC DATA
# ============================================================
#
# This model is retained because your existing
# excel_importer.py contains:
#
#     from scoc_monitoring.models import ScocDailyData
#
# and the functions:
#
#     import_scoc_monitoring_row()
#     import_scoc_monitoring_excel()
#
# use this model.
#
# Do not remove it unless those older SCoC daily-data functions
# are also removed.
# ============================================================

class ScocDailyData(models.Model):

    report_date = models.DateField()

    vessel_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    me_power = models.FloatField(
        null=True,
        blank=True,
    )

    running_hours = models.FloatField(
        null=True,
        blank=True,
    )

    cylinder_oil_consumption_l = models.FloatField(
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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-report_date",
            "vessel_name",
            "id",
        ]

    def __str__(self):

        if self.vessel_name:
            return (
                f"{self.vessel_name} - "
                f"{self.report_date}"
            )

        return str(self.report_date)
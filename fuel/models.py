from django.db import models



class Vessel(models.Model):

    name = models.CharField(
        max_length=100
    )

    imo_number = models.CharField(
        max_length=50,
        blank=True
    )

    vessel_type = models.CharField(
        max_length=100,
        blank=True
    )

    engine = models.CharField(
        max_length=100,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:

        verbose_name = "Vessel"

        verbose_name_plural = "🚢 Vessels"



    def __str__(self):

        return self.name





class MetisUpload(models.Model):

    vessel = models.ForeignKey(
        Vessel,
        on_delete=models.CASCADE
    )

    file_name = models.CharField(
        max_length=255
    )

    upload_date = models.DateTimeField(
        auto_now_add=True
    )

    start_time = models.DateTimeField(
        null=True,
        blank=True
    )

    end_time = models.DateTimeField(
        null=True,
        blank=True
    )

    rows_processed = models.IntegerField(
        default=0
    )

    status = models.CharField(
        max_length=50,
        default="Completed"
    )



    class Meta:

        verbose_name = "METIS Upload"

        verbose_name_plural = "📂 METIS Data Uploads"



    def __str__(self):

        return self.file_name





class FuelPerformance(models.Model):

    upload = models.OneToOneField(
        MetisUpload,
        on_delete=models.CASCADE
    )


    operating_hours = models.FloatField(
        default=0
    )


    total_fuel_tons = models.FloatField(
        default=0
    )


    average_sfoc = models.FloatField(
        default=0
    )


    average_load = models.FloatField(
        default=0
    )


    average_speed = models.FloatField(
        default=0
    )


    co2_tons = models.FloatField(
        default=0
    )


    risk_level = models.CharField(
        max_length=20,
        default="Unknown"
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )



    class Meta:

        verbose_name = "Fuel Performance"

        verbose_name_plural = "⛽ Fuel Performance Results"



    def __str__(self):

        return f"{self.upload.vessel.name} Performance"
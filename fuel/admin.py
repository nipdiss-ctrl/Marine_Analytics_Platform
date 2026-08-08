from django.contrib import admin

from .models import (
    Vessel,
    MetisUpload,
    FuelPerformance
)



@admin.register(Vessel)
class VesselAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "imo_number",
        "vessel_type",
        "engine",
        "created_at",
    )

    search_fields = (
        "name",
        "imo_number",
    )

    list_filter = (
        "vessel_type",
    )





@admin.register(MetisUpload)
class MetisUploadAdmin(admin.ModelAdmin):

    list_display = (
        "file_name",
        "vessel",
        "upload_date",
        "rows_processed",
        "status",
    )

    search_fields = (
        "file_name",
        "vessel__name",
    )

    list_filter = (
        "status",
        "upload_date",
        "vessel",
    )





@admin.register(FuelPerformance)
class FuelPerformanceAdmin(admin.ModelAdmin):

    list_display = (
        "get_vessel",
        "average_sfoc",
        "total_fuel_tons",
        "operating_hours",
        "risk_level",
        "created_at",
    )


    search_fields = (
        "upload__vessel__name",
    )


    list_filter = (
        "risk_level",
        "created_at",
    )



    def get_vessel(self, obj):

        return obj.upload.vessel.name


    get_vessel.short_description = "Vessel"
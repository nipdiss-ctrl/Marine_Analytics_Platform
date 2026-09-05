from django.contrib import admin
from .models import Vessel, Inspection, InspectionFinding, ChecklistItem


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("ref_no", "inspected_item")
    search_fields = ("ref_no", "inspected_item")
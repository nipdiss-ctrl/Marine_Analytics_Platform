from django import forms

from .models import ScocVessel


class ScocVesselForm(forms.ModelForm):
    class Meta:
        model = ScocVessel
        fields = [
            "vessel_name",
            "engine_mcr_kw",
            "cylinder_oil_density",
            "target_scoc",
            "high_alarm_threshold",
            "low_alarm_threshold",
            "target_speed_laden",
            "target_consumption_laden",
            "target_speed_ballast",
            "target_consumption_ballast",
            "active",
        ]
        labels = {
            "vessel_name": "Vessel Name",
            "engine_mcr_kw": "Engine MCR (kW)",
            "cylinder_oil_density": "Cylinder Oil Density (kg/L)",
            "target_scoc": "Target SCoC (g/kWh)",
            "high_alarm_threshold": "High Alarm Threshold (%)",
            "low_alarm_threshold": "Low Alarm Threshold (%)",
            "target_speed_laden": "Laden Target Speed (kn)",
            "target_consumption_laden": "Laden Target Consumption (MT/day)",
            "target_speed_ballast": "Ballast Target Speed (kn)",
            "target_consumption_ballast": "Ballast Target Consumption (MT/day)",
            "active": "Active",
        }
        widgets = {
            field: forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            )
            for field in [
                "engine_mcr_kw",
                "cylinder_oil_density",
                "target_scoc",
                "high_alarm_threshold",
                "low_alarm_threshold",
                "target_speed_laden",
                "target_consumption_laden",
                "target_speed_ballast",
                "target_consumption_ballast",
            ]
        }
        widgets["vessel_name"] = forms.TextInput(attrs={"class": "form-control"})
        widgets["active"] = forms.CheckboxInput(attrs={"class": "form-check-input"})

    def clean_vessel_name(self):
        return self.cleaned_data["vessel_name"].strip()

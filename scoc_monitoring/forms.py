from django import forms

from .models import ScocVessel


class ScocVesselForm(forms.ModelForm):
    class Meta:
        model = ScocVessel
        fields = [
            "vessel_name",
            "vessel_type",
            "target_speed_laden",
            "target_consumption_laden",
            "target_speed_ballast",
            "target_consumption_ballast",
            "active",
        ]
        labels = {
            "vessel_name": "Vessel Name",
            "vessel_type": "Vessel Type",
            "target_speed_laden": "Laden Target Speed (kn)",
            "target_consumption_laden": "Laden Target Consumption (MT/day)",
            "target_speed_ballast": "Ballast Target Speed (kn)",
            "target_consumption_ballast": "Ballast Target Consumption (MT/day)",
            "active": "Active",
        }
        widgets = {
            "vessel_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "vessel_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "target_speed_laden": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "target_consumption_laden": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "target_speed_ballast": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "target_consumption_ballast": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "active": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def clean_vessel_name(self):
        return self.cleaned_data["vessel_name"].strip()
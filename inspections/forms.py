from django import forms
from .models import Vessel


class VesselForm(forms.ModelForm):

    class Meta:
        model = Vessel
        fields = [
        "vessel_name",
        "active",
]

        widgets = {

    

            'vessel_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Enter Vessel Name'
                }
            ),

            'active': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),

        }

        labels = {           
            'vessel_name': 'Vessel Name',
            'active': 'Active',
        }



######### inspection

from .models import Inspection


class InspectionForm(forms.ModelForm):

    class Meta:

        model = Inspection

        fields = [
           
            "vessel",
            "port",
            "inspection_date",
            "inspector",
            "validity_months",
            "status",
            "remarks",
        ]

        widgets = {

  
            "vessel": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "port": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Port",
                }
            ),

            "inspection_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "inspector": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Inspector",
                }
            ),

            "validity_months": forms.NumberInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),

        }

        labels = {

            "vessel": "Vessel",
            "port": "Port",
            "inspection_date": "Inspection Date",
            "inspector": "Inspector",
            "validity_months": "Validity (Months)",
            "status": "Status",
            "remarks": "Remarks",

        }


#######################################

from django import forms
from django.core.exceptions import ValidationError

from .models import InspectionFinding


class InspectionFindingForm(forms.ModelForm):

    class Meta:
        model = InspectionFinding

        fields = [
            "checklist_item",
            "finding_description",
            "risk_level",
        ]

        widgets = {

            "checklist_item": forms.Select(
                attrs={
                    "class": "form-select",
                    "id": "id_checklist_item",
                }
            ),

            "finding_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Enter finding description",
                }
            ),

            "risk_level": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

        }

        labels = {
            "checklist_item": "Reference No",
            "finding_description": "Finding Description",
            "risk_level": "Risk Level",
        }

    def __init__(self, *args, inspection=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inspection = inspection

    def clean_checklist_item(self):
        checklist_item = self.cleaned_data["checklist_item"]

        if (
            self.inspection
            and InspectionFinding.objects.filter(
                inspection=self.inspection,
                checklist_item=checklist_item,
            ).exists()
        ):
            raise ValidationError(
                "This Reference No has already been added for this inspection."
            )

        return checklist_item




    #######################

    from django import forms
from .models import ChecklistItem


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["ref_no", "inspected_item"]

        widgets = {
            "ref_no": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Reference Number",
            }),
            "inspected_item": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Enter inspected item...",
            }),
        }


########################################

from django import forms
from .models import InspectionFinding

class InspectionFindingRiskForm(forms.ModelForm):

    class Meta:
        model = InspectionFinding
        fields = ["risk_level"]
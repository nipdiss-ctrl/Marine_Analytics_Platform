from django.shortcuts import (
    render,
    get_object_or_404,
    redirect
)

from django.http import HttpResponse

from .models import (
    Vessel,
    MetisUpload,
    FuelPerformance
)

from .calculations import calculate_fuel_performance

import pandas as pd

from io import BytesIO

from reportlab.pdfgen import canvas



# =====================================================
# DATA CENTER - UPLOAD METIS FILE
# =====================================================

def data_center(request):

    message = None
    preview = None
    summary = None


    vessels = Vessel.objects.all()



    if request.method == "POST":


        uploaded_file = request.FILES.get(
            "file"
        )

        vessel_id = request.POST.get(
            "vessel"
        )



        if uploaded_file and vessel_id:


            vessel = get_object_or_404(
                Vessel,
                id=vessel_id
            )



            # Read file

            if uploaded_file.name.lower().endswith(".csv"):

                df = pd.read_csv(
                    uploaded_file
                )

            else:

                df = pd.read_excel(
                    uploaded_file
                )



            rows = len(df)



            # Calculate performance

            df, result = calculate_fuel_performance(
                df
            )



            # Save upload history

            upload = MetisUpload.objects.create(

                vessel=vessel,

                file_name=uploaded_file.name,

                rows_processed=rows,

                status="Completed"

            )



            # Save KPI results

            FuelPerformance.objects.create(

                upload=upload,


                operating_hours=result.get(
                    "operating_hours",
                    0
                ),


                total_fuel_tons=result.get(
                    "total_fuel_tons",
                    0
                ),


                average_sfoc=result.get(
                    "sfoc",
                    0
                ),


                average_load=result.get(
                    "average_load",
                    0
                ),


                average_speed=result.get(
                    "average_speed",
                    0
                ),


                co2_tons=result.get(
                    "co2_tons",
                    0
                ),


                risk_level=result.get(
                    "risk_level",
                    "Unknown"
                )

            )



            message = (
                "✓ METIS file processed "
                "and saved successfully"
            )



            preview = df.head(10).to_html(
                classes="table"
            )


            summary = result



    return render(

        request,

        "fuel/data_center.html",

        {

            "vessels": vessels,

            "message": message,

            "preview": preview,

            "summary": summary

        }

    )





# =====================================================
# UPLOAD HISTORY
# =====================================================

def upload_history(request):


    uploads = MetisUpload.objects.all().order_by(
        "-upload_date"
    )


    return render(

        request,

        "fuel/upload_history.html",

        {

            "uploads": uploads

        }

    )





# =====================================================
# DELETE UPLOAD
# =====================================================

def delete_upload(request, id):


    upload = get_object_or_404(

        MetisUpload,

        id=id

    )



    if request.method == "POST":


        upload.delete()


        return redirect(
            "upload_history"
        )



    return render(

        request,

        "fuel/delete_upload.html",

        {

            "upload": upload

        }

    )





# =====================================================
# ANALYSIS PAGE
# =====================================================

def upload_analysis(request, id):

    upload = get_object_or_404(
        MetisUpload,
        id=id
    )


    performance = FuelPerformance.objects.filter(
        upload=upload
    ).first()


    return render(

        request,

        "fuel/analysis.html",

        {
            "upload": upload,
            "performance": performance
        }

    )




# =====================================================
# DOWNLOAD EXCEL REPORT
# =====================================================

def download_excel(request, id):


    upload = get_object_or_404(

        MetisUpload,

        id=id

    )



    performance = upload.fuelperformance



    data = {


        "Vessel":[

            upload.vessel.name

        ],


        "File":[

            upload.file_name

        ],


        "Operating Hours":[

            performance.operating_hours

        ],


        "Fuel Consumption Tons":[

            performance.total_fuel_tons

        ],


        "Average SFOC":[

            performance.average_sfoc

        ],


        "Engine Load (%)":[

            performance.average_load

        ],


        "Average Speed":[

            performance.average_speed

        ],


        "CO2 Tons":[

            performance.co2_tons

        ],


        "Risk Level":[

            performance.risk_level

        ]

    }



    df = pd.DataFrame(
        data
    )



    response = HttpResponse(

        content_type=
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    )


    response["Content-Disposition"] = (

        f'attachment; filename="{upload.vessel.name}_fuel_report.xlsx"'

    )



    df.to_excel(

        response,

        index=False

    )



    return response





# =====================================================
# DOWNLOAD PDF REPORT
# =====================================================

def download_pdf(request, id):


    upload = get_object_or_404(

        MetisUpload,

        id=id

    )


    performance = upload.fuelperformance



    buffer = BytesIO()



    pdf = canvas.Canvas(
        buffer
    )



    pdf.drawString(

        50,

        800,

        "NEU Marine Intelligence - Fuel Report"

    )



    pdf.drawString(

        50,

        760,

        f"Vessel: {upload.vessel.name}"

    )


    pdf.drawString(

        50,

        730,

        f"File: {upload.file_name}"

    )



    pdf.drawString(

        50,

        690,

        f"Operating Hours: {performance.operating_hours}"

    )


    pdf.drawString(

        50,

        660,

        f"Fuel Consumption: {performance.total_fuel_tons} tons"

    )


    pdf.drawString(

        50,

        630,

        f"Average SFOC: {performance.average_sfoc}"

    )


    pdf.drawString(

        50,

        600,

        f"Engine Load: {performance.average_load}%"

    )


    pdf.drawString(

        50,

        570,

        f"CO2: {performance.co2_tons} tons"

    )


    pdf.drawString(

        50,

        540,

        f"Risk Level: {performance.risk_level}"

    )



    pdf.save()



    buffer.seek(0)



    response = HttpResponse(

        buffer,

        content_type="application/pdf"

    )



    response["Content-Disposition"] = (

        f'attachment; filename="{upload.vessel.name}_fuel_report.pdf"'

    )



    return response
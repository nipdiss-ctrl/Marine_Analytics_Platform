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

from .future_analysis import calculate_future_analysis

from django.conf import settings

import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from django.http import FileResponse


# =====================================================
# DATA CENTER - UPLOAD METIS FILE
# =====================================================

def data_center(request):

    message = None
    preview = None
    summary = None

    vessels = Vessel.objects.all()

    if request.method == "POST":

        uploaded_file = request.FILES.get("file")

        vessel_id = request.POST.get("vessel")

        if uploaded_file and vessel_id:

            vessel = get_object_or_404(
                Vessel,
                id=vessel_id
            )

            # -----------------------------------------
            # READ FILE
            # -----------------------------------------

            if uploaded_file.name.lower().endswith(".csv"):

                df = pd.read_csv(
                    uploaded_file
                )

            else:

                df = pd.read_excel(
                    uploaded_file
                )

            rows = len(df)

            # -----------------------------------------
            # CALCULATE PERFORMANCE
            # -----------------------------------------

            df, result = calculate_fuel_performance(
                df
            )

            # -----------------------------------------
            # SAVE UPLOAD HISTORY
            # -----------------------------------------

            upload = MetisUpload.objects.create(
                vessel=vessel,
                file_name=uploaded_file.name,
                rows_processed=rows,
                status="Completed"
            )

            # -----------------------------------------
            # SAVE KPI RESULTS
            # -----------------------------------------

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

            # -----------------------------------------
            # SUCCESS MESSAGE
            # -----------------------------------------

            message = (
                "✓ METIS file processed "
                "and saved successfully"
            )

            # -----------------------------------------
            # PREVIEW
            # -----------------------------------------

            preview = df.head(10).to_html(
                classes="table"
            )

            # -----------------------------------------
            # SUMMARY
            # -----------------------------------------

            summary = result

        else:

            message = (
                "Please select both a vessel "
                "and a file."
            )

    # -----------------------------------------
    # RENDER PAGE
    # -----------------------------------------

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

# =====================================================
# FUTURE ANALYSIS
# =====================================================

def future_analysis(request):

    result = None
    error = None
    vessel_name = "Vessel"
    table_html = None

    if request.method == "POST":

        uploaded_file = request.FILES.get("file")

        vessel_name = request.POST.get(
            "vessel_name",
            "Vessel"
        )

        if not uploaded_file:

            error = "Please upload an Excel file."

        else:

            try:

                # =================================================
                # READ ALL EXCEL SHEETS
                # =================================================

                sheets = pd.read_excel(
                    uploaded_file,
                    sheet_name=None,
                    header=None
                )

                if not sheets:

                    raise ValueError(
                        "The uploaded Excel file contains no sheets."
                    )

                # =================================================
                # SELECT VESSEL SHEET
                # =================================================

                if vessel_name in sheets:

                    df = sheets[vessel_name]

                else:

                    vessel_name = list(
                        sheets.keys()
                    )[0]

                    df = sheets[vessel_name]

                # =================================================
                # VALIDATE DATAFRAME
                # =================================================

                if df is None:

                    raise ValueError(
                        "Unable to read the Excel sheet."
                    )

                if not isinstance(
                    df,
                    pd.DataFrame
                ):

                    raise ValueError(
                        "The selected sheet is not a valid DataFrame."
                    )

                if df.empty:

                    raise ValueError(
                        "The selected Excel sheet is empty."
                    )

                # =================================================
                # CALCULATE FUTURE ANALYSIS
                # =================================================

                result = calculate_future_analysis(
                    df
                )

                if result is None:

                    raise ValueError(
                        "Future analysis returned no data."
                    )

                if not isinstance(
                    result,
                    pd.DataFrame
                ):

                    raise ValueError(
                        "Future analysis must return a DataFrame."
                    )

                # =================================================
                # STORE COMPLETE RESULT IN SESSION
                # =================================================

                request.session[
                    "future_analysis_data"
                ] = result.to_json(
                    orient="split",
                    date_format="iso"
                )

                request.session[
                    "future_analysis_vessel"
                ] = vessel_name

                # =================================================
                # PREPARE TABLE
                # =================================================

                try:

                    # -------------------------------------------------
                    # MAKE COPY
                    # -------------------------------------------------

                    display_df = result.copy()

                    # -------------------------------------------------
                    # RESET INDEX
                    # -------------------------------------------------

                    display_df = display_df.reset_index(
                        drop=True
                    )

                    # -------------------------------------------------
                    # ORIGINAL EXCEL COLUMN NAMES
                    #
                    # IMPORTANT:
                    # These are based ONLY on column position.
                    # We do not access columns by duplicate names.
                    # -------------------------------------------------

                    readable_columns = {

                        0: "Excel Column 1",
                        1: "Excel Column 2",
                        2: "Date",
                        3: "Duration (days)",
                        4: "Hours",
                        5: "Distance Travelled (NM)",
                        6: "Distance / Other",
                        7: "Fuel On Board - HSFO",
                        8: "Fuel On Board - LSFO",
                        9: "Fuel On Board - MGO",
                        10: "Excel Column 11",
                        11: "Speed (knots)",
                        12: "Target Speed (knots)",
                        13: "Speed Saved (knots)",
                        14: "Excel Column 15",
                        15: "Consumption",
                        16: "24h Consumption",
                        17: "Excel Column 18",
                        18: "Distance to Go",
                        19: "Majishan",
                        20: "Target",
                        21: "Average Speed",
                        22: "Expected",
                        23: "Extra Day",
                        24: "Cost",
                        25: "Excel Column 26",
                        26: "Consumption Target",
                        27: "Consumption",
                        28: "Remaining",
                        29: "Consumption Cost",
                        30: "Excel Column 31",
                        31: "Expected Total",
                        32: "Excel Column 33",
                        33: "Expected Time - Daily",
                        34: "Cumulative Time",
                        35: "Cost",
                        36: "Fuel - Daily",
                        37: "Fuel - Cumulative",
                        38: "Cost",
                        39: "Total",
                        40: "Excel Column 41",
                        41: "Date - Future",
                        42: "Expected Loss",
                    }

                    # -------------------------------------------------
                    # CREATE NEW COLUMN NAMES
                    #
                    # Calculated columns keep their names.
                    # Every other column is renamed by POSITION.
                    # -------------------------------------------------

                    new_columns = []

                    for position, column_name in enumerate(
                        display_df.columns
                    ):

                        # ---------------------------------------------
                        # Calculated columns
                        # ---------------------------------------------

                        if column_name in (
                            "Future Average Speed",
                            "Future Average Consumption",
                            "Today's Speed",
                            "Today's Consumption",
                        ):

                            new_columns.append(
                                str(column_name)
                            )

                        else:

                            new_columns.append(
                                readable_columns.get(
                                    position,
                                    f"Excel Column {position + 1}"
                                )
                            )

                    # -------------------------------------------------
                    # IMPORTANT:
                    # Make names unique.
                    #
                    # Your Excel has duplicate names such as:
                    # Consumption
                    # Cost
                    #
                    # Duplicate names can cause:
                    # "truth value of a Series is ambiguous"
                    # -------------------------------------------------

                    unique_columns = []

                    name_counts = {}

                    for column_name in new_columns:

                        if column_name not in name_counts:

                            name_counts[column_name] = 0

                            unique_columns.append(
                                column_name
                            )

                        else:

                            name_counts[column_name] += 1

                            unique_columns.append(
                                f"{column_name} "
                                f"({name_counts[column_name] + 1})"
                            )

                    display_df.columns = unique_columns

                    # =================================================
                    # REMOVE ONLY COMPLETELY EMPTY COLUMNS
                    #
                    # We work by POSITION.
                    # This avoids duplicate-column problems.
                    # =================================================

                    columns_to_keep = []

                    for position in range(
                        display_df.shape[1]
                    ):

                        column_series = (
                            display_df.iloc[:, position]
                        )

                        # Convert empty strings to NaN
                        cleaned = column_series.replace(
                            r"^\s*$",
                            pd.NA,
                            regex=True
                        )

                        # Keep if at least one real value exists
                        if cleaned.notna().any():

                            columns_to_keep.append(
                                position
                            )

                    display_df = display_df.iloc[
                        :,
                        columns_to_keep
                    ].copy()

                    # =================================================
                    # KEEP ACTUAL DAILY DATA
                    # =================================================

                    if "Date" in display_df.columns:

                        date_series = pd.to_datetime(
                            display_df["Date"],
                            errors="coerce"
                        )

                        valid_rows = date_series.notna()

                        display_df = display_df.loc[
                            valid_rows
                        ].copy()

                        date_series = date_series.loc[
                            valid_rows
                        ]

                        display_df["Date"] = (
                            date_series.dt.strftime(
                                "%d-%b-%Y"
                            )
                        )

                    # =================================================
                    # FORMAT FUTURE DATE
                    # =================================================

                    if "Date - Future" in display_df.columns:

                        future_date_series = pd.to_datetime(
                            display_df["Date - Future"],
                            errors="coerce"
                        )

                        display_df["Date - Future"] = (
                            future_date_series.dt.strftime(
                                "%d-%b-%Y"
                            )
                        )

                    # =================================================
                    # NUMERIC COLUMNS
                    #
                    # Find them by their exact unique names.
                    # =================================================

                    numeric_columns = [

                        "Duration (days)",
                        "Hours",
                        "Distance Travelled (NM)",
                        "Distance / Other",
                        "Fuel On Board - HSFO",
                        "Fuel On Board - LSFO",
                        "Fuel On Board - MGO",
                        "Speed (knots)",
                        "Target Speed (knots)",
                        "Speed Saved (knots)",
                        "Consumption",
                        "24h Consumption",
                        "Distance to Go",
                        "Majishan",
                        "Target",
                        "Average Speed",
                        "Expected",
                        "Extra Day",
                        "Cost",
                        "Consumption Target",
                        "Remaining",
                        "Consumption Cost",
                        "Expected Total",
                        "Expected Time - Daily",
                        "Cumulative Time",
                        "Fuel - Daily",
                        "Fuel - Cumulative",
                        "Total",
                        "Expected Loss",
                        "Future Average Speed",
                        "Future Average Consumption",
                        "Today's Speed",
                        "Today's Consumption",
                    ]

                    # -------------------------------------------------
                    # Convert numeric columns
                    # -------------------------------------------------

                    for column_name in numeric_columns:

                        if column_name in display_df.columns:

                            # IMPORTANT:
                            # get_loc can return a slice/list if
                            # duplicate names exist.
                            #
                            # Our names are now unique, so this is safe.

                            display_df[column_name] = (
                                pd.to_numeric(
                                    display_df[column_name],
                                    errors="coerce"
                                ).round(2)
                            )

                    # =================================================
                    # REPLACE NaN / NaT
                    # =================================================

                    display_df = display_df.fillna("")

                    # =================================================
                    # CREATE HTML TABLE
                    # =================================================

                    table_html = display_df.to_html(

                        classes=(
                            "table "
                            "table-sm "
                            "table-bordered "
                            "table-hover "
                            "future-analysis-table"
                        ),

                        index=False,

                        na_rep=""
                    )

                except Exception as table_error:

                    table_html = None

                    error = (
                        "Analysis completed, but the table "
                        "could not be prepared: "
                        f"{table_error}"
                    )

            except Exception as e:

                error = str(e)

    # =====================================================
    # RENDER PAGE
    # =====================================================

    return render(

        request,

        "fuel/future_analysis.html",

        {
            "result": result,
            "table_html": table_html,
            "error": error,
            "vessel_name": vessel_name,
        }
    )

# =====================================================
# SAFE FUTURE ANALYSIS TABLE PREPARATION
# =====================================================

def prepare_future_analysis_display(result):

    """
    Creates the web-display version of the Future Analysis.

    IMPORTANT:
    - Does not modify the original result.
    - Uses column POSITION for original Excel columns.
    - Uses exact column names for calculated columns.
    - Handles duplicate Excel column names safely.
    """

    # =================================================
    # COPY
    # =================================================

    df = result.copy()

    # =================================================
    # RESET INDEX
    # =================================================

    df = df.reset_index(drop=True)

    # =================================================
    # ORIGINAL EXCEL COLUMN NAMES
    # =================================================

    readable_columns = {

        0: "Unused",
        1: "Unused",
        2: "Date",
        3: "Duration (days)",
        4: "Hours",
        5: "Distance Travelled (NM)",
        6: "Distance / Other",
        7: "Fuel On Board - HSFO",
        8: "Fuel On Board - LSFO",
        9: "Fuel On Board - MGO",
        10: "Unused",
        11: "Speed (knots)",
        12: "Target Speed (knots)",
        13: "Speed Saved (knots)",
        14: "Unused",
        15: "Consumption",
        16: "24h Consumption",
        17: "Unused",
        18: "Distance to Go",
        19: "Majishan",
        20: "Target",
        21: "Average Speed",
        22: "Expected",
        23: "Extra Day",
        24: "Cost",
        25: "Unused",
        26: "Consumption Target",
        27: "Consumption",
        28: "Remaining",
        29: "Consumption Cost",
        30: "Unused",
        31: "Expected Total",
        32: "Unused",
        33: "Expected Time - Daily",
        34: "Cumulative Time",
        35: "Cost",
        36: "Fuel - Daily",
        37: "Fuel - Cumulative",
        38: "Cost",
        39: "Total",
        40: "Unused",
        41: "Date - Future",
        42: "Expected Loss",
    }

    # =================================================
    # CALCULATED COLUMNS
    # =================================================

    calculated_columns = {

        "Future Average Speed":
            "Future Average Speed",

        "Future Average Consumption":
            "Future Average Consumption",

        "Today's Speed":
            "Today's Speed",

        "Today's Consumption":
            "Today's Consumption",
    }

    # =================================================
    # BUILD NEW DATAFRAME SAFELY
    # =================================================
    #
    # We construct each column individually.
    #
    # This is important because:
    #
    # df["SomeName"]
    #
    # can return a DATAFRAME instead of a Series when
    # duplicate column names exist.
    #
    # That was the source of the ambiguous Series error.
    # =================================================

    output = {}

    original_column_count = len(df.columns)

    # =================================================
    # ORIGINAL EXCEL COLUMNS
    # =================================================

    for position in range(
        original_column_count
    ):

        column_name = readable_columns.get(
            position,
            f"Excel Column {position + 1}"
        )

        # ---------------------------------------------
        # SKIP UNUSED COLUMNS
        # ---------------------------------------------

        if column_name == "Unused":

            continue

        # ---------------------------------------------
        # GET COLUMN BY POSITION
        #
        # IMPORTANT:
        # iloc always gives the actual column at this
        # position, even if Excel contains duplicate
        # column names.
        # ---------------------------------------------

        series = df.iloc[
            :,
            position
        ].copy()

        # Make sure it is really a Series.
        if isinstance(
            series,
            pd.DataFrame
        ):

            series = series.iloc[
                :,
                0
            ]

        # ---------------------------------------------
        # CHECK IF COLUMN IS EMPTY
        # ---------------------------------------------

        cleaned = series.replace(
            r"^\s*$",
            pd.NA,
            regex=True
        )

        if not cleaned.notna().any():

            continue

        # ---------------------------------------------
        # ADD COLUMN
        # ---------------------------------------------

        output[column_name] = series

    # =================================================
    # CALCULATED COLUMNS
    # =================================================

    for column_name in calculated_columns:

        # ---------------------------------------------
        # Only add if it exists
        # ---------------------------------------------

        if column_name not in df.columns:

            continue

        # ---------------------------------------------
        # IMPORTANT:
        # If duplicate column names exist, df[column_name]
        # can return a DataFrame.
        #
        # Therefore handle both cases explicitly.
        # ---------------------------------------------

        calculated_data = df.loc[
            :,
            column_name
        ]

        if isinstance(
            calculated_data,
            pd.DataFrame
        ):

            # Take first matching column
            calculated_data = calculated_data.iloc[
                :,
                0
            ]

        calculated_data = calculated_data.copy()

        output[column_name] = calculated_data

    # =================================================
    # CREATE CLEAN DATAFRAME
    # =================================================

    clean_df = pd.DataFrame(
        output
    )

    # =================================================
    # DATE
    # =================================================

    if "Date" in clean_df.columns:

        date_values = pd.to_datetime(
            clean_df["Date"],
            errors="coerce"
        )

        # Keep only rows with valid dates
        valid_rows = date_values.notna()

        clean_df = clean_df.loc[
            valid_rows
        ].copy()

        date_values = date_values.loc[
            valid_rows
        ]

        clean_df["Date"] = (
            date_values.dt.strftime(
                "%d-%b-%Y"
            )
        )

    # =================================================
    # FUTURE DATE
    # =================================================

    if "Date - Future" in clean_df.columns:

        future_dates = pd.to_datetime(
            clean_df["Date - Future"],
            errors="coerce"
        )

        clean_df["Date - Future"] = (
            future_dates.dt.strftime(
                "%d-%b-%Y"
            )
        )

    # =================================================
    # NUMERIC COLUMNS
    # =================================================

    numeric_columns = [

        "Duration (days)",
        "Hours",
        "Distance Travelled (NM)",
        "Distance / Other",

        "Fuel On Board - HSFO",
        "Fuel On Board - LSFO",
        "Fuel On Board - MGO",

        "Speed (knots)",
        "Target Speed (knots)",
        "Speed Saved (knots)",

        "Consumption",
        "24h Consumption",

        "Distance to Go",
        "Majishan",
        "Target",
        "Average Speed",
        "Expected",
        "Extra Day",
        "Cost",

        "Consumption Target",
        "Remaining",
        "Consumption Cost",

        "Expected Total",
        "Expected Time - Daily",
        "Cumulative Time",

        "Fuel - Daily",
        "Fuel - Cumulative",

        "Total",

        "Expected Loss",

        "Future Average Speed",
        "Future Average Consumption",

        "Today's Speed",
        "Today's Consumption",
    ]

    # =================================================
    # CONVERT NUMERIC VALUES
    # =================================================

    for column_name in numeric_columns:

        if column_name not in clean_df.columns:

            continue

        # Make absolutely sure we have a Series
        values = clean_df.loc[
            :,
            column_name
        ]

        if isinstance(
            values,
            pd.DataFrame
        ):

            values = values.iloc[
                :,
                0
            ]

        clean_df[column_name] = pd.to_numeric(
            values,
            errors="coerce"
        ).round(2)

    # =================================================
    # REPLACE NaN / NaT
    # =================================================

    clean_df = clean_df.fillna("")

    # =================================================
    # RETURN
    # =================================================

    return clean_df


# =====================================================
# FUTURE ANALYSIS EXCEL DOWNLOAD
# =====================================================

def future_analysis_excel(request):

    json_data = request.session.get(
        "future_analysis_data"
    )

    vessel_name = request.session.get(
        "future_analysis_vessel",
        "Vessel"
    )

    # =================================================
    # CHECK DATA
    # =================================================

    if not json_data:

        return HttpResponse(
            "No analysis available. "
            "Please run Future Analysis first.",
            status=400
        )

    try:

        df = pd.read_json(
            json_data,
            orient="split"
        )

    except Exception as e:

        return HttpResponse(
            f"Unable to load analysis data: {e}",
            status=500
        )

    # =================================================
    # CREATE EXCEL RESPONSE
    # =================================================

    response = HttpResponse(

        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

    response["Content-Disposition"] = (

        f'attachment; '
        f'filename="{vessel_name}_future_analysis.xlsx"'
    )

    # =================================================
    # WRITE EXCEL
    # =================================================

    df.to_excel(

        response,

        index=False,

        sheet_name="Future Analysis"
    )

    return response


# =====================================================
# FUTURE ANALYSIS GRAPH
# =====================================================

def future_analysis_graph(request):

    json_data = request.session.get(
        "future_analysis_data"
    )

    vessel_name = request.session.get(
        "future_analysis_vessel",
        "Vessel"
    )

    # =================================================
    # CHECK DATA
    # =================================================

    if not json_data:

        return HttpResponse(
            "No analysis available. "
            "Please run Future Analysis first.",
            status=400
        )

    try:

        df = pd.read_json(
            json_data,
            orient="split"
        )

    except Exception as e:

        return HttpResponse(
            f"Unable to load analysis data: {e}",
            status=500
        )

    # =================================================
    # REQUIRED GRAPH COLUMNS
    # =================================================

    required_columns = [

        "Today's Speed",
        "Future Average Speed",
        "Today's Consumption",
        "Future Average Consumption",
    ]

    missing_columns = [

        column

        for column in required_columns

        if column not in df.columns
    ]

    if missing_columns:

        return HttpResponse(

            "Missing required analysis columns: "
            + ", ".join(missing_columns),

            status=400
        )

    # =================================================
    # CONVERT GRAPH VALUES
    # =================================================

    for column in required_columns:

        values = df.loc[
            :,
            column
        ]

        # Handle duplicate column names safely
        if isinstance(
            values,
            pd.DataFrame
        ):

            values = values.iloc[
                :,
                0
            ]

        df[column] = pd.to_numeric(
            values,
            errors="coerce"
        )

    # =================================================
    # DATE / X AXIS
    # =================================================

    if "Date" in df.columns:

        dates = df.loc[
            :,
            "Date"
        ]

        if isinstance(
            dates,
            pd.DataFrame
        ):

            dates = dates.iloc[
                :,
                0
            ]

        dates = pd.to_datetime(
            dates,
            errors="coerce"
        )

        valid_rows = dates.notna()

        df = df.loc[
            valid_rows
        ].copy()

        dates = dates.loc[
            valid_rows
        ]

        x = dates

        x_labels = dates.dt.strftime(
            "%d-%b"
        )

    else:

        x = list(
            range(
                1,
                len(df) + 1
            )
        )

        x_labels = [

            f"Day {i}"

            for i in x
        ]

    # =================================================
    # CHECK THERE IS DATA
    # =================================================

    if len(df) == 0:

        return HttpResponse(
            "No valid dated data available for graph.",
            status=400
        )

    # =================================================
    # CREATE FIGURE
    # =================================================

    fig, axes = plt.subplots(

        2,

        1,

        figsize=(13, 9)
    )

    # =================================================
    # SPEED GRAPH
    # =================================================

    axes[0].plot(

        x,

        df["Today's Speed"],

        marker="o",

        linewidth=2,

        label="Today's Speed"
    )

    axes[0].plot(

        x,

        df["Future Average Speed"],

        marker="o",

        linestyle="--",

        linewidth=2,

        label="Future Average Speed"
    )

    axes[0].set_title(

        f"{vessel_name} - Speed Analysis"
    )

    axes[0].set_ylabel(

        "Speed (knots)"
    )

    axes[0].grid(

        True,

        alpha=0.3
    )

    axes[0].legend()

    # =================================================
    # CONSUMPTION GRAPH
    # =================================================

    axes[1].plot(

        x,

        df["Today's Consumption"],

        marker="o",

        linewidth=2,

        label="Today's Consumption"
    )

    axes[1].plot(

        x,

        df["Future Average Consumption"],

        marker="o",

        linestyle="--",

        linewidth=2,

        label="Future Average Consumption"
    )

    axes[1].set_title(

        f"{vessel_name} - Consumption Analysis"
    )

    axes[1].set_ylabel(

        "Consumption"
    )

    axes[1].set_xlabel(

        "Date"
    )

    axes[1].grid(

        True,

        alpha=0.3
    )

    axes[1].legend()

    # =================================================
    # DATE LABELS
    # =================================================

    if "Date" in df.columns:

        axes[1].set_xticks(
            x
        )

        axes[1].set_xticklabels(

            x_labels,

            rotation=45,

            ha="right"
        )

    # =================================================
    # LAYOUT
    # =================================================

    plt.tight_layout()

    # =================================================
    # GRAPH DIRECTORY
    # =================================================

    graph_dir = os.path.join(

        settings.MEDIA_ROOT,

        "fuel",

        "graphs"
    )

    os.makedirs(

        graph_dir,

        exist_ok=True
    )

    # =================================================
    # SAFE VESSEL NAME
    # =================================================

    safe_vessel_name = "".join(

        character

        for character in vessel_name

        if character.isalnum()
        or character in (
            "_",
            "-",
            " "
        )
    ).strip()

    if not safe_vessel_name:

        safe_vessel_name = "Vessel"

    graph_path = os.path.join(

        graph_dir,

        f"{safe_vessel_name}_future_analysis.png"
    )

    # =================================================
    # SAVE GRAPH
    # =================================================

    plt.savefig(

        graph_path,

        dpi=150,

        bbox_inches="tight"
    )

    plt.close()

    # =================================================
    # RETURN GRAPH
    # =================================================

    return FileResponse(

        open(
            graph_path,
            "rb"
        ),

        as_attachment=True,

        filename=(
            f"{safe_vessel_name}_future_analysis.png"
        )
    )
import pandas as pd



def calculate_fuel_performance(df):

    summary = {}


    # Operating hours

    if "Timestamp (UTC)" in df.columns:

        df["Timestamp (UTC)"] = pd.to_datetime(
            df["Timestamp (UTC)"]
        )


        duration = (
            df["Timestamp (UTC)"].max()
            -
            df["Timestamp (UTC)"].min()
        )


        summary["operating_hours"] = round(
            duration.total_seconds()/3600,
            2
        )


    else:

        summary["operating_hours"] = 0



    # Fuel consumption

    inlet = (
        "Main Engine Fuel Oil Inlet Mass Flow - Instant (kg/hr)"
    )


    outlet = (
        "Main Engine Fuel Oil Outlet Mass Flow - Instant (kg/hr)"
    )



    if inlet in df.columns and outlet in df.columns:


        df["Fuel_Consumption_kg_hr"] = (
            df[inlet]
            -
            df[outlet]
        )


        df["Fuel_Consumption_kg_hr"] = (
            df["Fuel_Consumption_kg_hr"]
            .clip(lower=0)
        )


        summary["total_fuel_tons"] = round(

            df["Fuel_Consumption_kg_hr"]
            .sum()
            /
            60
            /
            1000,

            2

        )



    else:

        summary["total_fuel_tons"] = 0




    # Engine load

    load = (
        "Main Engine Fuel Load % - Instant (%)"
    )


    if load in df.columns:

        summary["average_load"] = round(

            df[load].mean(),

            2

        )

    else:

        summary["average_load"] = 0





    # Speed

    speed = (
        "Vessel Hull Through Water Longitudinal Speed - Instant (knots)"
    )


    if speed in df.columns:

        summary["average_speed"] = round(

            df[speed].mean(),

            2

        )

    else:

        summary["average_speed"] = 0





    # SFOC

    power = (
        "Vessel Propeller Shaft Mechanical Power - Instant (KW)"
    )


    if (
        power in df.columns
        and
        "Fuel_Consumption_kg_hr" in df.columns
    ):


        temp = df[

            (df[power] > 100)
            &
            (df["Fuel_Consumption_kg_hr"] > 0)

        ].copy()



        temp["SFOC"] = (

            temp["Fuel_Consumption_kg_hr"]
            *
            1000
            /
            temp[power]

        )



        temp = temp[

            (temp["SFOC"] > 50)
            &
            (temp["SFOC"] < 500)

        ]



        df["SFOC"] = temp["SFOC"]



        summary["sfoc"] = round(

            temp["SFOC"].mean(),

            2

        )


    else:

        summary["sfoc"] = 0




    return df, summary
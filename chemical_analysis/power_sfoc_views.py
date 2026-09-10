from django.shortcuts import render

from .services.power_sfoc_analysis import (
    build_power_sfoc_analysis,
)


def power_sfoc_analysis(request):

    vessel = (
        request.GET.get(
            "vessel",
            "DANIEL N",
        )
        .strip()
        .upper()
    )

    if vessel not in {
        "DANIEL N",
        "HELEN N",
        "COMBINED",
    }:
        vessel = "DANIEL N"

    try:
        min_power = float(
            request.GET.get(
                "min_power",
                8000,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        min_power = 8000.0

    try:
        max_power = float(
            request.GET.get(
                "max_power",
                10000,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        max_power = 10000.0

    result = build_power_sfoc_analysis(
        vessel=vessel,
        min_power=min_power,
        max_power=max_power,
    )

    # Chart.js needs the chart data separately.
    chart_data = result.get(
        "chart_data",
        {},
    )

    return render(
        request,
        "chemical_analysis/power_sfoc_analysis.html",
        {
            "vessel": vessel,
            "min_power": min_power,
            "max_power": max_power,
            "result": result,
            "chart_data": chart_data,
        },
    )
from django.shortcuts import render

from .services.analysis import get_vessel_analysis
from .services.effectiveness_analysis import (
    build_effectiveness_report,
)


def effectiveness_report(request):
    """
    Management-level chemical effectiveness report.

    URL example:

        /chemical-analysis/effectiveness/?vessel=DANIEL%20N

    Optional financial inputs:

        fuel_price
        additive_price
    """

    vessel = (
        request.GET.get(
            "vessel",
            "DANIEL N",
        )
        .strip()
    )


    # ---------------------------------------------------------
    # Financial scenario inputs
    # ---------------------------------------------------------

    fuel_price = (
        request.GET.get(
            "fuel_price",
            "0",
        )
        .strip()
    )

    additive_price = (
        request.GET.get(
            "additive_price",
            "0",
        )
        .strip()
    )


    # ---------------------------------------------------------
    # Get existing vessel analysis
    # ---------------------------------------------------------

    try:

        analysis_result = (
            get_vessel_analysis(
                vessel
            )
        )

    except Exception as exc:

        return render(
            request,
            "chemical_analysis/effectiveness_report.html",
            {
                "vessel": vessel,
                "error": (
                    "Unable to generate the "
                    f"effectiveness report: {exc}"
                ),
                "fuel_price": fuel_price,
                "additive_price": additive_price,
            },
        )


    # ---------------------------------------------------------
    # Build management report
    # ---------------------------------------------------------

    try:

        report = (
            build_effectiveness_report(
                analysis_result,
                fuel_price=fuel_price,
                additive_price=additive_price,
            )
        )

    except Exception as exc:

        return render(
            request,
            "chemical_analysis/effectiveness_report.html",
            {
                "vessel": vessel,
                "error": (
                    "Unable to build the "
                    f"effectiveness report: {exc}"
                ),
                "fuel_price": fuel_price,
                "additive_price": additive_price,
            },
        )


    # ---------------------------------------------------------
    # Render
    # ---------------------------------------------------------

    return render(
        request,
        "chemical_analysis/effectiveness_report.html",
        {
            "vessel": vessel,
            "report": report,
            "fuel_price": fuel_price,
            "additive_price": additive_price,
        },
    )
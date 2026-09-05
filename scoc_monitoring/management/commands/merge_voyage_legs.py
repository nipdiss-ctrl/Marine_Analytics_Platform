from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from scoc_monitoring.models import (
    VoyageLeg,
    VoyageObservation,
)


# ============================================================
# NORMALISATION
# ============================================================

def normalise(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .strip()
        .upper()
        .split()
    )


def route_key(leg):
    """
    Identify a voyage by:

        LOAD TYPE
        DEPARTURE
        DESTINATION
        VOYAGE REFERENCE

    Voyage reference is included when available.
    """

    return (
        normalise(leg.load_type),
        normalise(leg.departure),
        normalise(leg.destination),
        normalise(leg.voyage_reference),
    )


def same_route(a, b):
    return route_key(a) == route_key(b)


# ============================================================
# COMMAND
# ============================================================

class Command(BaseCommand):

    help = (
        "Merge daily VoyageLeg records into actual voyage legs "
        "and move their observations underneath the merged leg."
    )

    def handle(self, *args, **options):

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Starting SCoC voyage-leg consolidation..."
            )
        )
        self.stdout.write("")

        legs = list(
            VoyageLeg.objects
            .all()
            .prefetch_related("observations")
            .order_by(
                "load_type",
                "departure",
                "destination",
                "start_date",
                "id",
            )
        )

        if not legs:
            self.stdout.write(
                self.style.WARNING(
                    "No VoyageLeg records found."
                )
            )
            return

        merged_count = 0
        observation_count = 0

        # --------------------------------------------------------
        # GROUP BY ROUTE
        # --------------------------------------------------------

        groups = {}

        for leg in legs:

            key = route_key(leg)

            groups.setdefault(
                key,
                []
            ).append(leg)

        # --------------------------------------------------------
        # PROCESS EACH ROUTE
        # --------------------------------------------------------

        with transaction.atomic():

            for key, route_legs in groups.items():

                if len(route_legs) <= 1:
                    continue

                route_legs.sort(
                    key=lambda x: (
                        x.start_date
                        or x.end_date
                        or x.created_at,
                        x.id,
                    )
                )

                # ------------------------------------------------
                # Split into actual voyages when there is a
                # significant date gap.
                #
                # Daily reports normally belong to the same
                # voyage when they are consecutive.
                # ------------------------------------------------

                voyages = []
                current = []

                previous_date = None

                for leg in route_legs:

                    leg_date = (
                        leg.start_date
                        or leg.end_date
                    )

                    if (
                        previous_date is not None
                        and leg_date is not None
                    ):

                        gap = (
                            leg_date.date()
                            - previous_date.date()
                        ).days

                        # More than 3 days means this is
                        # probably another voyage.
                        if gap > 3:

                            if current:
                                voyages.append(
                                    current
                                )

                            current = []

                    current.append(leg)

                    if leg_date is not None:
                        previous_date = leg_date

                if current:
                    voyages.append(current)

                # ------------------------------------------------
                # MERGE EACH VOYAGE
                # ------------------------------------------------

                for voyage_legs in voyages:

                    if len(voyage_legs) <= 1:
                        continue

                    # --------------------------------------------
                    # Use the earliest leg as the master
                    # --------------------------------------------

                    master = voyage_legs[0]

                    self.stdout.write(
                        f"Merging route: "
                        f"{master.departure} → "
                        f"{master.destination} "
                        f"({master.load_type})"
                    )

                    # --------------------------------------------
                    # Collect all observations
                    # --------------------------------------------

                    observations = []

                    for leg in voyage_legs:

                        for observation in (
                            VoyageObservation.objects
                            .filter(leg=leg)
                            .order_by(
                                "reported_time",
                                "id",
                            )
                        ):

                            observations.append(
                                observation
                            )

                    # --------------------------------------------
                    # Move observations to master
                    # --------------------------------------------

                    seen_times = set()

                    for observation in observations:

                        reported_time = (
                            observation.reported_time
                        )

                        if reported_time in seen_times:

                            # Duplicate daily report.
                            observation.delete()
                            continue

                        seen_times.add(
                            reported_time
                        )

                        if observation.leg_id != master.id:

                            observation.leg = master

                            observation.save(
                                update_fields=[
                                    "leg",
                                    "updated_at",
                                ]
                            )

                        observation_count += 1

                    # --------------------------------------------
                    # Update master date range
                    # --------------------------------------------

                    dates = [
                        leg.start_date
                        for leg in voyage_legs
                        if leg.start_date
                    ]

                    end_dates = [
                        leg.end_date
                        for leg in voyage_legs
                        if leg.end_date
                    ]

                    if dates:

                        master.start_date = min(
                            dates
                        )

                    if end_dates:

                        master.end_date = max(
                            end_dates
                        )

                    # --------------------------------------------
                    # Calculate route averages from observations
                    # --------------------------------------------

                    master_observations = (
                        VoyageObservation.objects
                        .filter(leg=master)
                    )

                    speeds = [
                        x.speed
                        for x in master_observations
                        if x.speed is not None
                    ]

                    consumptions = [
                        x.consumption
                        for x in master_observations
                        if x.consumption is not None
                    ]

                    dtgs = [
                        x.distance_to_go
                        for x in master_observations
                        if x.distance_to_go is not None
                    ]

                    if speeds:
                        master.average_speed = (
                            sum(speeds)
                            / len(speeds)
                        )

                    if consumptions:
                        master.average_consumption = (
                            sum(consumptions)
                            / len(consumptions)
                        )

                    if dtgs:
                        master.distance_to_go = (
                            dtgs[-1]
                        )

                    # --------------------------------------------
                    # Preserve target values.
                    #
                    # First non-empty value wins.
                    # --------------------------------------------

                    if master.target_speed is None:

                        for leg in voyage_legs:

                            if (
                                leg.target_speed
                                is not None
                            ):
                                master.target_speed = (
                                    leg.target_speed
                                )
                                break

                    if master.target_consumption is None:

                        for leg in voyage_legs:

                            if (
                                leg.target_consumption
                                is not None
                            ):
                                master.target_consumption = (
                                    leg.target_consumption
                                )
                                break

                    master.save()

                    # --------------------------------------------
                    # Delete duplicate child legs
                    # --------------------------------------------

                    for leg in voyage_legs[1:]:

                        self.stdout.write(
                            f"    Removing daily leg "
                            f"#{leg.id}"
                        )

                        leg.delete()

                        merged_count += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    → Master leg "
                            f"#{master.id} now contains "
                            f"{master_observations.count()} "
                            f"observations"
                        )
                    )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "================================================"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Voyage legs merged: {merged_count}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Observations processed: {observation_count}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Voyage consolidation completed."
            )
        )

        self.stdout.write("")
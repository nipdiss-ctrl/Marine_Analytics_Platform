from django.db import migrations, models
import django.db.models.deletion


def add_scoc_vessel_columns(apps, schema_editor):
    """
    The scoc_monitoring_scocvessel table already exists in the
    database. Add only the columns that are missing.
    """

    with schema_editor.connection.cursor() as cursor:

        cursor.execute(
            """
            ALTER TABLE scoc_monitoring_scocvessel
            ADD COLUMN target_speed_laden REAL NULL
            """
        )

        cursor.execute(
            """
            ALTER TABLE scoc_monitoring_scocvessel
            ADD COLUMN target_consumption_laden REAL NULL
            """
        )

        cursor.execute(
            """
            ALTER TABLE scoc_monitoring_scocvessel
            ADD COLUMN target_speed_ballast REAL NULL
            """
        )

        cursor.execute(
            """
            ALTER TABLE scoc_monitoring_scocvessel
            ADD COLUMN target_consumption_ballast REAL NULL
            """
        )

        cursor.execute(
            """
            ALTER TABLE scoc_monitoring_scocvessel
            ADD COLUMN active bool NOT NULL DEFAULT 1
            """
        )


def create_historical_scoc_vessels(apps, schema_editor):
    """
    Create ScocVessel records corresponding to the existing
    inspections.Vessel records used by VoyageLeg.

    Existing VoyageLeg relationships:

        inspections_vessel ID 10 = XH Atop
        inspections_vessel ID 11 = Abigail N

    We deliberately use the SAME IDs in ScocVessel.

    This means the existing VoyageLeg vessel_id values 10 and 11
    remain valid while Django changes the foreign-key target.
    """

    db_alias = schema_editor.connection.alias

    ScocVessel = apps.get_model(
        "scoc_monitoring",
        "ScocVessel",
    )

    # ---------------------------------------------------------
    # XH Atop
    # ---------------------------------------------------------

    xh_atop, created = ScocVessel.objects.using(db_alias).get_or_create(
        pk=10,
        defaults={
            "vessel_name": "XH Atop",
            "engine_mcr_kw": 0,
            "cylinder_oil_density": 0.93,
            "target_scoc": 0.9,
            "high_alarm_threshold": 10,
            "low_alarm_threshold": -10,
            "target_speed_laden": None,
            "target_consumption_laden": None,
            "target_speed_ballast": None,
            "target_consumption_ballast": None,
            "active": True,
        },
    )

    if not created and xh_atop.vessel_name != "XH Atop":
        raise RuntimeError(
            "ScocVessel ID 10 already exists but is not XH Atop."
        )

    # ---------------------------------------------------------
    # Abigail N
    # ---------------------------------------------------------

    abigail_n, created = ScocVessel.objects.using(db_alias).get_or_create(
        pk=11,
        defaults={
            "vessel_name": "Abigail N",
            "engine_mcr_kw": 0,
            "cylinder_oil_density": 0.93,
            "target_scoc": 0.9,
            "high_alarm_threshold": 10,
            "low_alarm_threshold": -10,
            "target_speed_laden": None,
            "target_consumption_laden": None,
            "target_speed_ballast": None,
            "target_consumption_ballast": None,
            "active": True,
        },
    )

    if not created and abigail_n.vessel_name != "Abigail N":
        raise RuntimeError(
            "ScocVessel ID 11 already exists but is not Abigail N."
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "scoc_monitoring",
            "0010_alter_ship_id_alter_voyageleg_id_and_more",
        ),
    ]

    operations = [

        # =====================================================
        # 1. Add the missing physical columns to ScocVessel
        # =====================================================

        migrations.RunPython(
            add_scoc_vessel_columns,
            migrations.RunPython.noop,
        ),

        # =====================================================
        # 2. Add me_consumption_24 to VoyageObservation
        # =====================================================

        migrations.AddField(
            model_name="voyageobservation",
            name="me_consumption_24",
            field=models.FloatField(
                blank=True,
                null=True,
            ),
        ),

        # =====================================================
        # 3. Tell Django that ScocVessel already exists
        # =====================================================

        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ScocVessel",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "vessel_name",
                            models.CharField(
                                max_length=100,
                                unique=True,
                            ),
                        ),
                        (
                            "engine_mcr_kw",
                            models.FloatField(default=0),
                        ),
                        (
                            "cylinder_oil_density",
                            models.FloatField(default=0.93),
                        ),
                        (
                            "target_scoc",
                            models.FloatField(default=0.9),
                        ),
                        (
                            "high_alarm_threshold",
                            models.FloatField(default=10),
                        ),
                        (
                            "low_alarm_threshold",
                            models.FloatField(default=-10),
                        ),
                        (
                            "target_speed_laden",
                            models.FloatField(
                                blank=True,
                                null=True,
                            ),
                        ),
                        (
                            "target_consumption_laden",
                            models.FloatField(
                                blank=True,
                                null=True,
                            ),
                        ),
                        (
                            "target_speed_ballast",
                            models.FloatField(
                                blank=True,
                                null=True,
                            ),
                        ),
                        (
                            "target_consumption_ballast",
                            models.FloatField(
                                blank=True,
                                null=True,
                            ),
                        ),
                        (
                            "active",
                            models.BooleanField(default=True),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True,
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(
                                auto_now=True,
                            ),
                        ),
                    ],
                    options={
                        "ordering": [
                            "vessel_name",
                            "id",
                        ],
                    },
                ),
            ],
        ),

        # =====================================================
        # 4. Create XH Atop and Abigail N using IDs 10 and 11
        # =====================================================

        migrations.RunPython(
            create_historical_scoc_vessels,
            migrations.RunPython.noop,
        ),

        # =====================================================
        # 5. Change VoyageLeg FK from inspections.Vessel
        #    to scoc_monitoring.ScocVessel
        #
        # Existing vessel_id values:
        #
        #     10 = XH Atop
        #     11 = Abigail N
        #
        # Those IDs now exist in ScocVessel, so the values
        # do NOT need to be changed.
        # =====================================================

        migrations.AlterField(
            model_name="voyageleg",
            name="vessel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="voyage_legs",
                to="scoc_monitoring.scocvessel",
            ),
        ),
    ]
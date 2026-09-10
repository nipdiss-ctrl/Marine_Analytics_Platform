from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "scoc_monitoring",
            "0011_scocvessel_voyageobservation_me_consumption_24_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="scocvessel",
            name="vessel_type",
            field=models.CharField(
                choices=[
                    ("Bulk Carrier", "Bulk Carrier"),
                    ("Ore Carrier", "Ore Carrier"),
                ],
                default="Bulk Carrier",
                max_length=30,
            ),
        ),
    ]
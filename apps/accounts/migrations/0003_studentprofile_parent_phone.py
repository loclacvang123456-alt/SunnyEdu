from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_privacyrequest")]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="parent_phone",
            field=models.CharField(blank=True, default="", max_length=15),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0008_remove_assignment_assignment_valid_dates_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='instant_feedback',
            field=models.BooleanField(default=False),
        ),
    ]

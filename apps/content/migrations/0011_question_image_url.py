from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0010_question_pirate_game'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='image_url',
            field=models.CharField(blank=True, default='', max_length=1000),
        ),
    ]

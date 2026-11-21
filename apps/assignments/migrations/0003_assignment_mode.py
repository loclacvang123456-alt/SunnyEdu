from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('assignments', '0002_response_ordered_option_ids')]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='mode',
            field=models.CharField(choices=[('PRACTICE', 'Luyện tập'), ('EXAM', 'Bài kiểm tra')], default='EXAM', max_length=8),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='assignment',
            name='mode',
            field=models.CharField(choices=[('PRACTICE', 'Luyện tập'), ('EXAM', 'Bài kiểm tra')], default='PRACTICE', max_length=8),
        ),
        migrations.AddConstraint(
            model_name='assignment',
            constraint=models.CheckConstraint(condition=models.Q(('mode__in', ['PRACTICE', 'EXAM'])), name='assignment_mode_valid'),
        ),
    ]

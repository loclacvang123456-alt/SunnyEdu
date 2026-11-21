from django.db import models


class SiteAppearance(models.Model):
    theme = models.CharField(max_length=20, default='auto')

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trosnoth', '0006_auto_20160209_2008'),
    ]

    operations = [
        migrations.AddField(
            model_name='trosnothserversettings',
            name='allowRemoteGameRegistration',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='achievementprogress',
            name='progress',
            field=models.IntegerField(default=0),
            preserve_default=True,
        ),
    ]

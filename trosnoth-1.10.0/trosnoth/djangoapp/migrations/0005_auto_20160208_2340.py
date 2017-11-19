# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trosnoth', '0004_auto_20160208_2327'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trosnothserversettings',
            name='iceProxyStringOverride',
            field=models.TextField(default=b'', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='trosnothserversettings',
            name='iceSecret',
            field=models.TextField(default=b'', blank=True),
            preserve_default=True,
        ),
    ]

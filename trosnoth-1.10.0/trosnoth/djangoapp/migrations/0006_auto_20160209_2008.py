# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trosnoth', '0005_auto_20160208_2340'),
    ]

    operations = [
        migrations.CreateModel(
            name='UpgradesUsedInGameRecord',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('upgrade', models.CharField(max_length=1)),
                ('count', models.IntegerField(default=0)),
                ('gamePlayer', models.ForeignKey(to='trosnoth.GamePlayer')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='upgradesusedingamerecord',
            unique_together=set([('gamePlayer', 'upgrade')]),
        ),
        migrations.RemoveField(
            model_name='gameplayer',
            name='upgradesUsed',
        ),
        migrations.AddField(
            model_name='gameplayer',
            name='botName',
            field=models.TextField(default=b'', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='gamerecord',
            name='replayName',
            field=models.TextField(default=b'', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='gamerecord',
            name='winningTeam',
            field=models.CharField(max_length=1, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='gameplayer',
            name='team',
            field=models.CharField(max_length=1, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='gameplayer',
            name='user',
            field=models.ForeignKey(to='trosnoth.TrosnothUser', null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='playerkills',
            name='killee',
            field=models.ForeignKey(related_name='+', to='trosnoth.GamePlayer'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='playerkills',
            name='killer',
            field=models.ForeignKey(related_name='+', to='trosnoth.GamePlayer', null=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='playerkills',
            unique_together=set([('killer', 'killee')]),
        ),
        migrations.RemoveField(
            model_name='playerkills',
            name='game',
        ),
    ]

# Generated by Django 2.0.2 on 2018-05-26 09:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deceases', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='symptom',
            name='name',
            field=models.CharField(db_index=True, max_length=1024, unique=True),
        ),
    ]

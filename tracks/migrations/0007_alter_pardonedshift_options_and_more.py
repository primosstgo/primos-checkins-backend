# Generated by Django 4.0.4 on 2024-04-02 16:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tracks', '0006_pardonedshift_rename_shift_stampedshift_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pardonedshift',
            options={'ordering': ['date', 'block']},
        ),
        migrations.AlterModelOptions(
            name='stampedshift',
            options={'ordering': ['checkin']},
        ),
    ]
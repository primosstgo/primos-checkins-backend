# Generated by Django 4.0.3 on 2022-04-08 19:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracks', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='primo',
            name='mail',
            field=models.CharField(default='sku@skrrr@skere', max_length=100, unique=True),
            preserve_default=False,
        ),
    ]
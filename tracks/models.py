# type: ignore
from django.db.models import *

class Primo(Model):
    rol = IntegerField(primary_key=True)
    mail = CharField(unique=True, max_length=100)
    
    name = CharField(max_length=100)
    nick = CharField(max_length=100)

    schedule = CharField(max_length=100)

class StampedShift(Model):
    id = AutoField(primary_key=True)
    primo = ForeignKey(Primo, on_delete=CASCADE)
    
    checkin = DateTimeField()
    checkout = DateTimeField(null=True)

    class Meta:
        ordering = ['checkin']

class PardonedShift(Model):
    id = AutoField(primary_key=True)

    block = IntegerField()
    date = DateField()

    class Meta:
        ordering = ['date', 'block']
        constraints = [
            UniqueConstraint(fields=['block', 'date'], name='unique_block_date')
        ]

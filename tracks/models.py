from django.db import models

class Primo(models.Model):
    rol = models.IntegerField(primary_key=True)
    mail = models.CharField(unique=True, max_length=100)
    
    name = models.CharField(max_length=100)
    nick = models.CharField(max_length=100)

    schedule = models.CharField(max_length=100)

class Shift(models.Model):
    id = models.AutoField(primary_key=True)
    primo = models.ForeignKey(Primo, on_delete=models.CASCADE)
    
    checkin = models.DateTimeField()
    checkout = models.DateTimeField(null=True)

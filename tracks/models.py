from django.db import models

# Create your models here.

class Primo(models.Model):
    rol = models.IntegerField(primary_key=True)
    
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    nick = models.CharField(max_length=100)

class Turno(models.Model):
    id_turno = models.AutoField(primary_key=True)
    rol = models.ForeignKey(Primo, on_delete=models.CASCADE)
    
    llegada = models.DateTimeField()
    salida = models.DateTimeField()

class Usuario(models.Model):
    #id_usuario = models.AutoField(primary_key=True)
    rol = models.IntegerField(primary_key=True)
    correo = models.CharField(max_length=200)
    #rol = models.ForeignKey(Primo, on_delete=models.CASCADE)
    #usuario = models.CharField(max_length=100)
    #contrasenna = models.CharField(max_length=50)

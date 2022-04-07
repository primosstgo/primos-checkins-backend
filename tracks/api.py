from xmlrpc.client import DateTime
from ninja import NinjaAPI
from ninja import Schema
from tracks import models
from django.shortcuts import get_list_or_404, get_object_or_404
api = NinjaAPI()

#======SCHEMAS======#

class PrimoIn(Schema):
    rol: int
    nombre: str
    apellido: str
    nick: str

class UsuarioIn(Schema):
    rol: int
    correo: str

class TurnoIn(Schema):
    id_turno: int
    rol: int
    llegada: DateTime

class TurnoOut(Schema):
    id_turno: int
    rol: int
    llegada: DateTime
    salida: DateTime


#======CRUD======#

#Agrega un primo a la base de datos en la tabla tracks.primos.
@api.post("/primos")
def crear_primo(request, payload: PrimoIn):
    primo = models.Primo.objects.create(**payload.dict())
    return {"rol": primo.rol}

#Encuentra un primo según su rol en la base de datos en la tabla tracks.primo.
@api.get("/primos/{rol}", response=PrimoIn)
def get_primo(request, rol_id: int):
    primo = get_object_or_404(models.Primo, rol=rol_id)
    return primo



#Agrega un usuario a la base de datos en la tabla tracks.usuario.
@api.post("/usuarios")
def crear_usuario(request, payload: UsuarioIn):
    usuario = models.Usuario.objects.create(**payload.dict())
    return {"usuario": usuario.rol}

#Encuentra un usuario según su rol en la base de datos en la tabla tracks.usuario.
@api.get("/usuarios/{rol}", response=UsuarioIn)
def get_usuario(request, rol_id: int):
    usuario = get_object_or_404(models.Usuario, rol=rol_id)
    return usuario



#Agrega un turno nuevo a la base de datos en la tabla tracks.turno.
@api.post("/turnos")
def crear_turno(request, payload: TurnoIn):
    turno = models.Turno.objects.create(**payload.dict())
    return {"turno": {turno.id_turno, turno.rol, turno.llegada}}

#Encuentra un turno según su id_turno en la base de datos en la tabla tracks.turno.
@api.get("/usuarios/{id_turno}", response=TurnoOut)
def get_turno(request, id_t: int):
    turno = get_object_or_404(models.Usuario, id_turno=id_t)
    return turno

#Actualiza un turno con la hora de salida según la id del turno entregado.
@api.put("/turno/{id_turno}")
def update_salida(request, id_t: int, payload: TurnoOut):
    turno = get_object_or_404(models.Turno, id_turno=id_t)
    turno.salida = payload.salida
    turno.save()
    return {"success": True}
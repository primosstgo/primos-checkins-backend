from datetime import datetime, timedelta
from os import times
import sched
from typing import List, Optional
from ninja import NinjaAPI, Schema
from django.shortcuts import get_list_or_404, get_object_or_404
from django.db.utils import IntegrityError

from tracks.models import *
from tracks import utils
from tracks import parameters

api = NinjaAPI()

class Detail(Schema):
    detail: str

class ShiftOut(Schema):
    id: int
    
    rol: int
    nick: str

    checkin: datetime
    checkout: Optional[datetime]

class PrimoInfo(Schema):
    rol: int
    mail: str

    name: str
    nick: str
    
    schedule: str
    # Si tengo algún turno corriendo
    running: Optional[ShiftOut]

class UpcomingShift(Schema):
    isactive: bool
    shift: str
    checkin: datetime
    checkout: datetime

class Now(Schema):
    weekday: int
    time: str
    datetime: datetime

    # Actual o siguiente turno (Si es que ahora mismo no hay un turno activo)
    ushift: UpcomingShift
    pair: List[PrimoInfo]

class ShiftIn(Schema):
    rol: int

class ShiftUpdate(Schema):
    id: int

@api.get("/now", response=Now)
def get_now_time(_):
    now = utils.now()
    
    ushift = utils.upcomingShift()
    pair = []
    for primo in Primo.objects.all():
        schedule = utils.parseSchedule(primo.schedule)
        if ushift in schedule:
            pair.append(primo)
        
    # Dejo toterancia al principio para que puedas empezar el turno antes,
    # pero no al final porque podrías iniciar un turno cuando el bloque ya terminó
    ushift["isactive"] = (ushift["checkin"]  - parameters.tolerance) < utils.now() < ushift["checkout"]

    return {
        "weekday": now.weekday(),
        "time": f"{now.hour:02d}:{now.minute:02d}",
        "datetime": now,
        
        "ushift": ushift,
        "pair": pair
    }

@api.get("/primos/{str:mail}", response=PrimoInfo)
def get_primo(_, mail: str):
    primo = get_object_or_404(Primo, mail=mail)
    firstHour = utils.now().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rshift = Shift.objects.get(checkin__gt=firstHour, primo=primo, checkout__isnull=True)
        running = {
            "id": rshift.id,

            "rol": primo.rol,
            "nick": primo.nick,

            "checkin": rshift.checkin,
            "checkout": rshift.checkout
        }
    except Shift.DoesNotExist:
        running = None

    ushift = utils.parseSchedule(primo.schedule)[0]

    return {
        "rol": primo.rol,
        "mail": primo.mail,

        "name": primo.name,
        "nick": primo.nick,
        
        "schedule": primo.schedule,
        "running": running,
    }

@api.post("/primos", response={200: PrimoInfo, 400: Detail})
def push_a_primo(_, payload: PrimoInfo):
    try:
        if not utils.verifyRegex(payload.schedule):
            return 400, {"detail": "Invalid schedule"}
        primo = Primo.objects.create(**payload.dict())
    except IntegrityError as e:
        return 400, {"detail": "Duplicated key"}

    return 200, primo

@api.get("/shifts", response=List[ShiftOut])
def get_shifts(_):
    return [{
        "id": shift.id,
        
        "rol": shift.primo.rol,
        "nick": shift.primo.nick,
        
        "checkin": shift.checkin,
        "checkout": shift.checkout,
    } for shift in Shift.objects.all()]

@api.post("/shifts", response={200: ShiftOut, 403: Detail})
def push_a_shift(_, payload: ShiftIn):
    now = utils.now()
    primo = get_object_or_404(Primo, rol=payload.rol)
    shifts = utils.parseSchedule(primo.schedule)
    
    for shift in shifts:
        if (shift["checkin"] - parameters.tolerance) < now < (shift["checkout"] + parameters.tolerance):
            break
    else:
        return 403, {"detail": "You're not on your shift"}
    
    shift = Shift.objects.create(**{"primo": primo, "checkin": now})
    return 200, {
        "id": shift.id,

        "rol": payload.rol,
        "nick": shift.primo.nick,
        
        "checkin": shift.checkin,
    }

@api.post("/DEBUGshifts")
def push_a_shift_debug(_, payload: ShiftOut):
    primo = get_object_or_404(Primo, rol=payload.rol)
    shift = Shift.objects.create(**{
        "primo": primo,
        "checkin": payload.checkin,
        "checkout": payload.checkout
    })
    return 200, {
        "id": shift.id,
        
        "rol": payload.rol,
        
        "checkin": shift.checkin,
    }

@api.get("/shifts/week", response=List[List[ShiftOut]])
def get_week_shifts(_):
    now = utils.now()
    
    week = [[], [], [], [], []]
    for shift in Shift.objects.filter(checkin__gt=utils.firstWeekday()).order_by('checkin'):
        week[shift.checkin.weekday()].append({
            "id": shift.id,
            
            "rol": shift.primo.rol,
            "nick": shift.primo.nick,
            
            "checkin": shift.checkin,
            "checkout": shift.checkout,
        })

    # Esta parte del código se encarga de fusionar turnos consecutivos
    onemin = timedelta(minutes=1)
    for day in week:
        thisshift = 0
        while thisshift < len(day):
            nextshift = thisshift + 1
            while nextshift < len(day):
                if (day[thisshift]["checkout"] == None) or (day[nextshift]["checkin"] - day[thisshift]["checkout"]) > onemin:
                    # Ya que los turnos están ordenados se que esta condición se va a cumplir para todos los siguientes turnos
                    break
                elif day[thisshift]["rol"] == day[nextshift]["rol"]:
                    # Fusiono dos turnos si la diferencia entre que finalizó uno y empezó otro es de menos de 1 minuto
                    day[thisshift]["checkout"] = day.pop(nextshift)["checkout"]    
                nextshift += 1
            thisshift += 1

    return week

@api.get("/shifts/{int:rol}", response=List[ShiftOut])
def get_shifts_by_rol(_, rol: int):
    shifts = get_list_or_404(Shift, primo=rol)
    return [{
        "id": shift.id,
        
        "rol": rol,
        "nick": shift.primo.nick,
        
        "checkin": shift.checkin,
        "checkout": shift.checkout,
    } for shift in shifts]

@api.put("/shifts", response={200: ShiftOut, 403: Detail})
def update_a_shift(_, payload: ShiftUpdate):
    now = utils.now()
    shift = get_object_or_404(Shift, id=payload.id)
    if shift.checkin.date() != now.date():
        return 403, {"detail": "The check-in day is already over"}
    
    shift.checkout = now
    shift.save()
    return 200, {
        "id": shift.id,
        
        "rol": shift.primo.rol,
        "nick": shift.primo.nick,
        
        "checkin": shift.checkin,
        "checkout": shift.checkout
    }

from datetime import datetime, timedelta
from re import findall, fullmatch
from tracks import parameters

days = 'lmxjv'

# Esta función es importante para el debug, ya que nos
# permite cambiar fácilmente la hora en toda la app
def now():
    return datetime.now()#.replace(day=4, hour=15, minute=51, second=0, microsecond=0)

def firstWeekday():
    _now = now()
    return _now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days = _now.weekday())

def getRegex():
    lastShift = len(parameters.shifts) - 1
    return f'([{days}](?:[0-{lastShift}],)*[0-{lastShift}])'

def verifyRegex(schedule: str) -> bool:
    return fullmatch(f'{getRegex()}+', schedule) != None

def parseSchedule(schedule: str):
    _now = now()
    nextWeek = timedelta(days=7)
    shifts = []
    
    for daily in findall(getRegex(), schedule):
        for i in daily[1:].split(','):
            shift = parameters.shifts[int(i)]
            checkout = firstWeekday().replace(hour=shift[2][0], minute=shift[2][1]) + timedelta(days.index(daily[0]))
            # Si el turno de esta semana ya terminó, entonces lo tiro para la próxima semana
            if checkout < _now:
                checkout += nextWeek
            checkin = checkout.replace(hour=shift[1][0], minute=shift[1][1])
            shifts.append({
                "block": shift[0],
                "checkin": checkin,
                "checkout": checkout
            })
    
    shifts.sort(key=lambda s: s["checkin"])
    return shifts

def aproximateToBlock(date: datetime, strictmode = True):
    firstHour = date.replace(hour=0, minute=0, second=0, microsecond=0)
    if (weekday := firstHour.weekday()) > 4:
        if strictmode:
            raise Exception(f'<date> ({date}) is not a weekday, so is not close enough to any block')
        firstHour += timedelta(days=7 - weekday)
    
    for shift in parameters.shifts:
        checkin = firstHour.replace(hour=shift[1][0], minute=shift[1][1])
        checkout = firstHour.replace(hour=shift[2][0], minute=shift[2][1])

        if strictmode:
            nextblockCondition = checkin > date >= checkin - parameters.tolerance
        else:
            nextblockCondition = checkin > date

        if (checkin > date) and (not nextblockCondition):
            print(f'{checkin} > {date} >= {checkin - parameters.tolerance}', nextblockCondition)
        if (checkin <= date <= checkout) or nextblockCondition:
            return {
                "block": shift[0],
                "checkin": checkin,
                "checkout": checkout
            }
    if strictmode:
        raise Exception(f'<date> ({date}) is not close enough to any block')
    
    nextWeek = timedelta(days=7)
    shift = parameters.shifts[0]
    return {
        "block": shift[0],
        "checkin": checkin + nextWeek,
        "checkout": checkout  + nextWeek
    }

def upcomingShift():
    return aproximateToBlock(now(), False)
from datetime import time, timedelta
from warnings import warn

days = 'lmxjv'

class BlockMeta(type):    
    _blocks = []

    def __len__(self):
        return len(self._blocks)

    def __iter__(self):
        return iter(self._blocks)

    def __getitem__(self, key):
        return self._blocks[key]

class Block(metaclass=BlockMeta):
    def __init__(self, block: str, start: time, end: time) -> None:
        self.block = block
        self.start = start
        self.end = end
        Block._blocks.append(self)

Block( "1-2",  time( 8, 15), time( 9, 25))
Block( "3-4",  time( 9, 35), time(10, 45))
Block( "5-6",  time(10, 55), time(12,  5))
Block( "7-8",  time(12, 15), time(13, 25))
Block( "9-10", time(14, 30), time(15, 40))
Block("11-12", time(15, 50), time(17,  0))
Block("13-14", time(17, 10), time(18, 20))
Block("15-16", time(18, 30), time(19, 40))

# TOLERANCIAS
# beforeStartTolerance: Cuanto tiempo antes de que comienze el turno se puede
#  iniciar el mismo. Establecer el valor de este parámetro por sobre el tiempo
#  de descanso entre bloques podría ocasionar bugs (no comprobado), puesto que
#   abre la posibilidad a comenzar un turno antes de que acabe el anterior.
beforeStartTolerance = timedelta(minutes=10)
# afterStartTolerance: Cuanto tiempo después de que comenzó el turno se puede
#  iniciar el mismo. Una buena idea es agregar 59 segundos extras, de esta forma
#  se concede el último minuto entero para iniciar el turno. Por ejemplo, si la
#  tolerancia es de 10 minutos, esta medida permite a los primos iniciar su turno
#  entre el minuto 0 y el minuto 10 ([0, 10]), de modo que el turno se cerrará
#  apenas comience el minuto 11. De no agregar estos 59 segundos el turno se
#  cerraría apenas comiencie el minuto 10 ([0, 10[).
afterStartTolerance = beforeStartTolerance + timedelta(seconds=59)
# afterEndTolerance: Cuanto tiempo se concede al primo para cerrar su turno,
#  una vez terminada la hora, sin que se considere sospechoso.
afterEndTolerance = beforeStartTolerance

# Esta función se asegura de que los parámetros tengan sentido
def checks():
    badBlocks = []
    for i in range(len(Block)):
        if not (Block[i].start < Block[i].end):
            badBlocks.append(Exception(f'El bloque {Block[i].block} ({Block[i].start.isoformat("minutes")} - {Block[i].end.isoformat("minutes")}) termina antes de comenzar'))
    for i in range(len(Block) - 1):
        if not (Block[i].end < Block[i + 1].start):
            badBlocks.append(Exception(f'El bloque {Block[i + 1].block} comienza antes de que termine el bloque anterior'))
    if badBlocks:
        raise Exception(badBlocks)
    
    minDuration = timedelta(hours=Block[0].end.hour, minutes=Block[0].end.minute) - timedelta(hours=Block[0].start.hour, minutes=Block[0].start.minute)
    for shift in Block[1:]:
        duration = timedelta(hours=shift.end.hour - shift.start.hour, minutes=shift.end.minute - shift.start.minute)
        if duration < minDuration:
            minDuration = duration
    if afterStartTolerance >= minDuration:
        raise Exception(f'La tolerancia <afterStartTolerance> ({str(afterStartTolerance)}) es mayor a la duración del bloque más corto ({minDuration})')

    minRest = timedelta(hours=Block[1].start.hour, minutes=Block[1].start.minute) - timedelta(hours=Block[0].end.hour, minutes=Block[0].end.minute)
    for i in range(len(Block) - 2):
        start, end = Block[i + 1].end, Block[i + 2].start
        if (rest := timedelta(hours=end.hour - start.hour, minutes=end.minute - start.minute)) < minRest:
            minRest = rest
    if beforeStartTolerance > minRest:
        warn(f'El tiempo de tolerancia <beforeStartTolerance> ({str(beforeStartTolerance)}) es mayor al descanso más pequeño ({minRest})')
    if afterEndTolerance > minRest:
        warn(f'El tiempo de tolerancia <afterEndTolerance> ({str(afterEndTolerance)}) es mayor al descanso más pequeño ({minRest})')
checks()

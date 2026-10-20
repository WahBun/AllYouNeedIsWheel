"""Generate Wheel's original browser alert cues (no third-party recordings)."""
import math
from pathlib import Path
import struct
import wave

RATE = 22050
OUTPUT = Path(__file__).resolve().parents[1] / 'frontend/static/audio'


def render(name, notes, duration):
    samples = [0.0] * int(RATE * duration)
    for start, length, frequency, voice in notes:
        for index in range(int(length * RATE)):
            t = index / RATE
            attack = min(1, t / .008)
            release = min(1, (length - t) / .025)
            if voice == 'bell':
                value = sum(gain * math.sin(2 * math.pi * frequency * ratio * t) * math.exp(-decay * t)
                            for ratio, gain, decay in [(1, .65, 3), (2.76, .24, 5), (5.4, .08, 9)])
            elif voice == 'chime':
                value = (math.sin(2 * math.pi * frequency * t) +
                         .18 * math.sin(4 * math.pi * frequency * t)) * math.exp(-4 * t)
            elif voice == 'chirp':
                value = math.sin(2 * math.pi * (frequency * t + 1100 * t * t))
            else:
                value = math.sin(2 * math.pi * frequency * t)
                if voice == 'alarm':
                    value += .25 * math.sin(6 * math.pi * frequency * t)
            target = int(start * RATE) + index
            if target < len(samples):
                samples[target] += attack * release * value
    peak = max(abs(v) for v in samples)
    # Leave headroom; every cue ends in silence and has click-free edges.
    pcm = b''.join(struct.pack('<h', round(v / peak * 18000)) for v in samples)
    with wave.open(str(OUTPUT / f'alert-{name}.wav'), 'wb') as output:
        output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        output.writeframes(pcm)


if __name__ == '__main__':
    render('alarm-clock', [(t, .11, 880, 'alarm') for t in (0, .16, .32, .48, .85, 1.01, 1.17, 1.33)], 1.6)
    render('beep-beep', [(0, .18, 660, 'sine'), (.3, .18, 660, 'sine')], .7)
    render('three-notes', [(0, .7, 523.25, 'chime'), (.22, .7, 659.25, 'chime'), (.44, .8, 783.99, 'chime')], 1.4)
    render('soft-chime', [(0, 1.1, 659.25, 'chime'), (.15, 1.1, 987.77, 'chime')], 1.5)
    render('hand-bell', [(0, 1.3, 1046.5, 'bell'), (.3, 1.1, 1046.5, 'bell')], 1.6)
    render('chirpy', [(0, .16, 1300, 'chirp'), (.25, .16, 1600, 'chirp'), (.5, .2, 1300, 'chirp')], .9)

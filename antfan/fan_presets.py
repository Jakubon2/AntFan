"""Předvolby Xiaomi ventilátorů (MIoT siid/piid).

Vygenerováno ze specifikací na https://miot-spec.org (služba fan: on + fan-level
nebo speed-level, alarm = pípání, indicator-light/brightness = podsvícení).
Formát: model: (power, level, hodnoty, pípání, podsvícení)
  hodnoty = tuple přípustných hodnot stupně, nebo ("range", od, do) pro rychlost v %.
"""

PRESETS = {
    "dmaker.fan.01": ((2, 1), (2, 2), (1, 2, 3, 4), None, None),
    "dmaker.fan.02": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.1c": ((2, 1), (2, 2), (1, 2, 3), (2, 11), (2, 12)),
    "dmaker.fan.1e": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p10": ((2, 1), (2, 2), (1, 2, 3, 4), (4, 1), (5, 1)),
    "dmaker.fan.p11": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p15": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p18": ((2, 1), (2, 2), (1, 2, 3, 4), (2, 8), (2, 7)),
    "dmaker.fan.p220": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p221": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p23": ((5, 1), (5, 2), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (7, 1), (9, 1)),
    "dmaker.fan.p28": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p30": ((2, 1), (2, 2), (1, 2, 3, 4), (2, 8), (2, 7)),
    "dmaker.fan.p33": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p39": ((2, 1), (2, 2), (1, 2, 3, 4), (2, 7), (2, 9)),
    "dmaker.fan.p42": ((2, 1), (2, 2), (1, 2, 3, 4), (2, 8), (2, 7)),
    "dmaker.fan.p44": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p45": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p5c": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), (4, 1)),
    "dmaker.fan.p8": ((2, 1), (2, 2), (1, 2, 3), (4, 1), (5, 1)),
    "dmaker.fan.p9": ((2, 1), (2, 2), (1, 2, 3, 4), (4, 1), (5, 1)),
    "dmaker.fan.tn1": ((2, 1), (2, 2), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10), None, None),
    "dreame.fan.l2146": ((2, 1), (2, 2), ('range', 1, 100), (12, 1), None),
    "dreame.fan.p2018": ((2, 1), (2, 2), ('range', 1, 100), (12, 1), None),
    "leshow.fan.ss310": ((2, 1), (2, 2), (1, 25, 50, 75, 100), (3, 1), None),
    "leshow.fan.ss320": ((2, 1), (2, 2), (1, 25, 50, 75, 100), (3, 1), None),
    "leshow.fan.ss4": ((2, 1), (2, 2), ('range', 1, 100), (3, 1), None),
    "viomi.fan.v13": ((2, 1), (2, 2), ('range', 1, 99), (6, 1), None),
    "viomi.fan.v5": ((2, 1), (2, 2), (1, 2, 3, 4), None, None),
    "viomi.fan.v6": ((2, 1), (2, 2), ('range', 1, 99), (6, 1), None),
    "viomi.fan.v7": ((2, 1), (2, 2), ('range', 1, 100), (6, 1), None),
    "viomi.fan.v8": ((2, 1), (2, 2), ('range', 1, 100), (6, 1), None),
    "xiaomi.fan.2lite": ((2, 1), (2, 4), (0, 1, 2), (7, 1), (5, 1)),
    "xiaomi.fan.p23": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p23w": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p30": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p43": ((2, 1), (2, 6), ('range', 1, 100), (5, 1), (4, 1)),
    "xiaomi.fan.p45": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p51": ((2, 1), (2, 6), ('range', 1, 100), (6, 1), (5, 1)),
    "xiaomi.fan.p69": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p70": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p76": ((2, 1), (2, 5), ('range', 1, 100), (7, 1), (5, 1)),
    "xiaomi.fan.p85": ((2, 1), (2, 4), (1, 2, 3, 4), (7, 1), (5, 1)),
    "xiaomi.fan.p90": ((2, 1), (2, 4), ('range', 1, 100), (7, 1), None),
    "zhimi.fan.fa1": ((2, 1), (2, 2), (1, 2, 3, 4, 5), (2, 11), None),
    "zhimi.fan.fa2": ((2, 1), (2, 2), (1, 2, 3, 4), (2, 11), None),
    "zhimi.fan.fb1": ((2, 1), (2, 2), (1, 2, 3, 4, 5), (2, 11), None),
    "zhimi.fan.za5": ((2, 1), (2, 2), (1, 2, 3, 4), (5, 1), None),
}

# starší modely se starým protokolem miIO (příkazy set_power / s_power…)
LEGACY = {
    "zhimi.fan.v2": "zhimi",
    "zhimi.fan.v3": "zhimi",
    "zhimi.fan.sa1": "zhimi",
    "zhimi.fan.za1": "zhimi",
    "zhimi.fan.za3": "zhimi",
    "zhimi.fan.za4": "zhimi",
    "dmaker.fan.p5": "p5"
}

"""Minimální generátor QR kódu (bajtový režim, korekce M, verze 1–10).

Stačí na adresu pro mobil (do ~200 znaků). Bez externích knihoven.
Postup podle ISO/IEC 18004, struktura převzatá z qrcodegen (Nayuki, MIT).
"""
from __future__ import annotations
from .i18n import _

# korekce M: verze -> (EC kódových slov na blok, [(počet bloků, datových slov v bloku), ...])
_BLOCKS_M = {
    1: (10, [(1, 16)]),
    2: (16, [(1, 28)]),
    3: (26, [(1, 44)]),
    4: (18, [(2, 32)]),
    5: (24, [(2, 43)]),
    6: (16, [(4, 27)]),
    7: (18, [(4, 31)]),
    8: (22, [(2, 38), (2, 39)]),
    9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
_ECL_M_BITS = 0  # formátové bity pro úroveň M


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    res = [0] * (degree - 1) + [1]
    root = 1
    for _u in range(degree):
        for j in range(degree):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _gf_mul(root, 0x02)
    return res


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    res = [0] * len(divisor)
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i, coef in enumerate(divisor):
            res[i] ^= _gf_mul(coef, factor)
    return res


def _data_capacity(ver: int) -> int:
    return sum(n * k for n, k in _BLOCKS_M[ver][1])


def encode(text: str, mask: int | None = None) -> list[list[bool]]:
    """Vrátí matici modulů (True = tmavý), bez okraje."""
    data = text.encode("utf-8")
    for ver in range(1, 11):
        cnt_bits = 8 if ver < 10 else 16
        if 4 + cnt_bits + 8 * len(data) <= _data_capacity(ver) * 8:
            break
    else:
        raise ValueError(_("text je na QR kód příliš dlouhý"))

    # --- datové bity
    bits: list[int] = []

    def put(val, n):
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))

    put(0b0100, 4)
    put(len(data), cnt_bits)
    for b in data:
        put(b, 8)
    cap = _data_capacity(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, (-len(bits)) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < cap // 8:
        words.append(pad)
        pad ^= 0xEC ^ 0x11

    # --- bloky, Reed-Solomon a prokládání
    ec_len, groups = _BLOCKS_M[ver]
    div = _rs_divisor(ec_len)
    blocks, pos = [], 0
    for n, k in groups:
        for _u in range(n):
            blk = words[pos:pos + k]
            pos += k
            blocks.append((blk, _rs_remainder(blk, div)))
    final: list[int] = []
    for i in range(max(len(b[0]) for b in blocks)):
        final.extend(b[0][i] for b in blocks if i < len(b[0]))
    for i in range(ec_len):
        final.extend(b[1][i] for b in blocks)

    # --- matice
    size = ver * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fun = [[False] * size for _ in range(size)]

    def setf(x, y, dark):
        mod[y][x] = dark
        fun[y][x] = True

    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    setf(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _ALIGN[ver]
    for i, ax in enumerate(al):
        for j, ay in enumerate(al):
            if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def format_bits(m):
        d = (_ECL_M_BITS << 3) | m
        rem = d
        for _u in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        b = ((d << 10) | rem) ^ 0x5412
        for i in range(6):
            setf(8, i, (b >> i) & 1 == 1)
        setf(8, 7, (b >> 6) & 1 == 1)
        setf(8, 8, (b >> 7) & 1 == 1)
        setf(7, 8, (b >> 8) & 1 == 1)
        for i in range(9, 15):
            setf(14 - i, 8, (b >> i) & 1 == 1)
        for i in range(8):
            setf(size - 1 - i, 8, (b >> i) & 1 == 1)
        for i in range(8, 15):
            setf(8, size - 15 + i, (b >> i) & 1 == 1)
        setf(8, size - 8, True)

    format_bits(0)  # rezervace
    if ver >= 7:
        rem = ver
        for _u in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vb = (ver << 12) | rem
        for i in range(18):
            bit = (vb >> i) & 1 == 1
            a, b = size - 11 + i % 3, i // 3
            setf(a, b, bit)
            setf(b, a, bit)

    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                up = ((right + 1) & 2) == 0
                y = size - 1 - vert if up else vert
                if not fun[y][x] and i < len(final) * 8:
                    mod[y][x] = (final[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2

    masks = [
        lambda x, y: (x + y) % 2 == 0,
        lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0,
        lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0,
        lambda x, y: x * y % 2 + x * y % 3 == 0,
        lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    ]

    def apply(m):
        f = masks[m]
        for y in range(size):
            for x in range(size):
                if not fun[y][x] and f(x, y):
                    mod[y][x] = not mod[y][x]

    if mask is None:
        best, mask = None, 0
        for m in range(8):
            apply(m)
            format_bits(m)
            p = _penalty(mod)
            if best is None or p < best:
                best, mask = p, m
            apply(m)  # XOR zpět
    apply(mask)
    format_bits(mask)
    return mod


def _penalty(mod: list[list[bool]]) -> int:
    size = len(mod)
    score = 0
    lines = mod + [list(c) for c in zip(*mod)]
    pat1 = [True, False, True, True, True, False, True, False, False, False, False]
    pat2 = pat1[::-1]
    for ln in lines:
        run, prev = 0, None
        for v in ln:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
        for k in range(size - 10):
            seg = ln[k:k + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    for y in range(size - 1):
        for x in range(size - 1):
            v = mod[y][x]
            if v == mod[y][x + 1] == mod[y + 1][x] == mod[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, mod))
    total = size * size
    score += (abs(dark * 20 - total * 10) + total - 1) // total * 10 - 10 if dark * 20 != total * 10 else 0
    return score

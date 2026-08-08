#!/usr/bin/env python3
"""Celebi colour quantization — Wu's cut, then weighted k-means.

A port of material-color-utilities (Google, Apache-2.0): `quantize/
quantizer_wu.ts`, `quantizer_wsmeans.ts` and `quantizer_celebi.ts`. It is the
quantizer Android runs on a wallpaper to build a Material You theme, so using
it here means a festival's poster is read the way the design system's own
reference implementation reads an image.

Two stages, which is the whole idea of Celebi's 2011 paper (*Improving the
Performance of K-Means for Color Quantization*, arXiv:1101.0395): k-means is
sensitive to where its centroids start, and random starts give a different
answer every run and a worse one on average. So Wu's algorithm runs first — it
cuts the RGB cube along whichever axis removes the most variance, which is
deterministic and cheap — and its output seeds k-means. What k-means then does
is fix Wu's blind spot: a cube cut is axis-aligned, and colours do not group
into boxes.

The k-means half works in CIELAB rather than in RGB, as the reference does:
distance in RGB is not distance to the eye, and clusters formed in it merge
colours nobody would call the same. Hue and chroma are read in CAM16 afterwards
by `hct.py`, which is where they matter.

Deterministic on purpose. The reference seeds its initial assignment with
`Math.random()`; a build that reads a colour off a picture has to give the same
answer every time it runs, or a rebuild quietly re-themes the site. The
randomness is kept — it is part of the algorithm — but drawn from a generator
seeded with a constant.
"""
from __future__ import annotations

import random

# ── Wu ─────────────────────────────────────────────────
# The cube is quantized to 32 levels a side, plus one because the moment tables
# are cumulative and index 0 holds the running zero.
INDEX_BITS = 5
SIDE_LENGTH = 33
TOTAL_SIZE = SIDE_LENGTH ** 3
RED, GREEN, BLUE = 0, 1, 2


def _index(r: int, g: int, b: int) -> int:
    return (r << (INDEX_BITS * 2)) + (r << (INDEX_BITS + 1)) + r + \
        (g << INDEX_BITS) + g + b


class _Box:
    __slots__ = ("r0", "r1", "g0", "g1", "b0", "b1", "vol")

    def __init__(self):
        self.r0 = self.r1 = self.g0 = self.g1 = self.b0 = self.b1 = 0
        self.vol = 0


class _Wu:
    def __init__(self):
        z = [0] * TOTAL_SIZE
        self.weights = list(z)
        self.moments_r = list(z)
        self.moments_g = list(z)
        self.moments_b = list(z)
        self.moments = [0.0] * TOTAL_SIZE
        self.cubes: list[_Box] = []

    def quantize(self, counts: dict[int, int], max_colors: int) -> list[int]:
        self._histogram(counts)
        self._moments()
        n = self._boxes(max_colors)
        return self._result(n)

    def _histogram(self, counts: dict[int, int]) -> None:
        shift = 8 - INDEX_BITS
        for argb, count in counts.items():
            r = (argb >> 16) & 0xff
            g = (argb >> 8) & 0xff
            b = argb & 0xff
            i = _index((r >> shift) + 1, (g >> shift) + 1, (b >> shift) + 1)
            self.weights[i] += count
            self.moments_r[i] += count * r
            self.moments_g[i] += count * g
            self.moments_b[i] += count * b
            self.moments[i] += count * (r * r + g * g + b * b)

    def _moments(self) -> None:
        """Turn the histogram into summed-area tables, so the weight of any
        box is four lookups rather than a walk."""
        for r in range(1, SIDE_LENGTH):
            area = [0] * SIDE_LENGTH
            area_r = [0] * SIDE_LENGTH
            area_g = [0] * SIDE_LENGTH
            area_b = [0] * SIDE_LENGTH
            area2 = [0.0] * SIDE_LENGTH
            for g in range(1, SIDE_LENGTH):
                line = line_r = line_g = line_b = 0
                line2 = 0.0
                for b in range(1, SIDE_LENGTH):
                    i = _index(r, g, b)
                    line += self.weights[i]
                    line_r += self.moments_r[i]
                    line_g += self.moments_g[i]
                    line_b += self.moments_b[i]
                    line2 += self.moments[i]
                    area[b] += line
                    area_r[b] += line_r
                    area_g[b] += line_g
                    area_b[b] += line_b
                    area2[b] += line2
                    prev = _index(r - 1, g, b)
                    self.weights[i] = self.weights[prev] + area[b]
                    self.moments_r[i] = self.moments_r[prev] + area_r[b]
                    self.moments_g[i] = self.moments_g[prev] + area_g[b]
                    self.moments_b[i] = self.moments_b[prev] + area_b[b]
                    self.moments[i] = self.moments[prev] + area2[b]

    def _boxes(self, max_colors: int) -> int:
        self.cubes = [_Box() for _ in range(max_colors)]
        variance = [0.0] * max_colors
        self.cubes[0].r1 = self.cubes[0].g1 = self.cubes[0].b1 = SIDE_LENGTH - 1
        generated = max_colors
        nxt = 0
        i = 1
        while i < max_colors:
            if self._cut(self.cubes[nxt], self.cubes[i]):
                variance[nxt] = self._variance(self.cubes[nxt]) \
                    if self.cubes[nxt].vol > 1 else 0.0
                variance[i] = self._variance(self.cubes[i]) \
                    if self.cubes[i].vol > 1 else 0.0
            else:
                variance[nxt] = 0.0
                i -= 1
            nxt = 0
            temp = variance[0]
            for j in range(1, i + 1):
                if variance[j] > temp:
                    temp = variance[j]
                    nxt = j
            if temp <= 0.0:
                generated = i + 1
                break
            i += 1
        return generated

    def _result(self, count: int) -> list[int]:
        out = []
        for i in range(count):
            cube = self.cubes[i]
            w = self._volume(cube, self.weights)
            if w > 0:
                r = round(self._volume(cube, self.moments_r) / w)
                g = round(self._volume(cube, self.moments_g) / w)
                b = round(self._volume(cube, self.moments_b) / w)
                out.append((0xff << 24) | ((r & 0xff) << 16)
                           | ((g & 0xff) << 8) | (b & 0xff))
        return out

    def _variance(self, cube: _Box) -> float:
        dr = self._volume(cube, self.moments_r)
        dg = self._volume(cube, self.moments_g)
        db = self._volume(cube, self.moments_b)
        m = self.moments
        xx = (m[_index(cube.r1, cube.g1, cube.b1)]
              - m[_index(cube.r1, cube.g1, cube.b0)]
              - m[_index(cube.r1, cube.g0, cube.b1)]
              + m[_index(cube.r1, cube.g0, cube.b0)]
              - m[_index(cube.r0, cube.g1, cube.b1)]
              + m[_index(cube.r0, cube.g1, cube.b0)]
              + m[_index(cube.r0, cube.g0, cube.b1)]
              - m[_index(cube.r0, cube.g0, cube.b0)])
        return xx - (dr * dr + dg * dg + db * db) / self._volume(cube, self.weights)

    def _cut(self, one: _Box, two: _Box) -> bool:
        whole_r = self._volume(one, self.moments_r)
        whole_g = self._volume(one, self.moments_g)
        whole_b = self._volume(one, self.moments_b)
        whole_w = self._volume(one, self.weights)
        mr = self._maximize(one, RED, one.r0 + 1, one.r1,
                            whole_r, whole_g, whole_b, whole_w)
        mg = self._maximize(one, GREEN, one.g0 + 1, one.g1,
                            whole_r, whole_g, whole_b, whole_w)
        mb = self._maximize(one, BLUE, one.b0 + 1, one.b1,
                            whole_r, whole_g, whole_b, whole_w)
        if mr[1] >= mg[1] and mr[1] >= mb[1]:
            if mr[0] < 0:
                return False
            direction = RED
        elif mg[1] >= mr[1] and mg[1] >= mb[1]:
            direction = GREEN
        else:
            direction = BLUE
        two.r1, two.g1, two.b1 = one.r1, one.g1, one.b1
        if direction == RED:
            one.r1 = mr[0]
            two.r0, two.g0, two.b0 = one.r1, one.g0, one.b0
        elif direction == GREEN:
            one.g1 = mg[0]
            two.r0, two.g0, two.b0 = one.r0, one.g1, one.b0
        else:
            one.b1 = mb[0]
            two.r0, two.g0, two.b0 = one.r0, one.g0, one.b1
        one.vol = (one.r1 - one.r0) * (one.g1 - one.g0) * (one.b1 - one.b0)
        two.vol = (two.r1 - two.r0) * (two.g1 - two.g0) * (two.b1 - two.b0)
        return True

    def _maximize(self, cube, direction, first, last,
                  whole_r, whole_g, whole_b, whole_w) -> tuple[int, float]:
        br = self._bottom(cube, direction, self.moments_r)
        bg = self._bottom(cube, direction, self.moments_g)
        bb = self._bottom(cube, direction, self.moments_b)
        bw = self._bottom(cube, direction, self.weights)
        best, cut = 0.0, -1
        for i in range(first, last):
            hr = br + self._top(cube, direction, i, self.moments_r)
            hg = bg + self._top(cube, direction, i, self.moments_g)
            hb = bb + self._top(cube, direction, i, self.moments_b)
            hw = bw + self._top(cube, direction, i, self.weights)
            if hw == 0:
                continue
            temp = (hr * hr + hg * hg + hb * hb) / hw
            hr, hg, hb, hw = whole_r - hr, whole_g - hg, whole_b - hb, whole_w - hw
            if hw == 0:
                continue
            temp += (hr * hr + hg * hg + hb * hb) / hw
            if temp > best:
                best, cut = temp, i
        return cut, best

    def _volume(self, c: _Box, m) -> float:
        return (m[_index(c.r1, c.g1, c.b1)] - m[_index(c.r1, c.g1, c.b0)]
                - m[_index(c.r1, c.g0, c.b1)] + m[_index(c.r1, c.g0, c.b0)]
                - m[_index(c.r0, c.g1, c.b1)] + m[_index(c.r0, c.g1, c.b0)]
                + m[_index(c.r0, c.g0, c.b1)] - m[_index(c.r0, c.g0, c.b0)])

    def _bottom(self, c: _Box, direction: int, m) -> float:
        if direction == RED:
            return (-m[_index(c.r0, c.g1, c.b1)] + m[_index(c.r0, c.g1, c.b0)]
                    + m[_index(c.r0, c.g0, c.b1)] - m[_index(c.r0, c.g0, c.b0)])
        if direction == GREEN:
            return (-m[_index(c.r1, c.g0, c.b1)] + m[_index(c.r1, c.g0, c.b0)]
                    + m[_index(c.r0, c.g0, c.b1)] - m[_index(c.r0, c.g0, c.b0)])
        return (-m[_index(c.r1, c.g1, c.b0)] + m[_index(c.r1, c.g0, c.b0)]
                + m[_index(c.r0, c.g1, c.b0)] - m[_index(c.r0, c.g0, c.b0)])

    def _top(self, c: _Box, direction: int, pos: int, m) -> float:
        if direction == RED:
            return (m[_index(pos, c.g1, c.b1)] - m[_index(pos, c.g1, c.b0)]
                    - m[_index(pos, c.g0, c.b1)] + m[_index(pos, c.g0, c.b0)])
        if direction == GREEN:
            return (m[_index(c.r1, pos, c.b1)] - m[_index(c.r1, pos, c.b0)]
                    - m[_index(c.r0, pos, c.b1)] + m[_index(c.r0, pos, c.b0)])
        return (m[_index(c.r1, c.g1, pos)] - m[_index(c.r1, c.g0, pos)]
                - m[_index(c.r0, c.g1, pos)] + m[_index(c.r0, c.g0, pos)])


# ── weighted square means ──────────────────────────────
MAX_ITERATIONS = 10
MIN_MOVEMENT_DISTANCE = 3.0

_E = 216 / 24389
_KAPPA = 24389 / 27
_WHITE = (95.047, 100.0, 108.883)


def _lab(argb: int) -> tuple[float, float, float]:
    def lin(v):
        n = v / 255.0
        return (n / 12.92) * 100.0 if n <= 0.040449936 else \
            ((n + 0.055) / 1.055) ** 2.4 * 100.0
    r = lin((argb >> 16) & 0xff)
    g = lin((argb >> 8) & 0xff)
    b = lin(argb & 0xff)
    x = (0.41233895 * r + 0.35762064 * g + 0.18051042 * b) / _WHITE[0]
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / _WHITE[1]
    z = (0.01932141 * r + 0.11916382 * g + 0.95034478 * b) / _WHITE[2]
    f = lambda t: t ** (1 / 3) if t > _E else (_KAPPA * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _argb_from_lab(L: float, a: float, b: float) -> int:
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    g_ = lambda t: t ** 3 if t ** 3 > _E else (116 * t - 16) / _KAPPA
    x, y, z = g_(fx) * _WHITE[0], g_(fy) * _WHITE[1], g_(fz) * _WHITE[2]
    rl = (3.2413774792388685 * x - 1.5376652402851851 * y - 0.49885366846268053 * z) / 100
    gl = (-0.9691452513005321 * x + 1.8758853451067872 * y + 0.04156585616912061 * z) / 100
    bl = (0.05562093689691305 * x - 0.20395524564742123 * y + 1.0571799111220335 * z) / 100
    def srgb(v):
        v = 12.92 * v if v <= 0.0031308 else 1.055 * max(v, 0.0) ** (1 / 2.4) - 0.055
        return max(0, min(255, round(v * 255)))
    return (0xff << 24) | (srgb(rl) << 16) | (srgb(gl) << 8) | srgb(bl)


def _dist2(p, q) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def _wsmeans(counts: dict[int, int], starts: list[int],
             cluster_count: int) -> dict[int, int]:
    rng = random.Random(0)
    pixels = list(counts.keys())
    points = [_lab(p) for p in pixels]
    weights = [counts[p] for p in pixels]
    n = len(points)

    clusters = [_lab(c) for c in starts][:cluster_count]
    for _ in range(cluster_count - len(clusters)):
        clusters.append((rng.random() * 100.0,
                         rng.random() * 201.0 - 100.0,
                         rng.random() * 201.0 - 100.0))
    k = len(clusters)
    if not k:
        return {}
    idx = [rng.randrange(k) for _ in range(n)]
    sums = [0] * k

    for iteration in range(MAX_ITERATIONS):
        # Distances between clusters, sorted — the optimisation the paper is
        # named for: if a rival cluster is more than twice as far away as the
        # one a point already belongs to, it cannot win, so it is never
        # measured. (Squared distances throughout, hence 4×.)
        near = []
        for i in range(k):
            row = sorted(((_dist2(clusters[i], clusters[j]), j)
                          for j in range(k)), key=lambda t: t[0])
            near.append(row)

        moved = 0
        for i in range(n):
            point = points[i]
            prev = idx[i]
            prev_d = _dist2(point, clusters[prev])
            best_d, best = prev_d, -1
            for d_cluster, j in near[prev]:
                if d_cluster >= 4 * prev_d:
                    break
                d = _dist2(point, clusters[j])
                if d < best_d:
                    best_d, best = d, j
            if best != -1 and abs(best_d ** .5 - prev_d ** .5) > MIN_MOVEMENT_DISTANCE:
                moved += 1
                idx[i] = best
        if moved == 0 and iteration != 0:
            break

        a_s = [0.0] * k
        b_s = [0.0] * k
        c_s = [0.0] * k
        sums = [0] * k
        for i in range(n):
            c = idx[i]
            w = weights[i]
            sums[c] += w
            a_s[c] += points[i][0] * w
            b_s[c] += points[i][1] * w
            c_s[c] += points[i][2] * w
        for i in range(k):
            if sums[i] == 0:
                clusters[i] = (0.0, 0.0, 0.0)
            else:
                clusters[i] = (a_s[i] / sums[i], b_s[i] / sums[i], c_s[i] / sums[i])

    out: dict[int, int] = {}
    for i in range(k):
        if sums[i] == 0:
            continue
        argb = _argb_from_lab(*clusters[i])
        out[argb] = out.get(argb, 0) + sums[i]
    return out


def celebi(counts: dict[int, int], max_colors: int = 128) -> dict[int, int]:
    """{argb: population} for an image, given {argb: count} of its pixels."""
    if not counts:
        return {}
    wu = _Wu().quantize(counts, max_colors)
    return _wsmeans(counts, wu, max_colors)


def counts_from_image(path, sample: int = 128) -> dict[int, int]:
    """Every pixel of the picture, tallied by colour.

    Downsampled first, and with NEAREST: averaging neighbouring pixels invents
    colours that are in no part of the picture — a red beside a cream becomes a
    pink that was never printed — and inventing colours is the one thing a
    colour reader must not do. Fully transparent pixels are skipped, as the
    reference does.
    """
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    im.thumbnail((sample, sample), Image.Resampling.NEAREST)
    counts: dict[int, int] = {}
    for r, g, b, a in im.getdata():
        if a < 255:
            continue
        argb = (0xff << 24) | (r << 16) | (g << 8) | b
        counts[argb] = counts.get(argb, 0) + 1
    return counts

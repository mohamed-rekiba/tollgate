"""Isometric scenes, in the same colors and type as the flat diagrams.

A scene is a ground of fine grid, objects standing on it, lanes between them
with dots that move, labels in monospace, and one ticket that travels a path.

    s = Scene("light", 1200, 700, origin=(600, 330), scale=0.7)
    s.room(0, 0, "ai")
    s.lane([(0, 60), (0, 200)], label="the change")
    svg = s.render("Title", "What it shows.")

Ground units: x runs down and to the right on the page, y runs down and to the
left, z runs up.
"""

import re
from itertools import pairwise
from xml.sax.saxutils import escape

from diagram import aws
from diagram.flow import MONO, THEMES
from diagram.icons import icon


def mix(a: str, b: str, t: float) -> str:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb, strict=True))


class Scene:
    def __init__(self, theme, width, height, origin, scale):
        self.c = THEMES[theme]
        self.theme = theme
        self.w, self.h = width, height
        self.ox, self.oy = origin
        self.s = scale
        self.back, self.out, self.front = [], [], []  # ground, objects, labels on top
        self.legs = []  # the ticket's path
        self.css = []
        self.ids = 0

    # Geometry -----------------------------------------------------------------
    def iso(self, x, y, z=0.0):
        return self.ox + (x - y) * 0.866 * self.s, self.oy + ((x + y) * 0.5 - z) * self.s

    @staticmethod
    def pts(points):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    def faces(self, kind):
        accent, tint = self.c["kinds"][kind]
        if self.theme == "light":
            return accent, tint, mix(tint, accent, 0.16), mix(tint, accent, 0.3)
        return accent, mix(tint, accent, 0.18), tint, mix(tint, "#000000", 0.35)

    # Shapes -------------------------------------------------------------------
    def prism(self, x0, y0, x1, y1, z0, z1, kind, into=None, glass=False):
        stroke, top, left, right = self.faces(kind)
        a, b = self.iso(x0, y1, z1), self.iso(x1, y1, z1)
        c, d = self.iso(x1, y0, z1), self.iso(x0, y0, z1)
        a0, b0, c0 = self.iso(x0, y1, z0), self.iso(x1, y1, z0), self.iso(x1, y0, z0)
        fill = ' fill-opacity="0.3"' if glass else ""
        dash = ' stroke-dasharray="3 4"' if glass else ""
        common = f'stroke="{stroke}" stroke-width="1.3" stroke-linejoin="round"{fill}{dash}'
        (self.out if into is None else into).extend([
            f'<polygon points="{self.pts([a, b, b0, a0])}" fill="{left}" {common}/>',
            f'<polygon points="{self.pts([b, c, c0, b0])}" fill="{right}" {common}/>',
            f'<polygon points="{self.pts([a, b, c, d])}" fill="{top}" {common}/>',
        ])

    def platform(self, x0, y0, x1, y1, kind="neutral", h=8):
        self.prism(x0, y0, x1, y1, 0, h, kind, into=self.back)

    def text(self, x, y, z, head, sub=None, anchor="middle", color=None):
        px, py = self.iso(x, y, z)
        self.front.append(f'<text x="{px:.1f}" y="{py:.1f}" text-anchor="{anchor}" font-size="12" '
                          f'font-weight="700" letter-spacing="1.4" '
                          f'fill="{color or self.c["text"]}">{escape(head)}</text>')
        for n, line in enumerate([sub] if isinstance(sub, str) else sub or []):
            self.front.append(f'<text x="{px:.1f}" y="{py + 16 * (n + 1):.1f}" '
                              f'text-anchor="{anchor}" font-size="12" '
                              f'fill="{self.c["sub"]}">{escape(line)}</text>')

    def badge(self, x, y, z, name, kind):
        """An icon in a ring, floating over an object, tied to it by a thin line."""
        accent = self.c["kinds"][kind][0]
        px, py = self.iso(x, y, z)
        gx, gy = self.iso(x, y, z - 26)
        self.out.append(f'<line x1="{gx:.1f}" y1="{gy:.1f}" x2="{px:.1f}" y2="{py + 16:.1f}" '
                        f'stroke="{accent}" stroke-width="1" stroke-dasharray="2 3"/>')
        self.out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="16" fill="{self.c["page"]}" '
                        f'stroke="{accent}" stroke-width="1.4"/>')
        self.out.append(icon(name, px - 10, py - 10, 20, accent, 1.7))

    def pill(self, px, py, label, color=None):
        color = color or self.c["sub"]
        w = len(label) * 6.6 + 16
        self.front.append(f'<rect x="{px - w / 2:.1f}" y="{py - 10:.1f}" width="{w:.1f}" '
                          f'height="20" rx="3" fill="{self.c["page"]}" stroke="{color}"/>')
        self.front.append(f'<text x="{px:.1f}" y="{py + 4:.1f}" text-anchor="middle" '
                          f'font-size="11" fill="{color}">{escape(label)}</text>')

    def lane(self, ground, label=None, at=0.5, tone=None, side=False, z=2):
        """A path on the ground through (x, y) points, with dots that move along it."""
        color = self.c["tones"].get(tone, self.c["edge"] if side else self.c["kinds"]["ai"][0])
        points = [self.iso(x, y, z) for x, y in ground]
        marker = f"arrow-{tone or ('side' if side else 'main')}"
        self.back.append(f'<polyline class="{"side" if side else "main"}" '
                         f'points="{self.pts(points)}" fill="none" stroke="{color}" '
                         f'stroke-linecap="round" stroke-linejoin="round" '
                         f'marker-end="url(#{marker})"/>')
        if label:
            px, py = self.along(points, at)
            self.pill(px, py, label, self.c["tones"].get(tone, self.c["sub"]))
        return points

    @staticmethod
    def along(points, at):
        lengths = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in pairwise(points)]
        goal = sum(lengths) * at
        for (a, b), n in zip(pairwise(points), lengths, strict=True):
            if goal <= n and n:
                f = goal / n
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
            goal -= n
        return points[-1]

    # Objects ------------------------------------------------------------------
    def room(self, x, y, kind="ai", size=110):
        """A glass room with the builder inside."""
        h = size / 2
        self.prism(x - h, y - h, x + h, y + h, 0, 5, kind)
        q = size * 0.18
        self.prism(x - q, y - q, x + q, y + q, 5, 5 + 2 * q, kind)
        self.prism(x - h, y - h, x + h, y + h, 5, size * 0.85, kind, glass=True)

    def booth(self, x, y, arm_to, kind="check", arm_class="arm", axis="x"):
        """A toll booth with a lock, and a striped barrier across the road.

        With axis "x" the barrier runs along x from the booth to x = arm_to; with
        axis "y" it runs along y to y = arm_to.
        """
        stroke = self.faces(kind)[0]
        self.prism(x - 22, y - 22, x + 22, y + 22, 0, 70, kind)
        self.prism(x - 28, y - 28, x + 28, y + 28, 70, 76, kind)
        lx, ly = self.iso(x + 22, y, 34)
        self.out.append(f'<rect x="{lx - 6:.1f}" y="{ly - 2:.1f}" width="12" height="10" rx="2" '
                        f'fill="{stroke}"/>')
        self.out.append(f'<path d="M{lx - 3.5:.1f},{ly - 2:.1f} v-3.5 a3.5,3.5 0 0 1 7,0 v3.5" '
                        f'fill="none" stroke="{stroke}" stroke-width="1.8"/>')
        if axis == "x":
            post, start, end = (arm_to, y), self.iso(x - 22, y, 42), self.iso(arm_to, y, 42)
            turn = 52
        else:
            post, start, end = (x, arm_to), self.iso(x, y + 22, 42), self.iso(x, arm_to, 42)
            turn = 80
        self.prism(post[0] - 6, post[1] - 6, post[0] + 6, post[1] + 6, 0, 30, kind)
        (px, py), (ex, ey) = start, end
        arm = (f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
               f'stroke="{stroke}" stroke-width="8" stroke-linecap="round"/>'
               f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
               f'stroke="{self.c["page"]}" stroke-width="4" stroke-dasharray="9 9"/>')
        # The moving copy gets its rotation from lift(), on the same SVG clock as the
        # ticket. The still copy shows instead for readers who ask for less motion.
        self.out.append(f'<g class="moving-arm">{arm}<!--lift:{arm_class}--></g>'
                        f'<g class="still-arm">{arm}</g>')
        self.out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{stroke}"/>')
        self.pivots = getattr(self, "pivots", {}) | {arm_class: (px, py)}
        self.turns = getattr(self, "turns", {}) | {arm_class: turn}

    def server(self, x, y, kind="server", levels=3, size=90):
        stroke = self.faces(kind)[0]
        h = size / 2
        for n in range(levels):
            z0 = n * 28
            self.prism(x - h, y - h, x + h, y + h, z0, z0 + 24, kind)
            for k in range(3):
                lx, ly = self.iso(x - h + 14 + k * 9, y + h, z0 + 12)
                self.out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.1" fill="{stroke}"/>')
            a, b = self.iso(x + 6, y + h, z0 + 12), self.iso(x + h - 8, y + h, z0 + 12)
            self.out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
                            f'y2="{b[1]:.1f}" stroke="{stroke}" stroke-width="2" '
                            f'stroke-linecap="round"/>')

    def papers(self, x, y, kind="ai", count=3):
        """A stack of pages: a plan."""
        stroke = self.faces(kind)[0]
        for n in range(count):
            dx = n * 4
            self.prism(x - 30 + dx, y - 40 - dx, x + 30 + dx, y + 40 - dx, n * 7, n * 7 + 4, kind)
        top = count * 7 - 3
        for k in range(4):
            a = self.iso(x - 20 + (count - 1) * 4 + k * 11, y - 25 - (count - 1) * 4, top)
            b = self.iso(x - 20 + (count - 1) * 4 + k * 11, y + 20 - (count - 1) * 4, top)
            self.out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
                            f'y2="{b[1]:.1f}" stroke="{stroke}" stroke-width="1.4" '
                            f'stroke-linecap="round"/>')

    def laptop(self, x, y, kind="you"):
        stroke, top, left, _ = self.faces(kind)
        self.prism(x - 30, y - 40, x + 30, y + 40, 0, 5, kind)
        # The screen stands at the back edge, facing the reader.
        p = [self.iso(x - 30, y - 40, 5), self.iso(x - 30, y + 40, 5),
             self.iso(x - 30, y + 40, 62), self.iso(x - 30, y - 40, 62)]
        self.out.append(f'<polygon points="{self.pts(p)}" fill="{left}" stroke="{stroke}" '
                        f'stroke-width="1.3" stroke-linejoin="round"/>')
        q = [self.iso(x - 30, y - 32, 13), self.iso(x - 30, y + 32, 13),
             self.iso(x - 30, y + 32, 55), self.iso(x - 30, y - 32, 55)]
        self.out.append(f'<polygon points="{self.pts(q)}" fill="{top}" stroke="{stroke}" '
                        f'stroke-width="1"/>')
        a, b = self.iso(x - 30, y + 20, 40), self.iso(x - 30, y - 5, 40)
        self.out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                        f'stroke="{stroke}" stroke-width="2" stroke-linecap="round"/>')

    def vault(self, x, y, kind="server"):
        """A locked box: tests that nobody can change."""
        stroke = self.faces(kind)[0]
        self.prism(x - 32, y - 32, x + 32, y + 32, 0, 58, kind)
        lx, ly = self.iso(x, y + 32, 30)
        self.out.append(f'<rect x="{lx - 8:.1f}" y="{ly - 3:.1f}" width="16" height="13" rx="2" '
                        f'fill="{stroke}"/>')
        self.out.append(f'<path d="M{lx - 4.5:.1f},{ly - 3:.1f} v-4.5 a4.5,4.5 0 0 1 9,0 v4.5" '
                        f'fill="none" stroke="{stroke}" stroke-width="2"/>')

    def board(self, x, y, kind="ai"):
        """A board with a small chart: the retro."""
        stroke, top, _, _ = self.faces(kind)
        self.prism(x - 6, y - 6, x + 6, y + 6, 0, 30, "neutral")
        p = [self.iso(x, y - 42, 30), self.iso(x, y + 42, 30), self.iso(x, y + 42, 86),
             self.iso(x, y - 42, 86)]
        self.out.append(f'<polygon points="{self.pts(p)}" fill="{top}" stroke="{stroke}" '
                        f'stroke-width="1.3" stroke-linejoin="round"/>')
        bars = [(-24, 14), (-6, 30), (12, 22), (30, 40)]
        for dy, hgt in bars:
            a, b = self.iso(x, y + dy, 38), self.iso(x, y + dy, 38 + hgt)
            self.out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
                            f'y2="{b[1]:.1f}" stroke="{stroke}" stroke-width="5"/>')

    def house(self, x, y, kind="you", size=90):
        stroke, top, left, right = self.faces(kind)
        h = size / 2
        self.prism(x - h, y - h, x + h, y + h, 0, 50, kind)
        ridge_a, ridge_b = self.iso(x - h, y, 85), self.iso(x + h, y, 85)
        a, b = self.iso(x - h, y + h, 50), self.iso(x + h, y + h, 50)
        c, d = self.iso(x + h, y - h, 50), self.iso(x - h, y - h, 50)
        self.out.append(f'<polygon points="{self.pts([a, b, ridge_b, ridge_a])}" fill="{left}" '
                        f'stroke="{stroke}" stroke-width="1.3" stroke-linejoin="round"/>')
        self.out.append(f'<polygon points="{self.pts([b, c, ridge_b])}" fill="{right}" '
                        f'stroke="{stroke}" stroke-width="1.3" stroke-linejoin="round"/>')
        self.out.append(f'<polygon points="{self.pts([d, c, ridge_b, ridge_a])}" fill="{top}" '
                        f'stroke="{stroke}" stroke-width="1.3" stroke-linejoin="round" '
                        f'fill-opacity="0"/>')
        door = [self.iso(x + 10, y + h, 0), self.iso(x - 10, y + h, 0),
                self.iso(x - 10, y + h, 28), self.iso(x + 10, y + h, 28)]
        self.out.append(f'<polygon points="{self.pts(door)}" fill="{stroke}"/>')

    def database(self, x, y, kind="server", r=34, h=60):
        """A cylinder: stored data."""
        stroke, top, left, _ = self.faces(kind)
        cx, cy0 = self.iso(x, y, 0)
        _, cy1 = self.iso(x, y, h)
        rx, ry = r * 1.2247 * self.s, r * 0.7071 * self.s
        self.out.append(f'<path d="M{cx - rx:.1f},{cy1:.1f} V{cy0:.1f} A{rx:.1f},{ry:.1f} 0 0 0 '
                        f'{cx + rx:.1f},{cy0:.1f} V{cy1:.1f} Z" fill="{left}" stroke="{stroke}" '
                        f'stroke-width="1.3"/>')
        mid = (cy0 + cy1) / 2
        self.out.append(f'<path d="M{cx - rx:.1f},{mid:.1f} A{rx:.1f},{ry:.1f} 0 0 0 '
                        f'{cx + rx:.1f},{mid:.1f}" fill="none" stroke="{stroke}" stroke-width="1"/>')
        self.out.append(f'<ellipse cx="{cx:.1f}" cy="{cy1:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                        f'fill="{top}" stroke="{stroke}" stroke-width="1.3"/>')

    def pedestal(self, x, y, kind="neutral", icon_name=None, aws_name=None):
        """A short stand with an icon over it: any station that has no object of its own."""
        self.prism(x - 22, y - 22, x + 22, y + 22, 0, 22, kind)
        if aws_name:
            self.aws_icon(x, y, 70, aws_name)
        elif icon_name:
            self.badge(x, y, 80, icon_name, kind)

    def aws_icon(self, x, y, z, name, size=40):
        """An official AWS icon, unchanged, standing over a spot."""
        px, py = self.iso(x, y, z)
        self.ids += 1
        self.out.append(aws.place(aws.service(name, prefix=f"s{self.ids}"), px - size / 2,
                                  py - size / 2, size))

    def person(self, x, y, kind="you"):
        """A person on a small round base: someone who uses the system."""
        stroke, top, left, right = self.faces(kind)
        cx, cy = self.iso(x, y, 0)
        rx, ry = 30 * 1.2247 * self.s, 30 * 0.7071 * self.s
        _, cy1 = self.iso(x, y, 6)
        self.out.append(f'<path d="M{cx - rx:.1f},{cy1:.1f} V{cy:.1f} A{rx:.1f},{ry:.1f} 0 0 0 '
                        f'{cx + rx:.1f},{cy:.1f} V{cy1:.1f} Z" fill="{left}" stroke="{stroke}" '
                        f'stroke-width="1.3"/>')
        self.out.append(f'<ellipse cx="{cx:.1f}" cy="{cy1:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                        f'fill="{top}" stroke="{stroke}" stroke-width="1.3"/>')
        self.prism(x - 7, y - 13, x + 7, y - 2, 6, 40, kind)    # the legs
        self.prism(x - 7, y + 2, x + 7, y + 13, 6, 40, kind)
        self.prism(x - 9, y - 17, x + 9, y + 17, 40, 78, kind)  # the body
        hx, hy = self.iso(x, y, 96)
        r = 15 * self.s
        self.out.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{r:.1f}" fill="{right}" '
                        f'stroke="{stroke}" stroke-width="1.3"/>')
        self.out.append(f'<circle cx="{hx - r * 0.3:.1f}" cy="{hy - r * 0.3:.1f}" '
                        f'r="{r * 0.55:.1f}" fill="{top}"/>')

    def external(self, x, y, size=90):
        """A gray building with rows of windows: a system that is not ours. Always
        gray, whatever the kind, the way C4 draws an external system."""
        stroke = self.faces("neutral")[0]
        h, tall = size / 2, size * 1.1
        self.prism(x - h, y - h, x + h, y + h, 0, tall, "neutral")
        self.prism(x - h - 4, y - h - 4, x + h + 4, y + h + 4, tall, tall + 6, "neutral")
        rows = int((tall - 24) // 22)
        for k in range(rows):
            z0 = 14 + k * 22
            for n in range(3):
                d0 = -h + 10 + n * (size - 20) / 3
                d1 = d0 + (size - 20) / 3 - 8
                for face in ([(x + d0, y + h), (x + d1, y + h)],     # the left face
                             [(x + h, y - d0), (x + h, y - d1)]):    # the right face
                    (ax, ay), (bx, by) = face
                    p = [self.iso(ax, ay, z0), self.iso(bx, by, z0),
                         self.iso(bx, by, z0 + 12), self.iso(ax, ay, z0 + 12)]
                    self.out.append(f'<polygon points="{self.pts(p)}" fill="{stroke}" '
                                    f'fill-opacity="0.45"/>')

    def wall(self, x0, y0, x1, y1, h=46, kind="neutral"):
        self.prism(x0, y0, x1, y1, 8, h, kind)

    # The ticket ----------------------------------------------------------------
    def leg(self, points, tone=None, wait=0.4):
        """One stretch of the ticket's trip: page points, its color, the wait at the end."""
        color = self.c["tones"].get(tone, self.c["kinds"]["ai"][0])
        self.legs.append((points, color, wait))

    def ticket(self, speed=150, start_wait=0.5, rest=1.5):
        marks, colors, points, now, dist = [], [], [], 0.0, 0.0
        times = []  # (start, end) of each leg
        for n, (pts, color, wait) in enumerate(self.legs):
            if points:
                dist += abs(pts[0][0] - points[-1][0]) + abs(pts[0][1] - points[-1][1])
            points += pts
            marks.append((now, dist))
            colors.append((now, color))
            if n == 0:
                now += start_wait
                marks.append((now, dist))
            begin = now
            for a, b in pairwise(pts):
                step = abs(b[0] - a[0]) + abs(b[1] - a[1])
                dist += step
                now += step / speed
                marks.append((now, dist))
            times.append((begin, now))
            now += wait
            marks.append((now, dist))
        now += rest
        marks.append((now, dist))
        dur, total = now, dist
        path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
        key_times = ";".join(f"{t / dur:.4f}" for t, _ in marks)
        key_points = ";".join(f"{d / total:.4f}" for _, d in marks)
        shared = f'dur="{dur:.2f}s" repeatCount="indefinite"'
        fill = (f'<animate attributeName="fill" values="{";".join(c for _, c in colors)}" '
                f'keyTimes="{";".join(f"{t / dur:.4f}" for t, _ in colors)}" calcMode="discrete" '
                f'{shared}/>')
        base = colors[0][1]
        self.front.extend([
            '<g class="ticket">',
            f'<circle r="12" fill="{base}" opacity="0.22">{fill}</circle>',
            f'<circle r="6" fill="{base}" stroke="{self.c["page"]}" stroke-width="2">{fill}</circle>',
            (f'<animateMotion path="{path}" keyPoints="{key_points}" keyTimes="{key_times}" '
             f'calcMode="linear" {shared}/>'),
            "</g>",
        ])
        return dur, times

    def lift(self, name, dur, up, down, swing=0.5):
        """Lift the barrier of class `name`: it starts rising at time `up`, is fully up
        `swing` seconds later, and starts falling at time `down`, in a loop of `dur`.

        An SVG rotation, not CSS, so it runs on the same clock as the ticket: the
        two stay in step even when a browser pauses an image that is out of view."""
        up = max(up, 0.0)
        px, py = self.pivots[name]
        turn = getattr(self, "turns", {}).get(name, 52)
        keys = ";".join(f"{x / dur:.4f}" for x in (up, up + swing, down, min(down + swing, dur)))
        shut, open_ = f"0 {px:.1f} {py:.1f}", f"{turn} {px:.1f} {py:.1f}"
        self.lifts = getattr(self, "lifts", {}) | {name: (
            f'<animateTransform attributeName="transform" type="rotate" '
            f'values="{shut};{shut};{open_};{open_};{shut};{shut}" keyTimes="0;{keys};1" '
            f'dur="{dur:.2f}s" repeatCount="indefinite"/>')}

    # Callouts -----------------------------------------------------------------
    def number(self, x, y, n, accent):
        self.front.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{BADGE}" fill="{accent}"/>')
        self.front.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" '
                          f'font-weight="700" fill="{self.c["page"]}">{n}</text>')

    def callout(self, c, x, y, point):
        """A numbered label with its number at (x, y), and a dotted leader to a ring
        on the page point it names."""
        accent = self.c["kinds"][c.get("kind", "neutral")][0]
        px, py = point
        dx, dy = px - x, py - y
        far = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / far, dy / far
        a = (x + ux * (BADGE + 3), y + uy * (BADGE + 3))
        b = (px - ux * 5, py - uy * 5)
        # A page can find each callout and the point it names, to light that part.
        self.front.append(f'<g class="callout" data-n="{c["n"]}" data-x="{px:.1f}" '
                          f'data-y="{py:.1f}">')
        self.front.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                          f'stroke="{accent}" stroke-width="1.5" stroke-dasharray="1 4" '
                          f'stroke-linecap="round"/>')
        self.front.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{self.c["page"]}" '
                          f'fill-opacity="0.7" stroke="{accent}" stroke-width="1.8"/>')
        self.number(x, y, c["n"], accent)
        right = c["side"] == "right"
        tx = x + (INSET - BADGE) if right else x - (INSET - BADGE)
        anchor = "start" if right else "end"
        lines = wrap(c["line"], int((COLUMN - INSET - 12) / LINE_CHAR))
        self.front.append(f'<text x="{tx:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" '
                          f'font-size="12" font-weight="700" letter-spacing="1.4" '
                          f'fill="{self.c["text"]}">{escape(c["head"].upper())}</text>')
        for k, line in enumerate(lines):
            self.front.append(f'<text x="{tx:.1f}" y="{y + 4 + STEP * (k + 1):.1f}" '
                              f'text-anchor="{anchor}" font-size="12" '
                              f'fill="{self.c["sub"]}">{escape(line)}</text>')
        self.front.append("</g>")

    def pinned(self, label):
        """A label tied to its part by a stem: a flat ring on the part, a line
        straight up or down, one rounded turn, then level to the label. With
        "route": "level", the line goes level first, then up or down. A label
        with "n" shows that number where the stem ends; one without shows a dot."""
        n, kind = label.get("n"), label.get("kind", "neutral")
        accent = self.c["kinds"][kind][0]
        tx, ty = self.iso(*label["pin"])
        anchor = label.get("anchor", "middle")
        if "drop" in label:                      # under the part, right of the stem
            anchor, px, py = "start", tx + PIN_GAP, ty + label["drop"]
        else:
            px, py = self.iso(*label["at"])
            if anchor == "middle":
                anchor, px = "start", tx + PIN_GAP
        bx = px - PIN_GAP if anchor == "start" else px + PIN_GAP
        if abs(bx - tx) < 2 * BADGE:             # a straight stem: the number sits on it
            px, bx = px + tx - bx, tx
        by = py - 4
        r = BADGE + 2 if n else 3
        d = f"M{tx:.1f},{ty - 4:.1f} "
        if bx == tx:
            d += f"L{tx:.1f},{by + (-r if by > ty else r):.1f}"
        elif label.get("route") == "level":
            # Sideways first, then up or down to the number: for a part with an icon
            # over it, or a tall part that a line down its middle would cross.
            side = 1 if bx > tx else -1
            up = -1 if by < ty else 1
            y0 = ty - 4
            turn = min(10, abs(by - y0) / 2, abs(bx - tx) / 2)
            d += (f"L{bx - side * turn:.1f},{y0:.1f} Q{bx:.1f},{y0:.1f} {bx:.1f},"
                  f"{y0 + up * turn:.1f} L{bx:.1f},{by - up * r:.1f}")
        else:
            side = 1 if bx > tx else -1
            up = -1 if by < ty else 1
            turn = min(10, abs(by - ty) / 2, abs(bx - tx) / 2)
            d += (f"L{tx:.1f},{by - up * turn:.1f} Q{tx:.1f},{by:.1f} {tx + side * turn:.1f},"
                  f"{by:.1f} L{bx - side * r:.1f},{by:.1f}")
        self.front.append(f'<g class="pin" data-n="{n or ""}">')
        self.front.append(f'<path d="{d}" fill="none" stroke="{accent}" stroke-width="1.3" '
                          f'stroke-opacity="0.85" stroke-dasharray="2 3" stroke-linecap="round"/>')
        # The ring lies flat on the part, at the scene's own angle.
        ring = f'cx="{tx:.1f}" cy="{ty:.1f}" rx="7" ry="4"'
        self.front.append(f'<ellipse {ring} fill="{accent}" fill-opacity="0.25" '
                          f'stroke="{accent}" stroke-width="1.6"/>')
        self.front.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="1.8" fill="{accent}"/>')
        if n:
            # The rings pulse in the order of their numbers.
            self.front.append(f'<ellipse class="pulse" {ring} fill="none" stroke="{accent}" '
                              f'stroke-width="1.2" style="animation-delay:{(n - 1) * 0.6:.1f}s"/>')
            self.number(bx, by, n, accent)
        else:
            self.front.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="2.5" fill="{accent}"/>')
        self.front.append(f'<text x="{px:.1f}" y="{py:.1f}" text-anchor="{anchor}" font-size="12" '
                          f'font-weight="700" letter-spacing="1.4" fill="{self.c["text"]}">'
                          f'{escape(label["head"].upper())}</text>')
        for k, line in enumerate([label["sub"]] if isinstance(label.get("sub"), str)
                                 else label.get("sub") or []):
            self.front.append(f'<text x="{px:.1f}" y="{py + STEP * (k + 1):.1f}" '
                              f'text-anchor="{anchor}" font-size="12" '
                              f'fill="{self.c["sub"]}">{escape(line)}</text>')
        self.front.append("</g>")

    def note(self, x, y, c):
        """A numbered line under the caption, for a rule that holds for the whole picture."""
        accent = self.c["kinds"][c.get("kind", "neutral")][0]
        self.front.append(f'<g class="pin" data-n="{c["n"]}">')
        self.number(x + BADGE, y - 4, c["n"], accent)
        hx = x + 2 * BADGE + 8
        self.front.append(f'<text x="{hx:.1f}" y="{y:.1f}" font-size="12" font-weight="700" '
                          f'letter-spacing="1.4" fill="{self.c["text"]}">'
                          f'{escape(c["head"].upper())}</text>')
        lx = hx + len(c["head"]) * HEAD_CHAR + 14
        self.front.append(f'<text x="{lx:.1f}" y="{y:.1f}" font-size="12" '
                          f'fill="{self.c["sub"]}">{escape(c["line"])}</text>')
        self.front.append("</g>")

    def callout_under(self, c, cx, cy):
        """A numbered label on one line, centered under the scene, with no leader."""
        accent = self.c["kinds"][c.get("kind", "neutral")][0]
        x = cx - bottom_width(c) / 2
        self.front.append(f'<g class="callout" data-n="{c["n"]}">')
        self.number(x + BADGE, cy, c["n"], accent)
        hx = x + 2 * BADGE + 12
        self.front.append(f'<text x="{hx:.1f}" y="{cy + 4:.1f}" font-size="12" font-weight="700" '
                          f'letter-spacing="1.4" fill="{self.c["text"]}">'
                          f'{escape(c["head"].upper())}</text>')
        lx = hx + len(c["head"]) * HEAD_CHAR + 14
        self.front.append(f'<text x="{lx:.1f}" y="{cy + 4:.1f}" font-size="12" '
                          f'fill="{self.c["sub"]}">{escape(c["line"])}</text>')
        self.front.append("</g>")

    # The page ------------------------------------------------------------------
    def grid(self, extent=420, step=30):
        out = ['<g mask="url(#fade)">']
        for k in range(-extent, extent + 1, step):
            for a, b in ((self.iso(k, -extent), self.iso(k, extent)),
                         (self.iso(-extent, k), self.iso(extent, k))):
                out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                           f'stroke="{self.c["edge"]}" stroke-opacity="0.28" stroke-width="1"/>')
        out.append("</g>")
        self.back[:0] = out

    def caption(self, x, y, head, sub):
        self.front.append(f'<text x="{x}" y="{y}" font-size="13" font-weight="700" '
                          f'letter-spacing="2" fill="{self.c["text"]}">{escape(head)}</text>')
        self.front.append(f'<text x="{x}" y="{y + 20}" font-size="12" '
                          f'fill="{self.c["sub"]}">{escape(sub)}</text>')

    def render(self, title, desc):
        c = self.c
        markers = []
        for name, color in (("main", c["kinds"]["ai"][0]), ("side", c["edge"]),
                            ("fail", c["tones"]["fail"]), ("pass", c["tones"]["pass"])):
            markers.append(f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                           f'markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" '
                           f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9 L3.2,5 z" '
                           f'fill="{color}"/></marker>')
        style = (".main{stroke-width:3;stroke-dasharray:0 8;animation:flow .8s linear infinite}"
                 ".side{stroke-width:1.8;stroke-dasharray:6 6;animation:side 1.6s linear infinite}"
                 "@keyframes flow{to{stroke-dashoffset:-8}}@keyframes side{to{stroke-dashoffset:-12}}"
                 ".still-arm{display:none}"
                 ".pulse{transform-box:fill-box;transform-origin:center;opacity:0;"
                 "animation:pulse 4.2s ease-out infinite}"
                 "@keyframes pulse{0%{transform:scale(1);opacity:.8}25%{transform:scale(2.5);"
                 "opacity:0}100%{opacity:0}}"
                 "@media (prefers-reduced-motion:reduce){.main,.side,.pulse{animation:none}"
                 ".ticket,.moving-arm{display:none}.still-arm{display:inline}}")
        lifts = getattr(self, "lifts", {})
        self.out = [re.sub(r"<!--lift:([\w-]+)-->", lambda m: lifts.get(m.group(1), ""), s)
                    for s in self.out]
        head = [
            (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
             f'width="{self.w}" height="{self.h}" role="img" aria-labelledby="title desc" '
             f'font-family="{MONO}">'),
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(desc)}</desc>',
            ("<defs>"
             f'<radialGradient id="glow" cx="{self.ox / self.w:.3f}" cy="{self.oy / self.h:.3f}" '
             'r="0.6"><stop offset="0" stop-color="#fff" stop-opacity="1"/>'
             '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
             f'<mask id="fade"><rect width="{self.w}" height="{self.h}" fill="url(#glow)"/></mask>'
             + "".join(markers) + "</defs>"),
            f"<style>{style}</style>",
            f'<rect width="{self.w}" height="{self.h}" fill="{c["page"]}"/>',
        ]
        return "\n".join(head + self.back + self.out + self.front + ["</svg>"]) + "\n"


OBJECTS = ("room", "gate", "server", "vault", "papers", "laptop", "board", "house",
           "database", "pedestal", "wall", "aws", "person", "external")

# Callouts ---------------------------------------------------------------------
# A callout is a numbered label in a column beside the scene, with a dotted
# leader to a small ring on the part it names.
SIDES = ("left", "right", "bottom")
COLUMN = 270       # the width of a column of callouts
BOTTOM = 52        # the height of the row under the scene
BADGE = 10         # the radius of the number's circle
INSET = 28         # from the inner edge of a column to the start of its text
HEAD_CHAR = 8.6    # the width of one character of a head: 12 px mono, spaced 1.4
LINE_CHAR = 7.2    # the width of one character of a line: 12 px mono
STEP = 16          # from one line of text to the next
PIN_GAP = 20       # from a pinned label's number to the start of its words
GAP = 14           # the least space between two callouts in a column


def wrap(text, chars):
    """Break text into lines of at most `chars` characters, at spaces."""
    lines = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= chars:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def check_callouts(callouts, width=COLUMN):
    """Refuse a callout that cannot be drawn, with a message that says how to fix it."""
    kinds = set(THEMES["light"]["kinds"])
    numbers = [c.get("n") for c in callouts]
    if len(set(numbers)) != len(numbers):
        raise ValueError("each callout needs its own number 'n'")
    room = (width - INSET - 12) / LINE_CHAR
    for c in callouts:
        name = f"callout {c.get('n')}"
        for key in ("n", "head", "line", "side"):
            if not c.get(key):
                raise ValueError(f"{name} needs a '{key}'")
        if c["side"] not in SIDES:
            raise ValueError(f"{name}: side must be one of {', '.join(SIDES)}")
        if c.get("kind", "neutral") not in kinds:
            raise ValueError(f"{name}: kind must be one of {', '.join(sorted(kinds))}")
        if c["side"] != "bottom":
            if len(c.get("to") or []) != 3:
                raise ValueError(f"{name} needs 'to': the [x, y, z] point it names")
            if len(c["head"]) * HEAD_CHAR > width - INSET - 12:
                raise ValueError(f"{name}: the head is too long for one line; shorten it")
            if len(wrap(c["line"], int(room))) > 2:
                raise ValueError(f"{name}: the line wraps past two lines; shorten it")
    # Clockwise: up the left column, down the right one, then the row under the scene.
    groups = [[c["n"] for c in callouts if c["side"] == side] for side in SIDES]
    order = [n for g in groups for n in sorted(g)]
    if order != sorted(numbers):
        raise ValueError("number the callouts clockwise: the left column first, from its "
                         "lowest label up, then the right column from the top, then the bottom")


def crosses(a, b, c, d):
    """True when segment a-b crosses segment c-d."""
    def turn(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)
    return turn(a, b, c) * turn(a, b, d) < 0 and turn(c, d, a) * turn(c, d, b) < 0


def place_column(items, edge, top, bottom):
    """Place the labels of one column, given top to bottom, beside their points.

    `items` are (point, height) pairs: the page point a label names and the
    height of the label below its number. `edge` is the x of the numbers.
    Each label starts level with its point. Labels then move apart until none
    overlaps the next and no two leaders cross. Return the y of each number.
    """
    want = [p[1] for p, _ in items]
    space = [h + GAP for _, h in items]  # from a number down to the next one, at least
    extra = [0.0] * len(items)
    for _ in range(400):
        # Labels that touch form a block; each block sits at the mean of where its
        # labels want to be, so no label moves farther than it must.
        blocks = []  # [first, last, y of first]
        for i in range(len(want)):
            blocks.append([i, i, want[i]])
            while len(blocks) > 1:
                a, b = blocks[-2], blocks[-1]
                end = a[2] + sum(space[k] + extra[k] for k in range(a[0], a[1] + 1))
                if end <= b[2]:
                    break
                offs, run = [], 0.0
                for k in range(a[0], b[1] + 1):
                    offs.append(run)
                    run += space[k] + extra[k]
                y = sum(want[k] - o for k, o in zip(range(a[0], b[1] + 1), offs,
                                                    strict=True)) / len(offs)
                blocks[-2:] = [[a[0], b[1], y]]
        ys = []
        for first, last, y in blocks:
            for k in range(first, last + 1):
                ys.append(y if k == first else ys[-1] + space[k - 1] + extra[k - 1])
        ys[-1] = min(ys[-1], bottom - items[-1][1])
        for i in range(len(ys) - 2, -1, -1):  # push up, off the bottom
            ys[i] = min(ys[i], ys[i + 1] - space[i] - extra[i])
        ys[0] = max(ys[0], top)
        for i in range(1, len(ys)):  # push down, off the top
            ys[i] = max(ys[i], ys[i - 1] + space[i - 1] + extra[i - 1])
        if ys[-1] > bottom - items[-1][1]:
            raise ValueError("the callouts of a column do not fit; shorten them or make the "
                             "scene taller")
        bad = [(i, j) for i in range(len(ys)) for j in range(i + 1, len(ys))
               if crosses((edge, ys[i]), items[i][0], (edge, ys[j]), items[j][0])]
        if not bad:
            return ys
        for i, j in bad:
            for k in range(i, j):
                extra[k] += 4
    raise ValueError("the leaders of a column cross; move a point or a label to another side")


def callout_height(c, width=COLUMN):
    """The height of a callout below its number: the head and the wrapped line."""
    return STEP * len(wrap(c["line"], int((width - INSET - 12) / LINE_CHAR))) + 8


def callout_layout(callouts, iso, frame, width=COLUMN):
    """Where each callout goes. `iso` maps a ground point to the page; `frame` is
    (left, top, right, bottom) of the scene on the widened page.

    Return a dict from number to (number x, number y, page point or None)."""
    left, top, right, bottom = frame
    out = {}
    for side, edge in (("left", left - 8 - BADGE), ("right", right + 8 + BADGE)):
        column = sorted((c for c in callouts if c["side"] == side), key=lambda c: c["n"])
        if side == "left":
            column.reverse()  # it reads upward: its first label is the lowest
        if not column:
            continue
        points = [iso(*c["to"]) for c in column]
        ys = place_column([(p, callout_height(c, width)) for p, c in zip(points, column,
                                                                          strict=True)],
                          edge, top, bottom)
        for c, p, y in zip(column, points, ys, strict=True):
            out[c["n"]] = (edge, y, p)
    return out


def bottom_width(c):
    return 2 * BADGE + 12 + len(c["head"]) * HEAD_CHAR + 14 + len(c["line"]) * LINE_CHAR


def check_object(o):
    """Refuse an object that cannot be drawn, with a message that says how to fix it."""
    kinds = set(THEMES["light"]["kinds"])
    name = f"the {o.get('type', 'object')} object"
    at = o.get("at")
    if not isinstance(at, list) or len(at) < 2:
        raise ValueError(f"{name} needs 'at': the [x, y] point it stands on")
    if o.get("kind", "neutral") not in kinds:
        raise ValueError(f"{name}: kind must be one of {', '.join(sorted(kinds))}")
    size = o.get("size", 1)
    if isinstance(size, bool) or not isinstance(size, int | float) or size <= 0:
        raise ValueError(f"{name}: size must be a number above 0")


def from_spec(spec: dict, theme: str) -> str:
    """Draw a scene from a spec. See the format in diagram/__init__.py."""
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the scene needs a '{key}'")
    callouts = spec.get("callouts", [])
    check_callouts(callouts)
    w, h = spec.get("size", [1120, 640])
    ox, oy = spec.get("origin", [w / 2, h / 2])
    # The page grows by a column on each side that has callouts, and by a row
    # under the scene for the bottom ones.
    grow_l = COLUMN if any(c["side"] == "left" for c in callouts) else 0
    grow_r = COLUMN if any(c["side"] == "right" for c in callouts) else 0
    unders = sorted((c for c in callouts if c["side"] == "bottom"), key=lambda c: c["n"])
    grow_b = BOTTOM * len(unders)
    s = Scene(theme, w + grow_l + grow_r, h + grow_b, origin=(ox + grow_l, oy),
              scale=spec.get("scale", 0.8))
    s.grid(spec.get("grid", 460))
    if spec.get("caption"):
        s.caption(40, 48, spec["caption"][0].upper(), spec["caption"][1])
    if spec.get("note"):
        s.note(40, 102, spec["note"])
    for zone in spec.get("zones", []):
        x0, y0, x1, y1 = zone["at"]
        s.platform(x0, y0, x1, y1, zone.get("kind", "neutral"))
    for lane in spec.get("lanes", []):
        s.lane([tuple(p) for p in lane["path"]], lane.get("label"), lane.get("at", 0.5),
               lane.get("tone"), lane.get("side", False))
    for o in spec.get("objects", []):
        check_object(o)
    # Objects from back to front, so nearer ones cover farther ones.
    for o in sorted(spec.get("objects", []), key=lambda o: o["at"][0] + o["at"][1]):
        x, y = o["at"][:2]
        kind = o.get("kind")
        what = o["type"]
        if what == "room":
            s.room(x, y, kind or "ai", o.get("size", 110))
        elif what == "gate":
            s.booth(x, y, o["arm_to"], kind or "check", o.get("name", "arm"), o.get("axis", "x"))
        elif what == "server":
            s.server(x, y, kind or "server", o.get("levels", 3), o.get("size", 90))
        elif what == "vault":
            s.vault(x, y, kind or "server")
        elif what == "papers":
            s.papers(x, y, kind or "ai")
        elif what == "laptop":
            s.laptop(x, y, kind or "you")
        elif what == "board":
            s.board(x, y, kind or "ai")
        elif what == "house":
            s.house(x, y, kind or "you", o.get("size", 90))
        elif what == "database":
            s.database(x, y, kind or "server")
        elif what == "pedestal":
            s.pedestal(x, y, kind or "neutral", o.get("icon"))
        elif what == "aws":
            s.pedestal(x, y, kind or "neutral", aws_name=o["aws"])
        elif what == "person":
            s.person(x, y, kind or "you")
        elif what == "external":
            s.external(x, y, o.get("size", 90))
        elif what == "wall":
            x1, y1 = o["to"]
            s.wall(x, y, x1, y1, o.get("height", 46), kind or "neutral")
        else:
            raise ValueError(f"unknown object '{what}'; use one of {', '.join(OBJECTS)}")
    for label in spec.get("labels", []):
        if "pin" in label:
            if "at" not in label and "drop" not in label:
                raise ValueError(f"the label '{label['head']}' has a pin: give it 'at' or 'drop'")
            s.pinned(label)
            continue
        x, y, z = (label["at"] + [0])[:3]
        s.text(x, y, z, label["head"].upper(), label.get("sub"), label.get("anchor", "middle"))
    ticket = spec.get("ticket")
    if ticket and (not ticket.get("legs") or not all(leg.get("path") for leg in ticket["legs"])):
        raise ValueError("the ticket needs legs, each with a path")
    if ticket:
        for leg in ticket["legs"]:
            s.leg([s.iso(x, y, 2) for x, y in leg["path"]], leg.get("tone"), leg.get("wait", 0.4))
        dur, times = s.ticket(speed=ticket.get("speed", 150))
        if "lift" in ticket:
            n = ticket["lift"]
            if not 1 <= n < len(times):
                raise ValueError(f"lift names leg {n}; it must be 1 to {len(times) - 1}, a leg that "
                                 f"starts where the one before it stopped at the gate")
            # The barrier opens only after the change has reached it and waited a moment
            # (the tests run), and it is fully up before the change moves on.
            arrived, leaves = times[n - 1][1], times[n][0]
            swing = min(0.5, max(0.1, (leaves - arrived) / 2))
            s.lift(ticket.get("gate", "arm"), dur, leaves - swing - 0.05, times[n][1], swing)
    if callouts:
        top = 90 if spec.get("caption") else 24
        places = callout_layout(callouts, s.iso, (grow_l, top, grow_l + w, h - 16))
        for c in callouts:
            if c["side"] != "bottom":
                s.callout(c, *places[c["n"]])
        for k, c in enumerate(unders):
            s.callout_under(c, grow_l + w / 2, h + BOTTOM * k + BOTTOM / 2)
    return s.render(spec["title"], spec["desc"])

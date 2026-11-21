"""A small kit for isometric scenes, in the same colors and type as the flat diagrams.

A scene is a ground of fine grid, objects standing on it, lanes between them
with dots that move, labels in monospace, and one ticket that travels a path.

    s = Scene("light", 1200, 700, origin=(600, 330), scale=0.7)
    s.room(0, 0, "ai")
    s.lane([(0, 60), (0, 200)], label="the change")
    svg = s.render("Title", "What it shows.")

Ground units: x runs down and to the right on the page, y runs down and to the
left, z runs up.
"""

from itertools import pairwise
from xml.sax.saxutils import escape

from driver.diagram import MONO, THEMES
from driver.icons import icon


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
        self.front_post = post
        self.prism(post[0] - 6, post[1] - 6, post[0] + 6, post[1] + 6, 0, 30, kind)
        (px, py), (ex, ey) = start, end
        self.out.append(f'<g class="{arm_class}" style="transform-origin:{px:.1f}px {py:.1f}px">'
                        f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                        f'stroke="{stroke}" stroke-width="8" stroke-linecap="round"/>'
                        f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                        f'stroke="{self.c["page"]}" stroke-width="4" stroke-dasharray="9 9"/></g>')
        self.out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{stroke}"/>')
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
        stroke, top, left, _ = self.faces(kind)
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
        del left

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

    def lift(self, name, dur, up, down):
        """Lift the barrier of class `name` from time `up` to time `down`, in a loop of dur."""
        a, b = 100 * up / dur, 100 * down / dur
        self.css.append(f".{name}{{transform-box:view-box;animation:{name} {dur:.2f}s ease-in-out "
                        f"infinite}}@keyframes {name}{{0%,{max(a - 4, 0):.1f}%{{transform:rotate(0)}}"
                        f"{a:.1f}%,{b:.1f}%{{transform:rotate({getattr(self, 'turns', {}).get(name, 52)}deg)}}"
                        f"{min(b + 6, 100):.1f}%,100%{{transform:rotate(0)}}}}")
        self.reduced = getattr(self, "reduced", []) + [f".{name}"]

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
        quiet = ",".join([".main", ".side", *getattr(self, "reduced", [])])
        style = (".main{stroke-width:3;stroke-dasharray:0 8;animation:flow .8s linear infinite}"
                 ".side{stroke-width:1.8;stroke-dasharray:6 6;animation:side 1.6s linear infinite}"
                 "@keyframes flow{to{stroke-dashoffset:-8}}@keyframes side{to{stroke-dashoffset:-12}}"
                 + "".join(self.css)
                 + f"@media (prefers-reduced-motion:reduce){{{quiet}{{animation:none}}"
                 ".ticket{display:none}}")
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

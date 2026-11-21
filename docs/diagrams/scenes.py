"""The isometric scenes: the big-picture diagrams, drawn with iso.py.

Each function takes a theme ("light" or "dark") and returns the SVG text.
build.py draws them as <name>.svg and <name>-dark.svg.
"""

from iso import Scene


def how_it_works(theme: str) -> str:
    s = Scene(theme, 1180, 720, origin=(470, 400), scale=0.9)
    s.grid(520)
    s.caption(40, 48, "HOW TOLLGATE WORKS", "three loops: review the plan, build to green, learn")

    def g(points, z=2):
        return [s.iso(x, y, z) for x, y in points]

    # The road: up the left to the AI's room, then right to the gate and main.
    road = [[(0, 258), (0, 214)], [(0, 128), (0, 64)], [(0, 18), (0, -56)],
            [(0, -124), (0, -166)], [(54, -220), (323, -220)]]
    fail = [(110, -220), (110, -360), (0, -360), (0, -274)]
    # Lanes first, so the objects stand on them.
    s.lane([(-30, 40), (-110, 40), (-110, 170), (-32, 170)], "problems", tone="fail")
    s.lane(fail, "what failed goes back", at=0.66, tone="fail")
    s.lane([(370, -174), (370, 170), (34, 170)], "lessons tighten the rules", at=0.72, side=True)
    s.lane([(205, -205), (205, -84)], "stuck", side=True)
    s.lane([(172, -60), (100, -60), (100, -186), (54, -186)], "retry", at=0.35, side=True)
    for n, seg in enumerate(road):
        s.lane(seg, "clean" if n == 2 else None, tone="pass" if n == 2 else None)

    # Objects, back to front (by x + y).
    s.server(370, -220)
    s.room(0, -220, "ai", size=104)
    s.booth(190, -282, arm_to=-160, axis="y")
    s.vault(0, -90)
    s.prism(183, -82, 227, -38, 0, 22, "advisor")
    s.badge(205, -60, 80, "advisor", "advisor")
    s.prism(-22, 18, 22, 62, 0, 22, "check")
    s.badge(0, 40, 80, "check", "check")
    s.board(470, 40, "ai")
    s.papers(0, 170, "ai")
    s.laptop(0, 300, "you")

    # Labels, each beside its object.
    s.text(470, -150, 0, "MAIN", "only a pass goes in", "start")
    s.text(0, -300, 165, "THE AI BUILDS", "in its own room")
    s.text(250, -330, 40, "THE GATE", "locked tests decide", "start")
    s.text(240, -20, -18, "ADVISOR", "a second AI, or you")
    s.text(-90, -125, 24, "TESTS LOCKED", "before any code", "end")
    s.text(-150, 40, 40, "REVIEW", "fresh AIs check the plan", "end")
    s.text(-150, 190, 20, "THE PLAN", "small tickets", "end")
    s.text(-60, 330, 0, "YOU ASK", "in plain words", "end")
    s.text(540, 40, 70, "RETRO", "numbers and 3 lessons", "start")

    # One change travels the road: it fails at the gate once, goes back, then passes.
    to_gate = [(54, -220), (110, -220)]
    s.leg(g(road[0]))
    s.leg(g(road[1]))
    s.leg(g(road[2]), "pass")
    s.leg(g(road[3]))
    s.leg(g(to_gate), wait=0.9)
    s.leg(g(fail), "fail", wait=0.5)
    s.leg(g([(0, -274), (0, -220), (54, -220), (175, -220)]), wait=0.9)
    s.leg(g([(175, -220), (323, -220)]), "pass", wait=0.6)
    dur, times = s.ticket()
    s.lift("arm", dur, times[6][1] + 0.15, times[7][1])
    return s.render(
        "How Tollgate works, with its three feedback loops",
        "An isometric scene. You ask in plain words. The AI writes a plan, and fresh AIs review "
        "it; on problems it goes back to the plan. The tests are locked before any code. The AI "
        "builds in its own room. At the gate, the locked tests decide: on a fail, what failed "
        "goes back to the builder; when stuck, the advisor decides; on a pass, the barrier "
        "lifts and the change goes into main. The retro turns lessons into stricter rules for "
        "the next plan. A dot shows one change travelling: it fails once, then passes.")


def who_holds_the_key(theme: str) -> str:
    s = Scene(theme, 1120, 620, origin=(560, 360), scale=0.8)
    s.grid(420)
    s.caption(40, 48, "WHO HOLDS THE KEY",
              "the AI builds in its room; only the server can let a change in")
    s.platform(-310, -175, -60, 175, "ai")
    s.platform(60, -175, 340, 175, "server")
    # The change goes in on one lane; pass or fail comes back on the other.
    s.lane([(-150, -16), (214, -16)], "the change", at=0.78)
    s.lane([(214, 26), (-150, 26)], "pass or fail", at=0.82, side=True)
    s.prism(-6, -175, 6, -82, 8, 50, "neutral")                     # the wall, back half
    s.vault(170, -110)
    s.server(260, 10, levels=3, size=80)
    s.room(-190, 0, "ai", size=110)
    s.booth(0, -58, arm_to=62, axis="y")
    s.prism(-6, 64, 6, 175, 8, 50, "neutral")                       # the wall, front half
    s.text(-300, 60, 140, "THE AI'S ROOM", ["writes code, runs tests", "no key to the server"])
    s.text(170, -110, 110, "LOCKED TESTS", "nobody can change them")
    s.text(320, 90, -10, "MAIN", "only a pass goes in", "start")
    s.text(0, -58, 140, "THE GATE", "runs the locked tests")
    s.leg([s.iso(x, y, 2) for x, y in [(-150, -16), (-22, -16)]], wait=0.9)
    s.leg([s.iso(x, y, 2) for x, y in [(-22, -16), (214, -16)]], "pass", wait=0.6)
    dur, times = s.ticket(start_wait=0.6, rest=1.2)
    s.lift("arm", dur, times[0][1] + 0.3, times[1][1])
    return s.render(
        "The AI's room and the server",
        "An isometric scene in two parts with a wall between them. On the left, the AI's room: "
        "the AI writes code and runs tests there, with no key to the server. On the right, the "
        "server: it holds the locked tests, which nobody can change, and the main branch. The "
        "only way through the wall is the gate. A change goes in on one lane; the gate runs the "
        "locked tests, and pass or fail comes back on the other. On a pass the barrier lifts.")


def packaging(theme: str) -> str:
    s = Scene(theme, 1120, 600, origin=(560, 330), scale=0.78)
    s.grid(420)
    s.caption(40, 48, "WHERE EACH PART RUNS", "a plugin on your machine, one workflow on the server")
    s.platform(-330, -170, -60, 170, "you")
    s.platform(60, -170, 330, 170, "server")
    s.lane([(-130, -30), (140, -30)], "starts", at=0.5)
    s.lane([(140, 40), (-130, 40)], "reports back", at=0.5, side=True)
    s.vault(150, -100)
    s.server(240, 10, levels=2, size=76)
    s.booth(200, 120, arm_to=120, axis="x", arm_class="still")
    s.papers(-270, -90, "you")
    s.prism(-200, -36, -136, 28, 8, 70, "ai")
    s.badge(-168, -4, 112, "package", "ai")
    s.laptop(-260, 100, "you")
    s.text(-120, 250, -20, "YOUR MACHINE: THE PLUGIN",
           ["the skills you type in Claude Code", "the driver that runs the steps",
            "the instructions for each AI role"], "end")
    s.text(380, 60, -20, "THE SERVER: ONE WORKFLOW",
           ["the freeze locks the tests", "the gate runs them on every change"], "start")
    return s.render(
        "Where each part runs",
        "An isometric scene in two parts. On your machine runs the plugin: the skills you type "
        "in Claude Code, the driver that runs the steps, and the instructions for each AI role. "
        "On the server runs one workflow: the freeze that locks the tests, and the gate that "
        "runs them. The plugin starts the workflow, and the workflow reports back.")


def home(theme: str) -> str:
    s = Scene(theme, 1120, 640, origin=(500, 330), scale=0.74)
    s.grid(480)
    s.caption(40, 48, "A HOME WITH THREE PROJECTS",
              "one private repository holds the list and the shared rules")
    spots = [(170, -250, "A"), (170, 0, "B"), (170, 250, "C")]
    for _, y, _ in spots:
        s.lane([(-160, 0), (40, 0), (40, y), (90, y)] if y else [(-160, 0), (90, 0)],
               "shared rules" if y == -250 else None, at=0.55)
    s.platform(-330, -120, -100, 120, "you")
    s.house(-215, 0, "you", size=110)
    for x, y, name in spots:
        s.platform(x - 80, y - 90, x + 140, y + 90, "server")
        s.server(x + 40, y - 20, levels=2, size=64)
        s.booth(x + 40, y + 52, arm_to=x - 60, axis="x", arm_class="still")
        s.text(x + 170, y + 30, 0, f"PROJECT {name}", "its own rules and gate", "start")
    s.text(-330, 140, 30, "HOME", ["the list of projects", "and the rules they share"], "end")
    return s.render(
        "A home with three projects",
        "An isometric scene. A home repository holds the list of projects and the rules they "
        "share. Lanes carry the shared rules to three projects. Each project keeps its own "
        "rules and its own gate.")

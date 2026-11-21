"""Tollgate's own icons: simple line icons on a 24 by 24 grid, drawn for this project.

Each icon is a list of SVG path strings, stroked with round ends and no fill.
`icon(name, x, y, size, color)` returns the SVG for one icon at that place.

    from diagram.icons import ICONS, icon
"""

ICONS = {
    # Who acts.
    "person": ["M12 4.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z", "M5 20.5c0-3.9 3.1-7 7-7s7 3.1 7 7"],
    "ai": ["M11 3.5l1.9 5.1L18 10.5l-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9z",
           "M18.5 15l.8 2.2l2.2.8l-2.2.8l-.8 2.2l-.8-2.2l-2.2-.8l2.2-.8z"],
    "server": ["M4.5 4h15a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
               "M4.5 13h15a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1z",
               "M7.5 7.5h.01M7.5 16.5h.01M11.5 7.5h5M11.5 16.5h5"],
    "check": ["M12 3l7.5 3v5.5c0 4.4-3.2 8.2-7.5 9.5c-4.3-1.3-7.5-5.1-7.5-9.5V6z", "M8.8 12l2.2 2.2l4.3-4.4"],
    "advisor": ["M4 4.5h16v11H10l-4.5 4v-4H4z", "M8 8.5h8M8 11.5h5"],
    # Things.
    "lock": ["M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z",
             "M8 11V8a4 4 0 0 1 8 0v3", "M12 15v2.5"],
    "gate": ["M3.5 8h3v12.5h-3z", "M6.5 10h14v3h-14z", "M10 10l-2 3M14 10l-2 3M18 10l-2 3",
             "M2 20.5h20"],
    "test": ["M9 3h6", "M10 3v6.5l-5.2 8.7A1.9 1.9 0 0 0 6.4 21h11.2a1.9 1.9 0 0 0 1.6-2.8L14 9.5V3",
             "M7.4 15h9.2"],
    "plan": ["M6 3h8.5L19 7.5V21H6z", "M14.5 3v4.5H19", "M9 12h7M9 15.5h7M9 19h4"],
    "ticket": ["M3.5 7h17v3.2a1.8 1.8 0 0 0 0 3.6V17h-17v-3.2a1.8 1.8 0 0 0 0-3.6z",
               "M15 7v2M15 11v2M15 15v2"],
    "branch": ["M6 4a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 16a2 2 0 1 0 0 4a2 2 0 1 0 0-4z",
               "M18 6a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 8v8", "M18 10c0 4-5 4-11 6.5"],
    "pull-request": ["M6 4a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 16a2 2 0 1 0 0 4a2 2 0 1 0 0-4z",
                     "M18 16a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 8v8", "M18 16v-6a3 3 0 0 0-3-3h-4",
                     "M13 4.5L10.5 7L13 9.5"],
    "merge": ["M6 4a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 16a2 2 0 1 0 0 4a2 2 0 1 0 0-4z",
              "M18 10a2 2 0 1 0 0 4a2 2 0 1 0 0-4z", "M6 8v8", "M6 8c0 3 4 4 10 4"],
    "retro": ["M4 20.5h16", "M7 17v-4M12 17V8M17 17v-6.5", "M5 9l5-4.5l4 3l5-4"],
    "retry": ["M4 4.5v5h5", "M4.8 9.5A7.5 7.5 0 1 1 6 16.2"],
    "home": ["M3.5 11L12 4l8.5 7", "M5.5 9.5V20h13V9.5", "M10 20v-5.5h4V20"],
    "folder": ["M3.5 6h6l2 2h9v11.5h-17z"],
    "package": ["M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M4 7.5l8 4.5l8-4.5", "M12 12v9"],
    "workflow": ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M10 8.5v7l6-3.5z"],
    "cost": ["M12 3.5a8.5 8.5 0 1 0 0 17a8.5 8.5 0 1 0 0-17z",
             "M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5c-1.4 0-2.5.8-2.5 2s1.1 1.6 2.5 2s2.5.9 2.5 2s-1.1 2-2.5 2c-1 0-2-.5-2.5-1.5",
             "M12 6.5V8M12 16v1.5"],
    "warning": ["M12 3.5l9.5 17h-19z", "M12 10v5", "M12 18h.01"],
    "clock": ["M12 3.5a8.5 8.5 0 1 0 0 17a8.5 8.5 0 1 0 0-17z", "M12 7.5V12l3 2"],
    "terminal": ["M3.5 4.5h17v15h-17z", "M7 9l3 3l-3 3", "M12.5 15H17"],
}

# The icon a box gets from its kind, when it names none.
FOR_KIND = {"you": "person", "ai": "ai", "server": "server", "check": "check", "advisor": "advisor"}


def icon(name: str, x: float, y: float, size: float, color: str, width: float = 1.7) -> str:
    """The icon as an SVG group, its top-left corner at x, y."""
    scale = size / 24
    paths = "".join(f'<path d="{d}"/>' for d in ICONS[name])
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({scale:.4f})" fill="none" '
            f'stroke="{color}" stroke-width="{width / scale:.2f}" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</g>')

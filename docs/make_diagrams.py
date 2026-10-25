"""Generates the SVG diagrams for the phase-1 documentation.

Run:  python make_diagrams.py
Output: diagramy/*.svg
"""
from __future__ import annotations

import os

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagramy")
FONT = "'Segoe UI',Arial,sans-serif"

COLORS = {
    "terminal": ("#e8f5e9", "#2e7d32"),
    "process": ("#eef4fb", "#2b5d8a"),
    "decision": ("#fff8e6", "#b7791f"),
    "error": ("#fdecec", "#b03a3a"),
    "note": ("#f4f5f7", "#8a8f98"),
    "actor": ("#eef4fb", "#2b5d8a"),
}
ARROW = "#33475b"
TEXT = "#1b2430"

DEFS = (
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
    'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{ARROW}"/></marker></defs>'
)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}">',
        DEFS,
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]


def svg_close() -> str:
    return "</svg>"


def text_at(x: float, y: float, lines, size: float = 14, weight: str = "normal",
            anchor: str = "middle", fill: str = TEXT) -> str:
    if isinstance(lines, str):
        lines = [lines]
    line_height = size * 1.32
    first = y - (len(lines) - 1) * line_height / 2
    out = [f'<text text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" '
           f'fill="{fill}">']
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        out.append(f'<tspan x="{x}" y="{first + dy}">{esc(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def node(cx: float, cy: float, width: float, height: float, lines,
         kind: str = "process", size: float = 15) -> str:
    fill, stroke = COLORS[kind]
    if kind == "decision":
        points = (f"{cx},{cy - height / 2} {cx + width / 2},{cy} "
                  f"{cx},{cy + height / 2} {cx - width / 2},{cy}")
        shape = f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="1.7"/>'
    else:
        radius = 12 if kind == "terminal" else 8
        shape = (f'<rect x="{cx - width / 2}" y="{cy - height / 2}" width="{width}" '
                 f'height="{height}" rx="{radius}" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.7"/>')
    return shape + text_at(cx, cy, lines, size)


def arrow(points, label: str | None = None, label_at=None, label_size: float = 13.5,
          dashed: bool = False, color: str = ARROW) -> str:
    d = " ".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    out = [f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.8"'
           f'{dash} marker-end="url(#arrow)"/>']
    if label and label_at:
        x, y = label_at
        width = len(label) * label_size * 0.55 + 10
        out.append(f'<rect x="{x - width / 2}" y="{y - label_size * 0.9}" width="{width}" '
                   f'height="{label_size * 1.35}" fill="#ffffff" opacity="0.92"/>')
        out.append(text_at(x, y, label, label_size))
    return "".join(out)


def junction(x: float, y: float) -> str:
    return f'<circle cx="{x}" cy="{y}" r="4.5" fill="{ARROW}"/>'


def save(name: str, parts: list[str]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as handle:
        handle.write("\n".join(parts + [svg_close()]))


# --------------------------------------------------------------------------- #
# 1. Server - receive cycle
# --------------------------------------------------------------------------- #

def flow_server_receive() -> None:
    width, height = 1000, 1040
    cx = 340
    s = svg_open(width, height)

    s.append(node(cx, 55, 400, 56, ["Server: UDP listener", "(bind IP:port)"], "terminal"))
    s.append(node(cx, 170, 400, 60, ["recvfrom() – čakanie na datagram"]))
    s.append(node(cx, 320, 320, 132, ["JSON", "parsovateľný?"], "decision"))
    s.append(node(cx, 485, 320, 132, ["CRC (integrita)", "v poriadku?"], "decision"))
    s.append(node(cx, 625, 400, 72, ["Spracuj správu podľa typu",
                                     "REGISTER / DATA / KEEPALIVE_ACK"]))
    s.append(node(cx, 775, 320, 120, ["Token a hodnoty", "platné?"], "decision"))
    s.append(node(cx, 895, 400, 66, ["Odošli ACK (ak nie je potlačené)", "a zapíš dáta do logu"]))

    s.append(arrow([(cx, 83), (cx, 140)]))
    s.append(arrow([(cx, 200), (cx, 254)]))
    s.append(arrow([(cx, 386), (cx, 419)]))
    s.append(arrow([(cx, 551), (cx, 589)]))
    s.append(arrow([(cx, 661), (cx, 715)]))
    s.append(arrow([(cx, 835), (cx, 862)]))

    # loop back
    s.append(arrow([(cx, 928), (cx, 975), (70, 975), (70, 170), (138, 170)]))
    s.append(text_at(190, 960, "ďalší datagram", 12))

    # error branches
    s.append(node(805, 320, 300, 70, ["Zahodí datagram", "SYSTEM | WARNING"], "error", 14.5))
    s.append(arrow([(cx + 160, 320), (655, 320)], "nie", (600, 303)))

    s.append(node(805, 485, 300, 78, ["Integrity check failed", "odošli RETRANSMIT"], "error", 14.5))
    s.append(arrow([(cx + 160, 485), (655, 485)], "nie", (600, 468)))

    s.append(node(805, 775, 300, 70, ["Odošli NACK", "SYSTEM | WARNING"], "error", 14.5))
    s.append(arrow([(cx + 160, 775), (655, 775)], "nie", (600, 758)))

    # return bus from error handlers back into recvfrom()
    s.append('<polyline points="955,775 955,110 530,110 530,139" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    for y in (320, 485, 775):
        s.append(f'<line x1="955" y1="{y}" x2="970" y2="{y}" stroke="{ARROW}" stroke-width="1.8"/>')

    s.append(text_at(354, 402, "áno", 12, anchor="start"))
    s.append(text_at(354, 570, "áno", 12, anchor="start"))
    s.append(text_at(354, 848, "áno", 12, anchor="start"))
    save("flow_server_receive.svg", s)


# --------------------------------------------------------------------------- #
# 2. Server - idle monitor
# --------------------------------------------------------------------------- #

def flow_server_monitor() -> None:
    width, height = 1000, 960
    cx = 330
    s = svg_open(width, height)

    s.append(node(cx, 50, 400, 54, ["Idle monitor – každých 0,2 s"], "terminal"))
    s.append(node(cx, 140, 400, 54, ["Prejdi všetky aktívne relácie"]))
    s.append(node(cx, 270, 340, 118, ["≥ 15 s bez dát", "od senzora?"], "decision"))
    s.append(node(cx, 425, 360, 128, ["SENSOR IDLE už", "nahlásené?"], "decision"))
    s.append(node(cx, 580, 360, 128, ["Probe je naplánovaný", "a nastal jeho čas?"], "decision"))
    s.append(node(cx, 735, 340, 118, ["Odoslaných KEEPALIVE", "≥ 3?"], "decision"))
    s.append(node(cx, 870, 400, 66, ["SENSOR DISCONNECTED", "zneplatni token, zruš reláciu"], "error", 14.5))

    s.append(arrow([(cx, 77), (cx, 113)]))
    s.append(arrow([(cx, 167), (cx, 211)]))
    s.append(arrow([(cx, 329), (cx, 361)]))
    s.append(arrow([(cx, 489), (cx, 516)]))
    s.append(arrow([(cx, 644), (cx, 676)]))
    s.append(arrow([(cx, 794), (cx, 837)]))

    s.append(node(810, 425, 300, 76, ["log SENSOR IDLE", "naplánuj prvý KEEPALIVE"], "process", 14.5))
    s.append(arrow([(cx + 180, 425), (660, 425)], "nie", (600, 408)))
    s.append('<polyline points="810,463 810,510 330,510 330,516" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')

    s.append(node(810, 735, 300, 76, ["odošli KEEPALIVE", "naplánuj ďalší o +5 s"], "process", 14.5))
    s.append(arrow([(cx + 170, 735), (660, 735)], "nie", (600, 718)))
    s.append('<polyline points="810,773 810,905 70,905 70,140 130,140" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')

    s.append('<polyline points="160,270 70,270 70,905" fill="none" stroke="#33475b" stroke-width="1.8"/>')
    s.append('<polyline points="150,580 70,580" fill="none" stroke="#33475b" stroke-width="1.8"/>')
    s.append(text_at(150, 253, "nie", 12, anchor="end"))
    s.append(text_at(150, 563, "nie", 12, anchor="end"))
    s.append(text_at(400, 502, "áno", 12, anchor="start"))
    s.append(text_at(352, 812, "áno", 12, anchor="start"))
    save("flow_server_monitor.svg", s)


# --------------------------------------------------------------------------- #
# 3. Tester - send cycle
# --------------------------------------------------------------------------- #

def flow_tester_send() -> None:
    width, height = 1000, 1150
    cx = 330
    s = svg_open(width, height)

    s.append(node(cx, 50, 420, 54, ["Relácia aktívna, odosielanie zapnuté"], "terminal"))
    s.append(node(cx, 145, 420, 58, ["Čakaj 10 s (alebo okamžite", "po zapnutí odosielania)"]))
    s.append(node(cx, 245, 420, 58, ["Zostav DATA (seq, token, hodnoty)", "alebo vlastné hodnoty zadané používateľom"]))
    s.append(node(cx, 365, 320, 108, ["error injection", "nastavená?"], "decision"))
    s.append(node(cx, 480, 400, 58, ["Odošli správu (pokus n)"]))
    s.append(node(cx, 575, 400, 58, ["Čakaj na ACK max. 3 s"]))
    s.append(node(cx, 700, 320, 108, ["ACK prijaté?"], "decision"))
    s.append(node(cx, 825, 320, 108, ["NACK?"], "decision"))
    s.append(node(cx, 950, 320, 108, ["pokus < 3?"], "decision"))
    s.append(node(cx, 1075, 420, 62, ["Zahoď správu po 3 pokusoch"], "error", 14.5))

    s.append(arrow([(cx, 77), (cx, 116)]))
    s.append(arrow([(cx, 174), (cx, 216)]))
    s.append(arrow([(cx, 274), (cx, 311)]))
    s.append(arrow([(cx, 419), (cx, 451)]))
    s.append(arrow([(cx, 509), (cx, 546)]))
    s.append(arrow([(cx, 604), (cx, 646)]))
    s.append(arrow([(cx, 754), (cx, 771)]))
    s.append(arrow([(cx, 879), (cx, 896)]))
    s.append(arrow([(cx, 1004), (cx, 1044)]))

    s.append(node(810, 365, 290, 70, ["Poškodí datagram", "CRC už neplatí"], "note", 14.5))
    s.append(arrow([(cx + 160, 365), (665, 365)], "áno", (600, 348)))
    s.append('<polyline points="810,400 810,430 330,430" fill="none" stroke="#33475b" stroke-width="1.8"/>')
    s.append(junction(330, 430))

    s.append(node(810, 700, 290, 60, ["Ďalší cyklus"], "process", 14.5))
    s.append(arrow([(cx + 160, 700), (665, 700)], "áno", (600, 683)))

    s.append(node(810, 825, 290, 66, ["Zahoď správu", "log ERROR"], "error", 14.5))
    s.append(arrow([(cx + 160, 825), (665, 825)], "áno", (600, 808)))

    s.append('<polyline points="330,1004 60,1004 60,480 130,480" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    s.append(text_at(70, 520, "áno – odošli znova", 12, anchor="start"))
    s.append(text_at(70, 540, "rovnaké seq, max. 3 pokusy", 12, anchor="start"))
    s.append(text_at(150, 933, "áno", 12, anchor="end"))
    s.append(text_at(352, 1018, "nie", 12, anchor="start"))
    s.append(text_at(352, 759, "nie", 12, anchor="start"))
    s.append(text_at(352, 884, "nie", 12, anchor="start"))

    s.append('<polyline points="955,700 975,700 975,145 540,145" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    for y in (700, 825):
        s.append(f'<line x1="955" y1="{y}" x2="975" y2="{y}" stroke="{ARROW}" stroke-width="1.8"/>')
    s.append('<polyline points="540,1075 975,1075 975,700" fill="none" stroke="#33475b" stroke-width="1.8"/>')
    save("flow_tester_send.svg", s)


# --------------------------------------------------------------------------- #
# 4. Tester - receive cycle
# --------------------------------------------------------------------------- #

def flow_tester_receive() -> None:
    width, height = 1000, 900
    cx = 330
    s = svg_open(width, height)

    s.append(node(cx, 50, 400, 54, ["UDP receiver vlákno (tester)"], "terminal"))
    s.append(node(cx, 140, 400, 58, ["recvfrom() – čakanie na datagram"]))
    s.append(node(cx, 270, 340, 118, ["JSON a CRC", "v poriadku?"], "decision"))
    s.append(node(cx, 420, 340, 118, ["typ správy =", "KEEPALIVE?"], "decision"))
    s.append(node(cx, 575, 380, 78, ["ACK / NACK / RETRANSMIT", "priraď k senzoru podľa sensor_id a seq"]))
    s.append(node(cx, 690, 380, 66, ["aktualizuj last_server_contact", "watchdog 30 s"]))

    s.append(arrow([(cx, 77), (cx, 111)]))
    s.append(arrow([(cx, 169), (cx, 211)]))
    s.append(arrow([(cx, 329), (cx, 361)]))
    s.append(arrow([(cx, 479), (cx, 536)]))
    s.append(arrow([(cx, 614), (cx, 657)]))

    s.append(arrow([(cx, 723), (cx, 760), (70, 760), (70, 140), (130, 140)]))
    s.append(text_at(180, 748, "ďalší datagram", 12))

    s.append(node(790, 270, 300, 66, ["Zahoď datagram", "SYSTEM WARNING"], "error", 14.5))
    s.append(arrow([(cx + 170, 270), (640, 270)], "nie", (585, 253)))

    s.append(node(760, 420, 260, 118, ["token platný a", "relácia aktívna?"], "decision", 14.5))
    s.append(arrow([(cx + 170, 420), (630, 420)], "áno", (570, 403)))
    s.append(text_at(352, 512, "nie", 12, anchor="start"))

    s.append(node(760, 565, 290, 70, ["odošli KEEPALIVE_ACK", "obnov watchdog 30 s"], "process", 14.5))
    s.append(arrow([(760, 479), (760, 530)], "áno", (745, 503)))

    s.append(node(760, 690, 250, 64, ["ignoruj + WARNING"], "error", 14.5))
    s.append('<polyline points="890,420 935,420 935,690 885,690" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    s.append(text_at(925, 402, "nie", 12))

    s.append('<polyline points="955,690 975,690 975,100 530,100 530,139" fill="none" '
             f'stroke="{ARROW}" stroke-width="1.8" marker-end="url(#arrow)"/>')
    for y, x0 in ((270, 940), (565, 905), (690, 885)):
        s.append(f'<line x1="{x0}" y1="{y}" x2="975" y2="{y}" stroke="{ARROW}" stroke-width="1.8"/>')
    save("flow_tester_receive.svg", s)


# --------------------------------------------------------------------------- #
# 5. Sequence diagram - UAT 1
# --------------------------------------------------------------------------- #

def seq_uat1() -> None:
    width, height = 900, 960
    s = svg_open(width, height)
    lifelines = [
        (85, ["Server"]),
        (270, ["ThermoNode", "T-01"]),
        (455, ["WindSense", "W-01"]),
        (640, ["RainDetect", "R-01"]),
        (825, ["AirQuality", "A-01"]),
    ]
    top = 52
    bottom = height - 30
    for x, lines in lifelines:
        s.append(node(x, top, 126, 50, lines, "actor", 13))
        s.append(f'<line x1="{x}" y1="{top + 25}" x2="{x}" y2="{bottom}" stroke="#7d8a99" '
                 f'stroke-width="1.2" stroke-dasharray="6 5"/>')
    server_x = 85

    s.append('<rect x="30" y="100" width="840" height="38" rx="6" fill="#f4f5f7" '
             'stroke="#8a8f98" stroke-width="1"/>')
    s.append(text_at(450, 119, "Tester (jeden proces) emuluje všetky 4 senzory; po registrácii "
                               "sa automatické odosielanie zapne.", 13.5))

    y = 172
    for x, _ in lifelines[1:]:
        s.append(arrow([(x, y), (server_x + 8, y)], "REGISTER", (server_x + 65, y - 13), 13.5))
        y += 27
    y = 280
    for x, _ in lifelines[1:]:
        s.append(arrow([(server_x + 8, y), (x, y)], "ACK + token", (server_x + 65, y - 13),
                       13.5, dashed=True))
        y += 27

    s.append(text_at(450, 448, "automatické odosielanie dát každých 10 s", 14, "bold", fill="#2b5d8a"))

    def cycle(start_y: float) -> float:
        y = start_y
        for x, _ in lifelines[1:]:
            s.append(arrow([(x, y), (server_x + 8, y)], "DATA", (server_x + 55, y - 12), 12.5))
            y += 23
        y += 12
        for x, _ in lifelines[1:]:
            s.append(arrow([(server_x + 8, y), (x, y)], "ACK", (server_x + 55, y - 12),
                           12.5, dashed=True))
            y += 23
        return y

    y = cycle(478)
    s.append(text_at(450, y + 20, "… každých 10 s (ten istý cyklus sa opakuje)", 12.5,
                     fill="#55606e"))
    y = cycle(y + 55)
    s.append(text_at(450, y + 18, "…", 13))
    save("seq_uat1.svg", s)


# --------------------------------------------------------------------------- #
# 6. Sequence diagram - UAT 2
# --------------------------------------------------------------------------- #

def seq_uat2() -> None:
    width, height = 880, 760
    s = svg_open(width, height)
    lifelines = [
        (85, ["Server"]),
        (415, ["ThermoNode", "T-01"]),
        (795, ["WindSense", "W-01"]),
    ]
    top = 52
    bottom = height - 30
    for x, lines in lifelines:
        s.append(node(x, top, 150, 50, lines, "actor", 13))
        s.append(f'<line x1="{x}" y1="{top + 25}" x2="{x}" y2="{bottom}" stroke="#7d8a99" '
                 f'stroke-width="1.2" stroke-dasharray="6 5"/>')
    server_x = 85

    s.append('<rect x="30" y="100" width="820" height="38" rx="6" fill="#f4f5f7" '
             'stroke="#8a8f98" stroke-width="1"/>')
    s.append(text_at(440, 119, "Automatické odosielanie je zapnuté pre všetky senzory.", 13.5))

    s.append(arrow([(415, 175), (server_x + 8, 175)], "DATA (automaticky)",
                   ((415 + server_x) / 2, 162), 13.5))
    s.append(arrow([(server_x + 8, 205), (415, 205)], "ACK", ((415 + server_x) / 2, 192),
                   13.5, dashed=True))

    s.append(arrow([(795, 250), (server_x + 8, 250)], "DATA (automaticky)",
                   ((795 + server_x) / 2, 237), 13.5))
    s.append(arrow([(server_x + 8, 280), (795, 280)], "ACK", ((795 + server_x) / 2, 267),
                   13.5, dashed=True))

    s.append('<rect x="290" y="318" width="250" height="50" rx="6" fill="#fff8e6" '
             'stroke="#b7791f" stroke-width="1.2"/>')
    s.append(text_at(415, 343, ["používateľ zadá vlastné", "hodnoty pre T-01"], 12.5))

    s.append(arrow([(415, 408), (server_x + 8, 408)],
                   "DATA (custom=true, vlastné hodnoty)", ((415 + server_x) / 2, 395), 13.5))
    s.append(arrow([(server_x + 8, 438), (415, 438)], "ACK", ((415 + server_x) / 2, 425),
                   13.5, dashed=True))

    s.append(arrow([(795, 500), (server_x + 8, 500)], "DATA (automaticky)",
                   ((795 + server_x) / 2, 487), 13.5))
    s.append(arrow([(server_x + 8, 530), (795, 530)], "ACK", ((795 + server_x) / 2, 517),
                   13.5, dashed=True))

    s.append(arrow([(795, 595), (server_x + 8, 595)], "DATA (automaticky)",
                   ((795 + server_x) / 2, 582), 13.5))
    s.append(arrow([(server_x + 8, 625), (795, 625)], "ACK", ((795 + server_x) / 2, 612),
                   13.5, dashed=True))

    s.append(text_at(440, 690, "Automatické odosielanie ostatných senzorov pokračuje bez prerušenia.",
                     12.5, fill="#55606e"))
    save("seq_uat2.svg", s)


# --------------------------------------------------------------------------- #
# 7. Measured JSON message sizes / composition
# --------------------------------------------------------------------------- #

def chart_sizes() -> None:
    width, height = 1000, 470
    s = svg_open(width, height)
    s.append(text_at(500, 32, "Veľkosti správ JSON protokolu (merané na implementácii, bez L2–L4)",
                     13, "bold"))
    left, bottom = 110, 400
    chart_h = 300
    max_value = 200
    bars = [
        ("DATA\nThermoNode", 197, "#2b5d8a"),
        ("DATA\nWindSense", 197, "#2b5d8a"),
        ("DATA\nRainDetect", 196, "#2b5d8a"),
        ("DATA\nAirQuality", 172, "#2b5d8a"),
        ("ACK", 98, "#6d8fb3"),
        ("REGISTER", 90, "#6d8fb3"),
        ("KEEPALIVE", 119, "#b7791f"),
        ("RETRANSMIT", 99, "#b03a3a"),
    ]
    bar_w = 78
    gap = 34
    total = len(bars) * bar_w + (len(bars) - 1) * gap
    start = left + (width - left - 40 - total) / 2
    s.append(f'<line x1="{left}" y1="{bottom}" x2="{width - 40}" y2="{bottom}" '
             f'stroke="#33475b" stroke-width="1.4"/>')
    s.append(f'<line x1="{left}" y1="{bottom}" x2="{left}" y2="{bottom - chart_h - 10}" '
             f'stroke="#33475b" stroke-width="1.4"/>')
    for tick in range(0, 201, 50):
        y = bottom - tick / max_value * chart_h
        s.append(f'<line x1="{left}" y1="{y}" x2="{width - 40}" y2="{y}" stroke="#e3e8ef" stroke-width="1"/>')
        s.append(text_at(left - 12, y, str(tick), 12, anchor="end"))
    s.append(text_at(30, bottom - chart_h / 2, "bajty", 13.5, anchor="middle"))
    for index, (label, value, color) in enumerate(bars):
        x = start + index * (bar_w + gap)
        h = value / max_value * chart_h
        s.append(f'<rect x="{x}" y="{bottom - h}" width="{bar_w}" height="{h}" fill="{color}" rx="3"/>')
        s.append(text_at(x + bar_w / 2, bottom - h - 14, f"{value} B", 13.5, "bold"))
        s.append(text_at(x + bar_w / 2, bottom + 20, label.split("\n"), 12.5))
    s.append(text_at(500, height - 18, "Hodnoty sú dĺžky JSON správy vrátane CRC32 (pole \"crc\").",
                     10.5, fill="#55606e"))
    save("chart_message_sizes.svg", s)


def chart_composition() -> None:
    width, height = 1000, 330
    s = svg_open(width, height)
    s.append(text_at(500, 34, "Jedno meranie ThermoNode na úrovni L2: 379 B", 15.5, "bold"))
    total = 379
    segments = [
        ("dátová časť JSON – 79 B (20,8 %)", 79, "#2e7d32"),
        ("manažment JSON – 216 B (57,0 %)", 216, "#b7791f"),
        ("hlavičky Eth/IP/UDP – 84 B (22,2 %)", 84, "#2b5d8a"),
    ]
    x = 60
    width_total = 880
    for label, value, color in segments:
        w = value / total * width_total
        s.append(f'<rect x="{x}" y="70" width="{w}" height="70" fill="{color}"/>')
        if w > 90:
            s.append(text_at(x + w / 2, 105, f"{value} B", 14, "bold", fill="#ffffff"))
        x += w
    y = 180
    for label, value, color in segments:
        s.append(f'<rect x="60" y="{y}" width="16" height="16" fill="{color}" rx="2"/>')
        s.append(text_at(86, y + 8, label, 13.5, anchor="start"))
        y += 30
    s.append(text_at(60, 285, "DATA 197 B + ACK 98 B + 2× hlavičky L2–L4 (2×42 B) = 379 B "
                              "na jedno meranie.", 13, anchor="start", fill="#55606e"))
    save("chart_composition.svg", s)


if __name__ == "__main__":
    flow_server_receive()
    flow_server_monitor()
    flow_tester_send()
    flow_tester_receive()
    seq_uat1()
    seq_uat2()
    chart_sizes()
    chart_composition()
    print("diagrams written to", OUT_DIR)






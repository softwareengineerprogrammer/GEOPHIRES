"""
Figures for docs/Coupled-Wellbore-Model.md: flowcharts and schematics written as SVG directly, and physics plots of the
example wells drawn with matplotlib from superhot-wellbore and CoolProp.

Run with the GEOPHIRES development environment and superhot-wellbore installed:

    python src/geophires_docs/generate_coupled_wellbore_docs_figures.py

The physics plots solve the example wells with superhot-wellbore (tens of seconds each); the flowcharts need neither.
Output goes to docs/_images/coupled-wellbore-*.svg.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
import numpy as np

from geophires_x.Model import Model
from geophires_x.SurfacePlantCoupledWellbore import LIQUID_CORRELATION_MAX_TEMPERATURE_C
from geophires_x.SurfacePlantCoupledWellbore import SUPERHEAT_MARGIN_KJ_PER_KG
from geophires_x.SurfacePlantCoupledWellbore import WATER_CRITICAL_ENTHALPY_MJ_PER_KG
from geophires_x.SurfacePlantCoupledWellbore import WATER_CRITICAL_PRESSURE_MPA
from geophires_x_client import GeophiresInputParameters

_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / 'docs' / '_images'
_FIGURE_PREFIX = 'coupled-wellbore-'

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
_INK = '#1f2933'
_MUTED = '#52606d'
_EDGE = '#616e7c'


@dataclass(frozen=True)
class _Style:
    fill: str
    stroke: str
    title: str = _INK
    dash: str | None = None


_STYLES: dict[str, _Style] = {
    # GEOPHIRES code that existed before this model
    'geophires': _Style('#f0f4f8', '#829ab1', '#243b53'),
    # GEOPHIRES code added for this model
    'new': _Style('#e3efff', '#2f6fd1', '#123e7c'),
    # the superhot-wellbore package
    'package': _Style('#e1f5ee', '#2f8f6b', '#0f5132'),
    'plant': _Style('#fff1e0', '#d9822b', '#7a3e00'),
    'decision': _Style('#fffbea', '#c99a06', '#5c4400'),
    'input': _Style('#ffffff', '#9aa5b1', _INK, dash='5 3'),
    'ok': _Style('#e3f9e5', '#3f9142', '#14532d'),
    'warn': _Style('#fff4d6', '#cb6e17', '#7c2d12'),
    'abort': _Style('#ffe3e3', '#cf1124', '#610316'),
    'note': _Style('#fafafa', '#bcccdc', _MUTED),
}


@dataclass(frozen=True)
class _Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def top(self) -> tuple[float, float]:
        return self.cx, self.y

    @property
    def bottom(self) -> tuple[float, float]:
        return self.cx, self.y + self.h

    @property
    def left(self) -> tuple[float, float]:
        return self.x, self.cy

    @property
    def right(self) -> tuple[float, float]:
        return self.x + self.w, self.cy

    def at(self, fx: float, fy: float) -> tuple[float, float]:
        """Point at fractions (fx, fy) of the box width and height."""
        return self.x + fx * self.w, self.y + fy * self.h


_MARKUP = re.compile(r'([_^])\{([^}]*)\}')


def _rich_text(s: str) -> str:
    """Escape s and turn _{sub} and ^{sup} into tspans."""
    out = []
    pos = 0
    for m in _MARKUP.finditer(s):
        out.append(escape(s[pos : m.start()]))
        shift = 'sub' if m.group(1) == '_' else 'super'
        out.append(f'<tspan baseline-shift="{shift}" font-size="72%">{escape(m.group(2))}</tspan>')
        pos = m.end()
    out.append(escape(s[pos:]))
    return ''.join(out)


def _text_width(s: str, size: float) -> float:
    """Rough rendered width of s in px (for label backgrounds)."""
    plain = _MARKUP.sub(lambda m: m.group(2), s)
    return 0.56 * size * len(plain)


class _Svg:
    def __init__(self, width: float, height: float, title: str, description: str):
        self.width = width
        self.height = height
        self.title = title
        self.description = description
        self._defs: dict[str, str] = {}
        self._parts: list[str] = []

    # -- primitives -------------------------------------------------------------------------------------------------

    def _marker(self, color: str) -> str:
        marker_id = 'arrow-' + color.lstrip('#')
        if marker_id not in self._defs:
            self._defs[marker_id] = (
                f'<marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                f'orient="auto-start-reverse"><path d="M0,0.5 L10,5 L0,9.5 z" fill="{color}"/></marker>'
            )
        return marker_id

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 13,
        color: str = _INK,
        anchor: str = 'middle',
        weight: str = 'normal',
        italic: bool = False,
    ) -> None:
        style = ' font-style="italic"' if italic else ''
        self._parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}"{style}>{_rich_text(s)}</text>'
        )

    def lines(
        self,
        cx: float,
        cy: float,
        lines: list[str],
        size: float = 13,
        color: str = _INK,
        title_color: str | None = None,
        anchor: str = 'middle',
        line_height: float = 1.3,
    ) -> None:
        """
        Vertically centred block of lines. A line starting with '**' is bold (in title_color), one starting with '~'
        is smaller and muted.
        """
        heights = [size * (0.85 if line.startswith('~') else 1.0) * line_height for line in lines]
        y = cy - sum(heights) / 2
        for line, lh in zip(lines, heights):
            y += lh
            if line.startswith('**'):
                self.text(cx, y - lh * 0.27, line[2:], size, title_color or color, anchor, 'bold')
            elif line.startswith('~'):
                self.text(cx, y - lh * 0.27, line[1:], size * 0.85, _MUTED, anchor)
            else:
                self.text(cx, y - lh * 0.27, line, size, color, anchor)

    def node(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        lines: list[str],
        style: str = 'geophires',
        size: float = 13,
        radius: float = 7,
        stroke_width: float = 1.4,
        align: str = 'middle',
    ) -> _Box:
        st = _STYLES[style]
        dash = f' stroke-dasharray="{st.dash}"' if st.dash else ''
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" fill="{st.fill}" '
            f'stroke="{st.stroke}" stroke-width="{stroke_width}"{dash}/>'
        )
        if align == 'start':
            self.lines(x + 12, y + h / 2, lines, size, title_color=st.title, anchor='start')
        else:
            self.lines(x + w / 2, y + h / 2, lines, size, title_color=st.title)
        return _Box(x, y, w, h)

    def terminal(self, x: float, y: float, w: float, h: float, lines: list[str], style: str = 'ok', size=13) -> _Box:
        return self.node(x, y, w, h, lines, style, size, radius=h / 2)

    def decision(self, cx: float, cy: float, w: float, h: float, lines: list[str], size: float = 12.5) -> _Box:
        st = _STYLES['decision']
        points = (
            f'{cx:.1f},{cy - h / 2:.1f} {cx + w / 2:.1f},{cy:.1f} {cx:.1f},{cy + h / 2:.1f} {cx - w / 2:.1f},{cy:.1f}'
        )
        self._parts.append(f'<polygon points="{points}" fill="{st.fill}" stroke="{st.stroke}" stroke-width="1.4"/>')
        self.lines(cx, cy, lines, size, title_color=st.title)
        return _Box(cx - w / 2, cy - h / 2, w, h)

    def container(
        self, x: float, y: float, w: float, h: float, label: str, style: str = 'package', sublabel: str | None = None
    ) -> _Box:
        st = _STYLES[style]
        self._parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="12" fill="{st.fill}" '
            f'fill-opacity="0.45" stroke="{st.stroke}" stroke-width="1.6" stroke-dasharray="7 4"/>'
        )
        self.text(x + 14, y + 22, label, 14, st.title, anchor='start', weight='bold')
        if sublabel:
            self.text(x + 14, y + 39, sublabel, 11.5, _MUTED, anchor='start')
        return _Box(x, y, w, h)

    def arrow(
        self,
        points: list[tuple[float, float]],
        label: str | None = None,
        label_at: tuple[float, float] | None = None,
        color: str = _EDGE,
        dashed: bool = False,
        width: float = 1.5,
        label_anchor: str = 'middle',
        label_size: float = 11.5,
        both: bool = False,
    ) -> None:
        d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in points)
        marker = self._marker(color)
        dash = ' stroke-dasharray="5 4"' if dashed else ''
        start = f' marker-start="url(#{marker})"' if both else ''
        self._parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
            f'marker-end="url(#{marker})"{start}/>'
        )
        if label:
            if label_at is None:
                (x0, y0), (x1, y1) = points[0], points[1]
                label_at = ((x0 + x1) / 2, (y0 + y1) / 2)
            self.edge_label(label_at[0], label_at[1], label, label_anchor, label_size)

    def edge_label(self, x: float, y: float, s: str, anchor: str = 'middle', size: float = 11.5) -> None:
        label_lines = s.split('\n')
        width = max(_text_width(line, size) for line in label_lines) + 8
        height = len(label_lines) * size * 1.25 + 4
        left = x - width / 2 if anchor == 'middle' else (x - 4 if anchor == 'start' else x - width + 4)
        self._parts.append(
            f'<rect x="{left:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" rx="3" '
            'fill="#ffffff" fill-opacity="0.92"/>'
        )
        for i, line in enumerate(label_lines):
            ly = y - height / 2 + 2 + (i + 0.8) * size * 1.25
            self.text(x, ly, line, size, _MUTED, anchor, italic=True)

    def raw(self, svg: str) -> None:
        self._parts.append(svg)

    def legend(self, x: float, y: float, entries: list[tuple[str, str]], size: float = 11.5, gap: float = 18) -> None:
        for i, (style, label) in enumerate(entries):
            st = _STYLES[style]
            yy = y + i * gap
            dash = f' stroke-dasharray="{st.dash}"' if st.dash else ''
            self._parts.append(
                f'<rect x="{x:.1f}" y="{yy - 9:.1f}" width="16" height="11" rx="2.5" fill="{st.fill}" '
                f'stroke="{st.stroke}" stroke-width="1.2"{dash}/>'
            )
            self.text(x + 23, yy, label, size, _MUTED, anchor='start')

    # -- output -----------------------------------------------------------------------------------------------------

    def save(self, name: str) -> Path:
        path = _IMAGES_DIR / f'{_FIGURE_PREFIX}{name}.svg'
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width:.0f} {self.height:.0f}" '
            f'width="{self.width:.0f}" height="{self.height:.0f}" font-family="{_FONT}" role="img" '
            f'aria-labelledby="title desc">\n'
            f'<title id="title">{escape(self.title)}</title>\n<desc id="desc">{escape(self.description)}</desc>\n'
            f'<defs>{"".join(self._defs.values())}</defs>\n'
            # An opaque background, so that the figure reads on dark-themed pages (e.g. GitHub dark mode) too.
            f'<rect width="100%" height="100%" fill="#ffffff"/>\n' + '\n'.join(self._parts) + '\n</svg>\n'
        )
        path.write_text(svg, encoding='utf-8')
        print(f'wrote {path}')
        return path


# ---------------------------------------------------------------------------------------------------------------------
# Figure 1: where the coupled model sits in a GEOPHIRES run
# ---------------------------------------------------------------------------------------------------------------------


def model_chain_figure() -> Path:
    svg = _Svg(
        1000,
        700,
        'Coupled inflow-wellbore model in the GEOPHIRES calculation chain',
        'GEOPHIRES modules run top to bottom; the coupled wellbore model sends one request per production history '
        'to superhot-wellbore and receives a production profile with the wellhead state at every time step.',
    )

    left_x, left_w = 30, 400
    deck = svg.node(
        left_x,
        20,
        left_w,
        54,
        ['**GEOPHIRES input deck', '~Production Wellbore Model, 2 · Power Plant Type, 10'],
        'input',
    )
    reservoir = svg.node(
        left_x,
        104,
        left_w,
        72,
        [
            '**Reservoir model',
            '~any thermal model: Gringarten MPF, user-provided profile, ...',
            'far-field temperature history T_{res}(t)',
        ],
        'geophires',
    )
    standard = svg.node(
        left_x,
        206,
        left_w,
        90,
        [
            '**WellBores: standard pass',
            'far-field pressure history P_{res}(t)',
            '~Reservoir Hydrostatic Pressure × Overpressure, depletion',
            'redrilling: Maximum Drawdown on T_{res}(t) · injection wells',
        ],
        'geophires',
    )
    coupled = svg.node(
        left_x,
        326,
        left_w,
        128,
        [
            '**CoupledWellBores (Production Wellbore Model 2)',
            'Productivity Index → transmissivity k·b',
            'reservoir volume per well → drainage radius r_{e}',
            'operating point: flow rate or target wellhead pressure',
            'solve schedule along P_{res}(t), T_{res}(t) · failure checks',
            '~sets produced temperature, wellhead pressure, pumping',
        ],
        'new',
    )
    plant = svg.node(
        left_x,
        484,
        left_w,
        90,
        [
            '**Surface plant',
            'Power Plant Type 10: Coupled Wellbore Power Cycle',
            '~cycle-only · correlation-first · best-output',
            '~(or a conventional plant type, given Plant Outlet Pressure)',
        ],
        'plant',
    )
    economics = svg.node(
        left_x,
        604,
        left_w,
        72,
        [
            '**Economics',
            '~plant costed as a conventional plant type (by plant path);',
            '~production pumps costed with the standard correlation',
        ],
        'geophires',
    )
    for a, b in ((deck, reservoir), (reservoir, standard), (standard, coupled), (coupled, plant), (plant, economics)):
        svg.arrow([a.bottom, b.top])

    pkg = svg.container(
        550, 196, 430, 480, 'superhot-wellbore', 'package', 'coupled inflow-wellbore simulation (Scott, 2026)'
    )
    px, pw = 572, 386
    inflow = svg.node(
        px,
        254,
        pw,
        60,
        ['**Radial Darcy inflow', '~far-field P_{res}, T_{res} → sandface; k·b, r_{e}, r_{w}'],
        'package',
    )
    entry = svg.node(
        px,
        336,
        pw,
        50,
        ['**Entry into the well', '~isenthalpic expansion to the flowing bottom-hole pressure'],
        'package',
    )
    march = svg.node(
        px,
        408,
        pw,
        64,
        [
            '**Bottom-to-surface wellbore march',
            '~friction · gravity · kinetic energy · heat loss U·(T − T_{rock}(z))',
        ],
        'package',
    )
    pump = svg.node(
        px,
        494,
        pw,
        56,
        ['**Production pump stage', '~when the well does not self-flow (Coupled Wellbore Pump Policy)'],
        'package',
    )
    wellhead = svg.node(
        px,
        572,
        183,
        80,
        ['**Wellhead state', '~P, T, h, phase,', '~steam quality'],
        'package',
    )
    cycle = svg.node(px + 203, 572, 183, 80, ['**Coupled-wellbore', '**power cycle', '~gross power, exergy'], 'package')
    for a, b in ((inflow, entry), (entry, march), (march, pump)):
        svg.arrow([a.bottom, b.top])
    svg.arrow([pump.at(0.24, 1.0), wellhead.top])
    svg.arrow([wellhead.right, cycle.left])

    request_y = coupled.at(1.0, 0.3)[1]
    svg.arrow(
        [coupled.at(1.0, 0.3), (465, request_y), (465, inflow.cy), inflow.left],
        'request',
        label_at=(465, 330),
    )
    svg.arrow(
        [(pkg.x, 640), (505, 640), (505, coupled.at(1.0, 0.76)[1]), coupled.at(1.0, 0.76)],
        'production\nprofile',
        label_at=(505, 560),
    )

    svg.legend(
        640,
        40,
        [
            ('input', 'input'),
            ('geophires', 'existing GEOPHIRES module'),
            ('new', 'GEOPHIRES module added for this model'),
            ('plant', 'surface plant (added: Power Plant Type 10)'),
            ('package', 'superhot-wellbore package'),
        ],
    )
    return svg.save('model-chain')


# ---------------------------------------------------------------------------------------------------------------------
# Figure 2: calculation sequence of CoupledWellBores
# ---------------------------------------------------------------------------------------------------------------------


def calculation_sequence_figure() -> Path:
    svg = _Svg(
        1000,
        1170,
        'Calculation sequence of the coupled inflow-wellbore production wellbore model',
        'Flowchart from reading the parameters through the reservoir model, the operating point, the standard '
        'wellbore pass, the coupled solves along the production history and the failure checks to the surface plant.',
    )
    mx, mw = 90, 480  # main column
    cx = mx + mw / 2
    rx, rw = 650, 320  # right column
    rcx = rx + rw / 2

    read = svg.node(
        mx,
        20,
        mw,
        112,
        [
            '**Read parameters',
            'Redrilling Trigger Temperature → reservoir output temperature',
            'Ramey, constant temperature drop, productivity-index pump',
            'and impedance models → off',
            'Maximum Temperature raised if it would cap the well depth',
            '~a conventional Power Plant Type also requires Plant Outlet Pressure',
        ],
        'new',
    )
    reservoir = svg.node(
        mx, 160, mw, 52, ['**Reservoir model', '~T_{res}(t) at the deck flow rate (Reservoir.Calculate)'], 'geophires'
    )
    initial = svg.node(
        mx,
        240,
        mw,
        88,
        [
            '**Initial far-field state and inflow parameters',
            'P_{res,0} = hydrostatic pressure × Overpressure Percentage',
            'r_{e} = √(V_{res} / (n_{prod} π h_{frac}))   k·b = PI μ ln(r_{e}/r_{w}) / (2π ρ)',
            '~(μ, ρ at P_{res,0}, T_{res,0}; or Coupled Wellbore Feedzone Transmissivity)',
        ],
        'new',
    )
    flow_given = svg.decision(cx, 392, 330, 84, ['Production Flow Rate', 'per Well given?'])
    solve_flow = svg.node(
        rx,
        350,
        rw,
        86,
        [
            '**Solve the operating point',
            'steady state at P_{res,0}, T_{res,0}: flow rate that',
            'delivers the target wellhead pressure',
            '~Production Wellhead Pressure, else 10 MPa',
        ],
        'package',
    )
    rerun = svg.node(
        rx, 462, rw, 56, ['**Re-run the reservoir model', '~T_{res}(t) with the solved flow rate'], 'geophires'
    )
    standard = svg.node(
        mx,
        548,
        mw,
        74,
        [
            '**Standard WellBores pass',
            'P_{res}(t) · redrilling when T_{res} falls by Maximum Drawdown',
            '~(the history is repeated from the trigger) · injection wells and pumps',
        ],
        'geophires',
    )
    period = svg.decision(cx, 686, 330, 84, ['Redrilled, and P_{res}(t)', 'constant?'])
    one_period = svg.node(
        rx, 652, rw, 68, ['**Solve one redrilling period', '~and repeat it for the later periods'], 'new'
    )
    solve = svg.node(
        mx,
        770,
        mw,
        92,
        [
            '**Coupled solves along the history (superhot-wellbore)',
            'held flow rate · far-field P_{res}(t), T_{res}(t)',
            'at most Maximum Solve Points states, interpolated between',
            '~in-process memo keyed on the rounded request',
        ],
        'package',
    )
    ok = svg.decision(
        cx, 928, 360, 92, ['Every solved state succeeded,', 'and no pump flag the envelope', 'policy forbids?']
    )
    abort = svg.terminal(
        rx,
        896,
        rw,
        64,
        ['**Run aborts', '~time, reservoir state, pump flags and remedies'],
        'abort',
    )
    outputs = svg.node(
        mx,
        1000,
        mw,
        78,
        [
            '**Wellbore outputs',
            'produced temperature = wellhead temperature · WHP(t) · ΔP_{res}(t)',
            '~pump power, depth and ΔP → the standard production pumping outputs',
        ],
        'new',
    )
    plant = svg.terminal(
        mx + 40,
        1106,
        mw - 80,
        48,
        ['**Surface plant, then economics', '~Power Plant Type 10 or a conventional plant'],
        'plant',
    )

    svg.arrow([read.bottom, reservoir.top])
    svg.arrow([reservoir.bottom, initial.top])
    svg.arrow([initial.bottom, flow_given.top])
    svg.arrow([flow_given.bottom, standard.top], 'yes: prescribed', label_at=(cx, 490))
    svg.arrow([flow_given.right, solve_flow.left], 'no', label_at=((flow_given.right[0] + rx) / 2, flow_given.cy))
    svg.arrow([solve_flow.bottom, rerun.top])
    svg.arrow([rerun.bottom, (rcx, 585), standard.right])
    svg.arrow([standard.bottom, period.top])
    svg.arrow([period.right, one_period.left], 'yes', label_at=((period.right[0] + rx) / 2, period.cy))
    svg.arrow([period.bottom, solve.top], 'no: whole lifetime', label_at=(cx, 748))
    svg.arrow([one_period.bottom, (rcx, 816), solve.right])
    svg.arrow([solve.bottom, ok.top])
    svg.arrow([ok.right, abort.left], 'no', label_at=((ok.right[0] + rx) / 2, ok.cy))
    svg.arrow([ok.bottom, outputs.top], 'yes', label_at=(cx + 22, 984))
    svg.arrow([outputs.bottom, plant.top])

    svg.legend(
        rx + 20,
        40,
        [
            ('geophires', 'existing GEOPHIRES calculation'),
            ('new', 'CoupledWellBores'),
            ('package', 'superhot-wellbore solve'),
            ('decision', 'decision'),
        ],
    )
    return svg.save('calculation-sequence')


# ---------------------------------------------------------------------------------------------------------------------
# Figure 3: well schematic with the governing equations
# ---------------------------------------------------------------------------------------------------------------------


def well_schematic_figure() -> Path:
    svg = _Svg(
        1000,
        760,
        'Coupled inflow-wellbore model: geometry and governing equations',
        'Schematic of a production well from the feedzone to the wellhead with radial Darcy inflow, the wellbore '
        'control volume, heat loss to the formation, flashing and an optional pump, beside the governing equations.',
    )
    svg.raw(
        '<defs>'
        '<linearGradient id="geotherm" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fdf4e7"/><stop offset="1" stop-color="#f4b183"/></linearGradient>'
        '<pattern id="feedzone" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="8" height="8" fill="#f8d9c4"/><line x1="0" y1="0" x2="0" y2="8" stroke="#d98c5f" '
        'stroke-width="2"/></pattern>'
        '</defs>'
    )
    well_x, top, bottom = 300, 90, 620
    # formation and feedzone
    svg.raw(f'<rect x="40" y="{top}" width="520" height="{bottom - top}" fill="url(#geotherm)"/>')
    svg.raw(f'<rect x="40" y="{bottom}" width="520" height="70" fill="url(#feedzone)"/>')
    svg.raw(f'<line x1="30" y1="{top}" x2="570" y2="{top}" stroke="#52606d" stroke-width="2"/>')
    svg.text(50, top - 8, 'surface', 11.5, _MUTED, anchor='start')
    svg.text(
        50, bottom + 88, 'feedzone: thickness b = Fracture Height, at Reservoir Depth', 11.5, '#7a3e00', anchor='start'
    )
    svg.lines(
        150,
        360,
        [
            '**formation',
            '~T_{rock}(z): the GEOPHIRES gradient',
            '~segments, anchored at the',
            '~bottom-hole temperature;',
            '~fixed over the plant lifetime',
        ],
        12.5,
        title_color='#7a3e00',
    )
    # well (casing inner diameter D)
    svg.raw(
        f'<rect x="{well_x - 11}" y="{top - 26}" width="22" height="{bottom - top + 26 + 70}" fill="#ffffff" '
        'stroke="#334e68" stroke-width="2"/>'
    )
    # wellhead and outflow
    svg.raw(f'<rect x="{well_x - 20}" y="{top - 40}" width="40" height="16" rx="3" fill="#334e68"/>')
    svg.arrow([(well_x + 20, top - 32), (420, top - 32)], color='#d9822b', width=2.2)
    svg.lines(
        428,
        top - 32,
        ['**wellhead → surface plant', '~P_{wh}, h_{wh}, T_{wh}, phase, steam quality'],
        12,
        title_color='#7a3e00',
        anchor='start',
    )
    # flow direction inside the well
    for y in (560, 470, 380, 290, 200):
        svg.arrow([(well_x, y + 26), (well_x, y)], color='#2f8f6b', width=1.6)
    # flashing: bubbles above the flash depth
    flash_y = 250
    for dx, dy, r in (
        (-4, 0, 3),
        (4, -12, 2.5),
        (-3, -26, 3.5),
        (5, -40, 3),
        (-4, -56, 4),
        (3, -75, 4.5),
        (-3, -98, 5),
        (4, -120, 4.5),
    ):
        svg.raw(
            f'<circle cx="{well_x + dx}" cy="{flash_y + dy}" r="{r}" fill="#ffffff" stroke="#2f8f6b" stroke-width="1"/>'
        )
    svg.raw(
        f'<line x1="{well_x + 16}" y1="{flash_y + 6}" x2="{well_x + 70}" y2="{flash_y + 6}" stroke="#2f8f6b" '
        'stroke-dasharray="3 3"/>'
    )
    svg.lines(
        well_x + 76,
        flash_y,
        ['**flash depth', '~P falls to P_{sat}: two-phase above,', '~homogeneous mixture (HEM)'],
        12,
        title_color='#0f5132',
        anchor='start',
    )
    # optional pump
    pump_y = 150
    svg.raw(
        f'<rect x="{well_x - 16}" y="{pump_y - 12}" width="32" height="24" rx="4" fill="#fff4d6" stroke="#cb6e17" '
        'stroke-width="1.6" stroke-dasharray="4 2"/>'
    )
    svg.text(well_x, pump_y + 4, 'P', 12, '#7c2d12', weight='bold')
    svg.lines(
        well_x - 26,
        pump_y,
        ['**pump at z_{p} (when needed)', '~intake: liquid, P ≥ P_{sat} + NPSH margin'],
        12,
        title_color='#7c2d12',
        anchor='end',
    )
    # control volume
    cv_top, cv_bottom = 400, 450
    svg.raw(
        f'<rect x="{well_x - 24}" y="{cv_top}" width="48" height="{cv_bottom - cv_top}" fill="none" stroke="#123e7c" '
        'stroke-width="1.3" stroke-dasharray="4 3"/>'
    )
    svg.text(well_x + 32, cv_top + 14, 'Δz', 12, '#123e7c', anchor='start', weight='bold')
    svg.arrow([(well_x - 26, 425), (well_x - 78, 425)], color='#cf1124', width=1.6)
    svg.text(well_x - 82, 421, "q' = U (T − T_{rock})", 11.5, '#cf1124', anchor='end')
    svg.text(well_x - 82, 437, 'per metre of well', 10.5, _MUTED, anchor='end')
    svg.lines(
        well_x + 32,
        438,
        ['~gravity, friction,', '~kinetic energy'],
        11.5,
        anchor='start',
    )
    # radial inflow
    fz_y = bottom + 30
    for x0, x1 in ((80, well_x - 30), (520, well_x + 30)):
        svg.arrow([(x0, fz_y), (x1, fz_y)], color='#7a3e00', width=2)
    svg.text(well_x, fz_y + 5, 'r_{w}', 11.5, '#7a3e00', weight='bold')
    svg.raw(
        f'<line x1="{well_x + 12}" y1="{bottom + 56}" x2="552" y2="{bottom + 56}" stroke="#7a3e00" stroke-width="1" '
        'marker-end="url(#' + svg._marker('#7a3e00') + ')"/>'
    )
    svg.edge_label(445, bottom + 56, 'r_{e}: drainage radius', size=11)
    svg.edge_label(150, bottom + 12, 'far field (r = r_{e}): P_{res}(t), T_{res}(t)', size=11)
    svg.edge_label(440, bottom + 12, 'radial Darcy inflow, k·b', size=11)

    # equations panel
    ex, ew = 600, 380
    rows = [
        (
            'package',
            [
                '**1  Inflow (steady radial Darcy)',
                'ΔP_{res} = μ ṁ ln(r_{e}/r_{w}) / (2π ρ k b)',
                '~μ, ρ at P_{res} and the feedzone temperature (≤ 3 passes)',
            ],
            70,
        ),
        (
            'package',
            [
                '**2  Entry into the well (isenthalpic)',
                'h_{fz} = h(P_{res}, T_{res});  state (P_{bh}, h_{fz})',
                '~P_{bh} = P_{res} − ΔP_{res}; may flash at the sandface',
            ],
            70,
        ),
        (
            'package',
            [
                '**3  Momentum',
                'dP/dz = −ρ_{m} g − f ρ_{m} v^{2} / (2D)',
                '~f: Swamee–Jain on mixture ρ_{m}, μ_{m}; no acceleration term',
            ],
            70,
        ),
        (
            'package',
            [
                '**4  Energy',
                'dh/dz = −g + (ṁ/A)^{2} ρ^{−3} dρ/dz − U (T − T_{rock}) / ṁ',
                '~U constant in depth and time (default 2.5 W/m/K)',
            ],
            70,
        ),
        (
            'package',
            [
                '**5  Fluid properties',
                'pure water: IAPWS-95 (CoolProp); IAPWS-97',
                'for 21.56–27.06 MPa; two-phase: homogeneous',
                '1/ρ_{m} = x/ρ_{g} + (1 − x)/ρ_{f},  T = T_{sat}(P)',
            ],
            86,
        ),
        (
            'package',
            [
                '**6  Numerics',
                'explicit Euler, bottom → top, Δz = 10 m',
                '~flow held; one steady state per solved time step',
            ],
            62,
        ),
    ]
    y = 30
    for style, lines, h in rows:
        svg.node(ex, y, ew, h, lines, style, size=12.5, align='start')
        y += h + 12
    svg.text(ex, y + 8, 'z positive upward; ṁ per well; A = πD^{2}/4; v = ṁ/(ρA)', 11, _MUTED, anchor='start')
    return svg.save('well-schematic')


# ---------------------------------------------------------------------------------------------------------------------
# Figure 4: production pump stage
# ---------------------------------------------------------------------------------------------------------------------


def pump_stage_figure() -> Path:
    svg = _Svg(
        1000,
        1130,
        'Production pump stage of the coupled wellbore model',
        'Decision flowchart of the superhot-wellbore production pump stage for a prescribed flow rate: self-flow '
        'check, pump intake search, envelope check, target wellhead pressure and pump pressure rise.',
    )
    mx, mw = 70, 470
    cx = mx + mw / 2
    rx, rw = 630, 340

    start = svg.terminal(
        mx + 35, 16, mw - 70, 52, ['**Prescribed flow rate ṁ', '~at a far-field state P_{res}, T_{res}'], 'package'
    )
    inflow = svg.node(
        mx,
        94,
        mw,
        56,
        [
            '**Darcy inflow and isenthalpic entry',
            '~feedzone state (P_{bh}, h_{fz}); the state fails if P_{bh} < 0.5 MPa',
        ],
        'package',
    )
    march = svg.node(
        mx,
        176,
        mw,
        56,
        ['**Unpumped march, feedzone → surface', '~reaches the surface? WHP_{self}'],
        'package',
    )
    self_flow = svg.decision(
        cx,
        314,
        400,
        118,
        [
            "Policy 'never', or policy 'auto'",
            'and the well self-flows',
            '(reaches the surface with',
            'WHP_{self} ≥ floor)?',
        ],
    )
    unpumped = svg.terminal(
        rx,
        268,
        rw,
        92,
        [
            '**Unpumped result',
            '~self-flowing; under never, fails if the',
            '~well does not reach the surface, and',
            '~flags self_flow_below_floor below the floor',
        ],
        'ok',
    )
    svg.node(
        rx,
        392,
        rw,
        66,
        [
            '~floor = Coupled Wellbore Minimum Self-Flow',
            '~Wellhead Pressure, raised to Production',
            '~Wellhead Pressure when given with a flow rate',
        ],
        'note',
        size=12,
    )
    intake = svg.node(
        mx,
        412,
        mw,
        84,
        [
            '**Intake search (walk up from the feedzone)',
            'intake = top of the contiguous column that is',
            'single-phase liquid (ρ ≥ 322 kg/m^{3}) with P ≥ P_{sat}(T) + NPSH margin',
            '~NPSH margin: Coupled Wellbore Pump NPSH Margin (344.7 kPa)',
        ],
        'package',
    )
    found = svg.decision(cx, 562, 300, 76, ['Intake found?'])
    envelope = svg.decision(
        cx, 680, 400, 110, ['Intake depth ≤ Pump Maximum Depth', 'and intake T ≤ Pump Maximum', 'Intake Temperature?']
    )
    policy = svg.node(
        rx,
        548,
        rw,
        168,
        [
            '**Envelope policy (Coupled Wellbore Pump Envelope)',
            '~flags: no_liquid_intake + two_phase_at_sandface,',
            '~or depth_limit / temperature_limit + pump_outside_envelope',
            'flag: pump modelled anyway (no intake:',
            'unpumped result, success if it reached the surface)',
            'enforce: the state fails',
            'omit: unpumped well left below the floor if it',
            'reaches the surface; otherwise the state fails',
        ],
        'warn',
        size=12,
        align='start',
    )
    target = svg.node(
        mx,
        770,
        mw,
        70,
        [
            '**Pump target WHP',
            'Production Wellhead Pressure (with a prescribed flow rate),',
            'else P_{sat}(T_{intake}) + NPSH margin',
        ],
        'package',
    )
    zero = svg.decision(cx, 898, 300, 76, ['WHP_{self} ≥ target?'])
    zero_rise = svg.node(rx, 872, rw, 52, ['**ΔP = 0', '~zero-rise pump (pumped only for the floor)'], 'package')
    solve = svg.node(
        mx,
        962,
        mw,
        74,
        [
            '**Solve the pump pressure rise ΔP',
            're-march above the pump; secant with bisection, ±0.01 MPa',
            '~discharge h_{2} = h_{1} + ΔP / (ρ_{1} η): losses heat the fluid',
        ],
        'package',
    )
    result = svg.terminal(
        mx + 25,
        1062,
        mw - 50,
        56,
        ['**Pumped well: WHP = target', '~pump power ṁ ΔP / (ρ_{1} η) per well'],
        'ok',
    )
    svg.node(
        rx,
        980,
        rw,
        138,
        [
            '**In GEOPHIRES',
            '~a failed state aborts the run, as does a flag',
            '~the envelope policy forbids (enforce:',
            '~pump_outside_envelope, no_liquid_intake,',
            '~choked_flow; omit: choked_flow). Pump power',
            '~and depth feed the standard production',
            '~pumping outputs and pump cost.',
        ],
        'abort',
        size=12,
    )

    svg.arrow([start.bottom, inflow.top])
    svg.arrow([inflow.bottom, march.top])
    svg.arrow([march.bottom, self_flow.top])
    svg.arrow([self_flow.right, unpumped.left], 'yes', label_at=((self_flow.right[0] + rx) / 2, self_flow.cy))
    svg.arrow([self_flow.bottom, intake.top], "no (or 'always')", label_at=(cx, 396))
    svg.arrow([intake.bottom, found.top])
    svg.arrow(
        [found.right, (rx - 30, found.cy), (rx - 30, policy.y + 40), (rx, policy.y + 40)],
        'no',
        label_at=((found.right[0] + rx - 30) / 2, found.cy),
    )
    svg.arrow([found.bottom, envelope.top], 'yes', label_at=(cx + 20, 612))
    svg.arrow(
        [envelope.right, (rx - 30, envelope.cy), (rx - 30, policy.y + 128), (rx, policy.y + 128)],
        'no',
        label_at=((envelope.right[0] + rx - 30) / 2, envelope.cy),
    )
    svg.arrow([envelope.bottom, target.top], 'yes', label_at=(cx + 20, 752))
    svg.arrow(
        [(policy.cx, policy.y + policy.h), (policy.cx, 755), (cx + 80, 755), (cx + 80, target.y)],
        'flag',
        label_at=(policy.cx, 740),
    )
    svg.arrow([target.bottom, zero.top])
    svg.arrow([zero.right, zero_rise.left], 'yes', label_at=((zero.right[0] + rx) / 2, zero.cy))
    svg.arrow([zero.bottom, solve.top], 'no', label_at=(cx + 16, 946))
    svg.arrow([solve.bottom, result.top])
    svg.arrow([zero_rise.bottom, (zero_rise.cx, 948), (mx + mw + 40, 948), (mx + mw + 40, result.cy), result.right])
    return svg.save('pump-stage')


# ---------------------------------------------------------------------------------------------------------------------
# Physics figures of the example wells (superhot-wellbore and CoolProp)
# ---------------------------------------------------------------------------------------------------------------------

_EXAMPLES = {
    'example_SHR-4': 'SHR-4: 450 °C, 3.5 km, 10 MPa target WHP (self-flowing)',
    'example_SHR-5': 'SHR-5: 450 °C, 4 km, 60 kg/s (self-flowing)',
    'example_SHR-6': 'SHR-6: 200 °C, 5.1 km, 60 kg/s (pumped)',
}
_EXAMPLE_COLORS = {'example_SHR-4': '#c2410c', 'example_SHR-5': '#7e22ce', 'example_SHR-6': '#1d4ed8'}

_PATH_COLORS = {
    'correlation_orc': '#d6e6ff',
    'correlation_double_flash': '#d5f2e3',
    'wet_double_flash': '#ffe6c7',
    'coupled_wellbore_binary': '#eadcf8',
    'coupled_wellbore_flash': '#f9d9e6',
}

_models: dict = {}


def _example_model(name: str):
    """GEOPHIRES model of a tests/examples input file, read and calculated in-process (cached)."""
    if name in _models:
        return _models[name]

    input_params = GeophiresInputParameters(
        from_file_path=_IMAGES_DIR.parent.parent / 'tests' / 'examples' / f'{name}.txt'
    )
    stash_cwd, stash_argv = Path.cwd(), sys.argv
    sys.argv = ['', input_params.as_file_path()]
    try:
        model = Model(enable_geophires_logging_config=False)
        model.read_parameters()
        model.Calculate()
    finally:
        sys.argv = stash_argv
        os.chdir(stash_cwd)
    _models[name] = model
    return model


def _example_timesteps(name: str) -> list[dict]:
    """
    Per time step wellhead and pump state of an example's solved production profile, plus the plant path. Set
    GEOPHIRES_DOCS_FIGURE_CACHE to a directory to keep these between runs while iterating on the figures.
    """
    cache_dir = os.environ.get('GEOPHIRES_DOCS_FIGURE_CACHE')
    cache_path = Path(cache_dir) / f'{name}-timesteps.json' if cache_dir else None
    if cache_path is not None and cache_path.exists():
        return json.loads(cache_path.read_text())

    model = _example_model(name)
    paths = list(getattr(model.surfaceplant, 'coupled_plant_path', []))
    steps = []
    for i, ts in enumerate(model.wellbores.coupled_profile.timesteps):
        d = {k: v for k, v in dataclasses.asdict(ts).items() if isinstance(v, (int, float, str, bool, list))}
        d['plant_path'] = paths[i] if i < len(paths) else None
        d['electricity_MW'] = float(model.surfaceplant.ElectricityProduced.value[i])
        d['T_reservoir_farfield_C'] = float(model.reserv.Tresoutput.value[i])
        steps.append(d)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(steps, default=float))
    return steps


def _savefig(fig, name: str) -> Path:
    path = _IMAGES_DIR / f'{_FIGURE_PREFIX}{name}.svg'
    fig.savefig(path, bbox_inches='tight', metadata={'Date': None}, facecolor='white')
    print(f'wrote {path}')
    return path


def _mpl():
    plt.switch_backend('Agg')
    plt.rcParams.update(
        {
            'font.family': 'sans-serif',
            'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
            'font.size': 10,
            'axes.edgecolor': '#7b8794',
            'axes.labelcolor': _INK,
            'axes.titlesize': 11,
            'axes.titleweight': 'bold',
            'xtick.color': _MUTED,
            'ytick.color': _MUTED,
            'svg.fonttype': 'none',
            'svg.hashsalt': 'coupled-wellbore-docs',
        }
    )
    return plt


def plant_path_map_figure() -> Path:
    """
    Pressure-enthalpy diagram of water divided into the plant paths the correlation-first policy assigns to a wellhead
    state, with the wellhead trajectories of the example wells.
    """
    plt = _mpl()
    orc_max_C = 245.0
    P_c = WATER_CRITICAL_PRESSURE_MPA
    h_dense = WATER_CRITICAL_ENTHALPY_MJ_PER_KG * 1000.0
    P_min, P_max, h_max = 0.3, 60.0, 3400.0

    def h(P_MPa, T_C=None, Q=None):
        if Q is not None:
            return CP.PropsSI('H', 'P', P_MPa * 1e6, 'Q', Q, 'Water') / 1000.0
        return CP.PropsSI('H', 'P', P_MPa * 1e6, 'T', T_C + 273.15, 'Water') / 1000.0

    P_sub = np.geomspace(P_min, P_c * 0.99999, 300)
    P_sup = np.geomspace(P_c, P_max, 120)
    hf = np.array([h(p, Q=0) for p in P_sub])
    hg = np.array([h(p, Q=1) for p in P_sub])
    P_sat_orc = CP.PropsSI('P', 'T', orc_max_C + 273.15, 'Q', 0, 'Water') / 1e6

    def isotherm_liquid(T_C, P):
        return np.array([h(p, T_C) for p in P])

    h_orc_sub = np.array([min(f, h(p, orc_max_C)) if p > P_sat_orc else f for p, f in zip(P_sub, hf)])
    h_orc_sup = isotherm_liquid(orc_max_C, P_sup)

    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    fill = {'linewidth': 0}
    # sub-critical
    ax.fill_betweenx(P_sub, 0, h_orc_sub, color=_PATH_COLORS['correlation_orc'], **fill)
    ax.fill_betweenx(P_sub, h_orc_sub, hf, color=_PATH_COLORS['correlation_double_flash'], **fill)
    ax.fill_betweenx(P_sub, hf, hg + SUPERHEAT_MARGIN_KJ_PER_KG, color=_PATH_COLORS['wet_double_flash'], **fill)
    ax.fill_betweenx(
        P_sub, hg + SUPERHEAT_MARGIN_KJ_PER_KG, h_max, color=_PATH_COLORS['coupled_wellbore_binary'], **fill
    )
    # supercritical
    ax.fill_betweenx(P_sup, 0, h_orc_sup, color=_PATH_COLORS['correlation_orc'], **fill)
    ax.fill_betweenx(P_sup, h_orc_sup, h_dense, color=_PATH_COLORS['correlation_double_flash'], **fill)
    ax.fill_betweenx(P_sup, h_dense, h_max, color=_PATH_COLORS['coupled_wellbore_binary'], **fill)
    # best-output alternatives in the two-phase envelope: hatch
    ax.fill_betweenx(
        P_sub,
        hf,
        hg + SUPERHEAT_MARGIN_KJ_PER_KG,
        facecolor='none',
        edgecolor='#f2a7c6',
        hatch='////',
        linewidth=0,
    )

    # saturation envelope, critical point, boundaries
    ax.plot(hf, P_sub, color='#334e68', lw=1.4)
    ax.plot(hg, P_sub, color='#334e68', lw=1.4)
    ax.plot([h(P_c * 0.99999, Q=0), h(P_c * 0.99999, Q=1)], [P_c, P_c], color='#334e68', lw=1.4)
    ax.plot(hg + SUPERHEAT_MARGIN_KJ_PER_KG, P_sub, color='#7e22ce', lw=0.9, ls=(0, (4, 3)))
    ax.plot([h_dense, h_dense], [P_c, P_max], color='#7e22ce', lw=0.9, ls=(0, (4, 3)))
    ax.axhline(P_c, xmin=0, xmax=1, color='#9aa5b1', lw=0.7, ls=':')
    ax.plot(h_orc_sub[P_sub > P_sat_orc], P_sub[P_sub > P_sat_orc], color='#1d4ed8', lw=0.9, ls=(0, (4, 3)))
    ax.plot(h_orc_sup, P_sup, color='#1d4ed8', lw=0.9, ls=(0, (4, 3)))
    P_375 = np.geomspace(CP.PropsSI('P', 'T', 373.9 + 273.15, 'Q', 0, 'Water') / 1e6 * 1.0001, P_max, 100)
    P_375 = P_375[P_375 > P_c]
    ax.plot(isotherm_liquid(LIQUID_CORRELATION_MAX_TEMPERATURE_C, P_375), P_375, color='#15803d', lw=0.9, ls=':')
    h_crit = CP.PropsSI('H', 'T', CP.PropsSI('Tcrit', 'Water'), 'D', CP.PropsSI('rhocrit', 'Water'), 'Water') / 1000
    ax.plot([h_crit], [P_c], marker='o', ms=5, color='#334e68')
    ax.annotate(
        'critical point',
        (h_crit, P_c),
        (h_crit + 330, P_c * 0.72),
        fontsize=8.5,
        color='#334e68',
        ha='left',
        arrowprops={'arrowstyle': '-', 'color': '#334e68', 'lw': 0.7},
    )

    # reference isotherms
    for T_C in (200, 300, 400, 450, 500):
        if T_C < 373.9:
            # vapor branch up to the saturation pressure, across the envelope, liquid branch above
            P_sat = CP.PropsSI('P', 'T', T_C + 273.15, 'Q', 0, 'Water') / 1e6
            P_vap = np.geomspace(P_min, P_sat * 0.999, 60)
            P_liq = np.geomspace(P_sat * 1.001, P_max, 60)
            xs = [h(p, T_C) for p in P_vap] + [h(P_sat, Q=1), h(P_sat, Q=0)] + [h(p, T_C) for p in P_liq]
            ps = [*P_vap, P_sat, P_sat, *P_liq]
        else:
            ps = list(np.geomspace(P_min, P_max, 120))
            xs = [h(p, T_C) for p in ps]
        ax.plot(xs, ps, color='#9aa5b1', lw=0.6, zorder=1)
        # label at the bottom of the isotherm (its low-pressure vapor end), or at the right edge if that is off-axis
        if xs[0] < h_max - 60:
            ax.text(xs[0], P_min * 1.04, f'{T_C} °C', fontsize=7.5, color='#7b8794', ha='center', va='bottom')
        else:
            i = next(i for i, x in enumerate(xs) if x < h_max - 60)
            ax.text(h_max - 45, ps[i], f'{T_C} °C', fontsize=7.5, color='#7b8794', ha='right', va='center')

    # region labels
    label = {'fontsize': 9, 'ha': 'center', 'va': 'center', 'color': _INK}
    box = {'boxstyle': 'round,pad=0.25', 'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.85}
    ax.text(470, 1.0, 'correlation_orc\n(supercritical ORC fit)', **label)
    ax.text(1330, 11.0, 'correlation_\ndouble_flash', **label)
    ax.text(1400, 30.0, 'dense supercritical:\nliquid correlations', **label)
    ax.text(1800, 1.2, 'wet_double_flash\n(two-phase or saturated vapor)', bbox=box, **label)
    ax.text(3020, 1.0, 'coupled_wellbore_\nbinary (superheated)', **label)
    ax.text(2790, 42.0, 'vapor-like supercritical:\ncoupled_wellbore_binary', **label)
    ax.text(
        1800,
        0.5,
        'hatched: best-output also admits coupled_wellbore_flash',
        fontsize=7.5,
        ha='center',
        color='#9d174d',
        bbox=box,
    )
    ax.text(
        h(7.0, orc_max_C) - 25,
        7.0,
        f'{orc_max_C:g} °C: Coupled Wellbore\nORC Maximum Wellhead\nTemperature',
        fontsize=7.5,
        color='#1d4ed8',
        ha='right',
        va='center',
    )
    ax.text(
        isotherm_liquid(375.0, [47.0])[0] - 15,
        47.0,
        '375 °C: double-flash fit\nevaluated no hotter',
        fontsize=7.5,
        color='#15803d',
        ha='right',
        va='center',
    )
    ax.text(h_dense + 22, 25.0, 'h = 2084 kJ/kg', fontsize=7.5, color='#7e22ce', ha='left', rotation=90, va='bottom')
    ax.text(
        h(4.0, Q=1) + SUPERHEAT_MARGIN_KJ_PER_KG + 20,
        5.5,
        '+50 kJ/kg\nsuperheat',
        fontsize=7.5,
        color='#7e22ce',
        ha='left',
    )

    # example wellhead trajectories
    for name, title in _EXAMPLES.items():
        steps = _example_timesteps(name)
        hs = np.array([ts['h_wellhead_MJkg'] for ts in steps]) * 1000.0
        ps = np.array([ts['whp_MPa'] for ts in steps])
        solved = np.array([bool(ts.get('solved', False)) for ts in steps])
        color = _EXAMPLE_COLORS[name]
        ax.plot(hs, ps, color=color, lw=1.6, zorder=5, label=title)
        ax.plot(hs[solved], ps[solved], 'o', ms=4.5, mfc='white', mec=color, mew=1.4, zorder=6)
        ax.plot(hs[:1], ps[:1], 'o', ms=6, color=color, zorder=7)

    ax.set_yscale('log')
    ax.set_xlim(0, h_max)
    ax.set_ylim(P_min, P_max)
    ax.set_yticks([0.3, 0.5, 1, 2, 3, 5, 10, 20, 30, 50])
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:g}'))
    ax.set_xlabel('Wellhead specific enthalpy (kJ/kg)')
    ax.set_ylabel('Wellhead pressure (MPa)')
    ax.set_title(
        'Plant path by wellhead state (correlation-first policy) and example wellhead trajectories', loc='left'
    )
    leg = ax.legend(
        loc='upper left',
        bbox_to_anchor=(0.0, -0.1),
        ncol=1,
        fontsize=8,
        frameon=False,
        title='Example wellheads over the plant lifetime (filled marker: start of production; open markers: solved '
        'states, interpolated between)',
        title_fontsize=8,
    )
    leg._legend_box.align = 'left'
    return _savefig(fig, 'plant-path-map')


def _example_depth_profiles(name: str) -> dict:
    """
    Depth profiles (feedzone to wellhead) of an example well at its first and last solved states, re-solved with the
    request GEOPHIRES builds, since the production profile keeps only the wellhead state. Cached like
    _example_timesteps.
    """
    cache_dir = os.environ.get('GEOPHIRES_DOCS_FIGURE_CACHE')
    cache_path = Path(cache_dir) / f'{name}-depth-profiles.json' if cache_dir else None
    if cache_path is not None and cache_path.exists():
        return json.loads(cache_path.read_text())

    model = _example_model(name)
    wb = model.wellbores
    sh = wb._coupled_wellbore_client
    flow_kgs = float(wb.prodwellflowrate.value)
    solved = [ts for ts in wb.coupled_profile.timesteps if ts.solved and ts.success]
    # the last state is the most declined one (a redrilled history repeats, so it is not simply the last solve)
    most_declined = min(solved, key=lambda ts: (float(ts.T_reservoir_C), -float(ts.time_yr)))
    out = {'feedzone_depth_m': float(model.reserv.depth.quantity().to('m').magnitude)}
    for label, ts in (('start', solved[0]), ('end', most_declined)):
        request = wb._request(
            model,
            sh.OperatingConfig(control='flow', mass_flow_kgs=flow_kgs),
            float(ts.P_reservoir_MPa),
            float(ts.T_reservoir_C),
        )
        result, raw = sh.CoupledWellboreClient(request).solve_state(
            float(ts.P_reservoir_MPa), float(ts.T_reservoir_C), mass_flow_kgs=flow_kgs
        )
        T, P, h, _v, x, T_rock = (list(profile) for profile in raw['profiles'][:6])
        out[label] = {
            'time_yr': float(ts.time_yr),
            'T_reservoir_C': float(ts.T_reservoir_C),
            'depth_m': [float(d) for d, _ in P],
            'P_MPa': [float(p) for _, p in P],
            'T_C': [float(t) for _, t in T],
            'h_MJkg': [float(e) for _, e in h],
            'x': [float(q) if q is not None and np.isfinite(q) else None for _, q in x],
            'T_rock_C': [float(t) for _, t in T_rock],
            'pump_depth_m': float(result.pump_depth_m or 0.0),
            'whp_MPa': float(result.whp_MPa),
        }
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(out))
    return out


def depth_profiles_figure() -> Path:
    """Pressure and temperature along the example wells at the first and last solved states."""
    plt = _mpl()
    fig, axes = plt.subplots(2, 3, figsize=(11, 7.6), sharey='col')
    for col, (name, title) in enumerate(_EXAMPLES.items()):
        data = _example_depth_profiles(name)
        color = _EXAMPLE_COLORS[name]
        ax_p, ax_t = axes[0][col], axes[1][col]
        for label, ls in (('start', '-'), ('end', (0, (5, 3)))):
            d = data[label]
            depth = np.array(d['depth_m'])
            when = f"t = {d['time_yr']:.1f} yr, T_res = {d['T_reservoir_C']:.0f} °C"
            ax_p.plot(d['P_MPa'], depth, color=color, ls=ls, lw=1.6, label=when)
            ax_t.plot(d['T_C'], depth, color=color, ls=ls, lw=1.6, label=f'fluid, {when}')
            two_phase = np.array([q is not None and 0.0 < q < 1.0 for q in d['x']])
            if two_phase.any():
                top, bottom = float(depth[two_phase].min()), float(depth[two_phase].max())
                for ax in (ax_p, ax_t):
                    ax.axhspan(top, bottom, color='#ffe6c7', alpha=0.55, lw=0, zorder=0)
                ax_p.text(
                    0.97,
                    (top + bottom) / 2,
                    f'two-phase\n({"first" if label == "start" else "last"} state)',
                    transform=ax_p.get_yaxis_transform(),
                    ha='right',
                    va='center',
                    fontsize=8,
                    color='#7a3e00',
                )
            if label == 'start':
                ax_t.plot(d['T_rock_C'], depth, color='#9aa5b1', lw=1.2, label='formation T_rock(z)')
                if d['pump_depth_m'] > 0:
                    for ax in (ax_p, ax_t):
                        ax.axhline(d['pump_depth_m'], color='#cb6e17', lw=1.0, ls=':')
                    ax_p.text(
                        0.97,
                        d['pump_depth_m'],
                        f"pump {d['pump_depth_m']:.0f} m",
                        ha='right',
                        va='bottom',
                        transform=ax_p.get_yaxis_transform(),
                        fontsize=8,
                        color='#7c2d12',
                    )
        for ax in (ax_p, ax_t):
            ax.axhline(data['feedzone_depth_m'], color='#7a3e00', lw=0.8)
            ax.set_ylim(data['feedzone_depth_m'] * 1.03, -data['feedzone_depth_m'] * 0.02)
            ax.grid(color='#e4e7eb', lw=0.6)
        ax_p.set_title(title, loc='left', fontsize=9.5)
        ax_p.set_xlabel('Pressure (MPa)')
        ax_t.set_xlabel('Temperature (°C)')
        ax_p.legend(fontsize=7.5, loc='lower left', frameon=False)
        ax_t.legend(fontsize=7.5, loc='lower left', frameon=False)
    axes[0][0].set_ylabel('Depth (m)')
    axes[1][0].set_ylabel('Depth (m)')
    fig.suptitle(
        'Flowing profiles along the example wells (feedzone at the brown line; solid: first solved state, '
        'dashed: last)',
        x=0.01,
        ha='left',
        fontsize=10.5,
        fontweight='bold',
    )
    fig.tight_layout()
    return _savefig(fig, 'depth-profiles')


def _legend_below_data(ax) -> None:
    """Legend in the lower left, with the y range extended downwards so that it does not cover the data."""
    low, high = ax.get_ylim()
    ax.set_ylim(low - 0.55 * (high - low), high)
    ax.legend(fontsize=7.5, frameon=False, loc='lower left')


def time_histories_figure() -> Path:
    """Temperatures, wellhead pressure and plant output of the example wells over the plant lifetime."""
    plt = _mpl()
    fig, axes = plt.subplots(3, 3, figsize=(11, 8.2), sharex='col')
    for col, (name, title) in enumerate(_EXAMPLES.items()):
        steps = _example_timesteps(name)
        t = np.array([s['time_yr'] for s in steps])
        solved = np.array([bool(s.get('solved')) for s in steps])
        color = _EXAMPLE_COLORS[name]

        ax = axes[0][col]
        for key, label, c in (
            ('T_reservoir_C', 'far-field reservoir T_res', '#7a3e00'),
            ('T_feedzone_C', 'feedzone (after drawdown)', '#d9822b'),
            ('T_wellhead_C', 'wellhead', color),
        ):
            y = np.array([s[key] for s in steps], dtype=float)
            ax.plot(t, y, color=c, lw=1.5, label=label)
            ax.plot(t[solved], y[solved], 'o', ms=4, mfc='white', mec=c, mew=1.2)
        ax.set_title(title, loc='left', fontsize=9.5)
        ax.set_ylabel('Temperature (°C)' if col == 0 else '')
        _legend_below_data(ax)

        ax = axes[1][col]
        whp = np.array([s['whp_MPa'] for s in steps], dtype=float)
        ax.plot(t, whp, color=color, lw=1.5, label='wellhead pressure')
        ax.plot(t[solved], whp[solved], 'o', ms=4, mfc='white', mec=color, mew=1.2)
        self_flow = np.array(
            [np.nan if s.get('self_flow_whp_MPa') is None else s['self_flow_whp_MPa'] for s in steps], dtype=float
        )
        if np.any(np.isfinite(self_flow)) and np.any(np.array([bool(s.get('pumped')) for s in steps])):
            ax.plot(t, self_flow, color='#9aa5b1', lw=1.2, ls=(0, (4, 3)), label='unpumped (self-flow) WHP')
        ax.set_ylabel('Wellhead pressure (MPa)' if col == 0 else '')
        ax.set_ylim(0, np.nanmax(whp) * 1.45)
        ax.legend(fontsize=7.5, frameon=False, loc='upper right')

        ax = axes[2][col]
        power = np.array([s['electricity_MW'] for s in steps], dtype=float)
        # under cycle-only every time step is reported as the first one's cycle; show the cycle that actually served it
        paths = [
            (
                f"coupled_wellbore_{s['cycle']}"
                if (s.get('plant_path') or '').startswith('coupled_wellbore_') and s.get('cycle')
                else (s.get('plant_path') or '')
            )
            for s in steps
        ]
        for path in dict.fromkeys(paths):
            mask = np.array([p == path for p in paths])
            ax.fill_between(
                t, 0, power, where=mask, color=_PATH_COLORS.get(path, '#e4e7eb'), step=None, lw=0, label=path
            )
        ax.plot(t, power, color=color, lw=1.5)
        ax.plot(t[solved], power[solved], 'o', ms=4, mfc='white', mec=color, mew=1.2)
        ax.set_ylabel('Plant output (MW)' if col == 0 else '')
        ax.set_xlabel('Time (years)')
        ax.set_ylim(0, np.nanmax(power) * 1.5)
        ax.legend(fontsize=7.5, frameon=False, loc='upper right', title='plant path', title_fontsize=7.5)
        for row in axes:
            row[col].grid(color='#e4e7eb', lw=0.6)
    fig.suptitle(
        'Example wells over the plant lifetime (open markers: solved states; values in between are ' 'interpolated)',
        x=0.01,
        ha='left',
        fontsize=10.5,
        fontweight='bold',
    )
    fig.tight_layout()
    return _savefig(fig, 'time-histories')


def main() -> None:
    model_chain_figure()
    calculation_sequence_figure()
    well_schematic_figure()
    pump_stage_figure()
    plant_path_map_figure()
    depth_profiles_figure()
    time_histories_figure()


if __name__ == '__main__':
    main()
    sys.exit(0)

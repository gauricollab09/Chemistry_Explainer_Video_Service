"""Bonding scenes: outer shells, covalent sharing, example molecules, ionic transfer."""

from __future__ import annotations

import math

from app.generation.render.primitives import (
    Frame, arrow, atom, bezier, circle, clamp, ease, electron, lerp, lerp_color, lerp_point, line,
    on_circle, polyline, rich, rounded, shell_slots, stagger, text,
)
from app.generation.render.scenes.base import Reveal, SceneRenderer, check_numbered, numbered_actions
from app.generation.render.style import (
    ACCENT, ATOM_COLORS, ELECTRON, GOOD, MUTED, NEGATIVE, PANEL, POSITIVE, TEXT,
)

CY = 320


def _electrons_word(n: int) -> str:
    return f"{n} outer electron{'s' if n != 1 else ''}"


class AtomShellsScene(SceneRenderer):
    kind = "atom_shells"
    actions = numbered_actions("atom", 3) | {"slots"}

    def check_params(self, params, scene) -> list[str]:
        atoms = params["atoms"]
        problems = [] if 1 <= len(atoms) <= 3 else ["atoms must have 1-3 entries"]
        for a in atoms:
            if a["capacity"] not in (2, 8) or not 0 < a["electrons"] <= a["capacity"]:
                problems.append(f"bad atom {a!r}")
        return problems + check_numbered(scene, "atom", len(atoms))

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        atoms = scene.params["atoms"]
        xs = [640] if len(atoms) == 1 else [lerp(360, 920, i / (len(atoms) - 1)) for i in range(len(atoms))]
        slots_p = ease(rv("slots"))
        for i, (a, x) in enumerate(zip(atoms, xs)):
            p = ease(rv(f"atom{i + 1}"))
            if p <= 0:
                continue
            c = (x, CY + 20 * (1 - p))
            slots = shell_slots(a["capacity"], 0)
            filled, ghosts = slots[: a["electrons"]], slots[a["electrons"]:]
            atom(f, c, a["symbol"], 115, electrons=[], alpha=p)
            for j, angle in enumerate(filled):
                electron(f, on_circle(c, 115, angle), stagger(p, j, len(filled)))
            for angle in ghosts:
                pulse = slots_p * (0.7 + 0.3 * math.sin(slots_p * math.pi))
                circle(f, on_circle(c, 115, angle), 16, fill=ELECTRON, alpha=pulse * 0.15)
                circle(f, on_circle(c, 115, angle), 10, outline=ELECTRON, width=2, alpha=pulse)
            text(f, (x, CY + 115 + 48), a["name"], 28, TEXT, p, "mm", bold=True)
            text(f, (x, CY + 115 + 84), f"{_electrons_word(a['electrons'])} · room for {a['capacity']}", 21, MUTED, p, "mm")
            missing = a["capacity"] - a["electrons"]
            text(f, (x, CY - 115 - 36), f"needs {missing} more", 24, ELECTRON, slots_p, "mm", bold=True)


class CovalentShareScene(SceneRenderer):
    kind = "covalent_share"
    actions = frozenset({"approach", "overlap", "pair", "result"})
    R = 112

    def check_params(self, params, scene) -> list[str]:
        if params["full"] not in (2, 8) or not 0 < params["valence"] < params["full"]:
            return ["valence must be below the full shell count (2 or 8)"]
        if not params["symbol"] or not params["formula"]:
            return ["symbol and formula are required"]
        return []

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        sym, valence, full = scene.params["symbol"], scene.params["valence"], scene.params["full"]
        approach, overlap, pair, result = (ease(rv(a)) for a in ("approach", "overlap", "pair", "result"))
        R, cx = self.R, 640
        d = lerp(lerp(620, 330, approach), 170, overlap)
        left, right = (cx - d / 2, CY), (cx + d / 2, CY)
        alpha = clamp(approach * 3 + 0.001 if approach > 0 else 0)
        shell_color = lerp_color(MUTED, GOOD, result)

        if overlap > 0 and d < 2 * R:
            half_h = math.sqrt(R * R - (d / 2) ** 2)
            half_w = (2 * R - d) / 2
            f.draw.ellipse(
                [(cx - half_w) * 2, (CY - half_h) * 2, (cx + half_w) * 2, (CY + half_h) * 2],
                fill=(*ACCENT, round(40 * overlap)),
            )

        slots_l, slots_r = shell_slots(full, 0), shell_slots(full, 180)
        atom(f, left, sym, R, electrons=slots_l[1:valence], alpha=alpha, shell_color=shell_color)
        atom(f, right, sym, R, electrons=slots_r[1:valence], alpha=alpha, shell_color=shell_color)
        ghost_alpha = alpha * (1 - pair) * 0.8
        for c, slots in ((left, slots_l), (right, slots_r)):
            circle(f, on_circle(c, R, slots[valence]), 10, outline=ELECTRON, width=2, alpha=ghost_alpha)

        start_l, start_r = on_circle(left, R, slots_l[0]), on_circle(right, R, slots_r[0])
        electron(f, lerp_point(start_l, (cx, CY + 11), pair), alpha)
        electron(f, lerp_point(start_r, (cx, CY - 11), pair), alpha)
        if pair > 0:
            circle(f, (cx, CY), 30, outline=ELECTRON, width=2, alpha=pair * 0.7)
            line(f, (cx, CY - R - 18), (cx, CY - 36), ELECTRON, 2, pair)
            text(f, (cx, CY - R - 38), "shared pair", 26, ELECTRON, pair, "mm", bold=True)

        if result > 0:
            for c in (left, right):
                text(f, (c[0] - (40 if c is left else -40), CY + R + 40), f"{full} in outer shell", 22, GOOD, result, "mm", bold=True)
            rich(f, (cx, CY + R + 102), scene.params["formula"], 46, TEXT, result, bold=True)
            text(f, (cx, CY + R + 140), "one shared pair = one covalent bond", 20, MUTED, result, "mm")


class MoleculeExamplesScene(SceneRenderer):
    kind = "molecule_examples"
    actions = numbered_actions("mol", 3)
    RADIUS = {"H": 30, "O": 40, "Cl": 44}

    def check_params(self, params, scene) -> list[str]:
        molecules = params["molecules"]
        problems = [] if 1 <= len(molecules) <= 3 else ["molecules must have 1-3 entries"]
        for m in molecules:
            n = len(m["atoms"])
            if any(not (0 <= i < n and 0 <= j < n) for i, j in m["bonds"]):
                problems.append(f"{m['formula']}: bond refers to a missing atom")
        return problems + check_numbered(scene, "mol", len(molecules))

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        molecules = scene.params["molecules"]
        xs = [lerp(250, 1030, i / max(1, len(molecules) - 1)) for i in range(len(molecules))]
        for i, (m, cx) in enumerate(zip(molecules, xs)):
            p = ease(rv(f"mol{i + 1}"))
            if p <= 0:
                continue
            rounded(f, (cx - 175, 135 + 20 * (1 - p), cx + 175, 560), 20, PANEL, p * 0.85)
            scale = 0.85 + 0.15 * p
            center = (cx, 300)
            pos = [(center[0] + a["x"] * scale, center[1] + a["y"] * scale) for a in m["atoms"]]
            for a_i, b_i in m["bonds"]:
                a, b = pos[a_i], pos[b_i]
                line(f, a, b, (100, 116, 139), 10, p)
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
                nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
                electron(f, (mx + nx * 7, my + ny * 7), p, r=5.5)
                electron(f, (mx - nx * 7, my - ny * 7), p, r=5.5)
            for a, c in zip(m["atoms"], pos):
                color = ATOM_COLORS.get(a["symbol"], MUTED)
                r = self.RADIUS.get(a["symbol"], 38) * scale
                circle(f, c, r, fill=lerp_color(color, PANEL, 0.4), outline=color, width=3, alpha=p)
                text(f, c, a["symbol"], r * 0.85, TEXT, p, "mm", bold=True)
            rich(f, (cx, 455), m["formula"], 44, TEXT, p, bold=True)
            text(f, (cx, 505), m.get("name", ""), 22, MUTED, p, "mm")


class IonicTransferScene(SceneRenderer):
    kind = "ionic_transfer"
    actions = frozenset({"atoms", "transfer", "ions", "attract"})
    R_NA, R_CL = 100, 115

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        shown, transfer, ions, attract = (ease(rv(a)) for a in ("atoms", "transfer", "ions", "attract"))
        na, cl = (420 + 40 * attract, CY), (860 - 30 * attract, CY)
        cl_slots = shell_slots(8, 180)

        atom(f, na, "Na", self.R_NA, electrons=[], alpha=shown, shell_alpha=1 - ions,
             label="Na^+" if ions > 0.5 else "Na")
        atom(f, cl, "Cl", self.R_CL, electrons=cl_slots[:7], alpha=shown,
             shell_color=lerp_color(MUTED, GOOD, ions), label="Cl^-" if ions > 0.5 else "Cl")
        circle(f, on_circle(cl, self.R_CL, cl_slots[7]), 10, outline=ELECTRON, width=2,
               alpha=shown * (1 - transfer) * 0.8)

        start = on_circle(na, self.R_NA, -11)
        end = on_circle(cl, self.R_CL, cl_slots[7])
        control = ((start[0] + end[0]) / 2, CY - 200)
        if 0 < transfer:
            trail = [bezier(start, control, end, transfer * t / 30) for t in range(31)]
            polyline(f, trail, ELECTRON, 2, 0.35 * (1 - ions))
        electron(f, bezier(start, control, end, transfer), shown)

        for c, sign, color in ((na, "+", POSITIVE), (cl, "−", NEGATIVE)):
            badge = (c[0] + 52, c[1] - 52)
            circle(f, badge, 20, fill=color, alpha=ions)
            text(f, badge, sign, 28, (8, 12, 26), ions, "mm", bold=True)

        labels = (
            (na, "Sodium (metal)", _electrons_word(1), "Positive ion", "lost 1 electron"),
            (cl, "Chlorine (non-metal)", _electrons_word(7), "Negative ion", "gained 1 electron · full shell"),
        )
        for c, name, detail, ion_name, ion_detail in labels:
            y = CY + self.R_CL + 42
            text(f, (c[0], y), name, 26, TEXT, shown * (1 - ions), "mm", bold=True)
            text(f, (c[0], y + 34), detail, 21, MUTED, shown * (1 - ions), "mm")
            text(f, (c[0], y), ion_name, 26, TEXT, ions, "mm", bold=True)
            text(f, (c[0], y + 34), ion_detail, 21, MUTED, ions, "mm")

        if attract > 0:
            mid = (na[0] + cl[0]) / 2
            arrow(f, (na[0], 165), (mid - 18, 165), POSITIVE, 5, attract)
            arrow(f, (cl[0], 165), (mid + 18, 165), NEGATIVE, 5, attract)
            text(f, (mid, 132), "opposite charges attract", 22, MUTED, attract, "mm")
            text(f, (mid, CY + self.R_CL + 130), "electrostatic attraction = ionic bond", 28, ACCENT, attract, "mm", bold=True)


class ComparisonTableScene(SceneRenderer):
    kind = "comparison_table"
    actions = numbered_actions("row", 5) | {"header"}
    COLUMN_COLORS = [(251, 146, 60), GOOD, ACCENT]

    def check_params(self, params, scene) -> list[str]:
        columns, rows = params["columns"], params["rows"]
        problems = [] if 2 <= len(columns) <= 3 else ["table needs 2-3 columns"]
        if not 1 <= len(rows) <= 5:
            problems.append("table needs 1-5 rows")
        problems += [f"row '{r['label']}' has {len(r['values'])} values" for r in rows if len(r["values"]) != len(columns)]
        return problems + check_numbered(scene, "row", len(rows))

    def draw_body(self, f: Frame, scene, rv: Reveal) -> None:
        columns, rows = scene.params["columns"], scene.params["rows"]
        x0, x1, label_w = 110, 1170, 220
        col_w = (x1 - x0 - label_w) / len(columns)
        header = ease(rv("header"))
        for i, name in enumerate(columns):
            color = self.COLUMN_COLORS[i]
            left = x0 + label_w + i * col_w + 12
            rounded(f, (left, 128, left + col_w - 24, 184), 28, color, header * 0.18, outline=color, width=2)
            text(f, (left + (col_w - 24) / 2, 156), name, 30, color, header, "mm", bold=True)
        row_h = min(84, 380 / len(rows))
        for r, row in enumerate(rows):
            p = ease(rv(f"row{r + 1}"))
            if p <= 0:
                continue
            y = 204 + r * (row_h + 8)
            dx = 30 * (1 - p)
            rounded(f, (x0 + dx, y, x1 + dx, y + row_h), 14, PANEL, p * 0.8)
            text(f, (x0 + 24 + dx, y + row_h / 2), row["label"].upper(), 20, MUTED, p, "lm", bold=True)
            for i, value in enumerate(row["values"]):
                center = x0 + label_w + i * col_w + col_w / 2 + dx
                rich(f, (center, y + row_h / 2), value, 27, TEXT, p)

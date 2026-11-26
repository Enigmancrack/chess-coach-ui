"""Motion layer tests.

The board feel lives in `static/motion.js` (pure helpers) and in the CSS
contract.  Node runs the unit suite; these tests keep it wired into pytest and
pin the researched numbers so a refactor cannot silently change them.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def run_node(*args: str) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    return subprocess.run(
        [node, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_motion_unit_suite_is_green():
    proc = run_node("tests/motion.test.js")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "FAIL" not in proc.stdout
    assert "motion:" in proc.stdout and "ok" in proc.stdout


def test_animation_preference_values_reach_the_browser():
    proc = run_node(
        "-e",
        "process.stdout.write(String(require('./static/motion.js').animationMs('normal')))",
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "250"


CSS_CONTRACT = [
    ("eval width 20px", "width: 20px"),
    ("eval width 30px on wide screens", "width: 30px"),
    ("eval property", "@property --eval-percent"),
    ("eval transition", "transition: --eval-percent 1s ease"),
    ("eval dark stop", "#444 var(--eval-percent)"),
    ("eval light stop", "#c0c0c0 var(--eval-percent)"),
    ("eval inset shadow", "inset 0 0 5px rgb(0 0 0 / .5)"),
    ("eval zero tick", "width: 7px"),
    ("eval wide media query", "@media (min-width: 60em)"),
    ("selected square", "rgb(20 85 30 / .5)"),
    ("last move", "rgb(155 199 0 / .41)"),
    ("legal dot", "radial-gradient(rgb(20 85 30 / .5) 19%, transparent 20%)"),
    ("capture ring", "radial-gradient(transparent 79%, rgb(20 85 0 / .3) 80%)"),
    ("hover", "rgba(20, 85, 30, .3)"),
    ("premove dot", "radial-gradient(rgb(20 30 85 / .5) 19%, transparent 20%)"),
    ("premove ring", "radial-gradient(transparent 79%, rgb(20 30 85 / .2) 80%)"),
    ("premove square", "rgb(20 30 85 / .5)"),
    ("check gradient", "rgb(169 0 0 / 0) 89%"),
    ("piece box", "width: 12.5%"),
    ("piece cover", "background-size: cover"),
    ("piece will-change", "will-change: transform"),
    ("sliding z-index", ".piece.sliding { z-index: 8; }"),
    ("dragging z-index", ".piece.dragging { z-index: 11; cursor: move; }"),
    ("fading", ".piece.fading { z-index: 1; opacity: .5; }"),
    ("ghost", ".piece.ghost { z-index: 1; opacity: .3; }"),
    ("promo circle", "border-radius: 50%"),
    ("promo inset", "inset 0 0 25px 3px #808080"),
    ("promo hover", "inset 0 0 48px 8px"),
    ("promo transition", "transition: box-shadow 150ms ease"),
    ("promo scale", "transform: scale(.8)"),
    ("arrow opacity", "opacity: .6"),
]


@pytest.mark.parametrize("label,needle", CSS_CONTRACT, ids=[c[0] for c in CSS_CONTRACT])
def test_style_contract(label, needle):
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert needle in css, f"{label}: {needle!r} missing from style.css"


APP_CONTRACT = [
    ("rAF driven", "requestAnimationFrame"),
    ("transform tween", "translate(${x}px, ${y}px)"),
    ("drag threshold 3px", "drag.startY) < 3"),
    ("sound throttle", "now - lastSoundAt < 100"),
    ("decoded buffers", "decodeAudioData"),
    ("victory delay", "playResultSound(st), 600"),
    ("premove 1ms", "}, 1);"),
    ("arrow stroke", "'0.156'"),
    ("arrow head path", "M0,0 V4 L3,2 Z"),
    ("arrow refX", "'2.05'"),
    ("arrow shorten", "ARROW_DEST_SHIFT"),
    ("eval percent property", "--eval-percent"),
    ("animation preference persisted", "animSpeed: S.animSpeed"),
]


@pytest.mark.parametrize("label,needle", APP_CONTRACT, ids=[c[0] for c in APP_CONTRACT])
def test_app_contract(label, needle):
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert needle in app, f"{label}: {needle!r} missing from app.js"


def test_html_settings_and_scripts():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="animSpeed"' in html
    for value in ("default", "none", "fast", "normal", "slow"):
        assert f'value="{value}"' in html
    assert 'src="motion.js"' in html
    assert html.index('src="motion.js"') < html.index('src="app.js"')

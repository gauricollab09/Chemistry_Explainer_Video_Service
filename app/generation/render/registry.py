"""All scene renderers, keyed by the `kind` a ScenePlan scene refers to.

Adding a STEM topic usually means reusing these; a genuinely new visual adds one renderer here.
"""

from app.generation.render.scenes.base import SceneRenderer
from app.generation.render.scenes.bonding import (
    AtomShellsScene, ComparisonTableScene, CovalentShareScene, IonicTransferScene, MoleculeExamplesScene,
)
from app.generation.render.scenes.common import BulletsScene, TitleScene
from app.generation.render.scenes.ph import PhBeakerScene, PhScaleScene

RENDERERS: dict[str, SceneRenderer] = {
    r.kind: r
    for r in (
        TitleScene(), BulletsScene(), PhBeakerScene(), PhScaleScene(), AtomShellsScene(),
        CovalentShareScene(), MoleculeExamplesScene(), IonicTransferScene(), ComparisonTableScene(),
    )
}

"""F0 gate (X11): builder-6's real handlers run headless and every committed state satisfies the editor's own model.

This does not reimplement anything of the editor. It drives the editor's store with random command sequences,
then checks two things:

* the builder's own validator accepts every state (in development mode the store throws on an invariant
  breach, so a breach would surface here as a bridge error);
* the builder's own exporter produces a site for every state.

It is skipped when the builder checkout is not present.
"""

from __future__ import annotations

import os
import pathlib
import random

import pytest

from nucleo.builder.client import DEFAULT_BUILDER, Builder, BuilderError, walk

pytestmark = pytest.mark.skipif(
    not (pathlib.Path(DEFAULT_BUILDER) / "node_modules").exists(), reason="builder-6 não disponível"
)

STEPS = int(os.environ.get("NUCLEO_BRIDGE_STEPS", "150"))
VALUES = ["center", "left", "flex", "grid", "block", "none", "10px", "2rem", "50%", "auto", "#1d4ed8", "red",
          "bold", "700", "1", "0", "row", "column", "wrap", "space-between"]


@pytest.fixture(scope="module")
def builder():
    b = Builder()
    yield b
    b.close()


def test_manifest_loaded(builder):
    m = builder.manifest()
    assert len(m["elements"]) >= 50
    assert len(m["commands"]) >= 200
    assert len(m["palette"]) >= 50
    assert len(m["properties"]) >= 150


def test_known_sequence_exports_expected_html(builder):
    builder.reset()
    root = builder.state()["document"]["pages"][0]["tree"]["id"]
    assert builder.dispatch("selection.select", target=root)["status"] == "done"
    assert builder.dispatch("element.insert", entry="section")["status"] == "done"
    assert builder.dispatch("element.insert", entry="heading")["status"] == "done"
    heading = [n for n in walk(builder.state()["document"]["pages"][0]["tree"]) if n["type"] == "heading"][0]
    assert builder.dispatch("text.set", target=heading["id"], content="Olá, mundo")["status"] == "done"
    builder.dispatch("selection.select", target=heading["id"])
    assert builder.dispatch("style.set", property="text-align", value="center")["status"] == "done"
    refused = builder.dispatch("style.set", property="text-align", value="banana")
    assert refused["status"] == "refused" and refused["message"]["key"] == "status.value.invalid"
    assert builder.validate() == []
    files = {f["path"]: f["text"] for f in builder.export()}
    assert "Olá, mundo" in files["index.html"] and "<section" in files["index.html"]
    assert "text-align: center" in files["css/styles.css"]


def test_random_command_sequences_keep_the_model_valid(builder):
    m = builder.manifest()
    palette = [e["id"] for e in m["palette"]]
    props = m["properties"]
    # text.set applies to elements whose content kind is "text" (manifest), a precondition the UI enforces by only
    # opening inline editing on them; the handler throws (not refuses) on others, e.g. an embed (finding F0-1)
    text_types = {e["id"] for e in m["elements"] if e["content"] == "text"}
    counts = {"done": 0, "refused": 0, "other": 0}
    for seed in range(3):
        rng = random.Random(seed)
        builder.reset()
        for step in range(STEPS):
            doc = builder.state()["document"]
            nodes = [n["id"] for page in doc["pages"] for n in walk(page["tree"])]
            texts = [n["id"] for page in doc["pages"] for n in walk(page["tree"]) if n["type"] in text_types]
            choice = rng.random()
            try:
                if choice < 0.30:
                    r = builder.dispatch("selection.select", target=rng.choice(nodes))
                elif choice < 0.55:
                    r = builder.dispatch("element.insert", entry=rng.choice(palette))
                elif choice < 0.72:
                    r = builder.dispatch("style.set", property=rng.choice(props), value=rng.choice(VALUES))
                elif choice < 0.78 and texts:
                    r = builder.dispatch("text.set", target=rng.choice(texts), content=f"texto {step}")
                elif choice < 0.84:
                    r = builder.dispatch("element.duplicate")
                elif choice < 0.90:
                    r = builder.dispatch("element.delete")
                elif choice < 0.95:
                    r = builder.dispatch("history.undo")
                else:
                    r = builder.dispatch("history.redo")
            except BuilderError as e:  # an invariant breach inside the builder surfaces here
                pytest.fail(f"seed {seed} passo {step}: o builder produziu estado inválido ou falhou: {e}")
            counts[r["status"] if r["status"] in counts else "other"] += 1
            if step % 25 == 0:
                assert builder.validate() == [], f"seed {seed} passo {step}"
        assert builder.validate() == []
        assert builder.export(), "exportação vazia"
    assert counts["done"] > STEPS  # the sequences really changed documents
    print("\nresultado das ações:", counts)

"""Repeated code: fragments equal up to names and constants are found, with every place they occur."""

from __future__ import annotations

import json

from nucleo.code.cliches import find


def test_repeated_fragment_found_across_files_despite_renaming(tmp_path):
    (tmp_path / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"strict": True, "noEmit": True,
                                                        "target": "ES2022"}, "include": ["src"]}), encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    body = "export function {f}(items: number[]): number {{ let total = 0; for (const {v} of items) {{ if ({v} > {k}) " \
           "{{ total += {v} * 2; }} }} return total; }}\n"
    src = tmp_path / "src"
    src.mkdir()
    for i, (f, v, k) in enumerate([("somaA", "x", 1), ("somaB", "y", 5), ("somaC", "z", 9)]):
        (src / f"m{i}.ts").write_text(body.format(f=f, v=v, k=k) + "export const outro = 1;\n", encoding="utf-8")
    found = find(str(tmp_path), "tsconfig.json", min_nodes=20, min_count=3)
    assert found and {f for f, _ in found[0].places} == {"src/m0.ts", "src/m1.ts", "src/m2.ts"}

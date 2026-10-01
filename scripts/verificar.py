"""Validate working-tree files before staging; never stage, commit or push.

Usage: python scripts/verificar.py --titulo "Commit title" [--arquivos file ...]
After staging exactly those files: python scripts/verificar.py --confirmar RECEIPT
The changed journal entry must have "Commit: este commit — TITLE", with the
exact --titulo, "O que mudou", "Motivo" (or "Mudança de rumo"), "Falhas
restantes", "Próximo passo", and a measurement command and number.
After successful checks, the script writes only one "Verificação automática"
line into that entry, with the actual results and receipt path, before taking
the final snapshot. --rapido does not write the journal.
Exit 0 approves only the recorded file contents; 1 means failure, 2 means a
successful --rapido check, which is NEVER sufficient for a commit.

Source snapshots cover this repository's code, tests and executable configuration.
External resources (data/, installed packages and the separate builder checkout)
are not copied or fingerprinted here; this receipt does not certify their identity.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "1960f1c"
JOURNAL = "docs/codex/progresso.md"
REVIEW = "docs/codex/revisao.md"
FROZEN = tuple("experiments/a1/" + name for name in (
    "congelado.json", "treino.py", "dev.py", "teste.py", "holdout.py",
    "contrastes.py", "dialogos.py", "paginas.py", "acoes.py",
))
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".toml",
                   ".yaml", ".yml", ".ini", ".cfg", ".sh", ".ps1", ".bat", ".cmd", ".sql",
                   ".html", ".css", ".lock"}


class Invalid(RuntimeError):
    pass


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        detail = b"\n".join(part for part in (result.stdout, result.stderr) if part)
        raise Invalid(f"git {args[0]} falhou ({result.returncode}): " +
                      detail.decode("utf-8", errors="replace").strip())
    return result.stdout


def changed_paths(root: Path) -> set[str]:
    tracked = git(root, "diff", "--no-renames", "--name-only", "-z", "HEAD", "--")
    new = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return {name.decode("utf-8") for name in (tracked + new).split(b"\0") if name}


def protected(name: str) -> bool:
    folded = name.casefold()
    return (folded == REVIEW.casefold() or folded in {path.casefold() for path in FROZEN} or
            folded.startswith(("data/cache/", "data/externo/")))


def source_snapshot(root: Path) -> dict:
    """Executable repository inputs, including untracked additions and deletions."""
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = set()
    for raw in names.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = Path(name)
        if name.casefold().startswith(("docs/", "data/")):
            continue
        project_input = (name.startswith(("nucleo/", "bridge/", "scripts/", "experiments/", "tests/")) and
                         path.suffix.lower() not in {".md", ".rst"})
        if (project_input or path.suffix.lower() in SOURCE_SUFFIXES or
                path.name in {".gitattributes", ".gitignore", "Makefile", "Dockerfile", ".npmrc"}
                or (path.name.startswith("requirements") and path.suffix == ".txt")):
            paths.add(name)
    return snapshot(root, sorted(paths))


def requires_audit(paths: list[str]) -> bool:
    return any(name.startswith(("nucleo/", "bridge/")) or name == "run_web.py" for name in paths)


def select_paths(root: Path, requested: list[str] | None) -> list[str]:
    changed = changed_paths(root)
    choices = requested if requested is not None else sorted(name for name in changed if not protected(name))
    selected = set()
    for name in choices:
        path = root / name
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise Invalid(f"Arquivo fora do repositório: {name}") from exc
        if protected(relative):
            raise Invalid("Arquivo protegido não pode ser aprovado (revisor, congelado ou dados): " + relative)
        if path.is_symlink() or path.is_dir():
            raise Invalid(f"Informe um arquivo regular, sem link: {name}")
        if relative not in changed:
            raise Invalid(f"Arquivo sem alteração publicável: {relative}")
        selected.add(relative)
    if JOURNAL not in selected:
        raise Invalid("Inclua o diário alterado em --arquivos: " + JOURNAL)
    return sorted(selected)


def snapshot(root: Path, paths: list[str]) -> dict:
    out = {}
    for name in paths:
        path = root / name
        if path.is_symlink():
            raise Invalid(f"Link não permitido: {name}")
        out[name] = ({"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "mode": stat.S_IMODE(path.stat().st_mode)} if path.exists() else None)
    return out


def check_frozen_sources(root: Path) -> dict:
    """Compare immutable sources without displaying or executing their contents."""
    hashes = {}
    for name in FROZEN:
        expected = git(root, "show", f"{BASELINE}:{name}").replace(b"\r\n", b"\n")
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise Invalid(f"Fonte congelada ausente ou inválida: {name}")
        actual = path.read_bytes().replace(b"\r\n", b"\n")
        if actual != expected:
            raise Invalid(f"Fonte congelada difere de {BASELINE}: {name}")
        hashes[name] = hashlib.sha256(actual).hexdigest()
    return hashes


def check_frozen(root: Path) -> dict:
    sources = check_frozen_sources(root)
    # This check must precede freeze: its historical missing-file branch writes
    # a new manifest. No caller of this verifier may take that branch.
    if not (root / "experiments/a1/congelado.json").is_file():
        raise Invalid("congelado.json ausente; recongelamento proibido")
    sys.path.insert(0, str(root))
    from experiments.a1.avaliar import freeze

    try:
        datasets = freeze(False)  # hashes only; no preflight, train or evaluation
    except SystemExit as exc:
        raise Invalid(str(exc)) from exc
    return {"baseline": BASELINE, "sources": sources, "datasets": datasets}


def check_journal(current: str, previous: str, title: str) -> str:
    commit_line = "- Commit: este commit — " + title
    entries = re.findall(r"(?ms)^### .*?(?=^### |\Z)", current)
    matching = [entry for entry in entries if commit_line in entry.splitlines()
                and entry.replace("\r\n", "\n") not in previous.replace("\r\n", "\n")]
    if not title.strip() or title != title.strip() or "\n" in title or "\r" in title or len(matching) != 1:
        raise Invalid("O diário precisa de uma entrada nova/alterada com '- Commit: este commit — '"
                      " seguido do --titulo exato")
    entry = matching[0]
    if [line for line in entry.splitlines() if line.startswith("- Commit:")] != [commit_line]:
        raise Invalid("A entrada precisa de uma única linha Commit para este commit")
    for label in ("O que mudou", "Motivo|Mudança de rumo", "Falhas restantes", "Próximo passo"):
        if not re.search(rf"(?m)^- (?:{label}):[ \t]*\S", entry):
            raise Invalid("Campo obrigatório ausente ou vazio no diário: " + label)
    measures = re.findall(r"(?ms)^- (?:Medida|Medidas|Antes|Depois|Verificação):\s*"
                          r"(.*?)(?=^- [^\n]+:|\Z)", entry)
    measured = "\n".join(measures)
    if not re.search(r"`[^`\n]+\s[^`\n]+`", measured):
        raise Invalid("A entrada precisa de comando de medida entre crases")
    if not re.search(r"\d", re.sub(r"`[^`]*`", "", measured)):
        raise Invalid("A entrada precisa de número medido fora do comando")
    return entry


def check_diff(root: Path, paths: list[str]) -> None:
    git(root, "diff", "--check", "HEAD", "--", *paths)
    untracked = {p.decode("utf-8") for p in
                 git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if p}
    for name in sorted(untracked.intersection(paths)):
        # --no-index also covers new files before staging. Exit 1 can simply
        # mean two files differ; whitespace errors produce diagnostics.
        result = subprocess.run(["git", "diff", "--no-index", "--check", "--", os.devnull, name],
                                cwd=root, capture_output=True)
        if result.returncode not in (0, 1) or result.stdout:
            detail = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
            raise Invalid(f"diff --check: {name}: {detail}")


def run_suite(root: Path, log: Path) -> dict:
    xml = log.with_suffix(".xml")
    command = [sys.executable, "-m", "pytest", "-q", "tests", "--ignore=tests/test_web.py",
               "-o", "addopts=", "--junitxml=" + str(xml)]
    print("Suíte completa, em prioridade baixa; aguarde. Log: " + str(log), flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("PYTEST_ADDOPTS", None)  # an inherited -k/-m must not silently narrow this check
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
    summary = log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
    if result.returncode:
        raise Invalid(f"Suíte falhou ({result.returncode}); veja {log}\n" + "\n".join(summary))
    tree = ET.parse(xml).getroot()
    suites = [tree] if tree.tag == "testsuite" else tree.findall("testsuite")
    counts = {key: sum(int(suite.attrib[key]) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    if counts["passed"] <= 0 or min(counts.values()) < 0 or counts["failures"] or counts["errors"]:
        raise Invalid("JUnit sem suíte bem-sucedida; aprovação recusada")
    return {"command": command, "returncode": result.returncode, "log": str(log), "summary": summary,
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "counts": counts,
            "junitxml": str(xml), "junit_sha256": hashlib.sha256(xml.read_bytes()).hexdigest()}


def inspect_audit(report: dict) -> None:
    counts = ("handwritten intent rules (unreviewed word lists in executed code)", "regex intent rules",
              "legacy hand knowledge reached with effect", "init weights naming a word")
    summary = report.get("summary", {})
    if any(type(summary.get(key)) is not int or summary[key] != 0 for key in counts):
        raise Invalid("Auditoria ausente, incompleta ou com alertas: revise o JSON, não só o exitcode")
    if not report.get("utterances_run") or not report.get("functions_executed"):
        raise Invalid("Auditoria sem execução observada")
    for key in ("legacy_hand_knowledge_reached", "regexes", "literal_collections", "init_weights_naming_words"):
        if not isinstance(report.get(key), list):
            raise Invalid("Auditoria sem lista de achados: " + key)
    if (report["init_weights_naming_words"] or
            any(row.get("class") != "legado-sem-efeito" for row in report["legacy_hand_knowledge_reached"]) or
            any(row.get("class") == "INTENT REGEX" for row in report["regexes"]) or
            any(row.get("class") == "UNREVIEWED" and row.get("natural_words")
                for row in report["literal_collections"])):
        raise Invalid("Achados detalhados da auditoria impedem aprovação")


def run_audit(root: Path, log: Path) -> dict:
    command = [sys.executable, "experiments/a1/auditoria.py"]
    print("Auditoria TRAIN+DEV, depois da suíte; log: " + str(log), flush=True)
    started_ns = time.time_ns()
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=root, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise Invalid(f"Auditoria falhou ({result.returncode}); veja {log}")
    path = root / "data/cache/a1_auditoria.json"
    if path.stat().st_mtime_ns < started_ns:
        raise Invalid("Auditoria não atualizou o JSON; resultado antigo não aprova este snapshot")
    raw = path.read_bytes()
    report = json.loads(raw)
    inspect_audit(report)
    return {"command": command, "log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "report_path": str(path), "report_sha256": hashlib.sha256(raw).hexdigest(), "report": report}


def automatic_entry(entry: str, tests: dict, audit: dict | None, receipt: Path) -> str:
    counts = tests["counts"]
    line = (f"- Verificação automática: `{subprocess.list2cmdline(tests['command'])}` → "
            f"{counts['tests']} testes; {counts['passed']} passaram, {counts['failures']} falhas, "
            f"{counts['errors']} erros, {counts['skipped']} pulados")
    if audit:
        result = audit["report"]
        line += (f"; auditoria `{subprocess.list2cmdline(audit['command'])}` → "
                 f"{result['utterances_run']} enunciados, {result['functions_executed']} funções, "
                 f"{sum(result['summary'].values())} alertas")
    line += f". Comprovante: `{receipt.as_posix()}`.\n"
    lines = [text for text in entry.splitlines(keepends=True)
             if not text.startswith("- Verificação automática:")]
    if lines[0].endswith("\r\n"):
        line = line.removesuffix("\n") + "\r\n"
    return lines[0] + line + "".join(lines[1:])


def verify(root: Path, title: str, requested: list[str] | None, quick: bool, log: Path,
           receipt: Path | None = None) -> dict:
    paths = select_paths(root, requested)
    head = git(root, "rev-parse", "HEAD").decode("ascii").strip()
    before = snapshot(root, paths)
    sources = source_snapshot(root)
    excluded_code = (changed_paths(root) & set(sources)) - set(paths)
    if excluded_code:
        raise Invalid("Código alterado excluído do commit influencia a validação: " + ", ".join(sorted(excluded_code)))
    frozen = check_frozen(root)
    journal_text = (root / JOURNAL).read_bytes().decode("utf-8")
    entry = check_journal(journal_text,
                          git(root, "show", f"HEAD:{JOURNAL}").decode("utf-8"), title)
    check_diff(root, paths)
    tests = None if quick else run_suite(root, log)
    motor = requires_audit(paths)
    audit = run_audit(root, log.with_name(log.stem + "-audit.log")) if motor and not quick else None
    if snapshot(root, paths) != before:
        raise Invalid("Arquivos a publicar mudaram durante a validação; execute novamente")
    if source_snapshot(root) != sources:
        raise Invalid("Fontes, testes ou configuração mudaram durante a validação; execute novamente")
    if git(root, "rev-parse", "HEAD").decode("ascii").strip() != head:
        raise Invalid("HEAD mudou durante a validação; execute novamente")
    if check_frozen_sources(root) != frozen["sources"]:
        raise Invalid("Fontes congeladas mudaram durante a validação")
    check_diff(root, paths)
    if not quick:
        updated = automatic_entry(entry, tests, audit, receipt or log.with_suffix(".json"))
        if (root / JOURNAL).read_bytes().decode("utf-8") != journal_text:
            raise Invalid("Diário mudou antes do registro automático")
        # The only deliberate source-tree write: actual successful results,
        # never a predicted test count or a premature approval.
        journal_bytes = journal_text.replace(entry, updated, 1).encode("utf-8")
        (root / JOURNAL).write_bytes(journal_bytes)
        expected = dict(before)
        expected[JOURNAL] = {"sha256": hashlib.sha256(journal_bytes).hexdigest(), "mode": before[JOURNAL]["mode"]}
        final = snapshot(root, paths)
        if final != expected or source_snapshot(root) != sources:
            raise Invalid("Arquivos mudaram durante o registro automático")
        if git(root, "rev-parse", "HEAD").decode("ascii").strip() != head:
            raise Invalid("HEAD mudou durante o registro automático")
        before, entry = final, updated
        check_diff(root, paths)
    return {"head": head, "frozen": frozen, "files": before, "sources": sources, "tests": tests, "audit": audit,
            "journal_entry_sha256": hashlib.sha256(entry.encode("utf-8")).hexdigest(),
            "valido_para_commit": not quick, "aprovados": [] if quick else paths}


def artifact_bytes(root: Path, name: str, digest: str) -> bytes:
    path = root / name
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise Invalid("Artefato fora do repositório") from exc
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise Invalid("Hash do artefato difere do comprovante: " + name)
    return raw


def confirm(root: Path, receipt: Path) -> list[str]:
    """Cheap post-stage check. Read the index; never acquire it for mutation."""
    report = json.loads(receipt.read_text(encoding="utf-8"))
    paths = report.get("aprovados", [])
    if (report.get("status") != "aprovado" or report.get("valido_para_commit") is not True or
            not paths or sorted(paths) != sorted(report.get("files", {})) or
            (report.get("tests") or {}).get("returncode") != 0):
        raise Invalid("Comprovante não aprova um commit completo")
    for name in paths:
        try:
            normalized = (root / name).resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise Invalid("Comprovante contém caminho fora do repositório") from exc
        if normalized != name or protected(name):
            raise Invalid("Comprovante contém caminho inválido ou protegido: " + name)
    if git(root, "rev-parse", "HEAD").decode("ascii").strip() != report["head"]:
        raise Invalid("HEAD difere do comprovante; valide novamente")
    if snapshot(root, paths) != report["files"]:
        raise Invalid("Arquivos atuais diferem do comprovante; valide novamente")
    if source_snapshot(root) != report.get("sources"):
        raise Invalid("Fontes, testes ou configuração diferem do comprovante; valide novamente")
    if check_frozen_sources(root) != report["frozen"]["sources"]:
        raise Invalid("Fontes congeladas diferem do comprovante")
    tests = report["tests"]
    artifact_bytes(root, tests["log"], tests["log_sha256"])
    artifact_bytes(root, tests["junitxml"], tests["junit_sha256"])
    audit = report.get("audit")
    if requires_audit(paths) and not audit:
        raise Invalid("Comprovante sem auditoria obrigatória do motor")
    if audit:
        artifact_bytes(root, audit["log"], audit["log_sha256"])
        raw = artifact_bytes(root, audit["report_path"], audit["report_sha256"])
        if json.loads(raw) != audit["report"]:
            raise Invalid("Auditoria incorporada difere do artefato verificado")
        inspect_audit(audit["report"])
    staged = {name.decode("utf-8") for name in
              git(root, "diff", "--cached", "--no-renames", "--name-only", "-z", "HEAD", "--").split(b"\0") if name}
    if staged != set(paths):
        raise Invalid("Index deve conter exatamente os arquivos aprovados, sem extras nem ausências")
    for name in paths:
        entries = [row for row in git(root, "ls-files", "--stage", "-z", "--", name).split(b"\0") if row]
        if report["files"][name] is None:
            if entries:
                raise Invalid("Arquivo removido ainda presente no index: " + name)
            continue
        if len(entries) != 1:
            raise Invalid("Index ausente ou com conflito: " + name)
        mode, blob, stage = entries[0].partition(b"\t")[0].split()
        expected_mode = b"100755" if report["files"][name]["mode"] & stat.S_IXUSR else b"100644"
        if mode != expected_mode:
            raise Invalid("Modo/tipo do index difere do arquivo regular aprovado: " + name)
        expected = git(root, "hash-object", "--path=" + name, "--", name).strip()
        if stage != b"0" or blob != expected:
            raise Invalid("Blob do index difere do arquivo aprovado: " + name)
    git(root, "diff", "--cached", "--check", "--", *paths)
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--titulo")
    mode.add_argument("--confirmar", type=Path, help="Após stage, confere exatamente o comprovante aprovado")
    parser.add_argument("--arquivos", nargs="+", help="Somente arquivos deste passo, incluindo o diário")
    parser.add_argument("--rapido", action="store_true", help="Sem suíte; NÃO válido para commit (saída 2)")
    args = parser.parse_args(argv)
    if args.confirmar:
        if args.arquivos or args.rapido:
            parser.error("--confirmar não aceita --arquivos nem --rapido")
        try:
            sys.path.insert(0, str(ROOT))
            from experiments.a1.runtime import lower_priority

            lower_priority()
            paths = confirm(ROOT, args.confirmar)
        except (Invalid, OSError, ValueError, KeyError) as exc:
            print("Não confirmado: " + str(exc), file=sys.stderr)
            return 1
        print(f"Confirmado: index e arquivos atuais correspondem aos {len(paths)} arquivos aprovados")
        return 0
    cache = ROOT / "data/cache"
    cache.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    receipt = cache / f"verificar-{stamp}.json"
    log = cache / f"verificar-{stamp}-pytest.log"
    report = {"title": args.titulo, "requested_files": args.arquivos, "quick": args.rapido,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "valido_para_commit": False, "aprovados": []}
    try:
        sys.path.insert(0, str(ROOT))
        from experiments.a1.runtime import lower_priority

        lower_priority()
        report.update(verify(ROOT, args.titulo, args.arquivos, args.rapido, log, receipt))
        report["status"] = "rapido_nao_valido_para_commit" if args.rapido else "aprovado"
        code = 2 if args.rapido else 0
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        report.update(status="reprovado", error=str(exc) or type(exc).__name__)
        code = 1
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {len(report['aprovados'])} arquivos aprovados. Comprovante: {receipt}")
    if "error" in report:
        print(report["error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

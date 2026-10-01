"""Pre-commit verification without running pytest recursively or reading A1 data."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import verificar as v


ENTRY = """### 2026-10-01 18:00: validação
- Commit: este commit — Verify ready work
- O que mudou: verificação dos arquivos deste passo.
- Motivo: impedir publicação sem validação.
- Medida: `python probe.py` → 3 verificações, 0 falhas.
- Falhas restantes: nenhuma nesta fixture.
- Próximo passo: preservar o resultado verificado.
"""


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    v.git(tmp_path, "config", "user.name", "Verifier test")
    v.git(tmp_path, "config", "user.email", "verifier@example.invalid")
    v.git(tmp_path, "config", "core.autocrlf", "false")
    write(tmp_path, v.JOURNAL, "# Diário\n")
    write(tmp_path, "unit.py", "old = 1\n")
    v.git(tmp_path, "add", "--", v.JOURNAL, "unit.py")
    v.git(tmp_path, "commit", "-qm", "Fixture")
    write(tmp_path, v.JOURNAL, "# Diário\n\n" + ENTRY)
    write(tmp_path, "unit.py", "new = 2\n")
    return tmp_path


def fake_frozen(monkeypatch):
    monkeypatch.setattr(v, "check_frozen", lambda root: {"sources": {"frozen": "same"}})
    monkeypatch.setattr(v, "check_frozen_sources", lambda root: {"frozen": "same"})


def fake_suite(root, log):
    log.write_text("3 passed\n", encoding="utf-8")
    xml = log.with_suffix(".xml")
    xml.write_text('<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>',
                   encoding="utf-8")
    return {"returncode": 0, "log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "junitxml": str(xml), "junit_sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
            "counts": {"tests": 3, "passed": 3, "failures": 0, "errors": 0, "skipped": 0},
            "command": [sys.executable, "-m", "pytest", "-q", "tests", "--ignore=tests/test_web.py",
                        "-o", "addopts=", "--junitxml=" + str(xml)]}


def test_journal_requires_current_title_command_number_and_reason():
    assert v.check_journal(ENTRY, "", "Verify ready work") == ENTRY
    for entry in (ENTRY.replace("3 verificações, 0 falhas", "sem contagem"),
                  ENTRY.replace("`python probe.py`", "comando omitido"),
                  ENTRY.replace("- Motivo:", "- Nota:")):
        with pytest.raises(v.Invalid):
            v.check_journal(entry, "", "Verify ready work")
    with pytest.raises(v.Invalid):
        v.check_journal(ENTRY, ENTRY, "Verify ready work")
    with pytest.raises(v.Invalid):
        v.check_journal(ENTRY, "", "Different title")


@pytest.mark.parametrize("field", ["Falhas restantes", "Próximo passo", "Motivo", "O que mudou"])
def test_journal_rejects_missing_or_empty_required_fields(field):
    lines = ENTRY.splitlines(keepends=True)
    missing = "".join(line for line in lines if not line.startswith("- " + field + ":"))
    empty = "".join("- " + field + ": \n" if line.startswith("- " + field + ":") else line for line in lines)
    for text in (missing, empty):
        with pytest.raises(v.Invalid, match="Campo obrigatório"):
            v.check_journal(text, "", "Verify ready work")


def test_journal_requires_exact_title_in_this_commit_line():
    elsewhere = ENTRY.replace("- Commit: este commit — Verify ready work", "- Commit: previous change")
    elsewhere += "- Nota: Verify ready work\n"
    for text, title in ((elsewhere, "Verify ready work"), (ENTRY, "verify ready work"),
                        (ENTRY.replace("este commit", "outro commit"), "Verify ready work"),
                        (ENTRY + "- Commit: another entry\n", "Verify ready work")):
        with pytest.raises(v.Invalid, match="Commit|titulo"):
            v.check_journal(text, "", title)


def test_git_error_includes_stdout_and_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(v.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=2, stdout=b"unit.py:1: trailing whitespace\n", stderr=b"additional diagnostic\n"))
    with pytest.raises(v.Invalid) as caught:
        v.git(tmp_path, "diff", "--check")
    assert "trailing whitespace" in str(caught.value)
    assert "additional diagnostic" in str(caught.value)


def test_explicit_scope_excludes_other_work_and_forbids_review(repo):
    write(repo, "other.py", "other = 1\n")
    write(repo, v.REVIEW, "# Review\n")
    assert v.select_paths(repo, [v.JOURNAL, "unit.py"]) == [v.JOURNAL, "unit.py"]
    assert v.REVIEW not in v.select_paths(repo, None)
    with pytest.raises(v.Invalid, match="revisor"):
        v.select_paths(repo, [v.JOURNAL, v.REVIEW])
    with pytest.raises(v.Invalid, match="diário"):
        v.select_paths(repo, ["unit.py"])
    with pytest.raises(v.Invalid, match="fora"):
        v.select_paths(repo, [v.JOURNAL, "../outside.py"])


def test_source_comparison_blocks_rewritten_frozen_manifest(repo, monkeypatch):
    # Synthetic files in a temporary repository, never actual A1 examples.
    names = ("fixture/data.json", "fixture/source.py")
    for name in names:
        write(repo, name, "unchanged\n")
    v.git(repo, "add", "--", *names)
    v.git(repo, "commit", "-qm", "Frozen fixture")
    monkeypatch.setattr(v, "BASELINE", "HEAD")
    monkeypatch.setattr(v, "FROZEN", names)
    assert len(v.check_frozen_sources(repo)) == 2
    write(repo, names[0], "rewritten\n")
    with pytest.raises(v.Invalid, match="congelada difere"):
        v.check_frozen_sources(repo)


def test_freeze_uses_only_false_and_never_creates_missing_manifest(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(v, "check_frozen_sources", lambda root: {"source": "same"})
    monkeypatch.setitem(sys.modules, "experiments.a1.avaliar", SimpleNamespace(
        freeze=lambda refreeze: calls.append(refreeze) or {"TRAIN": "hash"}))
    with pytest.raises(v.Invalid, match="recongelamento proibido"):
        v.check_frozen(repo)
    assert calls == []
    write(repo, "experiments/a1/congelado.json", "{}\n")
    assert v.check_frozen(repo)["datasets"] == {"TRAIN": "hash"}
    assert calls == [False]


def test_suite_runner_uses_complete_required_command(repo, monkeypatch):
    calls = []
    write(repo, "pytest.ini", "[pytest]\naddopts = -k narrow_selection\n")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-m narrow_selection")

    def run(command, **kwargs):
        calls.append(command)
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        kwargs["stdout"].write("3 passed in 0.1s\n")
        Path(command[-1].removeprefix("--junitxml=")).write_text(
            '<testsuites><testsuite tests="4" failures="0" errors="0" skipped="1"/></testsuites>', encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(v.subprocess, "run", run)
    result = v.run_suite(repo, repo / "suite.log")
    assert calls == [[sys.executable, "-m", "pytest", "-q", "tests", "--ignore=tests/test_web.py",
                      "-o", "addopts=", "--junitxml=" + str(repo / "suite.xml")]]
    assert result["returncode"] == 0
    assert result["summary"] == ["3 passed in 0.1s"]
    assert result["counts"] == {"tests": 4, "passed": 3, "failures": 0, "errors": 0, "skipped": 1}


@pytest.mark.parametrize("total, failures, errors, skipped", [(3, 0, 0, 3), (0, 0, 0, 0),
                                                            (3, 1, 0, 0), (3, 0, 1, 0)])
def test_suite_rejects_no_passes_or_junit_failures_even_with_zero_exitcode(
        repo, monkeypatch, total, failures, errors, skipped):
    def run(command, **kwargs):
        kwargs["stdout"].write("mocked runner\n")
        Path(command[-1].removeprefix("--junitxml=")).write_text(
            f'<testsuites><testsuite tests="{total}" failures="{failures}" errors="{errors}" '
            f'skipped="{skipped}"/></testsuites>', encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(v.subprocess, "run", run)
    with pytest.raises(v.Invalid, match="JUnit"):
        v.run_suite(repo, repo / "suite.log")


def test_full_verification_requires_suite_and_does_not_stage(repo, monkeypatch):
    fake_frozen(monkeypatch)
    calls = []
    monkeypatch.setattr(v, "run_suite", lambda root, log: calls.append((root, log)) or fake_suite(root, log))
    before_index = v.git(repo, "ls-files", "--stage", "-z")
    log = repo / "result.log"
    result = v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, log)
    assert calls == [(repo, log)]
    assert result["valido_para_commit"] is True
    assert result["aprovados"] == [v.JOURNAL, "unit.py"]
    assert v.git(repo, "ls-files", "--stage", "-z") == before_index
    assert result["files"] == v.snapshot(repo, result["aprovados"])
    journal = (repo / v.JOURNAL).read_text(encoding="utf-8")
    assert journal.count("- Verificação automática:") == 1
    assert "3 testes; 3 passaram, 0 falhas, 0 erros, 0 pulados" in journal
    assert (repo / "result.json").as_posix() in journal
    assert ENTRY.split("- Motivo:")[1].strip() in journal


def test_quick_mode_never_approves_files(repo, monkeypatch):
    fake_frozen(monkeypatch)
    monkeypatch.setattr(v, "run_suite", lambda *args: pytest.fail("quick mode ran the suite"))
    before = (repo / v.JOURNAL).read_bytes()
    result = v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], True, repo / "result.log")
    assert result["valido_para_commit"] is False
    assert result["aprovados"] == []
    assert result["tests"] is None
    assert (repo / v.JOURNAL).read_bytes() == before


def test_file_change_during_tests_invalidates_receipt(repo, monkeypatch):
    fake_frozen(monkeypatch)

    def changed(root, log):
        write(root, "unit.py", "changed_during_tests = 3\n")
        return {"returncode": 0}

    monkeypatch.setattr(v, "run_suite", changed)
    with pytest.raises(v.Invalid, match="mudaram durante"):
        v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "result.log")


def test_diff_check_includes_untracked_files_before_staging(repo):
    write(repo, "new.py", "bad = 1 \n")
    with pytest.raises(v.Invalid, match="diff --check"):
        v.check_diff(repo, ["new.py"])


def test_main_writes_failure_receipt_without_approved_files(repo, monkeypatch):
    from experiments.a1 import runtime

    monkeypatch.setattr(v, "ROOT", repo)
    monkeypatch.setattr(runtime, "lower_priority", lambda: None)

    def failed(*args):
        raise v.Invalid("suite failed")

    monkeypatch.setattr(v, "verify", failed)
    assert v.main(["--titulo", "Verify ready work"]) == 1
    receipts = list((repo / "data/cache").glob("verificar-*.json"))
    assert len(receipts) == 1
    report = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert report["status"] == "reprovado"
    assert report["valido_para_commit"] is False
    assert report["aprovados"] == []


def clean_audit():
    return {"utterances_run": 1, "functions_executed": 1,
            "legacy_hand_knowledge_reached": [], "regexes": [], "literal_collections": [],
            "init_weights_naming_words": [], "summary": {
                "handwritten intent rules (unreviewed word lists in executed code)": 0,
                "regex intent rules": 0, "legacy hand knowledge reached with effect": 0,
                "init weights naming a word": 0}}


def test_audit_checks_detailed_findings_even_with_zero_summary():
    report = clean_audit()
    v.inspect_audit(report)
    report["regexes"] = [{"class": "INTENT REGEX"}]
    with pytest.raises(v.Invalid, match="detalhados"):
        v.inspect_audit(report)
    with pytest.raises(v.Invalid, match="incompleta"):
        v.inspect_audit({"summary": {}})


def test_motor_change_runs_audit_after_suite(repo, monkeypatch):
    fake_frozen(monkeypatch)
    write(repo, "nucleo/lang/unit.py", "unit = 1\n")
    calls = []
    monkeypatch.setattr(v, "run_suite", lambda *args: calls.append("suite") or fake_suite(*args))
    monkeypatch.setattr(v, "run_audit", lambda *args: calls.append("audit") or {
        "command": [sys.executable, "experiments/a1/auditoria.py"], "report": clean_audit()})
    result = v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py", "nucleo/lang/unit.py"],
                      False, repo / "out.log")
    assert calls == ["suite", "audit"]
    assert result["audit"]["report"] == clean_audit()


def approved_receipt(repo, monkeypatch):
    fake_frozen(monkeypatch)
    monkeypatch.setattr(v, "run_suite", fake_suite)
    path = repo / "data/cache/receipt.json"
    report = v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "out.log", path)
    report["status"] = "aprovado"
    return write(repo, "data/cache/receipt.json", json.dumps(report))


def test_confirmation_checks_exact_index_and_current_contents(repo, monkeypatch):
    receipt = approved_receipt(repo, monkeypatch)
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    assert v.confirm(repo, receipt) == [v.JOURNAL, "unit.py"]
    write(repo, "docs/unrelated.md", "Other work\n")
    v.git(repo, "add", "--", "docs/unrelated.md")
    with pytest.raises(v.Invalid, match="exatamente"):
        v.confirm(repo, receipt)


def test_confirmation_rejects_stale_staged_blob(repo, monkeypatch):
    receipt = approved_receipt(repo, monkeypatch)
    write(repo, "unit.py", "incorrect_staged_version = 9\n")
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    write(repo, "unit.py", "new = 2\n")
    with pytest.raises(v.Invalid, match="Blob"):
        v.confirm(repo, receipt)


@pytest.mark.parametrize("mode", ["120000", "160000", "100755"])
def test_confirmation_rejects_wrong_index_type_or_mode(repo, monkeypatch, mode):
    receipt = approved_receipt(repo, monkeypatch)
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    # Symlink and executable variants reuse the approved blob; the gitlink
    # uses a real commit object, so all three index entries are Git-valid.
    object_id = v.git(repo, "rev-parse", "HEAD" if mode == "160000" else ":unit.py").decode("ascii").strip()
    v.git(repo, "update-index", "--cacheinfo", f"{mode},{object_id},unit.py")
    with pytest.raises(v.Invalid, match="Modo/tipo"):
        v.confirm(repo, receipt)


def test_confirmation_rejects_quick_receipt(repo):
    receipt = write(repo, "quick.json", json.dumps({"status": "rapido_nao_valido_para_commit",
                                                   "valido_para_commit": False, "aprovados": []}))
    with pytest.raises(v.Invalid, match="completo"):
        v.confirm(repo, receipt)


@pytest.mark.parametrize("name", [v.FROZEN[0], v.FROZEN[1], "data/cache/tracked.py",
                                  "data/externo/resource.json", v.REVIEW])
def test_protected_files_cannot_be_selected_or_confirmed(repo, monkeypatch, name):
    receipt = approved_receipt(repo, monkeypatch)
    write(repo, name, "protected\n")
    with pytest.raises(v.Invalid, match="protegido"):
        v.select_paths(repo, [v.JOURNAL, name])
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["aprovados"].append(name)
    report["files"].update(v.snapshot(repo, [name]))
    receipt.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(v.Invalid, match="protegido"):
        v.confirm(repo, receipt)


@pytest.mark.parametrize("name", ["other.py", "pyproject.toml", "tests/fixture.txt"])
def test_unselected_code_blocks_validation_but_unselected_docs_do_not(repo, monkeypatch, name):
    fake_frozen(monkeypatch)
    monkeypatch.setattr(v, "run_suite", fake_suite)
    write(repo, "docs/other.md", "Other documentation\n")
    result = v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "out.log")
    assert result["valido_para_commit"]
    write(repo, name, "other = 1\n")
    with pytest.raises(v.Invalid, match="Código alterado excluído"):
        v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "out.log")


@pytest.mark.parametrize("new_source", [False, True])
def test_dependency_changes_during_suite_invalidate_result(repo, monkeypatch, new_source):
    fake_frozen(monkeypatch)
    if not new_source:
        write(repo, "support.py", "support = 1\n")
        v.git(repo, "add", "--", "support.py")
        v.git(repo, "commit", "-qm", "Support fixture")

    def run(root, log):
        result = fake_suite(root, log)
        write(root, "support.py", "support = 2\n")
        return result

    monkeypatch.setattr(v, "run_suite", run)
    with pytest.raises(v.Invalid, match="Fontes, testes ou configuração mudaram"):
        v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "out.log")


@pytest.mark.parametrize("name", ["nucleo/session.py", "nucleo/web_ui.py", "bridge/builder/main.ts", "run_web.py"])
def test_audit_includes_session_web_and_bridge(name):
    assert v.requires_audit([name])


def test_confirmation_rejects_modified_suite_log(repo, monkeypatch):
    receipt = approved_receipt(repo, monkeypatch)
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    write(repo, "out.log", "Edited result\n")
    with pytest.raises(v.Invalid, match="Hash do artefato"):
        v.confirm(repo, receipt)


def test_confirmation_rejects_new_executable_configuration(repo, monkeypatch):
    receipt = approved_receipt(repo, monkeypatch)
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    write(repo, "pytest.ini", "[pytest]\n")
    with pytest.raises(v.Invalid, match="configuração diferem"):
        v.confirm(repo, receipt)


def test_confirmation_checks_audit_artifact_and_embedded_result(repo, monkeypatch):
    receipt = approved_receipt(repo, monkeypatch)
    v.git(repo, "add", "--", v.JOURNAL, "unit.py")
    result = clean_audit()
    path = write(repo, "data/cache/audit.json", json.dumps(result))
    log = write(repo, "data/cache/audit.log", "Clean audit\n")
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["audit"] = {"log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                       "report_path": str(path), "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "report": result}
    receipt.write_text(json.dumps(report), encoding="utf-8")
    assert v.confirm(repo, receipt) == [v.JOURNAL, "unit.py"]
    report["audit"]["report"]["utterances_run"] = 2
    receipt.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(v.Invalid, match="incorporada"):
        v.confirm(repo, receipt)
    report["audit"]["report"]["utterances_run"] = 1
    receipt.write_text(json.dumps(report), encoding="utf-8")
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(v.Invalid, match="Hash do artefato"):
        v.confirm(repo, receipt)


def test_failed_suite_does_not_write_success_into_journal(repo, monkeypatch):
    fake_frozen(monkeypatch)
    before = (repo / v.JOURNAL).read_bytes()

    def failed(*args):
        raise v.Invalid("suite failed")

    monkeypatch.setattr(v, "run_suite", failed)
    with pytest.raises(v.Invalid, match="suite failed"):
        v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / "out.log")
    assert (repo / v.JOURNAL).read_bytes() == before


def test_rerun_replaces_single_automatic_journal_line(repo, monkeypatch):
    fake_frozen(monkeypatch)
    monkeypatch.setattr(v, "run_suite", fake_suite)
    for name in ("first", "second"):
        v.verify(repo, "Verify ready work", [v.JOURNAL, "unit.py"], False, repo / (name + ".log"))
    journal = (repo / v.JOURNAL).read_text(encoding="utf-8")
    assert journal.count("- Verificação automática:") == 1
    assert "second.json" in journal
    assert "first.json" not in journal

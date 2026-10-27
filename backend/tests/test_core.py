import codecs
import json
import threading
from pathlib import Path

import pytest

from logsanitizer.engine import Detector, replace
from logsanitizer.formats import FormatError, iter_blocks
from logsanitizer.pipeline import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_READY,
    run_project,
)
from logsanitizer.project import Workspace
from logsanitizer.rules import Rule, RuleError, RuleSet, check_regex_performance, default_ruleset


def sanitize_text(text, names=None, mapping=None):
    detector = Detector(default_ruleset(), names)
    mapping = {} if mapping is None else mapping

    def lookup(category, value):
        key = (category, value)
        if key not in mapping:
            mapping[key] = f"[{category}_{sum(c == category for c, _ in mapping) + 1}]"
        return mapping[key]

    return replace(text, detector.find(text), lookup)[0]


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "ws")


def write(path: Path, text: str, encoding="utf-8", bom=b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bom + text.encode(encoding))
    return path


def output_of(project, report, rel):
    return (project.runs_dir / report["run_id"] / "output" / rel).read_bytes()


# --- engine -----------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("from 10.1.2.3 port 22", "from [IP_1] port 22"),
    ("srv01.corp.local up", "[Server_1].[Domain_1] up"),
    ("mail to jdoe@corp.local", "mail to [User_1]@[Domain_1]"),
    ("CORP\\jdoe logged on", "[Domain_1]\\[User_1] logged on"),
    ("open \\\\fs01\\share", "open \\\\[Server_1]\\share"),
    ("hw 00:1a:2b:3c:4d:5e", "hw [MAC_1]"),
    ("v6 fd00::1 ok", "v6 [IPv6_1] ok"),
    ("password=hunter2;x", "password=[Secret_1];x"),
    ("mapped ::ffff:10.1.2.3 end", "mapped ::ffff:[IP_1] end"),
    ("zero 010.001.002.003 and 10.1.2.3", "zero [IP_1] and [IP_1]"),
    ("v6 fe80::1%eth0, full 2001:db8:0:0:0:0:2:1.", "v6 [IPv6_1], full [IPv6_2]."),
])
def test_default_rules(text, expected):
    assert sanitize_text(text) == expected


@pytest.mark.parametrize("text", [
    "at com.example.db.Pool.open(Pool.java:42)",
    "10:15:00 started version 1.2.3",
    "C:\\Windows\\System32\\drivers",
    "listening on 127.0.0.1 and ::1",
    "std::vector<int> and System.Net.Http.HttpClient",
])
def test_no_false_positives(text):
    assert sanitize_text(text) == text


def test_same_value_same_placeholder_and_case_insensitive():
    mapping = {}
    a = sanitize_text("SRV01.CORP.LOCAL and 10.0.0.1", mapping=mapping)
    b = sanitize_text("srv01.corp.local and 10.0.0.1", mapping=mapping)
    assert a == b == "[Server_1].[Domain_1] and [IP_1]"


def test_name_lists_match_short_hostnames():
    names = {"Server": ["dc01"], "User": ["svc_backup"]}
    assert sanitize_text("dc01 ran as svc_backup", names) == "[Server_1] ran as [User_1]"
    assert sanitize_text("dc010 unchanged", names) == "dc010 unchanged"


def test_no_double_replacement_and_placeholders_are_stable():
    once = sanitize_text("user=a@srv1.corp.local token: abc")
    assert sanitize_text(once) == once


# --- rules ------------------------------------------------------------------------

def test_ruleset_roundtrip(tmp_path):
    path = tmp_path / "rules.json"
    default_ruleset().save(path)
    loaded = RuleSet.load(path)
    assert [r.id for r in loaded.rules] == [r.id for r in default_ruleset().rules]
    assert "names" not in json.loads(path.read_text(encoding="utf-8"))


def test_invalid_rules_are_rejected():
    data = default_ruleset().to_dict()
    data["rules"].append({"id": "bad", "name": "x", "pattern": "(", "category": "X"})
    with pytest.raises(RuleError):
        RuleSet.from_dict(data)
    data["rules"][-1] = {"id": "empty", "name": "x", "pattern": "a*", "category": "X"}
    with pytest.raises(RuleError):
        RuleSet.from_dict(data)


def test_catastrophic_regex_is_detected():
    slow = Rule(id="slow", name="slow", pattern=r"(a+)+$", category="X")
    assert not check_regex_performance(slow, [], timeout=1.0)
    assert check_regex_performance(default_ruleset().rules[0], [], timeout=5.0)


# --- streaming --------------------------------------------------------------------

def test_iter_blocks_keeps_lines_and_splits_long_lines():
    import io
    text = "a\r\nb\n" + "x " * 50 + "\n"
    blocks = list(iter_blocks(io.StringIO(text, newline=""), block_chars=16))
    assert "".join(blocks) == text
    assert all(len(b) <= 32 for b in blocks)


# --- pipeline ---------------------------------------------------------------------

def test_consistent_across_files_runs_and_order(workspace, tmp_path):
    a = write(tmp_path / "in" / "a.log", "host srv01.corp.local ip 10.0.0.1\n")
    b = write(tmp_path / "in" / "b.log", "ip 10.0.0.2 then 10.0.0.1 on SRV01.corp.local\n")
    p1 = workspace.create("Eins")
    p1.add_sources([a, b])
    r1 = run_project(p1)
    assert r1["status"] == STATUS_READY
    assert output_of(p1, r1, "a.log") == b"host [Server_1].[Domain_1] ip [IP_1]\n"
    assert output_of(p1, r1, "b.log") == b"ip [IP_2] then [IP_1] on [Server_1].[Domain_1]\n"

    p2 = workspace.create("Zwei")
    p2.add_sources([b, a])
    r2 = run_project(p2)
    assert output_of(p2, r2, "a.log") == output_of(p1, r1, "a.log")

    c = write(tmp_path / "in" / "c.log", "new 10.0.0.0 old 10.0.0.2\n")
    p1.add_sources([c])
    r3 = run_project(p1)
    assert output_of(p1, r3, "b.log") == output_of(p1, r1, "b.log")
    assert output_of(p1, r3, "c.log") == b"new [IP_3] old [IP_2]\n"


def test_learned_values_replace_standalone_occurrences(workspace, tmp_path):
    src = write(tmp_path / "x.log", "login CORP\\jdoe\nlater jdoe again\n")
    project = workspace.create("p")
    project.add_sources([src])
    report = run_project(project)
    assert output_of(project, report, "x.log") == (
        b"login [Domain_1]\\[User_1]\nlater [User_1] again\n")


def test_json_structure_preserved_byte_for_byte(workspace, tmp_path):
    original = ('{\n  "srv01.corp.local" : {"ip":"10.0.0.1", "n": 1.50e3,\n'
                '   "path": "CORP\\\\jdoe", "esc": "a\\"b \\u00e4", "password": "x"},\n'
                '  "list": [ "dc01" , null, true ]\n}\n')
    src = write(tmp_path / "data.json", original)
    project = workspace.create("json")
    project.save_names({"Server": ["dc01"]})
    project.add_sources([src])
    report = run_project(project)
    assert report["status"] == STATUS_READY
    result = output_of(project, report, "data.json").decode()
    assert result == ('{\n  "[Server_2].[Domain_2]" : {"ip":"[IP_1]", "n": 1.50e3,\n'
                      '   "path": "[Domain_1]\\\\[User_1]", "esc": "a\\"b \\u00e4", '
                      '"password": "[Secret_1]"},\n'
                      '  "list": [ "[Server_1]" , null, true ]\n}\n')
    json.loads(result)


@pytest.mark.parametrize("encoding, bom, newline", [
    ("utf-8", b"", "\n"),
    ("utf-8", codecs.BOM_UTF8, "\r\n"),
    ("utf-16-le", codecs.BOM_UTF16_LE, "\r\n"),
    ("utf-16-be", codecs.BOM_UTF16_BE, "\n"),
    ("cp1252", b"", "\r\n"),
])
def test_encodings_and_line_endings_preserved(workspace, tmp_path, encoding, bom, newline):
    text = newline.join(["Größe für 10.0.0.1", "mixed\rcr", "ende"]) + newline
    src = write(tmp_path / "e.log", text, encoding, bom)
    project = workspace.create("enc")
    project.add_sources([src])
    report = run_project(project)
    assert report["status"] == STATUS_READY
    expected = bom + text.replace("10.0.0.1", "[IP_1]").encode(encoding)
    assert output_of(project, report, "e.log") == expected


def test_sources_unchanged_and_folder_import(workspace, tmp_path):
    write(tmp_path / "logs" / "a.log", "10.0.0.1\n")
    write(tmp_path / "logs" / "sub" / "b.log", "10.0.0.2\n")
    before = {p: p.read_bytes() for p in (tmp_path / "logs").rglob("*.log")}
    project = workspace.create("folder")
    project.add_sources([tmp_path / "logs"], recursive=True)
    assert sorted(s.rel for s in project.sources) == ["logs/a.log", "logs/sub/b.log"]
    report = run_project(project)
    assert report["status"] == STATUS_READY
    assert {p: p.read_bytes() for p in before} == before


def test_binary_file_fails_without_output(workspace, tmp_path):
    src = tmp_path / "x.bin"
    src.write_bytes(b"\x00\x01\x02binary\x00" * 100)
    project = workspace.create("bin")
    project.add_sources([src])
    report = run_project(project)
    assert report["status"] == STATUS_FAILED
    run_dir = project.runs_dir / report["run_id"]
    assert not (run_dir / "output").exists() and not (run_dir / "output.partial").exists()


def test_cancelled_run_leaves_no_output(workspace, tmp_path):
    src = write(tmp_path / "x.log", "10.0.0.1\n" * 10)
    project = workspace.create("cancel")
    project.add_sources([src])
    cancel = threading.Event()
    cancel.set()
    report = run_project(project, cancel=cancel)
    assert report["status"] == STATUS_CANCELLED
    assert not any((project.runs_dir / report["run_id"]).glob("output*"))


def test_residual_findings_block_release(workspace, tmp_path):
    src = write(tmp_path / "k.json", '{"srv01.corp.local": 1}\n')
    project = workspace.create("keys")
    rules = project.load_rules()
    rules.sanitize_json_keys = False
    project.save_rules(rules)
    project.add_sources([src])
    report = run_project(project)
    assert report["status"] == STATUS_BLOCKED
    run_dir = project.runs_dir / report["run_id"]
    assert not (run_dir / "output").exists()
    assert (run_dir / "output.blocked" / "NICHT_FREIGEGEBEN.txt").exists()
    assert report["residual_hits"]


def test_invalid_json_fails(workspace, tmp_path):
    src = write(tmp_path / "bad.json", '{"a": "unterminated\n')
    project = workspace.create("badjson")
    project.add_sources([src])
    project.update_source(project.sources[0].id, fmt="json")
    report = run_project(project)
    assert report["status"] == STATUS_FAILED


def test_workspace_cannot_be_source(workspace):
    project = workspace.create("self")
    with pytest.raises(ValueError):
        project.add_sources([workspace.root])


def test_selftest_passes(tmp_path, monkeypatch):
    from logsanitizer.cli import main
    assert main(["--workspace", str(tmp_path), "selftest"]) == 0


def test_format_error_on_wrong_encoding(tmp_path):
    from logsanitizer.formats import FileEncoding, open_text
    path = write(tmp_path / "x.log", "ä", "cp1252")
    with open_text(path, FileEncoding("utf-8")) as stream, pytest.raises(FormatError):
        list(iter_blocks(stream))


def test_worker_processes_give_identical_output(tmp_path, monkeypatch):
    from logsanitizer import samples

    outputs = []
    for workers in ("1", "2"):
        monkeypatch.setenv("LOGSANITIZER_WORKERS", workers)
        root = tmp_path / f"w{workers}"
        samples.generate(root / "in")
        project = Workspace(root / "ws").create("p")
        project.save_names(samples.NAME_LISTS)
        project.add_sources([root / "in" / "logs"], recursive=True)
        report = run_project(project)
        assert report["status"] == STATUS_READY
        assert report["workers"] == int(workers)
        out = project.runs_dir / report["run_id"] / "output"
        outputs.append({p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()})
    assert outputs[0] == outputs[1]


def test_jsonl_with_multiline_string_is_rejected(workspace, tmp_path):
    src = write(tmp_path / "x.jsonl", '{"a": "10.0.0.1"}\n{"b": "line\nbreak"}\n')
    project = workspace.create("jsonl")
    project.add_sources([src])
    report = run_project(project)
    assert report["status"] == STATUS_FAILED
    assert report["errors"][0].startswith("x.jsonl: ")


def test_json_rewriter_handles_any_chunk_boundary():
    import re as _re

    from logsanitizer.formats import JsonStringRewriter

    doc = '{"a\\\\": "x\\"10.0.0.1\\\\", "pw": "geheim", "n": [1, "dc01"]}\n'

    def callback(value, is_key, is_secret):
        return "SECRET" if is_secret else value.replace("10.0.0.1", "[IP_1]")

    whole = JsonStringRewriter(callback, _re.compile("pw")).feed(doc)
    assert whole == '{"a\\\\": "x\\"[IP_1]\\\\", "pw": "SECRET", "n": [1, "dc01"]}\n'
    for size in range(1, 8):
        rewriter = JsonStringRewriter(callback, _re.compile("pw"))
        out = "".join(rewriter.feed(doc[i:i + size]) for i in range(0, len(doc), size))
        rewriter.close()
        assert out == whole, size

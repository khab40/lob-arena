"""Offline reports, optionally following the unchanged approved collector."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from transformer_report_data import load, markdown, sha
from transformer_report_plots import render


def generate(directory, output):
    directory, output = directory.resolve(), output.resolve()
    if output == directory or output.is_relative_to(directory / "artifacts") or directory.is_relative_to(output):
        raise ValueError("report destination overlaps original evidence")
    data = load(directory)
    fingerprint = hashlib.sha256()
    fingerprint.update(data["receipt_sha256"].encode())
    for name in ("transformer_research_report.py", "transformer_report_data.py", "transformer_report_plots.py"):
        fingerprint.update(Path(__file__).with_name(name).read_bytes())
    identity = fingerprint.hexdigest()
    if output.exists():
        manifest = json.loads((output / "report-manifest.json").read_bytes())
        if manifest["report_fingerprint"] != identity:
            raise ValueError("existing report has different inputs or renderer; choose a new output directory")
        for name in ("report.md", "learning-curves.png", "confusion-matrix.png"):
            if sha((output / name).read_bytes()) != manifest["files"][name]:
                raise ValueError("existing report is damaged; choose a new output directory")
        return output / "report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".report-", dir=output.parent) as temporary:
        staging = Path(temporary)
        plots = render(data["result"], data["counts"], staging)
        (staging / "report.md").write_text(markdown(data))
        manifest = {"report_fingerprint": identity, "verification_sha256": data["receipt_sha256"],
                    "summary": {"trial": data["result"]["trial"], "metrics": data["metrics"],
                                "selected_epoch": data["result"]["selected_epoch"]},
                    "files": {name: sha((staging / name).read_bytes()) for name in ["report.md", *plots]}}
        (staging / "report-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(output)
    return output / "report.md"


def write_index(root):
    heading = "# Generated Transformer experiment reports\n"
    target = root / "index.md"
    if target.exists() and not target.read_text().startswith(heading):
        raise ValueError("index destination contains an unrelated document")
    lines = [heading, "Selection metrics are used for tuning; comparison with LightGBM remains separate.", "",
             "| Run | Width | Learning rate | Seed | Selection loss | F1 at 0.5 | Epoch |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for manifest_path in sorted(root.glob("*/report-manifest.json")):
        report = manifest_path.with_name("report.md")
        manifest = json.loads(manifest_path.read_bytes())
        if sha(report.read_bytes()) != manifest["files"]["report.md"]:
            raise ValueError("cannot index an altered report")
        name = manifest_path.parent.name
        summary = manifest["summary"]
        trial, metrics = summary["trial"], summary["metrics"]
        lines.append(f'| [{name}]({quote(name)}/report.md) | {trial["width"]} | {trial["learning_rate"]} | '
                     f'{trial["seed"]} | {metrics["log_loss"]:.8f} | {metrics["f1"]:.6f} | '
                     f'{summary["selected_epoch"]} |')
    target.write_text("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--operator-python", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"(?:search|seed)-[a-zA-Z0-9-]+", args.slot):
        raise ValueError("reports currently support training slots only")
    directory = args.evidence / args.slot
    if args.collect and not (directory / "verification.json").exists():
        if not all((args.operator_python, args.bundle, args.source_receipt)):
            parser.error("--collect requires --operator-python, --bundle and --source-receipt")
        if any((directory / name).exists() for name in
               ("artifacts", "provider-terminal.json", "report-collection-attempt.json")):
            raise ValueError("partial collection exists; reconcile it without automatic recollection")
        with (directory / "report-collection-attempt.json").open("x") as attempt:
            json.dump({"slot": args.slot, "automatic_recollection": False}, attempt)
        subprocess.run([str(args.operator_python), str(Path(__file__).with_name("transformer_research_operator.py")),
                        "collect", "--evidence", str(args.evidence), "--slot", args.slot,
                        "--bundle", str(args.bundle), "--source-receipt", str(args.source_receipt)], check=True)
    output = args.output or args.evidence / "reports" / args.slot
    report = generate(directory, output)
    if args.output is None:
        write_index(output.parent)
    return {"report_status": "ready", "report": str(report)}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"report_status": "failed", "error_type": type(error).__name__,
                          "collection_retry": False}), file=sys.stderr)
        sys.exit(1)

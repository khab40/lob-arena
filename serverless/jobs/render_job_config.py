import argparse
import re
import shlex
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("nebius_job_config.yaml")
DEFAULT_OUTPUT_ROOT = Path("outputs") / "experiments"
DEFAULT_JOB_OUTPUT_PREFIX = "/job/outputs/experiments"
IMAGE_DIGEST_PATTERN = re.compile(r"^(?P<repository>.+)@sha256:(?P<digest>[0-9a-f]{64})$")
WAVE1_INPUT_PATTERN = re.compile(
    r"s3://aimada-wave1-(?:dev|final)-e00g6zvxpr00/"
    r"releases/[a-z0-9][a-z0-9-]{2,62}/staging/?"
)
WAVE1_ENDPOINT_URL = "https://storage.eu-north1.nebius.cloud"


def render_job_config(
    *,
    experiment_id: str,
    runs: int,
    batch_size: int,
    scenarios: list[str],
    random_seed: int,
    image: str,
    output_dir: str,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    rendered_path: Path | None = None,
) -> Path:
    if not experiment_id.strip():
        raise ValueError("experiment_id is required")
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    clean_scenarios = [scenario.strip() for scenario in scenarios if scenario.strip()]
    if not clean_scenarios:
        raise ValueError("at least one scenario is required")
    if not image.strip():
        raise ValueError("image is required")
    if not output_dir.strip():
        raise ValueError("output_dir is required")

    config = _load_template(template_path)
    repository, tag = _split_image(image.strip())
    scenario_arg = ",".join(clean_scenarios)

    config["args"] = (
        f"/job/serverless/jobs/run_batch_experiments.py --runs {runs} "
        f"--batch-size {batch_size} --scenarios {scenario_arg} "
        f"--random-seed {random_seed} --output {output_dir}"
    )
    config["image"] = {"repository": repository, "tag": tag}
    config["scenarios"] = clean_scenarios
    config.setdefault("outputs", {})["directory"] = output_dir

    output_path = (rendered_path or DEFAULT_OUTPUT_ROOT / experiment_id / "nebius_job_config.rendered.yaml").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return output_path


def render_lightgbm_job_config(
    *,
    input_uri: str,
    endpoint_url: str,
    work_root: str,
    image: str,
    rendered_path: Path,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> Path:
    """Render the governed Wave 1 profile while rejecting mutable images."""

    match = IMAGE_DIGEST_PATTERN.fullmatch(image.strip())
    if match is None:
        raise ValueError("LightGBM Wave 1 image must be pinned by sha256 digest")
    if WAVE1_INPUT_PATTERN.fullmatch(input_uri) is None:
        raise ValueError("LightGBM input URI must be an exact approved S3 release prefix")
    if endpoint_url.rstrip("/") != WAVE1_ENDPOINT_URL:
        raise ValueError("LightGBM Object Storage endpoint must be the approved eu-north1 endpoint")
    if not work_root.startswith("/job/") or ".." in Path(work_root).parts:
        raise ValueError("LightGBM work root must be a bounded absolute /job path")
    config = _load_template(template_path)
    config["name"] = "lightgbm-wave1"
    config["kind"] = "governed_lightgbm_wave1"
    config["args"] = " ".join(
        (
            "/job/serverless/jobs/run_lightgbm_wave1.py",
            "run-s3",
            "--input-uri",
            shlex.quote(input_uri),
            "--work-root",
            shlex.quote(work_root),
            "--endpoint-url",
            shlex.quote(endpoint_url),
        )
    )
    config["image"] = {
        "repository": match.group("repository"),
        "digest": f"sha256:{match.group('digest')}",
    }
    config["scenarios"] = []
    config["outputs"] = {
        "directory": "/job/outputs/lightgbm-wave1",
        "artifacts": [
            "request.json",
            "input-inventory.json",
            "environment.json",
            "cloud-run.json",
            "metrics.json",
            "checksums.sha256",
            "SUCCESS",
        ],
    }
    rendered_path = rendered_path.resolve()
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return rendered_path


def _load_template(template_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"job config template is not a YAML object: {template_path}")
    return config


def _split_image(image: str) -> tuple[str, str]:
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    if last_colon > last_slash:
        repository = image[:last_colon]
        tag = image[last_colon + 1 :] or "latest"
        return repository, tag
    return image, "latest"


def _parse_scenarios(value: str) -> list[str]:
    return [scenario.strip() for scenario in value.split(",") if scenario.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Nebius Serverless Job config for one experiment.")
    parser.add_argument("--workload", choices=("synthetic", "lightgbm-wave1"), default="synthetic")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--runs", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--scenarios")
    parser.add_argument("--random-seed", type=int)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory inside the Nebius job container.",
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--rendered-path", type=Path, default=None)
    parser.add_argument("--input-uri")
    parser.add_argument("--work-root", default="/job/wave1")
    parser.add_argument("--endpoint-url", default="https://storage.eu-north1.nebius.cloud")
    args = parser.parse_args()

    if args.workload == "lightgbm-wave1":
        if not args.input_uri or args.rendered_path is None:
            parser.error("LightGBM Wave 1 requires --input-uri and --rendered-path")
        print(
            render_lightgbm_job_config(
                input_uri=args.input_uri,
                endpoint_url=args.endpoint_url,
                work_root=args.work_root,
                image=args.image,
                rendered_path=args.rendered_path,
                template_path=args.template,
            )
        )
        return
    if args.runs is None or args.batch_size is None or args.scenarios is None or args.random_seed is None:
        parser.error("synthetic workload requires --runs, --batch-size, --scenarios and --random-seed")

    job_output_dir = args.output_dir or f"{DEFAULT_JOB_OUTPUT_PREFIX}/{args.experiment_id}/local-batch"
    rendered_path = render_job_config(
        experiment_id=args.experiment_id,
        runs=args.runs,
        batch_size=args.batch_size,
        scenarios=_parse_scenarios(args.scenarios),
        random_seed=args.random_seed,
        image=args.image,
        output_dir=job_output_dir,
        template_path=args.template,
        rendered_path=args.rendered_path,
    )
    print(rendered_path)


if __name__ == "__main__":
    main()

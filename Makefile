.PHONY: help grader-smoke backend-test backend-dev frontend-dev java-control-plane generate-features generate-features-streaming generate-governed-features benchmark-feature-streaming governed-test lightgbm-phase0-test lightgbm-phase1-test build-governed-corpus generate-governed-split evaluate-governed-benchmark verify-governed-release mlflow-bootstrap mlflow-up mlflow-status mlflow-logs mlflow-verify mlflow-down serverless-benchmark serverless-build serverless-push serverless-smoke nebius-partial-plan nebius-partial-deploy nebius-vm-plan nebius-vm-deploy nebius-k8s-plan nebius-k8s-deploy secrets-plan secrets-rotate secrets-check secrets-test docker-up docker-up-serverless docker-up-prometheus docker-up-monitoring docker-up-all docker-down

help:
	@printf "%s\n" "Targets: grader-smoke backend-test backend-dev frontend-dev java-control-plane generate-features generate-features-streaming generate-governed-features benchmark-feature-streaming governed-test lightgbm-phase0-test lightgbm-phase1-test build-governed-corpus generate-governed-split evaluate-governed-benchmark verify-governed-release mlflow-bootstrap mlflow-up mlflow-status mlflow-logs mlflow-verify mlflow-down serverless-benchmark serverless-build serverless-push serverless-smoke nebius-partial-plan nebius-partial-deploy nebius-vm-plan nebius-vm-deploy nebius-k8s-plan nebius-k8s-deploy secrets-plan secrets-rotate secrets-check secrets-test docker-up docker-up-serverless docker-up-prometheus docker-up-monitoring docker-up-all docker-down"

grader-smoke:
	./scripts/grader-smoke.sh

backend-test:
	cd backend && uv run pytest

backend-dev:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && pnpm run dev

java-control-plane:
	./scripts/run-java-control-plane.sh --server.port=8081

generate-features:
	backend/.venv/bin/python scripts/generate_features.py \
		--events "$${FEATURE_EVENTS:-data/features/fixture/events.jsonl}" \
		--metadata "$${FEATURE_METADATA:-data/features/fixture/run-metadata.json}" \
		--labels "$${FEATURE_LABELS:-data/features/fixture/labels.json}" \
		--config "$${FEATURE_CONFIG:-configs/features/lightgbm-v1.json}" \
		--output "$${FEATURE_OUTPUT:-outputs/features/sample}" \
		$${FEATURE_OVERWRITE:+--overwrite}

generate-features-streaming:
	backend/.venv/bin/python scripts/generate_features.py \
		--events "$${FEATURE_EVENTS:-data/features/fixture/events.jsonl}" \
		--metadata "$${FEATURE_METADATA:-data/features/fixture/run-metadata.json}" \
		--labels "$${FEATURE_LABELS:-data/features/fixture/labels.json}" \
		--config "$${FEATURE_CONFIG:-configs/features/lightgbm-v1.json}" \
		--output "$${FEATURE_OUTPUT:-outputs/features/sample-streaming}" \
		--streaming \
		--row-group-size "$${FEATURE_ROW_GROUP_SIZE:-25000}" \
		--quantile-sample-size "$${FEATURE_QUANTILE_SAMPLE_SIZE:-2048}" \
		$${FEATURE_OVERWRITE:+--overwrite}

generate-governed-features:
	backend/.venv/bin/python scripts/generate_features.py \
		--replay-manifest "$${GOVERNED_REPLAY_MANIFEST}" \
		--clean-adjudications "$${GOVERNED_ADJUDICATIONS}" \
		--corpus-manifest "$${GOVERNED_CORPUS_MANIFEST}" \
		--benchmark-protocol "$${GOVERNED_PROTOCOL:-configs/benchmark/governed-benchmark-v1.json}" \
		--artifact-root "$${GOVERNED_ARTIFACT_ROOT}" \
		--config "$${FEATURE_CONFIG:-configs/features/lightgbm-v1.json}" \
		--output "$${FEATURE_OUTPUT:-outputs/features/governed}" \
		$${FEATURE_STREAMING:+--streaming} \
		$${FEATURE_OVERWRITE:+--overwrite}

benchmark-feature-streaming:
	backend/.venv/bin/python scripts/benchmark_feature_streaming.py \
		--events "$${FEATURE_EVENTS:-data/features/fixture/events.jsonl}" \
		--metadata "$${FEATURE_METADATA:-data/features/fixture/run-metadata.json}" \
		--labels "$${FEATURE_LABELS:-data/features/fixture/labels.json}" \
		--config "$${FEATURE_CONFIG:-configs/features/lightgbm-v1.json}" \
		--output "$${FEATURE_OUTPUT:-outputs/features/benchmark}" \
		--report "$${FEATURE_BENCHMARK_REPORT:-outputs/features/benchmark-performance.json}" \
		$${FEATURE_OVERWRITE:+--overwrite}

benchmark-governed-feature-streaming:
	backend/.venv/bin/python scripts/benchmark_feature_streaming.py \
		--replay-manifest "$${GOVERNED_REPLAY_MANIFEST}" \
		--artifact-root "$${GOVERNED_ARTIFACT_ROOT}" \
		--corpus "$${GOVERNED_CORPUS_MANIFEST}" \
		--protocol "$${GOVERNED_PROTOCOL:-configs/benchmark/governed-benchmark-v1.json}" \
		--config "$${FEATURE_CONFIG:-configs/features/lightgbm-v1.json}" \
		--output "$${FEATURE_OUTPUT:-outputs/features/governed-benchmark-primary}" \
		--comparison-output "$${FEATURE_COMPARISON_OUTPUT:-outputs/features/governed-benchmark-comparison}" \
		--report "$${FEATURE_STREAMING_EVIDENCE:-outputs/governed/evidence/feature-streaming.json}" \
		$${FEATURE_OVERWRITE:+--overwrite}

governed-test:
	backend/.venv/bin/python -m pytest \
		backend/tests/test_feature_pipeline.py \
		backend/tests/test_governed_benchmark_protocol.py \
		backend/tests/test_corpus_governance.py \
		backend/tests/test_corpus_splits.py \
		backend/tests/test_canonical_evaluation_bundle.py \
		backend/tests/test_streaming_feature_pipeline.py \
		backend/tests/test_governed_metrics.py \
		backend/tests/test_governed_regimes.py \
		backend/tests/test_governed_release.py \
		backend/tests/test_governed_benchmark_e2e.py \
		backend/tests/test_lightgbm_phase0_contracts.py

lightgbm-phase0-test:
	backend/.venv/bin/python -m pytest \
		backend/tests/test_governed_benchmark_protocol.py \
		backend/tests/test_lightgbm_phase0_contracts.py

lightgbm-phase1-test:
	cd backend && uv run --extra ml pytest \
		tests/test_lightgbm_phase0_contracts.py \
		tests/test_lightgbm_governed_data.py

generate-governed-contracts:
	backend/.venv/bin/python scripts/generate_governed_contracts.py

check-governed-contracts:
	backend/.venv/bin/python scripts/generate_governed_contracts.py --check

build-governed-corpus:
	backend/.venv/bin/python scripts/build_governed_corpus.py \
		--sessions "$${GOVERNED_SESSIONS}" \
		--adjudications "$${GOVERNED_ADJUDICATIONS}" \
		--protocol "$${GOVERNED_PROTOCOL:-configs/benchmark/governed-benchmark-v1.json}" \
		--corpus-id "$${GOVERNED_CORPUS_ID}" \
		--artifact-root "$${GOVERNED_ARTIFACT_ROOT}" \
		--output "$${GOVERNED_CORPUS_OUTPUT}" \
		$${GOVERNED_OVERWRITE:+--overwrite}

generate-governed-split:
	backend/.venv/bin/python scripts/generate_split_manifest.py \
		--corpus "$${GOVERNED_CORPUS_MANIFEST}" \
		--protocol "$${GOVERNED_PROTOCOL:-configs/benchmark/governed-benchmark-v1.json}" \
		--split-id "$${GOVERNED_SPLIT_ID}" \
		--output "$${GOVERNED_SPLIT_OUTPUT}" \
		$${GOVERNED_OVERWRITE:+--overwrite}

evaluate-governed-benchmark:
	backend/.venv/bin/python scripts/evaluate_governed_benchmark.py \
		--plan "$${GOVERNED_EVALUATION_PLAN}" \
		--corpus "$${GOVERNED_CORPUS_MANIFEST}" \
		--corpus-validation "$${GOVERNED_CORPUS_VALIDATION}" \
		--split "$${GOVERNED_SPLIT_MANIFEST}" \
		--protocol "$${GOVERNED_PROTOCOL:-configs/benchmark/governed-benchmark-v1.json}" \
		--output "$${GOVERNED_BENCHMARK_OUTPUT}" \
		--signing-key "$${GOVERNED_SIGNING_KEY}" \
		--signer "$${GOVERNED_SIGNER:-Market Surveillance QA}" \
		$${GOVERNED_OVERWRITE:+--overwrite}

verify-governed-release:
	backend/.venv/bin/python scripts/verify_governed_release.py "$${GOVERNED_BENCHMARK_OUTPUT}"

mlflow-bootstrap:
	./scripts/bootstrap-mlflow-env.sh

mlflow-up:
	@test -f deployments/mlflow/.env || { printf "%s\n" "Run 'make mlflow-bootstrap' first."; exit 1; }
	docker compose --env-file deployments/mlflow/.env --profile mlflow up -d --build --wait mlflow

mlflow-status:
	@test -f deployments/mlflow/.env || { printf "%s\n" "Run 'make mlflow-bootstrap' first."; exit 1; }
	docker compose --env-file deployments/mlflow/.env --profile mlflow ps -a mlflow mlflow-postgres mlflow-minio mlflow-minio-init

mlflow-logs:
	@test -f deployments/mlflow/.env || { printf "%s\n" "Run 'make mlflow-bootstrap' first."; exit 1; }
	docker compose --env-file deployments/mlflow/.env --profile mlflow logs --tail=200 mlflow mlflow-postgres mlflow-minio mlflow-minio-init

mlflow-verify:
	@test -f deployments/mlflow/.env || { printf "%s\n" "Run 'make mlflow-bootstrap' first."; exit 1; }
	docker compose --env-file deployments/mlflow/.env --profile mlflow exec -T mlflow \
		python /opt/lob-arena/mlflow/smoke_test.py

mlflow-down:
	@test -f deployments/mlflow/.env || { printf "%s\n" "Run 'make mlflow-bootstrap' first."; exit 1; }
	docker compose --env-file deployments/mlflow/.env --profile mlflow stop mlflow mlflow-minio mlflow-postgres
	docker compose --env-file deployments/mlflow/.env --profile mlflow rm -f mlflow mlflow-minio-init mlflow-minio mlflow-postgres

serverless-benchmark:
	cd serverless/jobs && uv run python run_batch_benchmark.py --config job_config.example.yaml

serverless-build:
	./scripts/build-serverless-images.sh

serverless-push:
	PUSH=true ./scripts/build-serverless-images.sh

serverless-smoke:
	SMOKE=true ./scripts/build-serverless-images.sh

nebius-partial-plan:
	./scripts/deploy-nebius-partial.sh --dry-run

nebius-partial-deploy:
	./scripts/deploy-nebius-partial.sh

nebius-vm-plan:
	./scripts/deploy-nebius-vm.sh --dry-run

nebius-vm-deploy:
	./scripts/deploy-nebius-vm.sh

nebius-k8s-plan:
	./scripts/deploy-nebius-k8s.sh --dry-run

nebius-k8s-deploy:
	./scripts/deploy-nebius-k8s.sh

secrets-plan:
	./scripts/rotate-secrets.sh

secrets-rotate:
	./scripts/rotate-secrets.sh --apply

secrets-check:
	./scripts/check-secrets.sh

secrets-test:
	cd backend && UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/lob-arena-uv-cache} uv run pytest tests/test_secret_scripts.py -q

docker-up:
	docker compose up --build

docker-up-serverless:
	NEBIUS_SERVERLESS_ENABLED=true NEBIUS_CLI_CONFIG_DIR="$${NEBIUS_CLI_CONFIG_DIR:-$${HOME}/.nebius}" docker compose up --build

docker-up-prometheus:
	docker compose --profile prometheus up --build

docker-up-monitoring:
	docker compose --profile grafana up --build

docker-up-all:
	NEBIUS_SERVERLESS_ENABLED=true NEBIUS_CLI_CONFIG_DIR="$${NEBIUS_CLI_CONFIG_DIR:-$${HOME}/.nebius}" docker compose --profile grafana up --build

docker-down:
	docker compose --profile "*" down

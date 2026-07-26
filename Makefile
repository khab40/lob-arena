.PHONY: help grader-smoke backend-test backend-dev frontend-dev java-control-plane generate-features serverless-benchmark serverless-build serverless-push serverless-smoke nebius-partial-plan nebius-partial-deploy nebius-vm-plan nebius-vm-deploy nebius-k8s-plan nebius-k8s-deploy secrets-plan secrets-rotate secrets-check secrets-test docker-up docker-up-serverless docker-up-prometheus docker-up-monitoring docker-up-all docker-down

help:
	@printf "%s\n" "Targets: grader-smoke backend-test backend-dev frontend-dev java-control-plane generate-features serverless-benchmark serverless-build serverless-push serverless-smoke nebius-partial-plan nebius-partial-deploy nebius-vm-plan nebius-vm-deploy nebius-k8s-plan nebius-k8s-deploy secrets-plan secrets-rotate secrets-check secrets-test docker-up docker-up-serverless docker-up-prometheus docker-up-monitoring docker-up-all docker-down"

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

.PHONY: install lint typecheck test migrate api bot worker docker-up docker-down estimate-index sync-sample sync-full

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .

typecheck:
	mypy app

test:
	pytest -m "not external" --cov-fail-under=80

migrate:
	alembic upgrade head

api:
	uvicorn app.main:app --reload

bot:
	python -m app.bot.app

worker:
	celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO

docker-up:
	docker compose up --build

docker-down:
	docker compose down

estimate-index:
	python -m app.cli estimate-index

sync-sample:
	python -m app.cli sync --limit 20

sync-full:
	python -m app.cli sync --full --commit --confirm

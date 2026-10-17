.PHONY: install lint test sync ask docker

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

lint:
	.venv/bin/ruff check .

test:
	.venv/bin/pytest

sync:
	PYTHONPATH=src .venv/bin/python main.py

ask:
	PYTHONPATH=src .venv/bin/python -m optibot.assistant "$(Q)"

docker:
	docker build -t optibot-sync .

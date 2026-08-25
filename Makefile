.PHONY: install migrations migrate seed test lint run
install:      ; uv sync
migrations:   ; uv run python manage.py makemigrations core projetos chamados documentacao apontamentos almoxarifado integracoes almoxarifado
migrate:      ; uv run python manage.py migrate
seed:         ; uv run python manage.py seed_demo
test:         ; uv run pytest --cov --cov-fail-under=80
lint:         ; uv run ruff check . && uv run mypy .
format:       ; uv run ruff format .
run:          ; uv run python manage.py runserver

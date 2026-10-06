PYTHON ?= python3

.PHONY: test lint format check install uninstall
test:
	$(PYTHON) -B -m unittest discover -s tests -v

lint:
	ruff check .
	ruff format --check .
	bash -n install.sh

format:
	ruff check --fix .
	ruff format .

check:
	./install.sh --check

install:
	sudo ./install.sh

uninstall:
	sudo ./install.sh --remove

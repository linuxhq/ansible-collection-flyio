.PHONY: all clean pre-commit python

all: pre-commit

clean:
	$(RM) -r venv

pre-commit: python
	venv/bin/pre-commit install

python: venv
	venv/bin/python3 -m pip install --upgrade pip
	PYTHONWARNINGS='ignore:DEPRECATION' venv/bin/pip install -r requirements.txt

venv:
	test -d venv || python3 -m venv venv

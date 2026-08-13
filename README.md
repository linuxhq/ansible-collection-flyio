# linuxhq.flyio

[![License](https://img.shields.io/badge/license-GPLv3-lightgreen)](https://www.gnu.org/licenses/gpl-3.0.en.html#license-text)
[![Ansible Galaxy](https://img.shields.io/badge/collection-linuxhq.flyio-blue)](https://galaxy.ansible.com/linuxhq/flyio)
[![Lint](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml)
[![Release](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml)

An Ansible collection of Fly.io modules and roles.

## Requirements

- Python `>= 3.13`
- `ansible-core >= 2.18.0`

## Installation

    ansible-galaxy collection install linuxhq.flyio

## Development

With Tox installed, install the pre-commit hook:

```sh
tox run -e pre-commit
```

Tox manages isolated environments under `.tox/`; no environment activation is required.

### Checks

Run the default checks:

```sh
tox
```

Run grouped checks:

```sh
tox run -m format
tox run -m lint
tox run -m unit
```

Run Ansible sanity tests for a module:

```sh
tox run -e ansible-test -- sanity --python "$(cat .python-version)" plugins/modules/apps.py
```

### Molecule

Each role has a Molecule scenario that also serves as an example playbook. Set `MOLECULE_ROLE`
to select a role:

```sh
MOLECULE_ROLE=apps_info tox run -e molecule -- test -s default
```

Molecule scenarios may create real Fly.io resources.

### Changelog and build

```sh
tox run -e changelog -- generate
tox run -e build
```

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

    make
    source venv/bin/activate

### Build

    ansible-galaxy collection build

### Changelog

    antsibull-changelog generate

### Lint

    ansible-lint
    yamllint -s .

### Test

Every role includes a Molecule scenario with an example playbook.

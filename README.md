# linuxhq.flyio

[![License](https://img.shields.io/badge/license-GPLv3-lightgreen)](https://www.gnu.org/licenses/gpl-3.0.en.html#license-text)
[![Ansible Galaxy](https://img.shields.io/badge/collection-linuxhq.flyio-blue)](https://galaxy.ansible.com/linuxhq/flyio)
[![Lint](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml)
[![Release](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml)

A collection of fly.io roles

# Collection

## Environment

    make
    source venv/bin/activate

## Build

    ansible-galaxy collection build

## Install

    ansible-galaxy collection install linuxhq.flyio

## Changelog

    antsibull-changelog generate

## Linting

    ansible-lint
    yamllint -s .

## Testing

All roles have molecule tests which provide example playbooks

# linuxhq.flyio

![License](https://img.shields.io/badge/license-GPLv3-lightgreen)
[![Ansible Galaxy](https://img.shields.io/badge/collection-linuxhq.flyio-blue)](https://galaxy.ansible.com/linuxhq/flyio)
[![Lint](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/pre-commit.yml)
[![Release](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml/badge.svg)](https://github.com/linuxhq/ansible-collection-flyio/actions/workflows/release.yml)

A collection of [Fly.io](https://fly.io) modules and roles for deploying
containers on virtual private networks across multiple datacenters.

# Collection

## Build

    ansible-galaxy collection build

## Install

    ansible-galaxy collection install linuxhq.flyio

## Requirements

| Name | Version |
| ---- | ------- |
| ansible | >= 14.2.0, < 15 |
| python | >= 3.9 |

## Modules

| Module | Description |
| ------ | ----------- |
| [linuxhq.flyio.apps](plugins/modules/apps.py) | Manage Fly.io apps |
| [linuxhq.flyio.apps_info](plugins/modules/apps_info.py) | Gather information about Fly.io apps |
| [linuxhq.flyio.ip_addresses](plugins/modules/ip_addresses.py) | Manage Fly.io IP addresses |
| [linuxhq.flyio.ip_addresses_info](plugins/modules/ip_addresses_info.py) | Gather information about Fly.io IP addresses |
| [linuxhq.flyio.machines](plugins/modules/machines.py) | Manage Fly.io machines |
| [linuxhq.flyio.machines_info](plugins/modules/machines_info.py) | Gather information about Fly.io machines |
| [linuxhq.flyio.volumes](plugins/modules/volumes.py) | Manage Fly.io volumes |
| [linuxhq.flyio.volumes_info](plugins/modules/volumes_info.py) | Gather information about Fly.io volumes |

## Roles

| Role | Description |
| ---- | ----------- |
| [apps](roles/apps) | Manage Fly.io apps |
| [apps_info](roles/apps_info) | Gather information about Fly.io apps |
| [ip_addresses](roles/ip_addresses) | Manage Fly.io IP addresses |
| [ip_addresses_info](roles/ip_addresses_info) | Gather information about Fly.io IP addresses |
| [machines](roles/machines) | Manage Fly.io machines |
| [machines_info](roles/machines_info) | Gather information about Fly.io machines |
| [volumes](roles/volumes) | Manage Fly.io volumes |
| [volumes_info](roles/volumes_info) | Gather information about Fly.io volumes |

## License

GPL-3.0-or-later

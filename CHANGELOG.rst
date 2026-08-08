===========================
linuxhq.flyio Release Notes
===========================

.. contents:: Topics

v1.0.7
======

Minor Changes
-------------

- info roles - remove the community.general json_query runtime dependency.
- machines role - pass static file configuration to the machines module.
- secrets - add modules and roles to manage and inspect fly.io app secrets.

Breaking Changes / Porting Guide
--------------------------------

- ip_addresses, machines, and volumes roles - group resources by app in nested inventory lists.

Bugfixes
--------

- apps - force app deletion by default and make the deletion request timeout configurable.
- apps_info, machines_info, and volumes_info - handle missing singular resources as documented.
- flyio_utils - use the FlyV1 authorization scheme when any credential in a compound token uses the fm1r or fm2 format.
- machines - preserve unspecified configuration during updates, purge removed dictionary values, reject region changes, and compare image references exactly.
- volumes - require a region for unambiguous name-based operations.

v1.0.6
======

Minor Changes
-------------

- machines_exec - add a module to execute commands on fly.io machines.

v1.0.5
======

Bugfixes
--------

- machines - avoid unnecessary updates when fly.io returns normalized configuration metadata.

v1.0.4
======

Bugfixes
--------

- volumes - ignore volumes pending destruction when resolving resources by name or ID.

v1.0.3
======

Minor Changes
-------------

- machines - add checks field for health check configuration.
- machines - add metadata field for machine metadata.
- machines - add restart field for restart policy configuration.

Bugfixes
--------

- flyio_utils - fix graphql_request silently discarding HTTP error details.
- flyio_utils - fix socket timeout on wait_for_machine long-poll requests.
- flyio_utils - fix values_differ not detecting key removals.
- flyio_utils - remove dead token field from client dict.
- flyio_utils - remove unused patch_result function.
- machines - mark env parameter as no_log to prevent credential exposure.

v1.0.2
======

Minor Changes
-------------

- machines - add init field to configure container entrypoint, cmd, exec, and tty.
- machines - add volumes_info role dependency for volume id lookups.

v1.0.1
======

Minor Changes
-------------

- machines - add files field to inject files into the rootfs overlay at launch.

v1.0.0
======

Release Summary
---------------

Initial release of the linuxhq.flyio collection.

Major Changes
-------------

- apps - new module to manage fly.io apps.
- apps - new role to manage fly.io apps.
- apps_info - new module to gather information about fly.io apps.
- apps_info - new role to gather information about fly.io apps.
- ip_addresses - new module to manage fly.io IP addresses.
- ip_addresses - new role to manage fly.io IP addresses.
- ip_addresses_info - new module to gather information about fly.io IP addresses.
- ip_addresses_info - new role to gather information about fly.io IP addresses.
- machines - new module to manage fly.io machines.
- machines - new role to manage fly.io machines.
- machines_info - new module to gather information about fly.io machines.
- machines_info - new role to gather information about fly.io machines.
- volumes - new module to manage fly.io volumes.
- volumes - new role to manage fly.io volumes.
- volumes_info - new module to gather information about fly.io volumes.
- volumes_info - new role to gather information about fly.io volumes.

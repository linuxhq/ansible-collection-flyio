#!/usr/bin/python
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


DOCUMENTATION = r"""
---
module: machines
short_description: Manage Fly.io Machines
description:
  - Create, update, start, stop, and destroy Fly.io Machines.
  - Machines are the compute units that run container images on Fly.io.
  - Use O(id) or O(name) to identify an existing Machine.
  - If multiple live Machines have the same name, use O(id) to select one.
  - Machine configuration options are used only when O(state=present).
version_added: '1.0.0'
author:
  - Taylor Kimball (@tkimball83)
options:
  api_token:
    required: true
    type: str
    description:
      - Fly.io API token.
  app_name:
    required: true
    type: str
    description:
      - App name.
  id:
    type: str
    description:
      - Machine identifier.
      - Either O(id) or O(name) is required.
      - Mutually exclusive with O(name).
  name:
    type: str
    description:
      - Machine name.
      - Either O(id) or O(name) is required.
      - Destroyed Machines are ignored, and so are Machines being destroyed,
        except that O(state=absent) considers those when no live Machine has
        this name.
      - The task fails when more than one of the considered Machines has this
        name.
      - Mutually exclusive with O(id).
  region:
    type: str
    description:
      - Region code, such as C(ord).
      - Must be a single region code. Region lists and region groups such as
        C(us) are not supported.
      - Surrounding whitespace is removed and the code is lowercased.
      - Cannot be changed on an existing Machine.
  image:
    type: str
    description:
      - Container image reference.
      - Required when O(state=present).
  init:
    type: dict
    description:
      - Container init configuration passed to the Fly.io API.
      - Merged with the current configuration; unspecified fields keep their
        current values.
    suboptions:
      cmd:
        type: list
        elements: str
        description:
          - Command to run.
      entrypoint:
        type: list
        elements: str
        description:
          - Entrypoint for the container.
      exec:
        type: list
        elements: str
        description:
          - Exec command.
      tty:
        type: bool
        description:
          - Allocate a pseudo-TTY.
          - Fly.io currently ignores this setting.
  guest:
    type: dict
    description:
      - Guest VM configuration passed to the Fly.io API.
      - Merged with the current configuration; unspecified fields keep their
        current values.
    suboptions:
      cpu_kind:
        type: str
        description:
          - CPU reservation type.
          - Must not be empty when specified.
      host_dedication_id:
        type: str
        description:
          - Host dedication identifier.
          - Must not be empty when specified.
      cpus:
        type: int
        description:
          - Number of CPU cores.
          - Must be greater than zero.
      memory_mb:
        type: int
        description:
          - Memory allocation in megabytes.
          - Must be a positive multiple of C(256).
      kernel_args:
        type: list
        elements: str
        description:
          - Kernel arguments.
      persist_rootfs:
        type: str
        choices:
          - never
          - restart
          - always
        description:
          - Root filesystem persistence policy.
  services:
    type: list
    elements: dict
    description:
      - Service port mappings passed to the Fly.io API.
      - Replaces the Machine's current services; services not listed are removed.
      - Fields omitted from a listed service or port keep their current values.
      - Listed services or ports that share identity keys, such as the same
        O(services[].internal_port) and O(services[].protocol), are paired with
        current entries in order.
      - Each service requires O(services[].internal_port).
      - O(services[].protocol) is required for new services.
    suboptions:
      protocol:
        type: str
        choices:
          - tcp
          - udp
        description:
          - Network protocol.
          - Required for a new service.
          - May be omitted when updating an existing service. It then pairs, in
            order, with current services on the same
            O(services[].internal_port), whatever their protocol.
      internal_port:
        type: int
        required: true
        description:
          - Port on which the Machine listens.
          - Must be between C(1) and C(65535).
      autostart:
        type: bool
        description:
          - Whether Fly Proxy starts the Machine for incoming requests.
      autostop:
        type: raw
        description:
          - Idle Machine behavior.
          - Accepts C(off), C(stop), C(suspend), C(true), or C(false).
      min_machines_running:
        type: int
        description:
          - Minimum Machines to keep running in the primary region.
          - Must not be negative.
      concurrency:
        type: dict
        description:
          - Fly Proxy concurrency limits.
        suboptions:
          type:
            type: str
            choices:
              - connections
              - requests
            description:
              - Unit counted for load balancing.
          soft_limit:
            type: int
            description:
              - Preferred concurrency limit.
              - Must be greater than zero. Fly.io uses C(20) when it is not set.
              - Must not exceed the hard limit that applies, whether requested or
                already set on the Machine.
          hard_limit:
            type: int
            description:
              - Maximum concurrency limit.
              - Must not be negative.
              - Set to C(0) to remove the hard limit.
              - When positive, must be greater than or equal to a requested
                O(services[].concurrency.soft_limit). Fly.io lowers an existing soft
                limit to the new hard limit.
      ports:
        type: list
        elements: dict
        description:
          - Public ports and handlers.
        suboptions:
          port:
            type: int
            description:
              - Public port.
              - Either O(services[].ports[].port) or a complete port range is
                required.
              - Must be between C(1) and C(65535).
              - Mutually exclusive with O(services[].ports[].start_port) and
                O(services[].ports[].end_port).
          start_port:
            type: int
            description:
              - First public port in a range.
              - Required with O(services[].ports[].end_port).
              - Either O(services[].ports[].port) or a complete port range is
                required.
              - Must be between C(1) and C(65535).
              - Mutually exclusive with O(services[].ports[].port).
          end_port:
            type: int
            description:
              - Last public port in a range.
              - Required with O(services[].ports[].start_port).
              - Must be between C(1) and C(65535).
              - Must be greater than or equal to O(services[].ports[].start_port).
              - Mutually exclusive with O(services[].ports[].port).
          handlers:
            type: list
            elements: str
            description:
              - Fly Proxy protocol handlers.
          force_https:
            type: bool
            description:
              - Whether HTTP requests redirect to HTTPS.
          http_options:
            type: dict
            description:
              - HTTP handler options.
            suboptions:
              compress:
                type: bool
                description:
                  - Whether Fly Proxy compresses HTTP responses.
              h2_backend:
                type: bool
                description:
                  - Whether the backend supports HTTP/2 with prior knowledge.
              response:
                type: dict
                description:
                  - HTTP response options.
                suboptions:
                  headers:
                    type: dict
                    description:
                      - Response headers added by Fly Proxy.
                      - Header names not listed keep their current values. Set a
                        header to C(false) to remove it.
                      - Header names must not be empty.
                      - Values may be strings, lists of strings, or C(false) to
                        remove a header.
                      - Values are not treated as sensitive.
                  pristine:
                    type: bool
                    description:
                      - Whether Fly Proxy preserves response headers unchanged.
          tls_options:
            type: dict
            description:
              - TLS handler options.
            suboptions:
              alpn:
                type: list
                elements: str
                description:
                  - ALPN protocols presented to TLS clients.
              default_self_signed:
                type: bool
                description:
                  - Whether to use a self-signed certificate as a fallback.
              versions:
                type: list
                elements: str
                description:
                  - Permitted TLS protocol versions.
          proxy_proto_options:
            type: dict
            description:
              - PROXY protocol options.
            suboptions:
              version:
                type: str
                description:
                  - PROXY protocol version accepted by the Machine.
                  - Must not be empty when specified.
  checks:
    type: dict
    description:
      - Health checks passed to the Fly.io API.
      - Each key is a check name and its value is a dictionary.
      - Check names must not be empty.
      - Replaces the Machine's current checks; checks not listed are removed.
      - Fields omitted from a listed check keep their current values unless the
        check's C(type) changes.
      - C(type) and C(port) are required for a new check and when changing a
        check's C(type).
      - C(type) accepts C(http) or C(tcp).
      - Changing a check's C(type) replaces the check instead of merging it.
      - Optional fields are C(interval), C(timeout), C(grace_period), C(method),
        C(path), C(protocol), C(kind), C(tls_server_name), C(tls_skip_verify),
        and C(headers).
      - C(kind) accepts C(informational) or C(readiness).
      - C(headers) is a list of dictionaries containing C(name) and C(values).
      - C(interval), C(timeout), and C(grace_period) accept integer nanoseconds
        or duration strings such as C(15s).
      - C(port) must be between C(1) and C(65535).
      - Integer durations must be greater than zero.
      - Values are not treated as sensitive. Do not put credentials in check
        headers.
  env:
    type: dict
    description:
      - Environment variables.
      - Replaces the Machine's current environment; variables not listed are
        removed.
      - Keys must not be empty.
      - Values must be strings. Quote numbers and booleans, for example C("8080").
      - Values are not treated as sensitive. Use M(linuxhq.flyio.secrets) for
        credentials.
  files:
    type: list
    elements: dict
    description:
      - Files injected into the rootfs overlay at launch.
      - Replaces the Machine's current files; files not listed are removed.
      - Each entry requires O(files[].guest_path) and one of O(files[].raw_value)
        or O(files[].secret_name).
    suboptions:
      guest_path:
        type: str
        required: true
        description:
          - Absolute path inside the Machine where the file is placed.
      raw_value:
        type: str
        description:
          - Base64-encoded file content.
          - Either O(files[].raw_value) or O(files[].secret_name) is required.
          - Mutually exclusive with O(files[].secret_name).
      secret_name:
        type: str
        description:
          - Name of a Fly.io secret whose value populates the file.
          - Must not be empty.
          - Either O(files[].raw_value) or O(files[].secret_name) is required.
          - Mutually exclusive with O(files[].raw_value).
  mounts:
    type: list
    elements: dict
    description:
      - Volume mount passed to the Fly.io API.
      - Fly.io supports one mounted volume per Machine.
      - Fields omitted from the mount keep their current values. Setting
        O(mounts[].add_size_gb) replaces a percentage-based extension set
        outside this module.
    suboptions:
      volume:
        type: str
        required: true
        description:
          - Volume identifier or name.
          - Must not be empty.
      path:
        type: str
        required: true
        description:
          - Absolute mount path inside the Machine.
      name:
        type: str
        description:
          - Ignored. Fly.io sets the volume name and ignores it in requests.
          - This option will be removed in version 2.0.0 of linuxhq.flyio.
      extend_threshold_percent:
        type: int
        description:
          - Usage percentage that triggers automatic extension.
          - Required with O(mounts[].add_size_gb).
          - Must be C(0), or between C(50) and C(99).
          - Set this and O(mounts[].add_size_gb) to C(0) to disable extension.
      add_size_gb:
        type: int
        description:
          - Gigabytes added by automatic extension.
          - Required with O(mounts[].extend_threshold_percent).
          - Must be C(0), or between C(1) and C(100).
          - Set this and O(mounts[].extend_threshold_percent) to C(0) to disable
            extension.
      size_gb_limit:
        type: int
        description:
          - Maximum size after automatic extension.
          - Must not be negative.
          - Set to C(0) to remove the limit.
      encrypted:
        type: bool
        description:
          - Ignored. Fly.io sets volume encryption and ignores it in requests.
          - This option will be removed in version 2.0.0 of linuxhq.flyio.
  auto_destroy:
    type: bool
    description:
      - Automatically destroy the Machine when it exits.
      - With O(wait=true), a Machine that exits and destroys itself before the
        wait completes is reported as changed without verifying its configuration.
      - Defaults to C(false) on the Fly.io API when not specified.
  restart:
    type: dict
    description:
      - Restart policy for the Machine passed to the Fly.io API.
      - Merged with the current configuration; unspecified fields keep their
        current values.
    suboptions:
      policy:
        type: str
        choices:
          - "no"
          - always
          - on-failure
        description:
          - Restart policy name.
          - Required when configuring a new restart policy.
      max_retries:
        type: int
        description:
          - Maximum restart attempts (only for C(on-failure) policy).
          - Must not be negative.
  metadata:
    type: dict
    description:
      - Metadata key-value pairs attached to the Machine.
      - Replaces the Machine's current metadata; keys not listed are removed.
      - Values must be strings. Quote numbers and booleans, for example C("8080").
      - Fly.io uses C(fly_*) keys, such as C(fly_process_group), for routing and
        process groups. Include them to keep them on Machines created by other
        tools.
      - Keys must not be empty.
  statics:
    type: list
    elements: dict
    description:
      - Static files served by Fly Proxy and passed to the Fly.io API.
      - Replaces the Machine's current statics; entries not listed are removed.
      - Fields omitted from a listed entry keep their current values.
    suboptions:
      guest_path:
        type: str
        required: true
        description:
          - Path containing the static files.
          - Must not be empty.
      url_prefix:
        type: str
        required: true
        description:
          - URL prefix from which files are served.
          - Must not be empty.
      tigris_bucket:
        type: str
        description:
          - Tigris bucket containing the static files.
          - Must not be empty when specified.
      index_document:
        type: str
        description:
          - Index document served for directory requests.
          - Must not be empty when specified.
  wait:
    type: bool
    default: true
    description:
      - Wait for the Machine to reach the target state.
      - For O(state=present), wait until the Machine reaches a stable state.
  wait_timeout:
    type: int
    default: 60
    description:
      - Timeout in seconds when waiting for Machine state.
      - Must be greater than zero when O(wait=true).
  state:
    type: str
    choices:
      - present
      - absent
      - started
      - stopped
    default: present
    description:
      - Desired state of the resource.
      - C(present) creates or updates the Machine.
      - C(started) ensures the Machine is running.
      - C(stopped) ensures the Machine is stopped.
      - C(absent) destroys the Machine. A running Machine is stopped forcibly
        before it is destroyed.
requirements:
  - python >= 3.9
attributes:
  check_mode:
    description: Supports predicting changes without applying them.
    support: full
  diff_mode:
    description: Determines whether the module returns change details in diff format.
    support: none

"""

EXAMPLES = r"""
- name: Deploy a container
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    guest:
      cpu_kind: shared
      cpus: 1
      memory_mb: 256
    services:
      - internal_port: 8080
        protocol: tcp
        ports:
          - port: 443
            handlers:
              - tls
              - http
    state: present

- name: Deploy with health checks
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    checks:
      httpcheck:
        type: http
        port: 8080
        path: /healthz
        interval: 15s
        timeout: 2s
    state: present

- name: Deploy with a volume mount
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: worker
    region: ord
    image: registry.fly.io/my-app:latest
    mounts:
      - volume: vol_abc123
        path: /data
    state: present

- name: Deploy with a custom entrypoint
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: worker
    region: ord
    image: registry.fly.io/my-app:latest
    init:
      entrypoint:
        - /bin/sh
      cmd:
        - -c
        - "exec my-worker"
    state: present

- name: Deploy with injected files
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    name: web
    region: ord
    image: registry.fly.io/my-app:latest
    files:
      - guest_path: /etc/myapp/config.conf
        raw_value: "{{ lookup('file', 'config.conf') | b64encode }}"
    state: present

- name: Stop a Machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: stopped

- name: Destroy a Machine
  linuxhq.flyio.machines:
    api_token: "{{ flyio_api_token }}"
    app_name: my-app
    id: d5683606c77187
    state: absent
"""

RETURN = r"""
---
machine:
  description:
    - Fly.io Machine.
    - C(env), C(headers), and C(raw_value) fields are removed from the returned
      data because they can contain secrets.
  returned: when available
  type: dict
  contains:
    id:
      description: Machine identifier.
      returned: always
      type: str
    name:
      description: Machine name.
      returned: when available
      type: str
    region:
      description: Region code.
      returned: when available
      type: str
    state:
      description: Current Machine state.
      returned: when available
      type: str
message:
  returned: always
  type: str
  description:
    - Operation summary.

"""

import base64
import binascii
import copy
import re
from decimal import Decimal

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
    delete_result,
    flyio_client,
    flyio_path,
    get_resource,
    list_all,
    nonempty_string,
    post_result,
    require_positive,
    require_region_code,
    sanitize_machine,
    seconds_left,
    valid_machine,
    wait_deadline,
    wait_for_machine,
)

CONFIG_FIELDS = (
    "auto_destroy",
    "checks",
    "env",
    "files",
    "guest",
    "image",
    "init",
    "metadata",
    "mounts",
    "restart",
    "services",
    "statics",
)
PURGE_CONFIG_FIELDS = ("checks", "env", "metadata")
CHECK_STRING_FIELDS = (
    "kind",
    "method",
    "path",
    "protocol",
    "tls_server_name",
    "type",
)
CHECK_INTEGER_FIELDS = ("port",)
CHECK_DURATION_FIELDS = ("grace_period", "interval", "timeout")
CHECK_BOOLEAN_FIELDS = ("tls_skip_verify",)
CHECK_FIELDS = set(
    CHECK_STRING_FIELDS + CHECK_INTEGER_FIELDS + CHECK_DURATION_FIELDS + CHECK_BOOLEAN_FIELDS + ("headers",)
)
# Fly.io sets these mount fields and ignores them in requests.
IGNORED_MOUNT_FIELDS = ("encrypted", "name")
LIST_ITEM_KEYS = (
    "guest_path",
    "url_prefix",
    "internal_port",
    "port",
    "start_port",
    "end_port",
    "name",
    "protocol",
)
# The union of the Machine states in the Fly.io Machines API specification and in the
# Machine states documentation (https://docs.fly.io/machines/machine-states); neither
# list is complete on its own.
TRANSITION_TARGETS = {
    "starting": "started",
    "restarting": "started",
    "stopping": "stopped",
    "suspending": "suspended",
    "destroying": "destroyed",
    "launch_failed": "destroyed",
}
AMBIGUOUS_TRANSITIONS = {"creating", "migrating", "pending", "replacing", "updating"}
# Fly.io documents no behaviour for archived Machines beyond allowing deletion.
UNMANAGED_STATES = {"archived"}
TRANSITIONAL_STATES = set(TRANSITION_TARGETS) | AMBIGUOUS_TRANSITIONS
# Transitions a healthy Machine may already be in right after a successful wait; excludes destruction.
MOVED_ON_STATES = TRANSITIONAL_STATES - {"destroying", "launch_failed"}
SELF_DESTROYED_STATES = {"destroying", "destroyed"}
TERMINAL_STATES = {"destroyed", "replaced", "migrated"}
PRESENT_STATES = {"created", "started", "stopped", "suspended"}


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if item is not None}

    if isinstance(value, list):
        return [clean(item) for item in value]

    return value


def find_machine(client, app_name, name=None, machine_id=None, missing_ok=False, include_destroying=False):
    """Find a live Machine; with include_destroying, fall back to one that is being destroyed."""
    if machine_id is not None:
        machine = get_machine(client, app_name, machine_id, missing_ok=True)
        if machine is not None and machine["state"] == "destroying" and not include_destroying:
            return None

        return machine

    machines = list_all(
        client,
        flyio_path("apps", app_name, "machines"),
        ok_statuses=[404] if missing_ok else None,
        required_fields=("id", "name", "state"),
    )

    named = [machine for machine in machines if machine.get("name") == name and machine["state"] not in TERMINAL_STATES]
    live = [machine for machine in named if machine["state"] != "destroying"]
    matches = live or (named if include_destroying else [])
    if len(matches) > 1:
        raise FlyioApiError(f"Multiple Machines named '{name}' match in app '{app_name}'; specify id")

    return matches[0] if matches else None


def build_config(params):
    config = clean({field: params.get(field) for field in CONFIG_FIELDS})
    for mount in config.get("mounts", []):
        for field in IGNORED_MOUNT_FIELDS:
            mount.pop(field, None)

    for service in config.get("services", []):
        if service.get("autostop") == "off":
            service["autostop"] = False
        elif service.get("autostop") == "stop":
            service["autostop"] = True

    return config


def validate_integer_range(module, value, name, minimum, maximum=None):
    if value is None:
        return

    if not isinstance(value, int) or isinstance(value, bool):
        module.fail_json(msg=f"{name} must be an integer")

    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            module.fail_json(msg=f"{name} must be at least {minimum}")
        else:
            module.fail_json(msg=f"{name} must be between {minimum} and {maximum}")


def validate_dictionary(module, value, name):
    if value is not None and not isinstance(value, dict):
        module.fail_json(msg=f"{name} must be a dictionary")

    return value or {}


def validate_string_mappings(module, config):
    for field in ("env", "metadata"):
        value = config.get(field)
        if value is not None and not all(nonempty_string(key) and isinstance(item, str) for key, item in value.items()):
            module.fail_json(msg=f"{field} must use non-empty string keys and string values")


def validate_check_strings(module, name, check):
    for field in CHECK_STRING_FIELDS:
        if field not in check:
            continue

        if not isinstance(check[field], str):
            module.fail_json(msg=f"checks.{name}.{field} must be a string")

        if not nonempty_string(check[field]):
            module.fail_json(msg=f"checks.{name}.{field} must not be empty")


def validate_check_fields(module, name, check):
    if not all(isinstance(field, str) for field in check):
        module.fail_json(msg=f"checks.{name} field names must be strings")

    unsupported = check.keys() - CHECK_FIELDS
    if unsupported:
        module.fail_json(msg=f"check '{name}' contains unsupported fields: {', '.join(sorted(unsupported))}")

    validate_check_strings(module, name, check)
    for field in CHECK_INTEGER_FIELDS:
        if field in check:
            validate_integer_range(
                module,
                check[field],
                f"checks.{name}.{field}",
                1,
                65535,
            )

    for field in CHECK_BOOLEAN_FIELDS:
        if field in check and not isinstance(check[field], bool):
            module.fail_json(msg=f"checks.{name}.{field} must be a boolean")


def validate_check_protocols(module, name, check):
    if check.get("kind") not in (None, "informational", "readiness"):
        module.fail_json(msg=f"checks.{name}.kind must be informational or readiness")

    if check.get("type") not in (None, "http", "tcp"):
        module.fail_json(msg=f"checks.{name}.type must be http or tcp")

    if check.get("protocol") not in (None, "http", "https"):
        module.fail_json(msg=f"checks.{name}.protocol must be http or https")


def validate_check_durations(module, name, check):
    for field in CHECK_DURATION_FIELDS:
        if field not in check:
            continue

        value = check[field]
        if not ((isinstance(value, int) and not isinstance(value, bool)) or nonempty_string(value)):
            module.fail_json(msg=f"checks.{name}.{field} must be an integer or duration string")

        if isinstance(value, int) and not isinstance(value, bool):
            validate_integer_range(module, value, f"checks.{name}.{field}", 1)


def validate_check_headers(module, name, headers):
    if headers is not None and (
        not isinstance(headers, list)
        or not all(
            isinstance(header, dict)
            and set(header) == {"name", "values"}
            and isinstance(header.get("name"), str)
            and header["name"].strip()
            and isinstance(header.get("values"), list)
            and all(isinstance(value, str) for value in header["values"])
            for header in headers
        )
    ):
        module.fail_json(msg=f"checks.{name}.headers must contain name and string values")


def validate_checks(module, checks):
    if checks is None:
        return

    if not isinstance(checks, dict) or not all(
        nonempty_string(name) and isinstance(check, dict) for name, check in checks.items()
    ):
        module.fail_json(msg="checks must map names to configuration dictionaries")

    for name, check in checks.items():
        validate_check_fields(module, name, check)
        validate_check_protocols(module, name, check)
        validate_check_durations(module, name, check)
        validate_check_headers(module, name, check.get("headers"))


def validate_paths(module, config):
    for option, field in (("files", "guest_path"), ("mounts", "path")):
        if any(
            not isinstance(item.get(field), str) or not item[field].startswith("/") for item in config.get(option) or []
        ):
            module.fail_json(msg=f"{option}[].{field} must be an absolute path")

    for field in ("guest_path", "url_prefix"):
        if any(not nonempty_string(item.get(field)) for item in config.get("statics") or []):
            module.fail_json(msg=f"statics[].{field} must not be empty")


def validate_files(module, files):
    for file in files:
        secret_name = file.get("secret_name")
        if secret_name is not None and not secret_name.strip():
            module.fail_json(msg="files[].secret_name must not be empty")

        raw_value = file.get("raw_value")
        if raw_value is None:
            continue

        try:
            base64.b64decode(raw_value, validate=True)
        except (binascii.Error, TypeError, ValueError):
            module.fail_json(msg="files[].raw_value must be valid Base64")


def validate_services(module, services):
    for service in services:
        validate_integer_range(
            module,
            service.get("internal_port"),
            "services[].internal_port",
            1,
            65535,
        )
        validate_integer_range(
            module,
            service.get("min_machines_running"),
            "services[].min_machines_running",
            0,
        )
        concurrency = validate_dictionary(
            module,
            service.get("concurrency"),
            "services[].concurrency",
        )
        for field in ("soft_limit", "hard_limit"):
            validate_integer_range(
                module,
                concurrency.get(field),
                f"services[].concurrency.{field}",
                0,
            )

        autostop = service.get("autostop")
        if autostop is not None and not (isinstance(autostop, bool) or autostop in ("off", "stop", "suspend")):
            module.fail_json(msg="service autostop must be off, stop, suspend, true, or false")

        ports = service.get("ports")
        if ports is not None and (not isinstance(ports, list) or not all(isinstance(port, dict) for port in ports)):
            module.fail_json(msg="services[].ports must be a list of dictionaries")

        for port in ports or []:
            for field in ("port", "start_port", "end_port"):
                validate_integer_range(
                    module,
                    port.get(field),
                    f"services[].ports[].{field}",
                    1,
                    65535,
                )

            if (
                port.get("start_port") is not None
                and port.get("end_port") is not None
                and port["start_port"] > port["end_port"]
            ):
                module.fail_json(msg="services[].ports[].start_port must not exceed end_port")

            http_options = validate_dictionary(
                module,
                port.get("http_options"),
                "services[].ports[].http_options",
            )
            response = validate_dictionary(
                module,
                http_options.get("response"),
                "services[].ports[].http_options.response",
            )
            headers = response.get("headers")
            if headers is not None and (
                not isinstance(headers, dict)
                or not all(
                    isinstance(header, str)
                    and header.strip()
                    and (
                        value is False
                        or isinstance(value, str)
                        or (isinstance(value, list) and all(isinstance(item, str) for item in value))
                    )
                    for header, value in headers.items()
                )
            ):
                module.fail_json(
                    msg=("service HTTP response headers must map non-empty strings to strings, string lists, or false")
                )


def validate_requested_strings(module, params):
    """Reject empty optional strings; Fly.io omits them from returned config, so they could never match."""
    guest = params.get("guest") or {}
    values = [(f"guest.{field}", guest.get(field)) for field in ("cpu_kind", "host_dedication_id")]
    values += [
        (f"statics[].{field}", static.get(field))
        for static in params.get("statics") or []
        for field in ("tigris_bucket", "index_document")
    ]
    values += [
        ("services[].ports[].proxy_proto_options.version", (port.get("proxy_proto_options") or {}).get("version"))
        for service in params.get("services") or []
        for port in service.get("ports") or []
    ]
    for name, value in values:
        if value is not None and not nonempty_string(value):
            module.fail_json(msg=f"{name} must not be empty")


def validate_concurrency_limits(module, requested_services, effective_services=None):
    """Check each requested soft_limit against the hard_limit that will apply.

    Fly.io lowers a soft_limit above the hard_limit, so a requested soft_limit can never be applied above
    the effective hard_limit; a requested hard_limit alone may go below the current soft_limit.
    """
    effective_services = requested_services if effective_services is None else effective_services
    for requested, effective in zip(requested_services, effective_services):
        soft_limit = (requested.get("concurrency") or {}).get("soft_limit")
        # Fly.io replaces a requested soft_limit of 0 with its default, so 0 could never be applied.
        if soft_limit is not None and soft_limit < 1:
            module.fail_json(msg="services[].concurrency.soft_limit must be at least 1")

        hard_limit = (effective.get("concurrency") or {}).get("hard_limit")
        if soft_limit is not None and hard_limit is not None and 0 < hard_limit < soft_limit:
            module.fail_json(msg="services[].concurrency.soft_limit must not exceed hard_limit")


def validate_guest(module, guest):
    if guest is None:
        return

    for field in ("cpus", "memory_mb"):
        validate_integer_range(module, guest.get(field), f"guest.{field}", 1)

    memory_mb = guest.get("memory_mb")
    if memory_mb is not None and memory_mb % 256:
        module.fail_json(msg="guest.memory_mb must be a multiple of 256")


def validate_mounts(module, mounts):
    for mount in mounts:
        if not nonempty_string(mount.get("volume")):
            module.fail_json(msg="mounts[].volume must not be empty")

        threshold = mount.get("extend_threshold_percent")
        if threshold:
            validate_integer_range(module, threshold, "mounts[].extend_threshold_percent", 50, 99)
        else:
            validate_integer_range(module, threshold, "mounts[].extend_threshold_percent", 0)

        validate_integer_range(module, mount.get("add_size_gb"), "mounts[].add_size_gb", 0, 100)
        validate_integer_range(module, mount.get("size_gb_limit"), "mounts[].size_gb_limit", 0)

        if (mount.get("extend_threshold_percent") == 0) != (mount.get("add_size_gb") == 0):
            module.fail_json(
                msg="mounts[].extend_threshold_percent and add_size_gb must both be zero to disable extension"
            )


def validate_restart(module, restart):
    if restart is None:
        return

    validate_integer_range(
        module,
        restart.get("max_retries"),
        "restart.max_retries",
        0,
    )


def validate_config(module, config):
    validate_string_mappings(module, config)
    validate_checks(module, config.get("checks"))
    validate_files(module, config.get("files") or [])
    validate_guest(module, config.get("guest"))
    validate_mounts(module, config.get("mounts") or [])
    validate_paths(module, config)
    validate_restart(module, config.get("restart"))
    validate_services(module, config.get("services") or [])


def validate_complete_config(
    module,
    config,
    existing_checks=(),
    requested_restart=None,
):
    for name, check in config.get("checks", {}).items():
        if name in existing_checks:
            continue

        missing = {"port", "type"} - check.keys()
        if missing:
            module.fail_json(msg=f"check '{name}' requires {' and '.join(sorted(missing))}")

    if any("protocol" not in service for service in config.get("services", [])):
        module.fail_json(msg="each service requires protocol")

    restart = config.get("restart")
    if restart is not None:
        if requested_restart is None:
            requested_restart = restart

        if "policy" not in restart:
            module.fail_json(msg="restart.policy is required")

        if "max_retries" in requested_restart and restart["policy"] != "on-failure":
            module.fail_json(msg="restart.max_retries is valid only with policy=on-failure")


def list_candidates(values, value):
    """Current list entries that share the requested entry's identity keys."""
    if not isinstance(value, dict):
        return []

    keys = [key for key in LIST_ITEM_KEYS if key in value]
    return [
        item for item in values if isinstance(item, dict) and keys and all(item.get(key) == value[key] for key in keys)
    ]


def find_list_item(values, value):
    # Entries sharing identity keys pair in order; match_list_items removes each match as it is used.
    matches = list_candidates(values, value)
    return matches[0] if matches else None


def has_list_identity(value):
    return isinstance(value, dict) and any(key in value for key in LIST_ITEM_KEYS)


def match_list_items(current, desired):
    remaining = list(current)
    for value in desired:
        match = find_list_item(remaining, value)
        if match is not None:
            remaining.remove(match)

        yield match, value


def config_values_differ(current, desired, purge=False):
    if isinstance(current, list) and isinstance(desired, list) and all(has_list_identity(value) for value in desired):
        return len(current) != len(desired) or any(
            match is None or config_values_differ(match, value) for match, value in match_list_items(current, desired)
        )

    if isinstance(current, list) and isinstance(desired, list):
        return len(current) != len(desired) or any(
            config_values_differ(cur, want) for cur, want in zip(current, desired)
        )

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return type(current) is not type(desired) or current != desired

    return (purge and current.keys() != desired.keys()) or any(
        key not in current or config_values_differ(current[key], value) for key, value in desired.items()
    )


def merge_values(current, desired):
    if isinstance(current, list) and isinstance(desired, list):
        if len(current) == len(desired) and not all(has_list_identity(value) for value in desired):
            return [merge_values(cur, value) for cur, value in zip(current, desired)]

        return [
            merge_values(match, value) if match is not None else value
            for match, value in match_list_items(current, desired)
        ]

    if not isinstance(current, dict) or not isinstance(desired, dict):
        return desired

    result = {**current, **desired}
    for key, value in desired.items():
        if key in current:
            result[key] = merge_values(current[key], value)

    return result


def merge_config(current, desired):
    # Copy so later adjustments to the merged config never alter the caller's request.
    desired = copy.deepcopy(desired)
    config = merge_values(current, desired)

    mount = matching_mount(current, desired)
    if mount is not None:
        # Keep the attached volume ID; sending a name could select a different volume.
        config["mounts"] = [{**merge_values(mount, desired["mounts"][0]), "volume": mount["volume"]}]
        if "add_size_gb" in desired["mounts"][0]:
            # Fly.io treats add_size_gb and add_size_percent as mutually exclusive.
            for field in ("add_size_percent", "min_add_size_gb"):
                config["mounts"][0].pop(field, None)

    for merged, requested in zip(config.get("files") or [], desired.get("files") or []):
        for field in ("image_config", "raw_value", "secret_name"):
            if field not in requested:
                merged.pop(field, None)

    requested_restart = desired.get("restart") or {}
    if requested_restart.get("policy") not in (None, "on-failure"):
        config["restart"].pop("max_retries", None)

    for field in PURGE_CONFIG_FIELDS:
        if field not in desired:
            continue

        if field == "checks":
            checks = current.get("checks")
            if not isinstance(checks, dict):
                checks = {}

            checks = copy.deepcopy(checks)
            for check in checks.values():
                headers = check.get("headers") if isinstance(check, dict) else None
                if isinstance(headers, list):
                    for header in headers:
                        if isinstance(header, dict) and header.get("values") is None:
                            # Fly omits empty values in existing headers. Caller
                            # headers are validated before merging provider data.
                            header["values"] = []

            config[field] = {
                name: merge_values(existing_check(checks, name, value), value) for name, value in desired[field].items()
            }
        else:
            config[field] = desired[field]

    return config


def existing_check(checks, name, desired):
    """Merge into the current check only when its type is unchanged; a new type replaces it."""
    check = checks.get(name)
    if not isinstance(check, dict) or ("type" in desired and check.get("type") != desired["type"]):
        return {}

    return check


def matching_mount(current, desired):
    current_mounts = current.get("mounts", [])
    desired_mounts = desired.get("mounts", [])
    if not current_mounts or not desired_mounts:
        return None

    # Requests identify the mount by volume ID or name; Fly.io reports both on the current mount.
    volume = desired_mounts[0].get("volume")
    identifiers = {volume} if isinstance(volume, str) and volume else set()
    current_identifiers = {
        current_mounts[0][key]
        for key in ("volume", "name")
        if isinstance(current_mounts[0].get(key), str) and current_mounts[0][key]
    }
    return current_mounts[0] if identifiers and identifiers <= current_identifiers else None


def mounts_differ(current, desired):
    current_mounts = current.get("mounts", [])
    if current_mounts is None:
        current_mounts = []

    if not isinstance(current_mounts, list) or not all(isinstance(mount, dict) for mount in current_mounts):
        return True

    if len(current_mounts) != len(desired.get("mounts", [])):
        return True

    return bool(current_mounts) and matching_mount(current, desired) is None


def mount_values_differ(current, desired):
    desired_mounts = desired.get("mounts", [])
    if not desired_mounts:
        return False

    values = {key: value for key, value in desired_mounts[0].items() if key not in ("volume", "name")}
    match = matching_mount(current, desired)
    return match is None or config_values_differ(match, values)


def validate_machine_data(module, machine):
    if machine is not None and not valid_machine(machine):
        module.fail_json(
            msg=f"Fly.io API returned malformed Machine data for app '{module.params['app_name']}'",
            machine=sanitize_machine(machine),
        )

    return machine


def validate_waited_machine(module, machine_id, current, expected_state):
    validate_machine_data(module, current)
    state = current.get("state") if current is not None else None
    if expected_state == "destroyed":
        reached = current is None or state == "destroyed"
    elif expected_state == "settled":
        reached = state in PRESENT_STATES
    else:
        reached = state == expected_state

    if not reached:
        module.fail_json(
            msg=(
                f"Machine '{machine_id}' in app '{module.params['app_name']}' "
                f"did not reach state '{expected_state}' (current state: {state or 'missing'})"
            ),
            machine=sanitize_machine(current),
        )


def machine_version(module, machine):
    version = machine.get("version")
    if not nonempty_string(version):
        module.fail_json(
            msg=(
                f"Fly.io API returned malformed data for Machine '{machine['id']}' "
                f"in app '{module.params['app_name']}': expected a version"
            ),
            machine=sanitize_machine(machine),
        )

    return version


def get_machine(client, app_name, machine_id, missing_ok=False):
    return get_resource(
        client,
        flyio_path("apps", app_name, "machines", machine_id),
        ok_statuses=[404] if missing_ok else None,
        required_fields=("id", "state"),
        expected={"id": machine_id},
    )


def wait_until_settled(module, client, machine, deadline):
    """Wait server-side until the Machine version just written leaves its transitional states."""
    app_name = module.params["app_name"]
    settled = wait_tolerating_self_destroy(
        module,
        client,
        machine,
        "settled",
        deadline,
        version=machine_version(module, machine) if "version" in machine else None,
    )
    current = get_machine(client, app_name, machine["id"], missing_ok=True)
    if auto_destroys(module, machine) and (current is None or current.get("state") in SELF_DESTROYED_STATES):
        # The Machine ran to completion and destroyed itself; there is nothing left to verify.
        return None

    # After a successful settled wait, a Machine that has already moved on (for example a job exiting) is fine.
    if settled and current is not None and current.get("state") in MOVED_ON_STATES:
        return validate_machine_data(module, current)

    validate_waited_machine(module, machine["id"], current, "settled")
    return current


def wait_tolerating_self_destroy(module, client, machine, state, deadline, version=None):
    """Wait for a Machine state; a self-destroying Machine may vanish or never reach it, so defer to a re-read.

    Returns True when the wait succeeded and False when a tolerated error ended it.
    """
    try:
        wait_for_machine(
            client,
            module.params["app_name"],
            machine["id"],
            state,
            seconds_left(deadline),
            version=version,
        )
    except FlyioApiError as exc:
        if exc.status_code not in (404, 408) or not auto_destroys(module, machine):
            raise

        return False

    return True


def auto_destroys(module, machine):
    """Whether the Machine destroys itself on exit, from the request or its existing configuration."""
    # The option configures the Machine only for state=present; other states use the Machine's own config.
    requested = module.params["state"] == "present" and module.params.get("auto_destroy")
    config = machine.get("config")
    return bool(requested or (isinstance(config, dict) and config.get("auto_destroy")))


def exit_self_destroyed(module, machine, action):
    module.exit_json(
        changed=True,
        message=f"Machine {action}; it completed and destroyed itself",
        machine=sanitize_machine(machine),
    )


def reject_unmanaged(module, machine):
    module.fail_json(
        msg=(
            f"Machine '{machine['id']}' in app '{module.params['app_name']}' is {machine['state']}; "
            "only state=absent is supported"
        ),
        machine=sanitize_machine(machine),
    )


def settle_machine(module, client, current, desired_state, deadline):
    app_name = module.params["app_name"]
    machine_id = current["id"]
    state = current.get("state")
    if state in TERMINAL_STATES:
        module.fail_json(
            msg=f"Machine '{machine_id}' in app '{app_name}' is in terminal state '{state}'",
            machine=sanitize_machine(current),
        )

    if state in UNMANAGED_STATES:
        reject_unmanaged(module, current)

    if state not in TRANSITIONAL_STATES:
        return current

    target = TRANSITION_TARGETS.get(state)
    if target == desired_state and (module.check_mode or not module.params["wait"]):
        module.exit_json(
            changed=False,
            message=f"Machine already transitioning to {desired_state}",
            machine=sanitize_machine(current),
        )

    if not module.params["wait"]:
        module.fail_json(
            msg=f"Machine '{machine_id}' in app '{app_name}' is currently {state}; enable wait or retry",
            machine=sanitize_machine(current),
        )

    wait_state = "settled" if target is None or desired_state == "present" else target
    wait_for_machine(
        client,
        app_name,
        machine_id,
        wait_state,
        seconds_left(deadline),
        version=machine_version(module, current) if wait_state == "stopped" else None,
    )
    # The wait succeeded; the checks below reject only Machines that are gone, unmanaged, or still moving.
    current = validate_machine_data(module, get_machine(client, app_name, machine_id, missing_ok=True))

    # The settled wait also matches archived Machines.
    if current is not None and current.get("state") in UNMANAGED_STATES:
        reject_unmanaged(module, current)

    if current is None or current.get("state") in TERMINAL_STATES:
        module.fail_json(
            msg=f"Machine '{machine_id}' in app '{app_name}' is no longer available",
            machine=sanitize_machine(current),
        )

    if current.get("state") in TRANSITIONAL_STATES:
        module.fail_json(
            msg=f"Transition of Machine '{machine_id}' in app '{app_name}' timed out",
            machine=sanitize_machine(current),
        )

    return current


def reject_unreachable_host(module, machine):
    """Fly.io returns no config while it cannot reach the Machine's host; report that, not bad data."""
    host_status = machine.get("host_status") if isinstance(machine, dict) else None
    if host_status not in (None, "ok"):
        module.fail_json(
            msg=(
                f"Host for Machine '{machine.get('id')}' in app '{module.params['app_name']}' "
                f"is not reachable (host_status={host_status}); retry later"
            ),
            machine=sanitize_machine(machine),
        )


def validate_machine_update(module, current, desired_config):
    app_name = module.params["app_name"]
    reject_unreachable_host(module, current)
    current_config = current.get("config")
    if not isinstance(current_config, dict):
        module.fail_json(
            msg=f"Fly.io API returned malformed configuration for Machine '{current['id']}' in app '{app_name}'",
            machine=sanitize_machine(current),
        )

    current_region = current.get("region")
    if module.params.get("region") is not None:
        if not isinstance(current_region, str) or not current_region:
            module.fail_json(
                msg=(f"Fly.io API returned malformed region data for Machine '{current['id']}' in app '{app_name}'"),
                machine=sanitize_machine(current),
            )

        if module.params["region"] != current_region:
            module.fail_json(msg=f"Region cannot be changed for Machine '{current['id']}' in app '{app_name}'")

    if "mounts" in desired_config and mounts_differ(current_config, desired_config):
        module.fail_json(msg=f"Attached volume cannot be changed for Machine '{current['id']}' in app '{app_name}'")

    return current_config


def duration_nanoseconds(value):
    if not isinstance(value, str):
        return value

    units = {
        "ns": 1,
        "us": 1000,
        "µs": 1000,
        "μs": 1000,
        "ms": 1000000,
        "s": 1000000000,
        "m": 60000000000,
        "h": 3600000000000,
    }
    pattern = r"(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)"
    unsigned = value.lstrip("+-")
    if value in ("0", "+0", "-0"):
        return 0

    if not re.fullmatch(r"[+-]?(?:" + pattern + r")+", value):
        return value

    total = sum(int(Decimal(number) * units[unit]) for number, unit in re.findall(pattern, unsigned))
    return -total if value.startswith("-") else total


def normalize_requested_defaults(config, requested, defaults):
    if not isinstance(config, dict) or not isinstance(requested, dict):
        return

    for field, default in defaults.items():
        if field in requested and config.get(field) is None:
            config[field] = copy.deepcopy(default)


def normalize_service_defaults(current, desired):
    """Supply the zero values Fly.io omits for the service fields the caller manages."""
    normalize_requested_defaults(current, desired, {"ports": [], "concurrency": {}})
    normalize_requested_defaults(
        current.get("concurrency"),
        desired.get("concurrency"),
        {"hard_limit": 0},
    )
    for port, desired_port in match_list_items(current.get("ports") or [], desired.get("ports") or []):
        if port is None:
            continue

        normalize_requested_defaults(
            port,
            desired_port,
            {
                "handlers": [],
                "force_https": False,
                "tls_options": {},
                "http_options": {},
                "proxy_proto_options": {},
            },
        )
        normalize_requested_defaults(
            port.get("tls_options"),
            desired_port.get("tls_options"),
            {"alpn": [], "versions": []},
        )
        http_options = port.get("http_options")
        desired_http_options = desired_port.get("http_options")
        if isinstance(http_options, dict) and isinstance(desired_http_options, dict):
            normalize_requested_defaults(http_options, desired_http_options, {"response": {}})
            normalize_requested_defaults(
                http_options.get("response"), desired_http_options.get("response"), {"headers": {}}
            )


def normalize_config_comparison(config, requested):
    # Fly omits zero-value fields in responses. Only supply defaults for fields
    # the caller manages, so omitted options remain unmanaged.
    config = copy.deepcopy(config)
    defaults = {
        "env": {},
        "metadata": {},
        "checks": {},
        "services": [],
        "files": [],
        "statics": [],
        "mounts": [],
        "init": {},
        "auto_destroy": False,
    }
    normalize_requested_defaults(config, requested, defaults)
    normalize_requested_defaults(
        config.get("init"),
        requested.get("init"),
        {"cmd": [], "entrypoint": [], "exec": [], "tty": False},
    )
    normalize_requested_defaults(
        config.get("guest"),
        requested.get("guest"),
        {"kernel_args": []},
    )
    normalize_requested_defaults(
        config.get("restart"),
        requested.get("restart"),
        {"max_retries": 0},
    )
    if requested.get("mounts"):
        normalize_requested_defaults(
            matching_mount(config, requested),
            requested["mounts"][0],
            {"extend_threshold_percent": 0, "add_size_gb": 0, "size_gb_limit": 0},
        )

    for current, desired in match_list_items(config.get("services") or [], requested.get("services") or []):
        if current is not None:
            normalize_service_defaults(current, desired)

    checks = config.get("checks")
    if isinstance(checks, dict):
        for name, check in checks.items():
            if isinstance(check, dict):
                desired_check = (requested.get("checks") or {}).get(name) or {}
                normalize_requested_defaults(check, desired_check, {"headers": []})
                for header, desired_header in match_list_items(
                    check.get("headers") or [], desired_check.get("headers") or []
                ):
                    normalize_requested_defaults(header, desired_header, {"values": []})

                for field in CHECK_DURATION_FIELDS:
                    if field in check:
                        check[field] = duration_nanoseconds(check[field])

    return config


def machine_config_changed(current_config, desired_config):
    current_config = normalize_config_comparison(current_config, desired_config)
    desired_config = normalize_config_comparison(desired_config, desired_config)
    if current_config.get("image") != desired_config["image"]:
        return True

    for field, value in desired_config.items():
        if field == "image":
            continue

        if field == "mounts":
            if mount_values_differ(current_config, desired_config):
                return True
        elif config_values_differ(
            current_config.get(field),
            value,
            purge=field in PURGE_CONFIG_FIELDS,
        ):
            return True

    return False


def validate_machine_postcondition(
    module,
    machine,
    desired_config,
    expected_name=None,
    expected_region=None,
):
    validate_machine_data(module, machine)
    reject_unreachable_host(module, machine)
    config = machine.get("config") if machine is not None else None
    machine_id = (
        machine.get("id") if isinstance(machine, dict) else module.params.get("id") or module.params.get("name")
    )
    if (
        not isinstance(config, dict)
        or machine_config_changed(config, desired_config)
        or (expected_name is not None and machine.get("name") != expected_name)
        or (expected_region is not None and machine.get("region") != expected_region)
    ):
        module.fail_json(
            msg=(
                f"Fly.io API did not apply the requested configuration to Machine "
                f"'{machine_id}' in app '{module.params['app_name']}'"
            ),
            machine=sanitize_machine(machine),
        )

    return machine


def update_machine(module, client, current, desired_config, deadline):
    params = module.params
    app_name = params["app_name"]
    if not params["wait"] and current.get("state") in TRANSITIONAL_STATES:
        # Without wait, a Machine that needs no change is reported unchanged instead of failing.
        current_config = validate_machine_update(module, current, desired_config)
        if not machine_config_changed(current_config, desired_config):
            module.exit_json(changed=False, message="Machine already present", machine=sanitize_machine(current))

    current = settle_machine(module, client, current, "present", deadline)
    current_config = validate_machine_update(module, current, desired_config)

    config = merge_config(current_config, desired_config)
    current_checks = current_config.get("checks")
    current_checks = current_checks if isinstance(current_checks, dict) else {}
    # A check whose type changes is replaced, so it must be complete like a new check.
    existing_checks = {
        name
        for name, check in (desired_config.get("checks") or {}).items()
        if existing_check(current_checks, name, check)
    }

    requested_config = {field: config[field] for field in desired_config}
    validate_config(module, requested_config)
    # Merged services follow the requested order, so each requested service pairs with its merged result.
    validate_concurrency_limits(module, desired_config.get("services") or [], config.get("services") or [])
    validate_complete_config(
        module,
        {field: requested_config[field] for field in ("checks", "services", "restart") if field in desired_config},
        existing_checks,
        requested_restart=desired_config.get("restart"),
    )

    if not machine_config_changed(current_config, desired_config):
        module.exit_json(
            changed=False,
            message="Machine already present",
            machine=sanitize_machine(current),
        )

    skip_launch = current.get("state") in ("created", "failed", "stopped", "suspended")
    if skip_launch and config.get("spot") is not None:
        # Fly.io does not allow skip_launch for spot Machines, and updating without it would start the Machine.
        module.fail_json(
            msg=(f"Spot Machine '{current['id']}' in app '{app_name}' must be running to be updated; start it first"),
            machine=sanitize_machine(current),
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be updated",
            machine=sanitize_machine(current),
        )

    body = {"config": config}
    if current.get("version") is not None:
        body["current_version"] = machine_version(module, current)

    if skip_launch:
        body["skip_launch"] = True

    result = post_result(
        client,
        flyio_path("apps", app_name, "machines", current["id"]),
        body,
    )
    if not valid_machine(result) or result["id"] != current["id"]:
        module.fail_json(
            msg=(f"Fly.io API returned malformed data while updating Machine '{current['id']}' in app '{app_name}'"),
            machine=sanitize_machine(result),
        )

    if params["wait"]:
        result = wait_until_settled(module, client, result, deadline) or exit_self_destroyed(module, result, "updated")

    validate_machine_postcondition(module, result, desired_config)

    module.exit_json(
        changed=True,
        message="Machine updated",
        machine=sanitize_machine(result),
    )


def create_machine(module, client, desired_config, deadline):
    params = module.params
    app_name = params["app_name"]
    if params.get("id") is not None:
        module.fail_json(msg=f"Machine '{params['id']}' not found in app '{app_name}'")

    validate_complete_config(module, desired_config)
    if module.check_mode:
        module.exit_json(changed=True, message="Machine would be created")

    body = {"config": desired_config}
    if params.get("name") is not None:
        body["name"] = params["name"]

    if params.get("region") is not None:
        body["region"] = params["region"]

    result = post_result(client, flyio_path("apps", app_name, "machines"), body)
    if not valid_machine(result):
        module.fail_json(
            msg=(f"Fly.io API returned malformed data while creating Machine '{params['name']}' in app '{app_name}'"),
            machine=sanitize_machine(result),
        )

    if params["wait"]:
        result = wait_until_settled(module, client, result, deadline) or exit_self_destroyed(module, result, "created")

    validate_machine_postcondition(
        module,
        result,
        desired_config,
        expected_name=params["name"],
        expected_region=params.get("region"),
    )

    module.exit_json(
        changed=True,
        message="Machine created",
        machine=sanitize_machine(result),
    )


def ensure_present(module, client):
    params = module.params
    if not params["image"].strip():
        module.fail_json(msg="image must not be empty")

    require_region_code(module)

    if params["wait"]:
        require_positive(module, "wait_timeout")

    if len(params.get("mounts") or []) > 1:
        module.fail_json(msg="only one volume can be mounted to a Machine")

    validate_config(module, params)
    validate_requested_strings(module, params)
    validate_concurrency_limits(module, params.get("services") or [])
    desired_config = build_config(params)
    deadline = wait_deadline(params["wait_timeout"])
    current = validate_machine_data(
        module,
        find_machine(
            client,
            params["app_name"],
            name=params.get("name"),
            machine_id=params.get("id"),
        ),
    )
    if current is not None:
        return update_machine(module, client, current, desired_config, deadline)

    return create_machine(module, client, desired_config, deadline)


def wait_until_machine_destroyed(module, client, machine, deadline):
    app_name = module.params["app_name"]
    machine_id = machine["id"]
    wait_for_machine(
        client,
        app_name,
        machine_id,
        "destroyed",
        seconds_left(deadline),
    )
    current = get_machine(client, app_name, machine_id, missing_ok=True)
    validate_waited_machine(module, machine_id, current, "destroyed")
    return current


def ensure_absent(module, client):
    params = module.params
    app_name = params["app_name"]
    if params["wait"]:
        require_positive(module, "wait_timeout")

    deadline = wait_deadline(params["wait_timeout"])
    current = validate_machine_data(
        module,
        find_machine(
            client,
            app_name,
            name=params.get("name"),
            machine_id=params.get("id"),
            missing_ok=True,
            include_destroying=True,
        ),
    )

    if current is None or current.get("state") == "destroyed":
        module.exit_json(changed=False, message="Machine already absent")

    if current.get("state") == "destroying":
        if params["wait"] and not module.check_mode:
            current = wait_until_machine_destroyed(module, client, current, deadline)

        values = {"changed": False, "message": "Machine already being destroyed"}
        if current is not None:
            values["machine"] = sanitize_machine(current)

        module.exit_json(**values)

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Machine would be destroyed",
            machine=sanitize_machine(current),
        )

    delete_result(
        client,
        f"{flyio_path('apps', app_name, 'machines', current['id'])}?force=true",
        ok_statuses=[404],
    )

    requested = current
    if params["wait"]:
        current = wait_until_machine_destroyed(module, client, current, deadline)

    module.exit_json(
        changed=True,
        message="Machine destroyed" if params["wait"] else "Machine destruction requested",
        machine=sanitize_machine(current if params["wait"] and current is not None else requested),
    )


def ensure_power_state(module, client, desired_state):
    params = module.params
    app_name = params["app_name"]
    action = "start" if desired_state == "started" else "stop"
    if params["wait"]:
        require_positive(module, "wait_timeout")

    deadline = wait_deadline(params["wait_timeout"])
    current = validate_machine_data(
        module,
        find_machine(
            client,
            app_name,
            name=params.get("name"),
            machine_id=params.get("id"),
        ),
    )

    if current is None:
        identifier = params.get("id") or params.get("name")
        module.fail_json(msg=f"Machine '{identifier}' not found in app '{app_name}'")

    current = settle_machine(module, client, current, desired_state, deadline)

    if desired_state == "stopped" and current.get("state") == "created":
        module.exit_json(
            changed=False,
            message="Machine has not been started",
            machine=sanitize_machine(current),
        )

    if current.get("state") == desired_state:
        module.exit_json(
            changed=False,
            message=f"Machine already {desired_state}",
            machine=sanitize_machine(current),
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            message=f"Machine would be {desired_state}",
            machine=sanitize_machine(current),
        )

    # Stopping waits on the current Machine version, so capture it first.
    version = machine_version(module, current) if params["wait"] and desired_state == "stopped" else None
    post_result(client, flyio_path("apps", app_name, "machines", current["id"], action))

    waited = params["wait"] and wait_tolerating_self_destroy(
        module, client, current, desired_state, deadline, version=version
    )

    requested = current
    current = validate_machine_data(module, get_machine(client, app_name, current["id"], missing_ok=True))
    if (current is None or current.get("state") in SELF_DESTROYED_STATES) and auto_destroys(module, requested):
        exit_self_destroyed(module, requested, f"{action} requested")

    if current is None:
        module.fail_json(msg=f"Machine '{requested['id']}' in app '{app_name}' is no longer available")

    # After a successful wait, a Machine that has already moved on (for example a job exiting) is fine.
    if params["wait"] and not (waited and current.get("state") in MOVED_ON_STATES | PRESENT_STATES):
        validate_waited_machine(module, current["id"], current, desired_state)

    message = f"Machine {desired_state}" if params["wait"] else f"Machine {action} requested"
    module.exit_json(
        changed=True,
        message=message,
        machine=sanitize_machine(current),
    )


def main():
    module = AnsibleModule(
        argument_spec={
            "api_token": {"required": True, "type": "str", "no_log": True},
            "app_name": {"required": True, "type": "str"},
            "id": {"type": "str"},
            "name": {"type": "str"},
            "region": {"type": "str"},
            "image": {"type": "str"},
            "init": {
                "type": "dict",
                "options": {
                    "cmd": {"type": "list", "elements": "str"},
                    "entrypoint": {"type": "list", "elements": "str"},
                    "exec": {"type": "list", "elements": "str"},
                    "tty": {"type": "bool"},
                },
            },
            "guest": {
                "type": "dict",
                "options": {
                    "cpu_kind": {"type": "str"},
                    "host_dedication_id": {"type": "str"},
                    "cpus": {"type": "int"},
                    "memory_mb": {"type": "int"},
                    "kernel_args": {"type": "list", "elements": "str"},
                    "persist_rootfs": {
                        "type": "str",
                        "choices": ["never", "restart", "always"],
                    },
                },
            },
            "services": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "protocol": {"type": "str", "choices": ["tcp", "udp"]},
                    "internal_port": {"type": "int", "required": True},
                    "autostart": {"type": "bool"},
                    "autostop": {"type": "raw"},
                    "min_machines_running": {"type": "int"},
                    "concurrency": {
                        "type": "dict",
                        "options": {
                            "type": {
                                "type": "str",
                                "choices": ["connections", "requests"],
                            },
                            "soft_limit": {"type": "int"},
                            "hard_limit": {"type": "int"},
                        },
                    },
                    "ports": {
                        "type": "list",
                        "elements": "dict",
                        "options": {
                            "port": {"type": "int"},
                            "start_port": {"type": "int"},
                            "end_port": {"type": "int"},
                            "handlers": {"type": "list", "elements": "str"},
                            "force_https": {"type": "bool"},
                            "http_options": {
                                "type": "dict",
                                "options": {
                                    "compress": {"type": "bool"},
                                    "h2_backend": {"type": "bool"},
                                    "response": {
                                        "type": "dict",
                                        "options": {
                                            "headers": {"type": "dict"},
                                            "pristine": {"type": "bool"},
                                        },
                                    },
                                },
                            },
                            "tls_options": {
                                "type": "dict",
                                "options": {
                                    "alpn": {"type": "list", "elements": "str"},
                                    "default_self_signed": {"type": "bool"},
                                    "versions": {
                                        "type": "list",
                                        "elements": "str",
                                    },
                                },
                            },
                            "proxy_proto_options": {
                                "type": "dict",
                                "options": {
                                    "version": {"type": "str"},
                                },
                            },
                        },
                        "mutually_exclusive": [
                            ("port", "start_port"),
                            ("port", "end_port"),
                        ],
                        "required_one_of": [("port", "start_port")],
                        "required_together": [("start_port", "end_port")],
                    },
                },
            },
            "checks": {"type": "dict"},
            "env": {"type": "dict"},
            "files": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "guest_path": {"type": "str", "required": True},
                    "raw_value": {"type": "str", "no_log": True},
                    "secret_name": {"type": "str"},
                },
                "mutually_exclusive": [("raw_value", "secret_name")],
                "required_one_of": [("raw_value", "secret_name")],
            },
            "mounts": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "volume": {"type": "str", "required": True},
                    "path": {"type": "str", "required": True},
                    "name": {
                        "type": "str",
                        "removed_in_version": "2.0.0",
                        "removed_from_collection": "linuxhq.flyio",
                    },
                    "extend_threshold_percent": {"type": "int"},
                    "add_size_gb": {"type": "int"},
                    "size_gb_limit": {"type": "int"},
                    "encrypted": {
                        "type": "bool",
                        "removed_in_version": "2.0.0",
                        "removed_from_collection": "linuxhq.flyio",
                    },
                },
                "required_together": [
                    ("extend_threshold_percent", "add_size_gb"),
                ],
            },
            "auto_destroy": {"type": "bool"},
            "restart": {
                "type": "dict",
                "options": {
                    "policy": {
                        "type": "str",
                        "choices": ["no", "always", "on-failure"],
                    },
                    "max_retries": {"type": "int"},
                },
            },
            "metadata": {"type": "dict"},
            "statics": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "guest_path": {"type": "str", "required": True},
                    "url_prefix": {"type": "str", "required": True},
                    "tigris_bucket": {"type": "str"},
                    "index_document": {"type": "str"},
                },
            },
            "wait": {"type": "bool", "default": True},
            "wait_timeout": {"type": "int", "default": 60},
            "state": {
                "type": "str",
                "choices": ["present", "absent", "started", "stopped"],
                "default": "present",
            },
        },
        mutually_exclusive=[
            ("id", "name"),
        ],
        required_one_of=[
            ("id", "name"),
        ],
        required_if=[
            ("state", "present", ("image",)),
        ],
        supports_check_mode=True,
    )

    with flyio_client(module) as client:
        state = module.params["state"]
        if state == "present":
            ensure_present(module, client)
        elif state == "absent":
            ensure_absent(module, client)
        else:
            ensure_power_state(module, client, state)


if __name__ == "__main__":
    main()

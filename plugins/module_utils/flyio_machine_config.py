# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Build, compare, and merge Fly.io Machine configurations without API access."""

import copy
import re
from decimal import Decimal

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
CHECK_DURATION_FIELDS = ("grace_period", "interval", "timeout")
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


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if item is not None}

    if isinstance(value, list):
        return [clean(item) for item in value]

    return value


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


def find_list_item(values, value):
    """First current list entry sharing the requested entry's identity keys.

    Entries sharing identity keys pair in order; match_list_items removes each match as it is used.
    """
    keys = [key for key in LIST_ITEM_KEYS if key in value] if isinstance(value, dict) else []
    if not keys:
        return None

    return next(
        (item for item in values if isinstance(item, dict) and all(item.get(key) == value[key] for key in keys)),
        None,
    )


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

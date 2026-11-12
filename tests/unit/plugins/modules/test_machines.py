# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible.module_utils.common.parameters import _list_no_log_values, remove_values

from ansible_collections.linuxhq.flyio.plugins.module_utils import flyio_machine_config as machine_config
from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import FlyioApiError
from ansible_collections.linuxhq.flyio.plugins.modules import machines
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


def params(**updates):
    values = {
        "app_name": "example",
        "id": None,
        "image": "example:latest",
        "name": "worker",
        "region": "ord",
        "state": "present",
        "wait": True,
        "wait_timeout": 60,
    }
    values.update(updates)
    return values


class MachinesTests(TestCase):
    def setUp(self):
        for name, kwargs in (
            ("wait_deadline", {"return_value": 60}),
            ("seconds_left", {"side_effect": lambda deadline: deadline}),
        ):
            patcher = patch.object(machines, name, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_accepts_normalized_machine_responses(self):
        cases = [
            ({"env": {}}, {}),
            ({"metadata": {}}, {}),
            ({"checks": {}}, {}),
            ({"services": []}, {}),
            ({"files": []}, {}),
            ({"statics": []}, {}),
            ({"auto_destroy": False}, {}),
            ({"init": {"tty": False}}, {"init": {}}),
            ({"init": {"cmd": []}}, {"init": {}}),
            ({"init": {"entrypoint": [], "exec": []}}, {"init": {}}),
            (
                {
                    "services": [
                        {
                            "protocol": "tcp",
                            "internal_port": 8080,
                            "ports": [{"port": 80, "force_https": False, "handlers": []}],
                        }
                    ]
                },
                {"services": [{"protocol": "tcp", "internal_port": 8080, "ports": [{"port": 80}]}]},
            ),
            (
                {"services": [{"protocol": "tcp", "internal_port": 8080, "ports": []}]},
                {"services": [{"protocol": "tcp", "internal_port": 8080}]},
            ),
        ]
        for field in ("alpn", "versions"):
            service = {"protocol": "tcp", "internal_port": 8080}
            port = {"port": 443, "handlers": ["tls", "http"]}
            for returned in ({}, {"tls_options": None}, {"tls_options": {}}, {"tls_options": {field: None}}):
                cases.append(
                    (
                        {"services": [{**service, "ports": [{**port, "tls_options": {field: []}}]}]},
                        {"services": [{**service, "ports": [{**port, **returned}]}]},
                    )
                )

        service = {"protocol": "tcp", "internal_port": 8080}
        port = {"port": 80, "handlers": ["http"]}
        for returned in (
            {},
            {"http_options": None},
            {"http_options": {}},
            {"http_options": {"response": None}},
            {"http_options": {"response": {}}},
            {"http_options": {"response": {"headers": None}}},
        ):
            requested_port = {**port, "http_options": {"response": {"headers": {}}}}
            cases.append(
                (
                    {"services": [{**service, "ports": [requested_port]}]},
                    {"services": [{**service, "ports": [{**port, **returned}]}]},
                )
            )

        check = {"port": 8080, "type": "http"}
        for returned in ({"name": "X-Test"}, {"name": "X-Test", "values": None}):
            cases.append(
                (
                    {"checks": {"health": {**check, "headers": [{"name": "X-Test", "values": []}]}}},
                    {"checks": {"health": {**check, "headers": [returned]}}},
                )
            )

        for field, value in (
            ("env", {}),
            ("metadata", {}),
            ("checks", {}),
            ("services", []),
            ("files", []),
            ("statics", []),
            ("mounts", []),
        ):
            cases.append(({field: value}, {field: None}))

        cases.append(
            (
                {"restart": {"policy": "on-failure", "max_retries": 0}},
                {"restart": {"policy": "on-failure"}},
            )
        )
        for values in (
            {"extend_threshold_percent": 0, "add_size_gb": 0},
            {"size_gb_limit": 0},
        ):
            mount = {"volume": "vol-one", "path": "/data"}
            cases.append(({"mounts": [{**mount, **values}]}, {"mounts": [mount]}))

        for requested_duration, returned_duration in (
            (15000000000, "15s"),
            ("60s", "1m0s"),
            ("1500ms", "1.5s"),
            ("1h30m", "1h30m0s"),
        ):
            for field in ("interval", "timeout", "grace_period"):
                check = {"port": 8080, "type": "tcp"}
                cases.append(
                    (
                        {"checks": {"health": {**check, field: requested_duration}}},
                        {"checks": {"health": {**check, field: returned_duration}}},
                    )
                )

        for requested, returned in cases:
            for operation in ("create", "update", "unchanged"):
                with self.subTest(requested=requested, operation=operation):
                    result = {
                        "id": "machine-one",
                        "name": "worker",
                        "region": "ord",
                        "state": "started",
                        "config": {"image": "example:latest", **returned},
                    }
                    current = (
                        None
                        if operation == "create"
                        else {
                            **result,
                            "config": {
                                **result["config"],
                                "image": "example:old" if operation == "update" else "example:latest",
                            },
                        }
                    )
                    module = FakeModule(params(**requested))
                    with (
                        patch.object(machines, "find_machine", return_value=current),
                        patch.object(machines, "post_result", return_value=result) as post,
                        patch.object(machines, "wait_for_machine"),
                        patch.object(machines, "get_resource", return_value=result),
                        self.assertRaises(ModuleExit) as raised,
                    ):
                        machines.ensure_present(module, {})

                    self.assertEqual(raised.exception.values["changed"], operation != "unchanged")
                    if operation == "unchanged":
                        post.assert_not_called()
                    else:
                        post.assert_called_once()
                        for field, value in requested.items():
                            self.assertEqual(post.call_args.args[2]["config"][field], value)

    def test_normalization_preserves_real_configuration_differences(self):
        for current, desired in (
            ({"env": {"OLD": "value"}}, {"env": {}}),
            ({"services": [{"internal_port": 8080}]}, {"services": []}),
            ({"auto_destroy": True}, {"auto_destroy": False}),
            ({}, {"auto_destroy": True}),
            ({"checks": {"health": {"interval": "15s"}}}, {"checks": {"health": {"interval": "16s"}}}),
            ({"env": {"TIME": "15s"}}, {"env": {"TIME": "15000ms"}}),
            ({"init": {"tty": True}}, {"init": {"tty": False}}),
            ({"init": {"cmd": ["old"]}}, {"init": {"cmd": []}}),
            (
                {"services": [{"internal_port": 80, "ports": [{"port": 80, "force_https": True}]}]},
                {"services": [{"internal_port": 80, "ports": [{"port": 80, "force_https": False}]}]},
            ),
        ):
            with self.subTest(current=current, desired=desired):
                self.assertTrue(
                    machine_config.machine_config_changed(
                        {"image": "example:latest", **current},
                        {"image": "example:latest", **desired},
                    )
                )

        self.assertFalse(
            machine_config.machine_config_changed(
                {"image": "example:latest", "env": {"KEEP": "value"}, "auto_destroy": True},
                {"image": "example:latest"},
            )
        )

    def test_tls_normalization_preserves_managed_changes_and_unmanaged_lists(self):
        def config(options):
            return {
                "image": "example:latest",
                "services": [
                    {
                        "protocol": "tcp",
                        "internal_port": 8080,
                        "ports": [{"port": 443, "tls_options": options}],
                    }
                ],
            }

        for field, value in (("alpn", ["h2"]), ("versions", ["TLSv1.2"])):
            for current, desired, changed in (
                ({field: value}, {field: []}, True),
                ({}, {field: value}, True),
                ({field: value}, {}, False),
            ):
                with self.subTest(field=field, current=current, desired=desired):
                    self.assertEqual(machine_config.machine_config_changed(config(current), config(desired)), changed)

    def test_header_normalization_preserves_real_changes(self):
        def config(values):
            return {
                "image": "example:latest",
                "checks": {"health": {"type": "http", "port": 8080, "headers": [{"name": "X-Test", **values}]}},
            }

        for current, desired in (({"values": ["old"]}, {"values": []}), ({}, {"values": ["new"]})):
            with self.subTest(current=current, desired=desired):
                self.assertTrue(machine_config.machine_config_changed(config(current), config(desired)))

        current = {
            "image": "example:latest",
            "services": [{"internal_port": 8080, "ports": [{"port": 80, "http_options": {"response": {}}}]}],
        }
        desired = {
            "image": "example:latest",
            "services": [
                {
                    "internal_port": 8080,
                    "ports": [{"port": 80, "http_options": {"response": {"headers": {"X-Test": "new"}}}}],
                }
            ],
        }
        self.assertTrue(machine_config.machine_config_changed(current, desired))
        self.assertFalse(machine_config.machine_config_changed(desired, current))

    def test_zero_defaults_preserve_mount_and_restart_changes(self):
        for field, old, new in (
            ("extend_threshold_percent", 80, 0),
            ("add_size_gb", 5, 0),
            ("size_gb_limit", 100, 0),
            ("encrypted", True, False),
        ):
            mount = {"volume": "vol-one", "path": "/data"}
            for before, after in (({field: old}, {field: new}), ({}, {field: old})):
                with self.subTest(field=field, before=before):
                    self.assertTrue(
                        machine_config.machine_config_changed(
                            {"image": "example:latest", "mounts": [{**mount, **before}]},
                            {"image": "example:latest", "mounts": [{**mount, **after}]},
                        )
                    )

        for before, after in (({"max_retries": 3}, {"max_retries": 0}), ({}, {"max_retries": 3})):
            self.assertTrue(
                machine_config.machine_config_changed(
                    {"image": "example:latest", "restart": {"policy": "on-failure", **before}},
                    {"image": "example:latest", "restart": {"policy": "on-failure", **after}},
                )
            )

    def test_finds_machine_by_name(self):
        listed = {
            "config": {"restart": {"policy": "on-failure"}},
            "id": "machine-one",
            "name": "worker",
            "state": "started",
        }

        with patch.object(machines, "list_all", return_value=[listed]):
            result = machines.find_machine({}, "example", name="worker")

        self.assertEqual(result, listed)

    def test_missing_parent_is_tolerated_only_when_requested(self):
        with patch.object(machines, "list_all", return_value=[]) as list_all:
            machines.find_machine({}, "example", name="worker")
            list_all.assert_called_once_with(
                {},
                "/apps/example/machines",
                ok_statuses=None,
                required_fields=("id", "name", "state"),
            )

            list_all.reset_mock()
            machines.find_machine({}, "example", name="worker", missing_ok=True)
            list_all.assert_called_once_with(
                {},
                "/apps/example/machines",
                ok_statuses=[404],
                required_fields=("id", "name", "state"),
            )

    def test_builds_config_without_none_values(self):
        config = machine_config.build_config(
            {
                "checks": {"health": {"port": 8080}},
                "env": None,
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                        "secret_name": None,
                    }
                ],
                "image": "example:latest",
                "init": {"entrypoint": ["/bin/sh"], "exec": None, "tty": None},
                "restart": {"policy": "on-failure"},
            }
        )

        self.assertEqual(
            config,
            {
                "checks": {"health": {"port": 8080}},
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                "image": "example:latest",
                "init": {"entrypoint": ["/bin/sh"]},
                "restart": {"policy": "on-failure"},
            },
        )

    def test_normalizes_autostop_to_provider_response_values(self):
        for value, expected in (("off", False), ("stop", True), ("suspend", "suspend")):
            with self.subTest(value=value):
                config = machine_config.build_config(
                    {
                        "image": "example:latest",
                        "services": [{"autostop": value, "internal_port": 8080}],
                    }
                )

                self.assertEqual(config["services"][0]["autostop"], expected)

    def test_rejects_invalid_config_before_api_lookup(self):
        for update, message in (
            ({"image": " "}, "image must not be empty"),
            ({"region": " "}, "region must not be empty"),
            (
                {"env": {"PORT": 8080}},
                "env must use non-empty string keys and string values",
            ),
            (
                {"metadata": {" ": "value"}},
                "metadata must use non-empty string keys and string values",
            ),
            (
                {"checks": {"health": None}},
                "checks must map names to configuration dictionaries",
            ),
            (
                {"checks": {"health": {1: "invalid"}}},
                "checks.health field names must be strings",
            ),
            (
                {"checks": {"health": {"port": "8080"}}},
                "checks.health.port must be an integer",
            ),
            (
                {"checks": {"health": {"timeout": False}}},
                "checks.health.timeout must be an integer or duration string",
            ),
            (
                {"checks": {"health": {"timeout": " "}}},
                "checks.health.timeout must be an integer or duration string",
            ),
            (
                {"checks": {"health": {"method": " "}}},
                "checks.health.method must not be empty",
            ),
            (
                {"checks": {"health": {"kind": "liveness"}}},
                "checks.health.kind must be informational or readiness",
            ),
            (
                {"checks": {"health": {"port": 0}}},
                "checks.health.port must be between 1 and 65535",
            ),
            (
                {"checks": {"health": {"interval": 0}}},
                "checks.health.interval must be at least 1",
            ),
            (
                {"checks": {"health": {"headers": {"X-Test": ["value"]}}}},
                "checks.health.headers must contain name and string values",
            ),
            (
                {"checks": {"health": {"headers": [{"name": "X-Test"}]}}},
                "checks.health.headers must contain name and string values",
            ),
            (
                {"checks": {"health": {"headers": [{"name": "X-Test", "values": None}]}}},
                "checks.health.headers must contain name and string values",
            ),
            (
                {"checks": {"health": {"headers": [{"name": " ", "values": ["x"]}]}}},
                "checks.health.headers must contain name and string values",
            ),
            (
                {"checks": {" ": {"port": 8080, "type": "tcp"}}},
                "checks must map names to configuration dictionaries",
            ),
            (
                {
                    "checks": {
                        "health": {
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "value": "secret",
                                    "values": ["secret"],
                                }
                            ]
                        }
                    }
                },
                "checks.health.headers must contain name and string values",
            ),
            ({"guest": {"cpus": 0}}, "guest.cpus must be at least 1"),
            (
                {"guest": {"memory_mb": 300}},
                "guest.memory_mb must be a multiple of 256",
            ),
            (
                {"services": [{"internal_port": 65536, "protocol": "tcp"}]},
                "services[].internal_port must be between 1 and 65535",
            ),
            (
                {
                    "services": [
                        {
                            "concurrency": {"hard_limit": 5, "soft_limit": 10},
                            "internal_port": 8080,
                            "protocol": "tcp",
                        }
                    ]
                },
                "services[].concurrency.soft_limit must not exceed hard_limit",
            ),
            (
                {
                    "mounts": [
                        {
                            "add_size_gb": 1,
                            "extend_threshold_percent": 101,
                            "path": "/data",
                            "volume": "vol-data",
                        }
                    ]
                },
                "mounts[].extend_threshold_percent must be between 50 and 99",
            ),
            (
                {
                    "mounts": [
                        {
                            "add_size_gb": 1,
                            "extend_threshold_percent": 10,
                            "path": "/data",
                            "volume": "vol-data",
                        }
                    ]
                },
                "mounts[].extend_threshold_percent must be between 50 and 99",
            ),
            (
                {
                    "mounts": [
                        {
                            "add_size_gb": 101,
                            "extend_threshold_percent": 80,
                            "path": "/data",
                            "volume": "vol-data",
                        }
                    ]
                },
                "mounts[].add_size_gb must be between 0 and 100",
            ),
            (
                {
                    "mounts": [
                        {
                            "add_size_gb": 1,
                            "extend_threshold_percent": 0,
                            "path": "/data",
                            "volume": "vol-data",
                        }
                    ]
                },
                ("mounts[].extend_threshold_percent and add_size_gb must both be zero to disable extension"),
            ),
            (
                {"restart": {"max_retries": -1, "policy": "on-failure"}},
                "restart.max_retries must be at least 0",
            ),
            (
                {
                    "services": [
                        {
                            "internal_port": 8080,
                            "ports": [{"http_options": {"response": {"headers": {"X-Test": True}}}}],
                        }
                    ]
                },
                ("service HTTP response headers must map non-empty strings to strings, string lists, or false"),
            ),
            (
                {
                    "services": [
                        {
                            "internal_port": 8080,
                            "ports": [{"http_options": {"response": {"headers": {"": "x"}}}}],
                        }
                    ]
                },
                ("service HTTP response headers must map non-empty strings to strings, string lists, or false"),
            ),
            (
                {"services": [{"autostop": 1, "internal_port": 8080}]},
                "service autostop must be off, stop, suspend, true, or false",
            ),
            (
                {
                    "files": [
                        {
                            "guest_path": "etc/example.conf",
                            "raw_value": "ZXhhbXBsZQ==",
                        }
                    ]
                },
                "files[].guest_path must be an absolute path",
            ),
            (
                {
                    "files": [
                        {
                            "guest_path": "/etc/example.conf",
                            "raw_value": "not Base64!",
                        }
                    ]
                },
                "files[].raw_value must be valid Base64",
            ),
            (
                {"mounts": [{"path": "data", "volume": "vol-data"}]},
                "mounts[].path must be an absolute path",
            ),
            (
                {"mounts": [{"path": "/data", "volume": " "}]},
                "mounts[].volume must not be empty",
            ),
            (
                {"files": [{"guest_path": "/etc/example.conf", "secret_name": " "}]},
                "files[].secret_name must not be empty",
            ),
            (
                {"statics": [{"guest_path": " ", "url_prefix": "/assets"}]},
                "statics[].guest_path must not be empty",
            ),
            (
                {"statics": [{"guest_path": "/assets", "url_prefix": " "}]},
                "statics[].url_prefix must not be empty",
            ),
        ):
            with (
                self.subTest(update=update),
                patch.object(machines, "find_machine") as find,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(**update)), {})

            find.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], message)

    def test_accepts_documented_check_durations(self):
        module = FakeModule(params())
        config = {
            "checks": {
                "health": {
                    "grace_period": 5_000_000_000,
                    "interval": "15s",
                    "timeout": "10s",
                }
            }
        }

        self.assertIsNone(machines.validate_config(module, config))

    def test_accepts_omitted_optional_lists(self):
        config = {
            "files": None,
            "mounts": None,
            "services": None,
            "statics": None,
        }

        self.assertIsNone(machines.validate_config(FakeModule(params()), config))

    def test_accepts_documented_check_headers(self):
        checks = {"health": {"headers": [{"name": "Authorization", "values": ["Bearer secret"]}]}}

        self.assertIsNone(machines.validate_checks(FakeModule(params()), checks))

    def test_accepts_documented_response_header_values(self):
        config = {
            "services": [
                {
                    "internal_port": 8080,
                    "ports": [
                        {
                            "http_options": {
                                "response": {
                                    "headers": {
                                        "X-Add": "value",
                                        "X-Multiple": ["one", "two"],
                                        "X-Remove": False,
                                    }
                                }
                            }
                        }
                    ],
                }
            ]
        }

        self.assertIsNone(machines.validate_config(FakeModule(params()), config))

    def test_accepts_zero_to_disable_mount_auto_extension(self):
        desired = {
            "mounts": [
                {
                    "add_size_gb": 0,
                    "extend_threshold_percent": 0,
                    "path": "/data",
                    "size_gb_limit": 0,
                    "volume": "vol-data",
                }
            ]
        }
        current = {
            "mounts": [
                {
                    "add_size_gb": 10,
                    "extend_threshold_percent": 80,
                    "path": "/data",
                    "size_gb_limit": 100,
                    "volume": "vol-data",
                }
            ]
        }

        self.assertIsNone(machines.validate_config(FakeModule(params()), desired))
        self.assertEqual(machine_config.merge_config(current, desired), desired)

    def test_create_requires_service_protocol(self):
        module = FakeModule(params(services=[{"internal_port": 8080}]))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "each service requires protocol",
        )

    def test_create_rejects_invalid_restart_policy_configuration(self):
        for restart, message in (
            ({"max_retries": 1}, "restart.policy is required"),
            (
                {"max_retries": 1, "policy": "always"},
                "restart.max_retries is valid only with policy=on-failure",
            ),
        ):
            module = FakeModule(params(restart=restart))

            with (
                self.subTest(restart=restart),
                patch.object(machines, "find_machine", return_value=None),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(module, {})

            post.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], message)

    def test_update_requires_protocol_for_unmatched_service(self):
        current = {
            "config": {
                "image": "example:latest",
                "services": [{"internal_port": 8080, "protocol": "tcp"}],
            },
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(services=[{"internal_port": 9090}], wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "each service requires protocol")

    def test_create_requires_complete_checks(self):
        module = FakeModule(params(checks={"health": {"port": 8080}}))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "check 'health' requires type",
        )

    def test_update_requires_complete_new_checks(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(checks={"health": {"port": 8080}}, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "check 'health' requires type")

    def test_partial_check_update_preserves_normalized_header_values(self):
        for header in (
            {"name": "X-Test"},
            {"name": "X-Test", "values": None},
            {"name": "X-Test", "values": ["existing"]},
        ):
            for timeout in ("2s", "3s"):
                for check_mode in (False, True):
                    with self.subTest(header=header, timeout=timeout, check_mode=check_mode):
                        check = {"type": "http", "port": 8080, "timeout": "2s", "headers": [header]}
                        current = {
                            "id": "machine-one",
                            "region": "ord",
                            "state": "started",
                            "config": {"image": "example:latest", "checks": {"health": check}},
                        }
                        result = {
                            **current,
                            "config": {
                                **current["config"],
                                "checks": {"health": {**check, "timeout": timeout}},
                            },
                        }
                        original_header = dict(header)
                        requested = {"health": {"timeout": timeout}}
                        module = FakeModule(params(checks=requested, wait=False), check_mode=check_mode)
                        with (
                            patch.object(machines, "find_machine", return_value=current),
                            patch.object(machines, "post_result", return_value=result) as post,
                            self.assertRaises(ModuleExit) as raised,
                        ):
                            machines.ensure_present(module, {})

                        self.assertEqual(raised.exception.values["changed"], timeout != "2s")
                        if check_mode or timeout == "2s":
                            post.assert_not_called()
                        else:
                            post.assert_called_once()
                            self.assertEqual(
                                post.call_args.args[2]["config"]["checks"]["health"]["headers"],
                                [{"name": "X-Test", "values": header.get("values") or []}],
                            )

                        self.assertEqual(header, original_header)
                        self.assertEqual(check["timeout"], "2s")
                        self.assertEqual(requested, {"health": {"timeout": timeout}})

    def test_update_requires_complete_malformed_existing_checks(self):
        module = FakeModule(params(checks={"health": {"timeout": "2s"}}, wait=False))

        for check, message in (
            (None, "check 'health' requires port and type"),
            ({"port": True, "type": "tcp"}, "checks.health.port must be an integer"),
            (
                {"port": 8080, "type": "http", "headers": [{"name": "X-Test", "values": "invalid"}]},
                "checks.health.headers must contain name and string values",
            ),
        ):
            current = {
                "config": {
                    "checks": {"health": check},
                    "image": "example:latest",
                },
                "id": "machine-one",
                "region": "ord",
                "state": "started",
            }
            with (
                self.subTest(check=check),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(module, {})

            post.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], message)

    def test_equivalent_machine_is_unchanged(self):
        current = {
            "config": {"image": "ghcr.io/example/app:latest"},
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(params(image="ghcr.io/example/app:latest"))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_normalized_machine_is_unchanged(self):
        current = {
            "config": {
                "checks": {
                    "health": {
                        "headers": [{"name": "Authorization", "values": ["secret"]}],
                        "port": 8080,
                        "timeout": "2s",
                        "type": "http",
                    }
                },
                "env": {"TOKEN": "secret"},
                "files": [
                    {
                        "guest_path": "/etc/example.conf",
                        "mode": "0644",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 256},
                "image": "example:latest",
                "init": {
                    "cmd": None,
                    "entrypoint": ["/bin/sh"],
                    "exec": None,
                    "tty": False,
                },
                "mounts": [
                    {
                        "encrypted": True,
                        "name": "data",
                        "path": "/data",
                        "size_gb": 1,
                        "volume": "vol-example",
                    }
                ],
                "restart": {"max_retries": 10, "policy": "on-failure"},
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(
            params(
                checks={"health": {"port": 8080, "type": "http"}},
                files=[
                    {
                        "guest_path": "/etc/example.conf",
                        "raw_value": "ZXhhbXBsZQ==",
                    }
                ],
                guest={"cpus": 1},
                init={"entrypoint": ["/bin/sh"]},
                mounts=[{"path": "/data", "volume": "vol-example"}],
                restart={"policy": "on-failure"},
            )
        )

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])
        result = raised.exception.values["machine"]
        self.assertEqual(result, current)

    def test_provider_restart_retries_do_not_break_always_policy(self):
        current = {
            "config": {
                "image": "example:latest",
                "restart": {"max_retries": 10, "policy": "always"},
            },
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(restart={"policy": "always"}))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_present_waits_for_existing_transition(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "version": "instance-one",
            "region": "ord",
            "state": "stopping",
        }
        stopped = {**current, "state": "stopped"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version=None)
        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_updates_machine_and_waits(self):
        current = {
            "config": {
                "env": {"PRESERVED": "value"},
                "image": "ghcr.io/library/example:latest",
                "services": [{"internal_port": 8080}],
            },
            "id": "machine-one",
            "version": "version-one",
            "region": "ord",
            "state": "started",
        }
        updated = {
            "id": "machine-one",
            "version": "version-two",
            "state": "starting",
        }
        started = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "state": "started",
        }
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            {
                "config": {
                    "env": {"PRESERVED": "value"},
                    "image": "example:latest",
                    "services": [{"internal_port": 8080}],
                },
                "current_version": "version-one",
            },
        )
        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version="version-two")
        self.assertEqual(raised.exception.values["machine"], started)

    def test_removes_concurrency_hard_limit(self):
        service = {
            "internal_port": 8080,
            "protocol": "tcp",
            "concurrency": {"type": "requests", "soft_limit": 20, "hard_limit": 30},
        }
        current = {
            "id": "machine-one",
            "state": "started",
            "region": "ord",
            "config": {"image": "example:latest", "services": [service]},
        }
        applied_service = {**service, "concurrency": {"type": "requests", "soft_limit": 20}}
        applied = {**current, "config": {**current["config"], "services": [applied_service]}}
        for concurrency in ({"hard_limit": 0}, {"soft_limit": 20, "hard_limit": 0}):
            for check_mode in (False, True):
                with self.subTest(concurrency=concurrency, check_mode=check_mode):
                    module = FakeModule(
                        params(services=[{"internal_port": 8080, "concurrency": concurrency}], wait=False),
                        check_mode=check_mode,
                    )
                    with (
                        patch.object(machines, "find_machine", return_value=current),
                        patch.object(machines, "post_result", return_value=applied) as post,
                        self.assertRaises(ModuleExit) as raised,
                    ):
                        machines.ensure_present(module, {})

                    self.assertTrue(raised.exception.values["changed"])
                    if check_mode:
                        post.assert_not_called()
                    else:
                        post.assert_called_once_with(
                            {},
                            "/apps/example/machines/machine-one",
                            {
                                "config": {
                                    **current["config"],
                                    "services": [
                                        {**service, "concurrency": {**service["concurrency"], "hard_limit": 0}}
                                    ],
                                }
                            },
                        )

                    with (
                        patch.object(machines, "find_machine", return_value=applied),
                        patch.object(machines, "post_result") as post,
                        self.assertRaises(ModuleExit) as raised,
                    ):
                        machines.ensure_present(module, {})

                    self.assertFalse(raised.exception.values["changed"])
                    post.assert_not_called()

    def test_update_wait_accepts_missing_response_instance_id(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "version": "instance-one",
            "region": "ord",
            "state": "started",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(
                machines,
                "post_result",
                return_value={"id": "machine-one", "state": "starting"},
            ),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(
                machines,
                "get_resource",
                return_value={
                    "config": {"image": "example:latest"},
                    "id": "machine-one",
                    "state": "started",
                },
            ),
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(FakeModule(params()), {})

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version=None)

    def test_update_rejects_malformed_current_version_before_mutation(self):
        for instance_id in ([], " "):
            current = {
                "config": {"image": "example:old"},
                "id": "machine-one",
                "version": instance_id,
                "region": "ord",
                "state": "started",
            }

            with (
                self.subTest(version=instance_id),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(wait=False)), {})

            post.assert_not_called()
            self.assertIn("expected a version", raised.exception.values["msg"])

    def test_rejects_malformed_update_response(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "version": "instance-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(wait=False))

        for response in (
            {},
            {"id": "machine-two"},
            {"id": "machine-one", "state": False},
        ):
            with (
                self.subTest(response=response),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result", return_value=response),
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data while updating Machine 'machine-one' in app 'example'",
            )

    def test_rejects_unapplied_update_response(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "region": "ord",
            "state": "stopped",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(wait=False)), {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API did not apply the requested configuration to Machine 'machine-one' in app 'example'",
        )

    def test_rejects_malformed_current_configuration(self):
        current = {"config": None, "id": "machine-one", "state": "started"}
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed configuration for Machine 'machine-one' in app 'example'",
        )

    def test_preserves_unmanaged_nested_config_on_update(self):
        current = {
            "config": {
                "checks": {
                    "health": {
                        "kind": "readiness",
                        "port": 8080,
                        "timeout": "2s",
                    },
                    "remove": {"port": 8081},
                },
                "guest": {"cpus": 1, "memory_mb": 2048},
                "image": "example:latest",
                "services": [
                    {
                        "internal_port": 8080,
                        "protocol": "tcp",
                        "ports": [{"force_https": True, "port": 80}],
                    }
                ],
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(
            params(
                checks={"health": {"port": 9090}},
                guest={"cpus": 2},
                services=[
                    {
                        "internal_port": 8080,
                        "ports": [{"handlers": ["http"], "port": 80}],
                    }
                ],
                wait=False,
            )
        )
        applied = {
            **current,
            "config": {
                "checks": {
                    "health": {
                        "kind": "readiness",
                        "port": 9090,
                        "timeout": "2s",
                    }
                },
                "guest": {"cpus": 2, "memory_mb": 2048},
                "image": "example:latest",
                "services": [
                    {
                        "internal_port": 8080,
                        "protocol": "tcp",
                        "ports": [
                            {
                                "force_https": True,
                                "handlers": ["http"],
                                "port": 80,
                            }
                        ],
                    }
                ],
            },
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=applied) as post,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        config = post.call_args.args[2]["config"]
        self.assertEqual(config["guest"], {"cpus": 2, "memory_mb": 2048})
        self.assertEqual(
            config["checks"],
            {
                "health": {
                    "kind": "readiness",
                    "port": 9090,
                    "timeout": "2s",
                }
            },
        )
        self.assertEqual(
            config["services"],
            [
                {
                    "internal_port": 8080,
                    "protocol": "tcp",
                    "ports": [{"force_https": True, "handlers": ["http"], "port": 80}],
                }
            ],
        )

    def test_switches_file_source_without_preserving_the_old_source(self):
        for current_source, desired_source in (
            ({"raw_value": "b2xk"}, {"secret_name": "new-secret"}),
            ({"secret_name": "old-secret"}, {"raw_value": "bmV3"}),
            ({"image_config": "old"}, {"raw_value": "bmV3"}),
        ):
            with self.subTest(desired_source=desired_source):
                result = machine_config.merge_config(
                    {"files": [{"guest_path": "/etc/example.conf", **current_source}]},
                    {"files": [{"guest_path": "/etc/example.conf", **desired_source}]},
                )

                self.assertEqual(
                    result,
                    {"files": [{"guest_path": "/etc/example.conf", **desired_source}]},
                )

    def test_changing_restart_policy_drops_stale_max_retries(self):
        self.assertEqual(
            machine_config.merge_config(
                {"restart": {"max_retries": 3, "policy": "on-failure"}},
                {"restart": {"policy": "always"}},
            ),
            {"restart": {"policy": "always"}},
        )

    def test_rejects_malformed_existing_nested_service_data(self):
        for current_service, desired_service, message in (
            (
                {"concurrency": [], "internal_port": 8080, "protocol": "tcp"},
                {"internal_port": 8080},
                "services[].concurrency must be a dictionary",
            ),
            (
                {"internal_port": 8080, "ports": {}, "protocol": "tcp"},
                {"internal_port": 8080},
                "services[].ports must be a list of dictionaries",
            ),
            (
                {
                    "internal_port": 8080,
                    "ports": [{"http_options": [], "port": 80}],
                    "protocol": "tcp",
                },
                {"internal_port": 8080, "ports": [{"port": 80}]},
                "services[].ports[].http_options must be a dictionary",
            ),
            (
                {
                    "internal_port": 8080,
                    "ports": [{"http_options": {"response": []}, "port": 80}],
                    "protocol": "tcp",
                },
                {"internal_port": 8080, "ports": [{"port": 80}]},
                "services[].ports[].http_options.response must be a dictionary",
            ),
        ):
            current = {
                "config": {
                    "image": "example:latest",
                    "services": [current_service],
                },
                "id": "machine-one",
                "region": "ord",
            }
            module = FakeModule(params(services=[desired_service], wait=False))

            with (
                self.subTest(message=message),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(module, {})

            post.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], message)

    def test_merges_reordered_list_items_by_identity(self):
        current = [
            {"internal_port": 8080, "protocol": "tcp"},
            {"internal_port": 9090, "protocol": "udp"},
        ]
        desired = [{"internal_port": 9090}, {"internal_port": 8080}]

        result = machine_config.merge_values(current, desired)

        self.assertFalse(machine_config.config_values_differ(current, desired))
        self.assertEqual(
            result,
            [
                {"internal_port": 9090, "protocol": "udp"},
                {"internal_port": 8080, "protocol": "tcp"},
            ],
        )

    def test_purge_detects_only_top_level_removed_keys(self):
        current = {
            "health": {"port": 8080, "timeout": "2s"},
            "remove": {"port": 8081},
        }

        self.assertFalse(
            machine_config.config_values_differ(
                current,
                {"health": {"port": 8080}},
            )
        )
        self.assertTrue(
            machine_config.config_values_differ(
                current,
                {"health": {"port": 8080}},
                purge=True,
            )
        )

    def test_config_comparison_distinguishes_booleans_from_integers(self):
        self.assertTrue(machine_config.config_values_differ(True, 1))
        self.assertTrue(machine_config.config_values_differ(False, 0))

    def test_nested_list_items_are_compared_by_identity(self):
        current = [{"internal_port": 8080, "ports": [{"port": 80}, {"port": 443}]}]
        desired = [{"internal_port": 8080, "ports": [{"port": 443}, {"port": 80}]}]

        self.assertFalse(machine_config.config_values_differ(current, desired))

    def test_range_ports_are_merged_by_identity(self):
        current = [
            {"end_port": 1099, "handlers": ["http"], "start_port": 1000},
            {"end_port": 2099, "handlers": ["tls"], "start_port": 2000},
        ]
        desired = [
            {"end_port": 2099, "start_port": 2000},
            {"end_port": 1099, "start_port": 1000},
        ]

        self.assertFalse(machine_config.config_values_differ(current, desired))
        self.assertEqual(
            machine_config.merge_values(current, desired),
            [current[1], current[0]],
        )

    def test_static_routes_with_shared_directory_match_by_url_prefix(self):
        statics = [
            {"guest_path": "/public", "url_prefix": "/assets", "index_document": "index.html"},
            {"guest_path": "/public", "url_prefix": "/legacy", "index_document": "legacy.html"},
        ]
        current = {
            "id": "machine-one",
            "state": "started",
            "region": "ord",
            "config": {"image": "example:latest", "statics": statics},
        }
        requested = [
            {"guest_path": route["guest_path"], "url_prefix": route["url_prefix"]} for route in reversed(statics)
        ]
        for image in ("example:latest", "example:new"):
            for check_mode in (False, True):
                with self.subTest(image=image, check_mode=check_mode):
                    module = FakeModule(params(image=image, statics=requested, wait=False), check_mode=check_mode)
                    applied = {**current, "config": {"image": image, "statics": list(reversed(statics))}}
                    with (
                        patch.object(machines, "find_machine", return_value=current),
                        patch.object(machines, "post_result", return_value=applied) as post,
                        self.assertRaises(ModuleExit) as raised,
                    ):
                        machines.ensure_present(module, {})

                    self.assertEqual(raised.exception.values["changed"], image != "example:latest")
                    if check_mode or image == "example:latest":
                        post.assert_not_called()
                    else:
                        post.assert_called_once()
                        self.assertEqual(post.call_args.args[2]["config"], applied["config"])

    def test_identityless_nested_items_preserve_defaults(self):
        current = [{"interval": "15s", "timeout": "2s", "type": "tcp"}]
        desired = [{"interval": "15s", "type": "tcp"}]

        self.assertFalse(machine_config.config_values_differ(current, desired))
        self.assertEqual(machine_config.merge_values(current, desired), current)

    def test_duplicate_list_items_need_distinct_matches(self):
        current = [{"internal_port": 8080}, {"internal_port": 9090}]
        desired = [{"internal_port": 8080}, {"internal_port": 8080}]

        self.assertTrue(machine_config.config_values_differ(current, desired))
        self.assertFalse(machine_config.config_values_differ(desired, desired))

    def test_rejects_multiple_mounts(self):
        module = FakeModule(
            params(
                mounts=[
                    {"path": "/data", "volume": "vol-data"},
                    {"path": "/logs", "volume": "vol-logs"},
                ]
            )
        )

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "only one volume can be mounted to a Machine",
        )

    def test_mount_name_and_id_are_equivalent(self):
        current = {
            "config": {
                "image": "example:latest",
                "mounts": [{"name": "data", "path": "/data", "volume": "vol-data"}],
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(params(mounts=[{"path": "/data", "volume": "data"}]))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_mount_updates_preserve_unmanaged_settings(self):
        mount = {
            "volume": "vol-data",
            "name": "data",
            "path": "/data",
            "extend_threshold_percent": 80,
            "add_size_gb": 5,
            "size_gb_limit": 100,
        }
        current = {
            "id": "machine-one",
            "state": "started",
            "region": "ord",
            "config": {"image": "example:old", "mounts": [mount]},
        }
        for requested in (
            {"volume": "data", "path": "/data"},
            {"volume": "vol-data", "path": "/new-data"},
            {"volume": "data", "path": "/data", "extend_threshold_percent": 0, "add_size_gb": 0},
        ):
            with self.subTest(requested=requested):
                module = FakeModule(params(mounts=[requested], wait=False))
                applied = {
                    **current,
                    # The attached volume ID is kept even when the mount is requested by name.
                    "config": {
                        "image": "example:latest",
                        "mounts": [{**mount, **requested, "volume": mount["volume"]}],
                    },
                }
                with (
                    patch.object(machines, "find_machine", return_value=current),
                    patch.object(machines, "post_result", return_value=applied) as post,
                    self.assertRaises(ModuleExit) as raised,
                ):
                    machines.ensure_present(module, {})

                self.assertTrue(raised.exception.values["changed"])
                self.assertEqual(post.call_args.args[2]["config"], applied["config"])
                self.assertEqual(current["config"], {"image": "example:old", "mounts": [mount]})
                self.assertEqual(mount["extend_threshold_percent"], 80)
                self.assertEqual(mount["add_size_gb"], 5)

    def test_conflicting_mount_identifiers_are_different(self):
        current = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-old"}]}
        desired = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-new"}]}

        self.assertTrue(machine_config.mounts_differ(current, desired))

    def test_malformed_current_mounts_are_different(self):
        self.assertTrue(machine_config.mounts_differ({"mounts": "invalid"}, {"mounts": []}))
        self.assertTrue(
            machine_config.mounts_differ(
                {"mounts": [{"volume": ["invalid"]}]},
                {"mounts": [{"volume": "data"}]},
            )
        )

    def test_malformed_current_checks_do_not_crash_merge(self):
        desired = {"checks": {"health": {"port": 8080}}}

        self.assertEqual(machine_config.merge_config({"checks": None}, desired), desired)

    def test_merges_duplicate_ports_by_complete_identity(self):
        current = [
            {"internal_port": 53, "protocol": "tcp", "tcp_checks": ["preserve"]},
            {"internal_port": 53, "protocol": "udp", "udp_checks": ["preserve"]},
        ]

        result = machine_config.merge_values(
            current,
            [
                {"internal_port": 53, "protocol": "udp"},
                {"internal_port": 53, "protocol": "tcp"},
            ],
        )

        self.assertEqual(
            result,
            [
                {
                    "internal_port": 53,
                    "protocol": "udp",
                    "udp_checks": ["preserve"],
                },
                {
                    "internal_port": 53,
                    "protocol": "tcp",
                    "tcp_checks": ["preserve"],
                },
            ],
        )

    def test_rejects_changing_attached_volume(self):
        current = {
            "config": {
                "image": "example:latest",
                "mounts": [{"path": "/data", "volume": "vol-old"}],
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(params(mounts=[{"path": "/data", "volume": "vol-new"}]))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Attached volume cannot be changed for Machine 'machine-one' in app 'example'",
        )

    def test_updates_stopped_machine_without_launching(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "version": "version-one",
            "region": "ord",
            "state": "stopped",
        }
        updated = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "state": "stopped",
        }
        module = FakeModule(params(wait=True))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=updated),
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        self.assertTrue(post.call_args.args[2]["skip_launch"])
        self.assertEqual(post.call_args.args[2]["current_version"], "version-one")
        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version=None)

    def test_removes_unspecified_environment_keys(self):
        current = {
            "config": {
                "env": {"KEEP": "value", "REMOVE": "value"},
                "image": "example:latest",
            },
            "id": "machine-one",
            "region": "ord",
        }
        module = FakeModule(params(env={"KEEP": "value"}, wait=False))
        updated = {
            **current,
            "config": {"env": {"KEEP": "value"}, "image": "example:latest"},
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            {
                "config": {
                    "env": {"KEEP": "value"},
                    "image": "example:latest",
                },
            },
        )

    def test_rejects_region_changes(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "region": "iad",
        }
        module = FakeModule(params(region="ord"))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Region cannot be changed for Machine 'machine-one' in app 'example'",
        )

    def test_rejects_missing_current_region_when_region_is_managed(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "state": "started",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params()), {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed region data for Machine 'machine-one' in app 'example'",
        )

    def test_check_mode_does_not_create_machine(self):
        module = FakeModule(params(), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])

    def test_missing_machine_id_fails_instead_of_creating(self):
        module = FakeModule(params(id="missing", name=None))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'missing' not found in app 'example'",
        )

    def test_create_wait_returns_refreshed_machine(self):
        created = {
            "id": "machine-one",
            "version": "instance-one",
            "state": "starting",
        }
        started = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "name": "worker",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version="instance-one")
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            ok_statuses=[404],
            required_fields=("id", "state"),
            expected={"id": "machine-one"},
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_rejects_malformed_create_response(self):
        module = FakeModule(params(wait=False))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value={}),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while creating Machine 'worker' in app 'example'",
        )

    def test_rejects_unapplied_create_response(self):
        created = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "name": "other",
            "region": "iad",
            "state": "started",
        }

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(wait=False)), {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API did not apply the requested configuration to Machine 'machine-one' in app 'example'",
        )

    def test_destroy_waits_for_destroyed_state(self):
        current = {
            "id": "machine-one",
            "version": "instance-one",
            "state": "started",
        }
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "delete_result", return_value=None) as delete,
            patch.object(machines, "get_resource", return_value=None) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        wait.assert_called_once_with({}, "example", "machine-one", "destroyed", 60)
        delete.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one?force=true",
            ok_statuses=[404],
        )
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            ok_statuses=[404],
            required_fields=("id", "state"),
            expected={"id": "machine-one"},
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["machine"], current)

    def test_destroy_rejects_surviving_machine_after_wait(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "delete_result", return_value=None),
            patch.object(machines, "get_resource", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' did not reach state 'destroyed' (current state: started)",
        )

    def test_destroy_without_wait_returns_request_status(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["message"],
            "Machine destruction requested",
        )
        self.assertEqual(raised.exception.values["machine"], current)

    def test_destroying_machine_waits_without_deleting_again(self):
        current = {"id": "machine-one", "state": "destroying"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result") as delete,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        delete.assert_not_called()
        wait.assert_called_once_with({}, "example", "machine-one", "destroyed", 60)
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["machine"], current)

    def test_destroying_machine_does_not_wait_in_check_mode(self):
        current = {"id": "machine-one", "state": "destroying"}
        module = FakeModule(params(image=None), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result") as delete,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource") as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        delete.assert_not_called()
        wait.assert_not_called()
        get.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["machine"], current)

    def test_starts_machine(self):
        current = {
            "id": "machine-one",
            "state": "stopped",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(
                machines,
                "post_result",
                return_value=None,
            ) as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        request.assert_called_once_with({}, "/apps/example/machines/machine-one/start")
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            version=None,
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_waiting_for_stop_requires_instance_id_before_mutation(self):
        current = {"id": "machine-one", "state": "started"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_power_state(FakeModule(params(image=None)), {}, "stopped")

        request.assert_not_called()
        self.assertIn("expected a version", raised.exception.values["msg"])

    def test_starting_machine_waits_without_starting_again(self):
        current = {
            "id": "machine-one",
            "state": "starting",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            version=None,
        )
        self.assertFalse(raised.exception.values["changed"])

    def test_target_transition_does_not_wait_in_check_mode(self):
        for state, desired_state in (
            ("starting", "started"),
            ("stopping", "stopped"),
        ):
            current = {"id": "machine-one", "state": state}
            module = FakeModule(params(image=None), check_mode=True)

            with (
                self.subTest(state=state),
                patch.object(machines, "wait_for_machine") as wait,
                patch.object(machines, "get_resource") as get,
                self.assertRaises(ModuleExit) as raised,
            ):
                machines.settle_machine(module, {}, current, desired_state, 60)

            wait.assert_not_called()
            get.assert_not_called()
            self.assertFalse(raised.exception.values["changed"])
            self.assertEqual(raised.exception.values["machine"], current)

    def test_rejects_waited_machine_in_wrong_state(self):
        current = {"id": "machine-one", "state": "stopping"}
        module = FakeModule(params(image=None))

        with self.assertRaises(ModuleFail) as raised:
            machines.validate_waited_machine(
                module,
                "machine-one",
                current,
                "started",
            )

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' did not reach state 'started' (current state: stopping)",
        )

    def test_present_wait_accepts_only_stable_usable_states(self):
        module = FakeModule(params(image=None))

        for state in machines.PRESENT_STATES:
            with self.subTest(state=state):
                self.assertIsNone(
                    machines.validate_waited_machine(
                        module,
                        "machine-one",
                        {"id": "machine-one", "state": state},
                        "settled",
                    )
                )

        for state in ("failed", "starting", "destroyed"):
            with self.subTest(state=state), self.assertRaises(ModuleFail):
                machines.validate_waited_machine(
                    module,
                    "machine-one",
                    {"id": "machine-one", "state": state},
                    "settled",
                )

    def test_waits_for_ambiguous_machine_transition_to_settle(self):
        current = {"id": "machine-one", "state": "replacing"}
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        request.assert_not_called()
        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version=None)
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_ambiguous_machine_transition_without_wait(self):
        current = {"id": "machine-one", "state": "replacing"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' is currently replacing; enable wait or retry",
        )

    def test_rejects_timed_out_machine_transition(self):
        current = {"id": "machine-one", "state": "replacing"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=current),
            patch.object(machines, "post_result") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        request.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Transition of Machine 'machine-one' in app 'example' timed out",
        )

    def test_settle_reports_machine_headed_for_destruction_as_gone(self):
        for state in ("destroying", "launch_failed"):
            with (
                self.subTest(state=state),
                patch.object(machines, "find_machine", return_value={"id": "machine-one", "state": "creating"}),
                patch.object(machines, "wait_for_machine"),
                patch.object(machines, "get_resource", return_value={"id": "machine-one", "state": state}),
                patch.object(machines, "post_result") as request,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_power_state(FakeModule(params(image=None)), {}, "started")

            request.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"], "Machine 'machine-one' in app 'example' is no longer available"
            )

    def test_stops_machine(self):
        current = {
            "id": "machine-one",
            "version": "instance-one",
            "state": "started",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(
                machines,
                "post_result",
                return_value=None,
            ) as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "stopped")

        request.assert_called_once_with({}, "/apps/example/machines/machine-one/stop")
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            version="instance-one",
        )
        self.assertEqual(raised.exception.values["machine"], stopped)

    def test_created_machine_is_already_not_running(self):
        current = {"id": "machine-one", "state": "created"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as request,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "stopped")

        request.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_nonpositive_wait_timeout(self):
        module = FakeModule(params(image=None, wait_timeout=0))

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "wait_timeout must be greater than zero",
        )

    def test_stopping_machine_waits_without_stopping_again(self):
        current = {
            "id": "machine-one",
            "version": "instance-one",
            "state": "stopping",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "stopped")

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            version="instance-one",
        )
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_duplicate_machine_names(self):
        listed = [
            {"id": "machine-one", "name": "worker", "state": "started"},
            {"id": "machine-two", "name": "worker", "state": "stopped"},
        ]

        with (
            patch.object(machines, "list_all", return_value=listed),
            self.assertRaises(FlyioApiError) as raised,
        ):
            machines.find_machine({}, "example", name="worker")

        self.assertEqual(
            str(raised.exception),
            "Multiple Machines named 'worker' match in app 'example' (machine-one, machine-two); specify id",
        )

    def test_returned_configuration_is_not_masked_by_no_log(self):
        with (
            patch.object(machines, "AnsibleModule", side_effect=RuntimeError) as module,
            self.assertRaises(RuntimeError),
        ):
            machines.main()

        spec = module.call_args.kwargs["argument_spec"]
        params = {
            "checks": {"web": {"type": "http", "port": 8080, "path": "/healthz"}},
            "env": {"DEBUG": "1"},
        }
        self.assertEqual(_list_no_log_values(spec, params), set())
        machine = {"id": "d1234", "config": {"image": "app:v1", "services": [{"internal_port": 8080}]}}
        self.assertEqual(remove_values(machine, _list_no_log_values(spec, params)), machine)

    def test_ignores_provider_owned_mount_fields(self):
        mount = {"volume": "vol-one", "path": "/data"}
        current = {
            "config": {"image": "example:latest", "mounts": [{**mount, "encrypted": True, "name": "data"}]},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(mounts=[{**mount, "encrypted": False, "name": "other"}], wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_changing_check_type_replaces_check(self):
        current = {
            "config": {
                "checks": {"web": {"type": "http", "port": 8080, "path": "/healthz", "method": "GET"}},
                "image": "example:latest",
            },
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        desired = {"type": "tcp", "port": 8080}
        updated = {**current, "config": {**current["config"], "checks": {"web": desired}}}
        module = FakeModule(params(checks={"web": desired}, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated) as post,
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(module, {})

        self.assertEqual(post.call_args.args[2]["config"]["checks"], {"web": desired})

    def test_replaced_check_must_be_complete(self):
        current = {
            "config": {"checks": {"web": {"type": "http", "port": 8080}}, "image": "example:latest"},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(checks={"web": {"type": "tcp"}}, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "check 'web' requires port")

    def test_waits_for_migrating_machine_before_update(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "migrating"}
        started = {**current, "state": "started"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit),
        ):
            machines.ensure_present(FakeModule(params()), {})

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60, version=None)

    def test_name_lookup_skips_destroying_machines_except_for_absent(self):
        destroying = {"id": "machine-old", "name": "worker", "state": "destroying"}
        started = {"id": "machine-new", "name": "worker", "state": "started"}

        with patch.object(machines, "list_all", return_value=[destroying, started]):
            self.assertEqual(machines.find_machine({}, "example", name="worker"), started)

        with patch.object(machines, "list_all", return_value=[destroying]):
            self.assertIsNone(machines.find_machine({}, "example", name="worker"))
            self.assertEqual(
                machines.find_machine({}, "example", name="worker", include_destroying=True),
                destroying,
            )

    def test_multiple_destroying_machines_are_not_ambiguous_for_absent(self):
        destroying = [
            {"id": "machine-one", "name": "worker", "state": "destroying"},
            {"id": "machine-two", "name": "worker", "state": "destroying"},
        ]

        live = [{**machine, "state": "started"} for machine in destroying]

        with patch.object(machines, "list_all", return_value=destroying):
            found = machines.find_machine({}, "example", name="worker", include_destroying=True)

        with (
            patch.object(machines, "list_all", return_value=live),
            self.assertRaises(FlyioApiError),
        ):
            machines.find_machine({}, "example", name="worker", include_destroying=True)

        self.assertEqual(found["id"], "machine-one")

    def test_id_lookup_treats_terminal_machines_as_absent(self):
        for state in ("destroyed", "replaced", "migrated"):
            with (
                self.subTest(state=state),
                patch.object(machines, "get_resource", return_value={"id": "machine-one", "state": state}),
            ):
                self.assertIsNone(
                    machines.find_machine({}, "example", machine_id="machine-one", include_destroying=True)
                )

    def test_absent_by_id_reports_migrated_machine_unchanged(self):
        module = FakeModule(params(id="machine-one", name=None, state="absent"))

        with (
            patch.object(machines, "get_resource", return_value={"id": "machine-one", "state": "migrated"}),
            patch.object(machines, "delete_result") as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        delete.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["message"], "Machine already absent")

    def test_lookup_treats_launch_failed_machines_as_not_live(self):
        failed = {"id": "machine-old", "name": "worker", "state": "launch_failed"}
        started = {"id": "machine-new", "name": "worker", "state": "started"}

        with patch.object(machines, "list_all", return_value=[failed, started]):
            self.assertEqual(machines.find_machine({}, "example", name="worker"), started)

        with patch.object(machines, "list_all", return_value=[failed]):
            self.assertIsNone(machines.find_machine({}, "example", name="worker"))
            self.assertEqual(machines.find_machine({}, "example", name="worker", include_destroying=True), failed)

        with patch.object(machines, "get_resource", return_value=failed):
            self.assertIsNone(machines.find_machine({}, "example", machine_id="machine-old"))

    def test_negative_soft_limit_reports_documented_minimum(self):
        services = [{"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": -1}}]

        with self.assertRaises(ModuleFail) as raised:
            machines.ensure_present(FakeModule(params(services=services)), {})

        self.assertEqual(raised.exception.values["msg"], "services[].concurrency.soft_limit must be at least 1")

    def test_create_accepts_auto_destroyed_machine_after_wait(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}
        module = FakeModule(params(auto_destroy=True))

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["machine"], created)
        self.assertEqual(raised.exception.values["message"], "Machine created; it completed and destroyed itself")

    def test_create_without_auto_destroy_rejects_destroyed_machine(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value={**created, "state": "destroyed"}),
            self.assertRaises(ModuleFail),
        ):
            machines.ensure_present(FakeModule(params()), {})

    def test_rejects_region_lists_and_groups(self):
        for region in ("us", "any", "ord,iad", "Europe"):
            with (
                self.subTest(region=region),
                patch.object(machines, "find_machine") as find,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(region=region)), {})

            find.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                "region must be a single region code; region lists and groups are not supported",
            )

    def test_unchanged_transitioning_machine_without_wait_is_unchanged(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "starting"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(FakeModule(params(wait=False)), {})

        post.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_changed_transitioning_machine_without_wait_still_fails(self):
        current = {"config": {"image": "example:old"}, "id": "machine-one", "region": "ord", "state": "starting"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail),
        ):
            machines.ensure_present(FakeModule(params(wait=False)), {})

        post.assert_not_called()

    def test_stop_accepts_machine_that_auto_destroys(self):
        current = {
            "config": {"auto_destroy": True, "image": "example:latest"},
            "id": "machine-one",
            "state": "started",
            "version": "v1",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result"),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(FakeModule(params(image=None)), {}, "stopped")

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(
            raised.exception.values["message"], "Machine stop requested; it completed and destroyed itself"
        )

    def test_update_accepts_self_destroy_from_existing_config(self):
        current = {
            "config": {"auto_destroy": True, "image": "example:old"},
            "id": "machine-one",
            "region": "ord",
            "state": "stopped",
            "version": "v1",
        }
        updated = {**current, "config": {"auto_destroy": True, "image": "example:latest"}, "version": "v2"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(FakeModule(params()), {})

        self.assertTrue(raised.exception.values["changed"])

    def test_id_lookup_skips_destroying_machine_except_for_absent(self):
        destroying = {"id": "machine-one", "state": "destroying"}

        with patch.object(machines, "get_resource", return_value=destroying):
            self.assertIsNone(machines.find_machine({}, "example", machine_id="machine-one"))
            self.assertEqual(
                machines.find_machine({}, "example", machine_id="machine-one", include_destroying=True),
                destroying,
            )

    def test_absent_name_lookup_prefers_live_machine(self):
        destroying = {"id": "machine-old", "name": "web", "state": "destroying"}
        live = {"id": "machine-new", "name": "web", "state": "started"}

        with patch.object(machines, "list_all", return_value=[destroying, live]):
            self.assertEqual(machines.find_machine({}, "example", name="web", include_destroying=True), live)

    def test_archived_machine_is_not_managed(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "archived"}

        for state in ("present", "started", "stopped"):
            with (
                self.subTest(state=state),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                if state == "present":
                    machines.ensure_present(FakeModule(params()), {})
                else:
                    machines.ensure_power_state(FakeModule(params(image=None)), {}, state)

            post.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                "Machine 'machine-one' in app 'example' is archived; only state=absent is supported",
            )

    def test_documented_transient_states_are_waited_on(self):
        for state in ("creating", "restarting", "launch_failed", "updating"):
            with self.subTest(state=state):
                self.assertIn(state, machines.TRANSITIONAL_STATES)

    def test_unreachable_host_is_reported_before_update(self):
        current = {
            "config": None,
            "host_status": "unreachable",
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params()), {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Host for Machine 'machine-one' in app 'example' is not reachable (host_status=unreachable); retry later",
        )

    def test_unreachable_host_after_update_is_not_reported_as_unapplied(self):
        current = {"config": {"image": "example:old"}, "id": "machine-one", "region": "ord", "state": "started"}
        updated = {"config": {"image": "example:latest"}, "id": "machine-one", "state": "started", "version": "v2"}
        unreachable = {"config": None, "host_status": "unreachable", "id": "machine-one", "state": "started"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result", return_value=updated),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=unreachable),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params()), {})

        self.assertIn("is not reachable (host_status=unreachable)", raised.exception.values["msg"])

    def test_self_destroying_machine_tolerates_wait_errors(self):
        current = {
            "config": {"auto_destroy": True, "image": "example:latest"},
            "id": "machine-one",
            "state": "stopped",
            "version": "v1",
        }
        for status in (404, 408):
            with (
                self.subTest(status=status),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result"),
                patch.object(machines, "wait_for_machine", side_effect=FlyioApiError("gone", status_code=status)),
                patch.object(machines, "get_resource", return_value=None),
                self.assertRaises(ModuleExit) as raised,
            ):
                machines.ensure_power_state(FakeModule(params(image=None)), {}, "started")

            self.assertEqual(
                raised.exception.values["message"],
                "Machine start requested; it completed and destroyed itself",
            )

    def test_wait_errors_still_fail_without_auto_destroy(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "state": "stopped", "version": "v1"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result"),
            patch.object(machines, "wait_for_machine", side_effect=FlyioApiError("gone", status_code=404)),
            self.assertRaises(FlyioApiError),
        ):
            machines.ensure_power_state(FakeModule(params(image=None)), {}, "started")

    def test_restart_retries_rejected_for_other_policy_without_current_restart(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "started"}
        module = FakeModule(params(restart={"policy": "always", "max_retries": 3}, wait=False), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(raised.exception.values["msg"], "restart.max_retries is valid only with policy=on-failure")
        self.assertEqual(module.params["restart"], {"policy": "always", "max_retries": 3})

    def test_machine_archived_after_wait_is_rejected(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "pending"}
        archived = {**current, "state": "archived"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=archived),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_power_state(FakeModule(params(image=None)), {}, "started")

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' is archived; only state=absent is supported",
        )

    def test_stopped_spot_machine_update_fails_before_request(self):
        for spot, check_mode in (
            ({"max_price_fraction": 0.5}, False),
            ({"max_price_fraction": 0.5}, True),
            ({}, False),
            ({}, True),
        ):
            current = {
                "config": {"image": "example:old", "spot": spot},
                "id": "machine-one",
                "region": "ord",
                "state": "stopped",
                "version": "v1",
            }
            with (
                self.subTest(spot=spot, check_mode=check_mode),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(), check_mode=check_mode), {})

            post.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                "Spot Machine 'machine-one' in app 'example' must be running to be updated; start it first",
            )

    def test_add_size_gb_replaces_percentage_extension(self):
        current = {
            "mounts": [
                {
                    "volume": "vol_1",
                    "name": "data",
                    "path": "/data",
                    "extend_threshold_percent": 80,
                    "add_size_percent": 10,
                    "min_add_size_gb": 2,
                }
            ]
        }
        desired = {"mounts": [{"volume": "vol_1", "path": "/data", "extend_threshold_percent": 80, "add_size_gb": 5}]}

        mount = machine_config.merge_config(current, desired)["mounts"][0]

        self.assertEqual(mount["add_size_gb"], 5)
        self.assertNotIn("add_size_percent", mount)
        self.assertNotIn("min_add_size_gb", mount)

    def test_auto_destroy_option_is_ignored_for_power_states(self):
        current = {
            "config": {"auto_destroy": False, "image": "example:latest"},
            "id": "machine-one",
            "state": "stopped",
        }

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result"),
            patch.object(machines, "wait_for_machine", side_effect=FlyioApiError("gone", status_code=404)),
            self.assertRaises(FlyioApiError),
        ):
            machines.ensure_power_state(
                FakeModule(params(image=None, state="started", auto_destroy=True)), {}, "started"
            )

    def test_duplicate_services_compare_equal_with_omitted_defaults(self):
        requested = {
            "image": "example:latest",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80, "force_https": False}]},
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 443}]},
            ],
        }
        returned = {
            "image": "example:latest",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80}]},
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 443}]},
            ],
        }

        self.assertFalse(machine_config.machine_config_changed(returned, requested))

    def test_machine_moving_on_after_settled_wait_is_accepted(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}
        stopping = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "name": "worker",
            "region": "ord",
            "state": "stopping",
        }

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=stopping),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(FakeModule(params()), {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["machine"]["state"], "stopping")

    def test_tolerated_wait_timeout_does_not_accept_transitional_machine(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}
        starting = {
            "config": {"auto_destroy": True, "image": "example:latest"},
            "id": "machine-one",
            "name": "worker",
            "region": "ord",
            "state": "starting",
        }

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine", side_effect=FlyioApiError("timeout", status_code=408)),
            patch.object(machines, "get_resource", return_value=starting),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(auto_destroy=True)), {})

        self.assertIn("did not reach state 'settled' (current state: starting)", raised.exception.values["msg"])

    def test_lowering_hard_limit_below_current_soft_limit_is_allowed(self):
        service = {
            "internal_port": 8080,
            "protocol": "tcp",
            "concurrency": {"type": "connections", "soft_limit": 20, "hard_limit": 25},
        }
        current = {
            "config": {"image": "example:latest", "services": [service]},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(
            params(services=[{"internal_port": 8080, "concurrency": {"hard_limit": 10}}], wait=False), check_mode=True
        )

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])

    def test_raising_soft_limit_above_current_hard_limit_fails_before_update(self):
        service = {
            "internal_port": 8080,
            "protocol": "tcp",
            "concurrency": {"type": "connections", "soft_limit": 20, "hard_limit": 25},
        }
        current = {
            "config": {"image": "example:latest", "services": [service]},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(services=[{"internal_port": 8080, "concurrency": {"soft_limit": 50}}], wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "services[].concurrency.soft_limit must not exceed hard_limit")

    def test_rejects_empty_optional_strings(self):
        for updates, name in (
            ({"guest": {"cpu_kind": ""}}, "guest.cpu_kind"),
            ({"guest": {"host_dedication_id": " "}}, "guest.host_dedication_id"),
            ({"statics": [{"guest_path": "/a", "url_prefix": "/", "tigris_bucket": ""}]}, "statics[].tigris_bucket"),
            ({"statics": [{"guest_path": "/a", "url_prefix": "/", "index_document": ""}]}, "statics[].index_document"),
            (
                {
                    "services": [
                        {
                            "internal_port": 80,
                            "protocol": "tcp",
                            "ports": [{"port": 80, "proxy_proto_options": {"version": ""}}],
                        }
                    ]
                },
                "services[].ports[].proxy_proto_options.version",
            ),
        ):
            with (
                self.subTest(name=name),
                patch.object(machines, "find_machine") as find,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(**updates)), {})

            find.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], f"{name} must not be empty")

    def test_region_is_normalized_to_lowercase_code(self):
        module = FakeModule(params(region=" ORD "))

        with (
            patch.object(machines, "find_machine", return_value=None),
            self.assertRaises(ModuleExit),
        ):
            module.check_mode = True
            machines.ensure_present(module, {})

        self.assertEqual(module.params["region"], "ord")

    def test_power_state_accepts_auto_destroying_or_moved_on_machine(self):
        for desired_state, state, reread, message in (
            ("stopped", "started", "destroying", "Machine stop requested; it completed and destroyed itself"),
            ("started", "stopped", "stopping", "Machine started"),
        ):
            current = {
                "config": {"auto_destroy": True, "image": "example:latest"},
                "id": "machine-one",
                "state": state,
                "version": "v1",
            }
            with (
                self.subTest(desired_state=desired_state, reread=reread),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result"),
                patch.object(machines, "wait_for_machine"),
                patch.object(machines, "get_resource", return_value={**current, "state": reread}),
                self.assertRaises(ModuleExit) as raised,
            ):
                machines.ensure_power_state(FakeModule(params(image=None)), {}, desired_state)

            self.assertTrue(raised.exception.values["changed"])
            self.assertEqual(raised.exception.values["message"], message)

    def test_destruction_after_successful_wait_fails_without_auto_destroy(self):
        for state in ("destroying", "launch_failed"):
            current = {"config": {"image": "example:latest"}, "id": "machine-one", "state": "stopped", "version": "v1"}
            with (
                self.subTest(path="start", state=state),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result"),
                patch.object(machines, "wait_for_machine"),
                patch.object(machines, "get_resource", return_value={**current, "state": state}),
                self.assertRaises(ModuleFail),
            ):
                machines.ensure_power_state(FakeModule(params(image=None)), {}, "started")

            created = {"id": "machine-one", "version": "v1", "state": "created"}
            reread = {
                "config": {"image": "example:latest"},
                "id": "machine-one",
                "name": "worker",
                "region": "ord",
                "state": state,
            }
            with (
                self.subTest(path="create", state=state),
                patch.object(machines, "find_machine", return_value=None),
                patch.object(machines, "post_result", return_value=created),
                patch.object(machines, "wait_for_machine"),
                patch.object(machines, "get_resource", return_value=reread),
                self.assertRaises(ModuleFail),
            ):
                machines.ensure_present(FakeModule(params()), {})

    def test_create_accepts_auto_destroying_machine_in_destroying_state(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}
        reread = {
            "config": {"auto_destroy": True, "image": "example:latest"},
            "id": "machine-one",
            "state": "destroying",
        }

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=reread),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(FakeModule(params(auto_destroy=True)), {})

        self.assertEqual(raised.exception.values["message"], "Machine created; it completed and destroyed itself")

    def test_empty_concurrency_and_proxy_proto_options_match_omitted_fields(self):
        current = {
            "image": "example:latest",
            "services": [{"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80}]}],
        }
        desired = {
            "image": "example:latest",
            "services": [
                {
                    "internal_port": 8080,
                    "protocol": "tcp",
                    "concurrency": {},
                    "ports": [{"port": 80, "proxy_proto_options": {}}],
                }
            ],
        }

        self.assertFalse(machine_config.machine_config_changed(current, desired))

    def test_check_named_headers_keeps_merge_comparison(self):
        current = {"image": "example:latest", "checks": {"headers": {"type": "tcp", "port": 8080, "interval": "15s"}}}
        desired = {"image": "example:latest", "checks": {"headers": {"type": "tcp", "port": 8080}}}

        self.assertFalse(machine_config.machine_config_changed(current, desired))

    def test_response_headers_merge_with_current_headers(self):
        def config(headers):
            port = {"port": 443, "http_options": {"response": {"headers": headers}}}
            return {
                "image": "example:latest",
                "services": [{"internal_port": 8080, "protocol": "tcp", "ports": [port]}],
            }

        current = config({"A": "1", "B": "2"})
        desired = config({"A": "1"})

        self.assertFalse(machine_config.machine_config_changed(current, desired))
        merged = machine_config.merge_config(current, desired)
        self.assertEqual(merged["services"][0]["ports"][0]["http_options"]["response"]["headers"], {"A": "1", "B": "2"})
        self.assertTrue(machine_config.machine_config_changed(current, config({"A": "1", "B": False})))

    def test_power_state_accepts_stable_state_reached_after_successful_wait(self):
        for desired_state, state, reread, message in (
            ("started", "stopped", "stopped", "Machine started"),
            ("stopped", "started", "started", "Machine stopped"),
        ):
            current = {"config": {"image": "example:latest"}, "id": "machine-one", "state": state, "version": "v1"}
            with (
                self.subTest(desired_state=desired_state),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result"),
                patch.object(machines, "wait_for_machine"),
                patch.object(machines, "get_resource", return_value={**current, "state": reread}),
                self.assertRaises(ModuleExit) as raised,
            ):
                machines.ensure_power_state(FakeModule(params(image=None)), {}, desired_state)

            self.assertTrue(raised.exception.values["changed"])
            self.assertEqual(raised.exception.values["message"], message)

    def test_settle_continues_when_machine_moves_past_wait_target(self):
        current = {"config": {"image": "example:latest"}, "id": "machine-one", "region": "ord", "state": "starting"}
        stopped = {**current, "state": "stopped"}

        with (
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=stopped),
        ):
            result = machines.settle_machine(FakeModule(params(image=None)), {}, current, "stopped", 60)

        self.assertEqual(result, stopped)

    def test_merge_pairs_duplicate_services_like_the_change_check(self):
        current = {
            "image": "example:old",
            "services": [
                {
                    "internal_port": 8080,
                    "protocol": "tcp",
                    "autostart": True,
                    "min_machines_running": 1,
                    "ports": [{"port": 80}],
                },
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80, "force_https": True}]},
            ],
        }
        desired = {
            "image": "example:new",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80, "force_https": False}]},
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80, "force_https": True}]},
            ],
        }

        merged = machine_config.merge_config(current, desired)

        self.assertTrue(merged["services"][0]["autostart"])
        self.assertEqual(merged["services"][0]["min_machines_running"], 1)
        self.assertFalse(merged["services"][0]["ports"][0]["force_https"])

    def test_merge_does_not_leak_comparison_defaults_into_other_services(self):
        current = {
            "image": "example:old",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80}]},
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 443}]},
            ],
        }
        desired = {
            "image": "example:new",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": 5}, "ports": [{"port": 80}]},
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 443}]},
            ],
        }

        merged = machine_config.merge_config(current, desired)

        self.assertEqual(merged["services"][0]["concurrency"], {"soft_limit": 5})
        self.assertNotIn("concurrency", merged["services"][1])
        self.assertEqual(merged["services"][1]["ports"], [{"port": 443}])

    def test_duplicate_services_pair_in_order_for_merge_and_compare(self):
        current = {
            "image": "example:latest",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80}]},
                {"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": 5}},
            ],
        }
        desired = {
            "image": "example:latest",
            "services": [
                {"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": 1}},
                {"internal_port": 8080, "protocol": "tcp", "ports": []},
            ],
        }

        merged = machine_config.merge_config(current, desired)

        self.assertFalse(machine_config.machine_config_changed(merged, desired))
        self.assertEqual(merged["services"][0]["ports"], [{"port": 80}])
        self.assertEqual(merged["services"][1]["concurrency"], {"soft_limit": 5})

    def test_reordering_duplicate_services_is_a_change(self):
        first = {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 80}]}
        second = {"internal_port": 8080, "protocol": "tcp", "ports": [{"port": 443}]}
        current = {"image": "example:latest", "services": [first, second]}

        self.assertFalse(
            machine_config.machine_config_changed(current, {"image": "example:latest", "services": [first, second]})
        )
        self.assertTrue(
            machine_config.machine_config_changed(current, {"image": "example:latest", "services": [second, first]})
        )

    def test_rejects_zero_soft_limit(self):
        services = [{"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": 0}}]

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(services=services)), {})

        find.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "services[].concurrency.soft_limit must be at least 1")

    def test_current_zero_soft_limit_does_not_block_other_updates(self):
        service = {"internal_port": 8080, "protocol": "tcp", "concurrency": {"soft_limit": 0}}
        current = {
            "config": {"image": "example:old", "services": [service]},
            "id": "machine-one",
            "region": "ord",
            "state": "started",
        }
        module = FakeModule(params(services=[{"internal_port": 8080, "protocol": "tcp"}], wait=False), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])

    def test_diff_mode_reports_created_config(self):
        module = FakeModule(params(env={"TOKEN": "secret"}), check_mode=True, diff=True)

        with (
            patch.object(machines, "find_machine", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        diff = raised.exception.values["diff"]
        self.assertEqual(diff["before"], {})
        self.assertEqual(diff["after"]["config"]["image"], "example:latest")
        self.assertEqual(diff["after"]["name"], "worker")
        self.assertEqual(diff["after"]["config"]["env"], {"TOKEN": "secret"})

    def test_diff_mode_reports_updated_config(self):
        current = {
            "id": "machine-one",
            "name": "worker",
            "region": "ord",
            "state": "started",
            "config": {"image": "example:old", "env": {"TOKEN": "secret"}},
        }
        module = FakeModule(params(env={"TOKEN": "changed"}), check_mode=True, diff=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(
            raised.exception.values["diff"],
            {
                "before": {"config": {"image": "example:old", "env": {"TOKEN": "secret"}}},
                "after": {"config": {"image": "example:latest", "env": {"TOKEN": "changed"}}},
            },
        )

    def test_diff_mode_reports_power_state(self):
        current = {"id": "machine-one", "name": "worker", "region": "ord", "state": "stopped"}
        module = FakeModule(params(state="started"), check_mode=True, diff=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_power_state(module, {}, "started")

        self.assertEqual(
            raised.exception.values["diff"],
            {"before": {"state": "stopped"}, "after": {"state": "started"}},
        )

    def test_diff_is_omitted_without_diff_mode(self):
        with (
            patch.object(machines, "find_machine", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(FakeModule(params(), check_mode=True), {})

        self.assertNotIn("diff", raised.exception.values)

    def test_diff_mode_reports_auto_destroyed_machine(self):
        created = {"id": "machine-one", "version": "v1", "state": "created"}
        module = FakeModule(params(auto_destroy=True), diff=True)

        with (
            patch.object(machines, "find_machine", return_value=None),
            patch.object(machines, "post_result", return_value=created),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "get_resource", return_value=None),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_present(module, {})

        self.assertEqual(raised.exception.values["message"], "Machine created; it completed and destroyed itself")
        self.assertEqual(raised.exception.values["diff"]["before"], {})
        self.assertEqual(raised.exception.values["diff"]["after"]["config"]["image"], "example:latest")

    def test_rejects_tty_that_fly_ignores(self):
        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(init={"tty": True})), {})

        find.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "init.tty cannot be true because Fly.io ignores it")

    def test_region_change_fails_before_waiting_for_transition(self):
        current = {"id": "machine-one", "name": "worker", "region": "ord", "state": "starting"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(region="iad")), {})

        wait.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"], "Region cannot be changed for Machine 'machine-one' in app 'example'"
        )

    def test_rejects_inverted_port_range(self):
        services = [{"internal_port": 8080, "protocol": "tcp", "ports": [{"start_port": 2000, "end_port": 1000}]}]

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(FakeModule(params(services=services)), {})

        find.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "services[].ports[].start_port must not exceed end_port")

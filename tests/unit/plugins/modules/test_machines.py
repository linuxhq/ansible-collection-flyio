# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

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
        "wait": True,
        "wait_timeout": 60,
    }
    values.update(updates)
    return values


class MachinesTests(TestCase):
    def test_finds_machine_by_name(self):
        listed = {
            "config": {"restart": {"policy": "on-failure"}},
            "id": "machine-one",
            "name": "worker",
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
                required_field="id",
                required_fields=("name", "state"),
            )

            list_all.reset_mock()
            machines.find_machine({}, "example", name="worker", missing_ok=True)
            list_all.assert_called_once_with(
                {},
                "/apps/example/machines",
                ok_statuses=[404],
                required_field="id",
                required_fields=("name", "state"),
            )

    def test_builds_config_without_none_values(self):
        config = machines.build_config(
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
                config = machines.build_config(
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
                "mounts[].extend_threshold_percent must be between 0 and 100",
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
                            "ports": [
                                {
                                    "http_options": {
                                        "response": {"headers": {"X-Test": True}}
                                    }
                                }
                            ],
                        }
                    ]
                },
                (
                    "service HTTP response headers must map non-empty strings to "
                    "strings, string lists, or false"
                ),
            ),
            (
                {
                    "services": [
                        {
                            "internal_port": 8080,
                            "ports": [
                                {"http_options": {"response": {"headers": {"": "x"}}}}
                            ],
                        }
                    ]
                },
                (
                    "service HTTP response headers must map non-empty strings to "
                    "strings, string lists, or false"
                ),
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
        checks = {
            "health": {
                "headers": [{"name": "Authorization", "values": ["Bearer secret"]}]
            }
        }

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
        self.assertEqual(machines.merge_config(current, desired), desired)

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
        self.assertEqual(
            raised.exception.values["msg"], "each service requires protocol"
        )

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
        self.assertNotIn("env", result["config"])
        self.assertNotIn("raw_value", result["config"]["files"][0])
        self.assertNotIn("headers", result["config"]["checks"]["health"])

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

    def test_present_rejects_terminal_machine(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "state": "destroyed",
        }
        module = FakeModule(params())

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "post_result") as post,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_present(module, {})

        post.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' is in terminal state 'destroyed'",
        )

    def test_present_waits_for_existing_transition(self):
        current = {
            "config": {"image": "example:latest"},
            "id": "machine-one",
            "instance_id": "instance-one",
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

        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "settled",
            60,
            instance_id=None,
        )
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
            "instance_id": "version-one",
            "region": "ord",
            "state": "started",
        }
        updated = {
            "id": "machine-one",
            "instance_id": "version-two",
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
            patch.object(machines, "get_resource", return_value=started) as get,
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
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "settled",
            60,
        )
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            required_field="id",
            expected_value="machine-one",
            required_fields=("state",),
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_update_wait_accepts_missing_response_instance_id(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "instance_id": "instance-one",
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

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60)

    def test_update_rejects_malformed_current_version_before_mutation(self):
        for instance_id in ([], " "):
            current = {
                "config": {"image": "example:old"},
                "id": "machine-one",
                "instance_id": instance_id,
                "region": "ord",
                "state": "started",
            }

            with (
                self.subTest(instance_id=instance_id),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "post_result") as post,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines.ensure_present(FakeModule(params(wait=False)), {})

            post.assert_not_called()
            self.assertIn("expected an instance ID", raised.exception.values["msg"])

    def test_rejects_malformed_update_response(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "instance_id": "instance-one",
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
                "Fly.io API returned malformed data while updating Machine "
                "'machine-one' in app 'example'",
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
            "Fly.io API did not apply the requested configuration to Machine "
            "'machine-one' in app 'example'",
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
            "Fly.io API returned malformed configuration for Machine "
            "'machine-one' in app 'example'",
        )

    def test_preserves_unmanaged_nested_config_on_update(self):
        current = {
            "config": {
                "checks": {
                    "health": {"port": 8080, "timeout": "2s"},
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
                "checks": {"health": {"port": 9090, "timeout": "2s"}},
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
        self.assertEqual(config["checks"], {"health": {"port": 9090, "timeout": "2s"}})
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

    def test_merges_reordered_list_items_by_identity(self):
        current = [
            {"internal_port": 8080, "protocol": "tcp"},
            {"internal_port": 9090, "protocol": "udp"},
        ]
        desired = [{"internal_port": 9090}, {"internal_port": 8080}]

        result = machines.merge_values(current, desired)

        self.assertFalse(machines.config_values_differ(current, desired))
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
            machines.config_values_differ(
                current,
                {"health": {"port": 8080}},
            )
        )
        self.assertTrue(
            machines.config_values_differ(
                current,
                {"health": {"port": 8080}},
                purge=True,
            )
        )

    def test_nested_list_items_are_compared_by_identity(self):
        current = [{"internal_port": 8080, "ports": [{"port": 80}, {"port": 443}]}]
        desired = [{"internal_port": 8080, "ports": [{"port": 443}, {"port": 80}]}]

        self.assertFalse(machines.config_values_differ(current, desired))

    def test_range_ports_are_merged_by_identity(self):
        current = [
            {"end_port": 1099, "handlers": ["http"], "start_port": 1000},
            {"end_port": 2099, "handlers": ["tls"], "start_port": 2000},
        ]
        desired = [
            {"end_port": 2099, "start_port": 2000},
            {"end_port": 1099, "start_port": 1000},
        ]

        self.assertFalse(machines.config_values_differ(current, desired))
        self.assertEqual(
            machines.merge_values(current, desired),
            [current[1], current[0]],
        )

    def test_identityless_nested_items_preserve_defaults(self):
        current = [{"interval": "15s", "timeout": "2s", "type": "tcp"}]
        desired = [{"interval": "15s", "type": "tcp"}]

        self.assertFalse(machines.config_values_differ(current, desired))
        self.assertEqual(machines.merge_values(current, desired), current)

    def test_duplicate_desired_list_items_need_distinct_matches(self):
        current = [{"internal_port": 8080}, {"internal_port": 9090}]
        desired = [{"internal_port": 8080}, {"internal_port": 8080}]

        self.assertTrue(machines.config_values_differ(current, desired))

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

    def test_conflicting_mount_identifiers_are_different(self):
        current = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-old"}]}
        desired = {"mounts": [{"name": "data", "path": "/data", "volume": "vol-new"}]}

        self.assertTrue(machines.mounts_differ(current, desired))

    def test_malformed_current_mounts_are_different(self):
        self.assertTrue(machines.mounts_differ({"mounts": None}, {"mounts": []}))

    def test_malformed_current_checks_do_not_crash_merge(self):
        desired = {"checks": {"health": {"port": 8080}}}

        self.assertEqual(machines.merge_config({"checks": None}, desired), desired)

    def test_merges_duplicate_ports_by_complete_identity(self):
        current = [
            {"internal_port": 53, "protocol": "tcp", "tcp_checks": ["preserve"]},
            {"internal_port": 53, "protocol": "udp", "udp_checks": ["preserve"]},
        ]

        result = machines.merge_values(
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
            "Attached volume cannot be changed for Machine 'machine-one' "
            "in app 'example'",
        )

    def test_updates_stopped_machine_without_launching(self):
        current = {
            "config": {"image": "example:old"},
            "id": "machine-one",
            "instance_id": "version-one",
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
        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60)

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
            "Fly.io API returned malformed region data for Machine "
            "'machine-one' in app 'example'",
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
            "instance_id": "instance-one",
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

        wait.assert_called_once_with({}, "example", "machine-one", "settled", 60)
        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            required_field="id",
            expected_value="machine-one",
            required_fields=("state",),
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
            "Fly.io API returned malformed data while creating Machine "
            "'worker' in app 'example'",
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
            "Fly.io API did not apply the requested configuration to Machine "
            "'machine-one' in app 'example'",
        )

    def test_destroy_waits_for_destroyed_state(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "started",
        }
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(
                machines, "delete_result", return_value={"ok": True}
            ) as delete,
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
            required_field="id",
            expected_value="machine-one",
            required_fields=("state",),
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("machine", raised.exception.values)

    def test_destroy_rejects_surviving_machine_after_wait(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine"),
            patch.object(machines, "delete_result", return_value={"ok": True}),
            patch.object(machines, "get_resource", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' did not reach state 'destroyed'",
        )

    def test_destroy_rejects_negative_acknowledgement(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result", return_value={"ok": False}),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while destroying Machine "
            "'machine-one' in app 'example'",
        )

    def test_destroy_without_wait_returns_request_status(self):
        current = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "delete_result", return_value={"ok": True}),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["message"],
            "Machine destruction requested",
        )
        self.assertNotIn("machine", raised.exception.values)

    def test_destroyed_machine_is_unchanged_in_check_mode(self):
        current = {"id": "machine-one", "state": "destroyed"}
        module = FakeModule(params(image=None), check_mode=True)

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_absent(module, {})

        self.assertFalse(raised.exception.values["changed"])

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
                "api_request",
                return_value=None,
            ) as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/start"
        )
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
        )
        self.assertEqual(raised.exception.values["machine"], started)

    def test_rejects_malformed_machine_action_responses(self):
        for action, state, message in (
            (machines.ensure_started, "stopped", "starting"),
            (machines.ensure_stopped, "started", "stopping"),
        ):
            current = {"id": "machine-one", "state": state}
            module = FakeModule(params(image=None, wait=False))

            with (
                self.subTest(action=action.__name__),
                patch.object(machines, "find_machine", return_value=current),
                patch.object(machines, "api_request", return_value={"ok": False}),
                patch.object(machines, "get_resource") as get,
                self.assertRaises(ModuleFail) as raised,
            ):
                action(module, {})

            get.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                f"Fly.io API returned malformed data while {message} Machine "
                "'machine-one' in app 'example'",
            )

    def test_waiting_for_stop_requires_instance_id_before_mutation(self):
        current = {"id": "machine-one", "state": "started"}

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_stopped(FakeModule(params(image=None)), {})

        request.assert_not_called()
        self.assertIn("expected an instance ID", raised.exception.values["msg"])

    def test_starting_machine_waits_without_starting_again(self):
        current = {
            "id": "machine-one",
            "state": "starting",
        }
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=started),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "started",
            60,
            instance_id=None,
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
                machines.settle_machine(module, {}, current, desired_state)

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
            "Machine 'machine-one' in app 'example' did not reach state 'started'",
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
        current = {"id": "machine-one", "state": "updating"}
        started = {"id": "machine-one", "state": "started"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(
                machines, "wait_for_machine_settled", return_value=started
            ) as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {}, "example", "machine-one", machines.TRANSITIONAL_STATES, 60
        )
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_ambiguous_machine_transition_without_wait(self):
        current = {"id": "machine-one", "state": "updating"}
        module = FakeModule(params(image=None, wait=False))

        with (
            patch.object(machines, "find_machine", return_value=current),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' is currently updating; "
            "enable wait or retry",
        )

    def test_rejects_timed_out_machine_transition(self):
        current = {"id": "machine-one", "state": "updating"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "wait_for_machine_settled", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        request.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Transition of Machine 'machine-one' in app 'example' timed out",
        )

    def test_rejects_terminal_machine_state(self):
        current = {"id": "machine-one", "state": "migrated"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'machine-one' in app 'example' is in terminal state 'migrated'",
        )

    def test_stops_machine(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "started",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(
                machines,
                "api_request",
                return_value=None,
            ) as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_called_once_with(
            {}, "post", "/apps/example/machines/machine-one/stop"
        )
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            instance_id="instance-one",
        )
        self.assertEqual(raised.exception.values["machine"], stopped)

    def test_created_machine_is_already_not_running(self):
        current = {"id": "machine-one", "state": "created"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_nonpositive_wait_timeout(self):
        module = FakeModule(params(image=None, wait_timeout=0))

        with (
            patch.object(machines, "find_machine") as find,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines.ensure_started(module, {})

        find.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "wait_timeout must be greater than zero",
        )

    def test_stopping_machine_waits_without_stopping_again(self):
        current = {
            "id": "machine-one",
            "instance_id": "instance-one",
            "state": "stopping",
        }
        stopped = {"id": "machine-one", "state": "stopped"}
        module = FakeModule(params(image=None))

        with (
            patch.object(machines, "find_machine", return_value=current),
            patch.object(machines, "api_request") as request,
            patch.object(machines, "wait_for_machine") as wait,
            patch.object(machines, "get_resource", return_value=stopped),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines.ensure_stopped(module, {})

        request.assert_not_called()
        wait.assert_called_once_with(
            {},
            "example",
            "machine-one",
            "stopped",
            60,
            instance_id="instance-one",
        )
        self.assertFalse(raised.exception.values["changed"])

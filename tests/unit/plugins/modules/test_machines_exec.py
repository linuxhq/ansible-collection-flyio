# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import machines_exec
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


def module(check_mode=False, **updates):
    params = {
        "app_name": "example",
        "command": "true",
        "container": None,
        "id": "machine-one",
        "stdin": None,
        "timeout": 30,
    }
    params.update(updates)
    return FakeModule(params, check_mode=check_mode)


class MachinesExecTests(TestCase):
    def test_rejects_empty_command_and_container(self):
        for name in ("command", "container"):
            with (
                self.subTest(name=name),
                patch.object(machines_exec, "AnsibleModule", return_value=module(**{name: " "})),
                patch.object(machines_exec, "post_result") as request,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines_exec.main()

            request.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], f"{name} must not be empty")

    def test_rejects_nonpositive_timeout(self):
        with (
            patch.object(machines_exec, "post_result") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(timeout=0), {})

        request.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "timeout must be greater than zero")

    def test_check_mode_does_not_execute(self):
        with (
            patch.object(machines_exec, "get_resource", return_value={"id": "machine-one"}),
            patch.object(machines_exec, "post_result") as request,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_exec.exec_command(module(check_mode=True), {})

        request.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])

    def test_check_mode_fails_for_missing_machine(self):
        with (
            patch.object(machines_exec, "get_resource", return_value=None),
            patch.object(machines_exec, "post_result") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(check_mode=True), {})

        request.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "Machine 'machine-one' not found in app 'example'")

    def test_check_mode_fails_for_gone_machine(self):
        for state in ("destroyed", "replaced", "migrated"):
            with (
                self.subTest(state=state),
                patch.object(machines_exec, "get_resource", return_value={"id": "machine-one", "state": state}),
                patch.object(machines_exec, "post_result") as request,
                self.assertRaises(ModuleFail) as raised,
            ):
                machines_exec.exec_command(module(check_mode=True), {})

            request.assert_not_called()
            self.assertEqual(raised.exception.values["msg"], "Machine 'machine-one' not found in app 'example'")

    def test_executes_command(self):
        result = {"exit_code": 0, "stderr": "", "stdout": "ready"}

        with (
            patch.object(machines_exec, "post_result", return_value=result) as request,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_exec.exec_command(module(stdin="input"), {})

        request.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one/exec",
            {
                "command": ["/bin/sh", "-c", "true"],
                "stdin": "input",
                "timeout": 30,
            },
            timeout=40,
        )
        self.assertEqual(raised.exception.values["stdout"], "ready")

    def test_fails_on_nonzero_exit(self):
        result = {"exit_code": 1, "stderr": "failed", "stdout": ""}

        with (
            patch.object(machines_exec, "post_result", return_value=result),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(), {})

        self.assertEqual(raised.exception.values["exit_code"], 1)
        self.assertEqual(raised.exception.values["stderr"], "failed")
        self.assertEqual(
            raised.exception.values["msg"],
            "Command failed on Machine 'machine-one' for app 'example'",
        )

    def test_rejects_malformed_response(self):
        for result in (None, ["invalid"], {"exit_code": "0"}, {"exit_code": False}, {"stdout": 1}):
            with (
                self.subTest(result=result),
                patch.object(machines_exec, "post_result", return_value=result),
                self.assertRaises(ModuleFail) as raised,
            ):
                machines_exec.exec_command(module(), {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data while executing a command on "
                "Machine 'machine-one' for app 'example'",
            )

    def test_stdin_is_no_log(self):
        with (
            patch.object(machines_exec, "AnsibleModule", side_effect=RuntimeError) as ansible_module,
            self.assertRaises(RuntimeError),
        ):
            machines_exec.main()

        self.assertTrue(ansible_module.call_args.kwargs["argument_spec"]["stdin"]["no_log"])

    def test_rejects_timeout_above_api_limit(self):
        with (
            patch.object(machines_exec, "post_result") as request,
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(timeout=601), {})

        request.assert_not_called()
        self.assertEqual(raised.exception.values["msg"], "timeout must not exceed 600")

    def test_missing_exit_code_means_success(self):
        with (
            patch.object(machines_exec, "post_result", return_value={"stdout": "ready"}),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_exec.exec_command(module(), {})

        self.assertEqual(raised.exception.values["exit_code"], 0)
        self.assertEqual(raised.exception.values["stdout"], "ready")

    def test_fails_when_terminated_by_signal(self):
        with (
            patch.object(machines_exec, "post_result", return_value={"exit_code": 0, "exit_signal": 9, "stdout": ""}),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(), {})

        self.assertEqual(raised.exception.values["exit_signal"], 9)

    def test_rejects_malformed_exit_signal(self):
        with (
            patch.object(machines_exec, "post_result", return_value={"exit_code": 0, "exit_signal": "9"}),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_exec.exec_command(module(), {})

        self.assertIn("malformed data", raised.exception.values["msg"])

    def test_returns_additional_response_fields(self):
        response = {"exit_code": 0, "stdout": "ok", "duration_ms": 12}

        with (
            patch.object(machines_exec, "post_result", return_value=response),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_exec.exec_command(module(), {})

        self.assertEqual(raised.exception.values["duration_ms"], 12)
        self.assertEqual(raised.exception.values["exit_signal"], 0)
        self.assertEqual(raised.exception.values["stderr"], "")

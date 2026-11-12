# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import apps_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class AppsInfoTests(TestCase):
    def test_info(self):
        app = {"name": "example"}
        module = FakeModule({"name": "example"})

        with (
            patch.object(apps_info, "get_app", return_value=app) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps_info.info(module, {})

        get.assert_called_once_with({}, "example")
        self.assertEqual(raised.exception.values["apps"], [app])

    def test_missing_app_fails(self):
        module = FakeModule({"name": "missing"})

        with (
            patch.object(apps_info, "get_app", return_value=None),
            self.assertRaises(ModuleFail) as raised,
        ):
            apps_info.info(module, {})

        self.assertEqual(raised.exception.values["msg"], "App 'missing' not found")

    def test_lists_apps(self):
        listed = [{"name": "one"}, {"name": "two"}]
        module = FakeModule({"org_slug": "linux&hq"})

        with (
            patch.object(apps_info, "api_request", return_value={"apps": listed}) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps_info.list_resources(module, {})

        get.assert_called_once_with({}, "get", "/apps?org_slug=linux%26hq")
        self.assertEqual(raised.exception.values["apps"], listed)

    def test_lists_every_page_of_apps(self):
        module = FakeModule({"org_slug": "linuxhq"})
        pages = [
            {"apps": [{"name": "one"}], "next_cursor": "page-two"},
            {"apps": [{"name": "two"}], "next_cursor": ""},
        ]

        with (
            patch.object(apps_info, "api_request", side_effect=pages) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps_info.list_resources(module, {})

        self.assertEqual(
            [call.args for call in get.call_args_list],
            [
                ({}, "get", "/apps?org_slug=linuxhq"),
                ({}, "get", "/apps?org_slug=linuxhq&cursor=page-two"),
            ],
        )
        self.assertEqual(raised.exception.values["apps"], [{"name": "one"}, {"name": "two"}])

    def test_rejects_repeated_cursor(self):
        module = FakeModule({"org_slug": "linuxhq"})
        page = {"apps": [{"name": "one"}], "next_cursor": "same"}

        with (
            patch.object(apps_info, "api_request", side_effect=[page, page]) as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            apps_info.list_resources(module, {})

        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while listing apps for organization 'linuxhq'",
        )

    def test_rejects_missing_apps_envelope(self):
        module = FakeModule({"org_slug": "linuxhq"})

        with (
            patch.object(apps_info, "api_request", return_value={}),
            self.assertRaises(ModuleFail) as raised,
        ):
            apps_info.list_resources(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Fly.io API returned malformed data while listing apps for organization 'linuxhq'",
        )

    def test_rejects_whitespace_app_name(self):
        module = FakeModule({"org_slug": "linuxhq"})

        with (
            patch.object(apps_info, "api_request", return_value={"apps": [{"name": " "}]}),
            self.assertRaises(ModuleFail),
        ):
            apps_info.list_resources(module, {})

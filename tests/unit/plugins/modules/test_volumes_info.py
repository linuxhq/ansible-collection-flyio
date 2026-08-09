# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import volumes_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class VolumesInfoTests(TestCase):
    def test_info(self):
        volume = {"id": "vol_one"}
        module = FakeModule({"app_name": "example", "id": "vol_one"})

        with (
            patch.object(volumes_info, "get_resource", return_value=volume) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes_info.info(module, {})

        get.assert_called_once_with(
            {},
            "/apps/example/volumes/vol_one",
            ok_statuses=[404],
            required_field="id",
            expected_value="vol_one",
        )
        self.assertEqual(raised.exception.values["volumes"], [volume])

    def test_missing_volume_fails(self):
        module = FakeModule({"app_name": "example", "id": "missing"})

        with (
            patch.object(volumes_info, "get_resource", return_value=None),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes_info.info(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Volume 'missing' not found in app 'example'",
        )

    def test_lists_volumes(self):
        volumes = [{"id": "one"}, {"id": "two"}]
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(volumes_info, "list_all", return_value=volumes) as list_all,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes_info.list_resources(module, {})

        list_all.assert_called_once_with(
            {}, "/apps/example/volumes", ok_statuses=[404], required_field="id"
        )
        self.assertEqual(raised.exception.values["volumes"], volumes)

    def test_rejects_malformed_documented_fields(self):
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(
                volumes_info,
                "list_all",
                return_value=[{"id": "vol_one", "size_gb": True}],
            ),
            self.assertRaises(ModuleFail) as raised,
        ):
            volumes_info.list_resources(module, {})

        self.assertIn("malformed volume data", raised.exception.values["msg"])

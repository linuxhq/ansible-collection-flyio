# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import volumes
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
)


class FindVolumeTests(TestCase):
    def test_skips_pending_destroy(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "state": "created",
        }

        with patch.object(volumes, "list_all", return_value=[pending, created]):
            result = volumes.find_volume({}, "example", name="data", region="ord")

        self.assertEqual(result, created)

    def test_destroyed_id_is_absent(self):
        destroyed = {"id": "vol_old", "state": "destroyed"}

        with patch.object(volumes, "get_result", return_value=destroyed):
            result = volumes.find_volume({}, "example", volume_id="vol_old")

        self.assertIsNone(result)

    def test_creates_replacement_for_pending_volume(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {"id": "vol_new", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "encrypted": True,
                "id": None,
                "name": "data",
                "region": "ord",
                "size_gb": 1,
                "wait": True,
                "wait_timeout": 60,
            }
        )

        with (
            patch.object(volumes, "list_all", return_value=[pending]),
            patch.object(volumes, "post_result", return_value=created) as post,
            patch.object(volumes, "wait_for_volume", return_value=created),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps/example/volumes",
            {"encrypted": True, "name": "data", "region": "ord", "size_gb": 1},
        )
        self.assertEqual(raised.exception.values["volume"], created)

    def test_deletes_volume(self):
        current = {"id": "vol_one", "state": "created"}
        module = FakeModule(
            {
                "app_name": "example",
                "id": "vol_one",
                "name": None,
                "region": None,
            }
        )

        with (
            patch.object(volumes, "get_result", return_value=current),
            patch.object(volumes, "delete_result") as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example/volumes/vol_one")
        self.assertTrue(raised.exception.values["changed"])

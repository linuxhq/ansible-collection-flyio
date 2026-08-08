# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    authorization_header,
    values_differ,
)


class FlyioUtilsTests(TestCase):
    def test_uses_flyv1_for_fly_machine_tokens(self):
        self.assertEqual(authorization_header("fm2_example"), "FlyV1 fm2_example")
        self.assertEqual(authorization_header("fm1r_example"), "FlyV1 fm1r_example")
        self.assertEqual(
            authorization_header("fo1_example,fm2_example"),
            "FlyV1 fo1_example,fm2_example",
        )

    def test_preserves_explicit_authorization_scheme(self):
        self.assertEqual(authorization_header("FlyV1 fm2_example"), "FlyV1 fm2_example")
        self.assertEqual(authorization_header("Bearer example"), "Bearer example")

    def test_purge_detects_removed_dictionary_keys(self):
        current = {"KEEP": "value", "REMOVE": "value"}

        self.assertFalse(values_differ(current, {"KEEP": "value"}))
        self.assertTrue(values_differ(current, {"KEEP": "value"}, purge=True))
        self.assertTrue(values_differ(current, {}, purge=True))

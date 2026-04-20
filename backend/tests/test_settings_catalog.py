import unittest

from backend.modules.settings.settings_catalog import normalize_value_for_key


class SettingsCatalogTests(unittest.TestCase):
    def test_normalize_bool(self) -> None:
        self.assertEqual(
            normalize_value_for_key("feature.hierarchy_builder.enabled", "YES"),
            "true",
        )

    def test_normalize_int_validation(self) -> None:
        with self.assertRaises(ValueError):
            normalize_value_for_key("orchestration.max_parallel_tasks", "0")

    def test_normalize_json(self) -> None:
        self.assertEqual(
            normalize_value_for_key("orchestration.routing.defaults", '{"fallback":"manager","mode":"capability_based"}'),
            '{"fallback":"manager","mode":"capability_based"}',
        )

    def test_unknown_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_value_for_key("unknown.key", "x")


if __name__ == "__main__":
    unittest.main()

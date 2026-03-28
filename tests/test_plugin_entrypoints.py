import pkgutil
import ast
import unittest
from pathlib import Path


def _iter_plugin_files(package_dir: Path, ignore: set[str]) -> list[Path]:
    module_paths: list[Path] = []
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name in ignore:
            continue
        if module_info.ispkg:
            init_path = package_dir / module_info.name / "__init__.py"
            if init_path.is_file():
                module_paths.append(init_path)
        else:
            module_paths.append(package_dir / f"{module_info.name}.py")
    return sorted(module_paths)


def _module_function_names(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class PluginEntrypointContractsTest(unittest.TestCase):
    def test_alert_plugins_expose_required_entrypoints(self) -> None:
        # Alerts now use a strict contract: config model + typed factory.
        alerts_dir = Path(__file__).resolve().parents[1] / "alerts" / "plugins"
        for module_file in _iter_plugin_files(
            alerts_dir, {"__init__"}
        ):
            fn_names = _module_function_names(module_file)
            self.assertTrue(
                "get_config_model" in fn_names,
                f"{module_file.stem} is missing get_config_model()",
            )
            self.assertTrue(
                "create_instance_plugin" in fn_names,
                f"{module_file.stem} is missing create_instance_plugin(config)",
            )

    def test_bot_plugins_expose_required_entrypoints(self) -> None:
        # Bots are loaded through bots.factory with the same contract shape.
        bots_dir = Path(__file__).resolve().parents[1] / "bots" / "plugins"
        for module_file in _iter_plugin_files(bots_dir, {"__init__"}):
            fn_names = _module_function_names(module_file)
            self.assertTrue(
                "get_config_model" in fn_names,
                f"{module_file.stem} is missing get_config_model()",
            )
            self.assertTrue(
                "create_instance_bot" in fn_names,
                f"{module_file.stem} is missing create_instance_bot(config)",
            )

    def test_lookup_plugins_expose_required_entrypoints(self) -> None:
        # Lookup plugins are loaded through lookup.factory.
        lookup_dir = Path(__file__).resolve().parents[1] / "lookup" / "plugins"
        for module_file in _iter_plugin_files(lookup_dir, {"__init__"}):
            fn_names = _module_function_names(module_file)
            self.assertTrue(
                "get_config_model" in fn_names,
                f"{module_file.stem} is missing get_config_model()",
            )
            self.assertTrue(
                "create_instance_lookup" in fn_names,
                f"{module_file.stem} is missing create_instance_lookup(config)",
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lspp_mcp.config import LsppConfig  # noqa: E402
from lspp_mcp.tools.casegen import (  # noqa: E402
    generate_lsdyna_cases,
    validate_case_generator_integration,
)
from lspp_mcp.variable_maps import default_variable_maps  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _fake_casegen_package(src: Path) -> None:
    root = src / "lsdyna_batch_generator"
    for package in [
        root,
        root / "core",
        root / "services",
    ]:
        (package / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")

    _write(
        root / "core" / "models.py",
        """
        from dataclasses import dataclass, field, asdict
        from enum import Enum

        class DataType(str, Enum):
            INTEGER = "int"
            FLOAT = "float"

        class GenerationMethod(str, Enum):
            EXCEL = "excel"
            RANDOM = "random"
            LHS = "lhs"

        class IntegerRounding(str, Enum):
            ROUND = "round"
            FLOOR = "floor"
            CEIL = "ceil"

        class OutputMode(str, Enum):
            FLAT = "flat"
            SEPARATE_FOLDERS = "separate_folders"

        class ConstraintOperator(str, Enum):
            EQ = "=="

        class ConstraintRightType(str, Enum):
            VALUE = "value"

        @dataclass
        class ParameterTarget:
            parameter_id: str
            alias: str
            keyword: str
            instance_index: int
            block_start_line: int
            relative_line_index: int
            file_line_number: int
            field_index: int
            current_value: str
            source_name: str = ""
            data_type: DataType = DataType.FLOAT
            minimum: float | None = None
            maximum: float | None = None
            group_name: str = "默认分组"

            def to_dict(self):
                data = asdict(self)
                data["data_type"] = self.data_type.value
                return data

            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload)
                payload["data_type"] = DataType(payload.get("data_type", "float"))
                return cls(**payload)

        @dataclass
        class ConstraintRule:
            constraint_id: str = "c1"
            left_alias: str = ""
            operator: ConstraintOperator = ConstraintOperator.EQ
            right_type: ConstraintRightType = ConstraintRightType.VALUE
            right_value: str = "0"
            enabled: bool = True
            description: str = ""
            def to_dict(self): return asdict(self)
            @classmethod
            def from_dict(cls, payload): return cls(**payload)

        @dataclass
        class GeneratorConfig:
            method: GenerationMethod = GenerationMethod.RANDOM
            sample_count: int = 2
            random_seed: int | None = None
            avoid_duplicates: bool = True
            integer_rounding: IntegerRounding = IntegerRounding.ROUND
            excel_path: str = ""
            def to_dict(self):
                data = asdict(self)
                data["method"] = self.method.value
                data["integer_rounding"] = self.integer_rounding.value
                return data
            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload)
                payload["method"] = GenerationMethod(payload.get("method", "random"))
                payload["integer_rounding"] = IntegerRounding(payload.get("integer_rounding", "round"))
                return cls(**payload)

        @dataclass
        class OutputNamingConfig:
            output_dir: str = ""
            output_mode: OutputMode = OutputMode.FLAT
            folder_template: str = "case_{case_id:03d}"
            file_template: str = "{case_name}.k"
            include_index_excel: bool = False
            include_index_csv: bool = True
            copy_support_files: list[str] = field(default_factory=list)
            def to_dict(self):
                data = asdict(self)
                data["output_mode"] = self.output_mode.value
                return data
            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload)
                payload["output_mode"] = OutputMode(payload.get("output_mode", "flat"))
                return cls(**payload)

        @dataclass
        class CaseDefinition:
            case_id: int
            values: dict
            def case_name(self, template="case_{case_id:03d}"):
                return template.format(case_id=self.case_id, **self.values)

        @dataclass
        class AppConfig:
            k_file_path: str = ""
            parameters: list[ParameterTarget] = field(default_factory=list)
            constraints: list[ConstraintRule] = field(default_factory=list)
            generator: GeneratorConfig = field(default_factory=GeneratorConfig)
            output: OutputNamingConfig = field(default_factory=OutputNamingConfig)
            @classmethod
            def from_dict(cls, payload):
                return cls(
                    k_file_path=payload.get("k_file_path", ""),
                    parameters=[ParameterTarget.from_dict(item) for item in payload.get("parameters", [])],
                    constraints=[ConstraintRule.from_dict(item) for item in payload.get("constraints", [])],
                    generator=GeneratorConfig.from_dict(payload.get("generator", {})),
                    output=OutputNamingConfig.from_dict(payload.get("output", {})),
                )
        """,
    )
    _write(
        root / "core" / "parser.py",
        """
        from dataclasses import dataclass
        from pathlib import Path
        @dataclass
        class Document:
            path: str
            lines: list[str]
            def keyword_summary(self):
                return {"*KEYWORD": 1}
        class KFileParser:
            def parse(self, path):
                lines = Path(path).read_text(encoding="utf-8").splitlines()
                return Document(str(path), lines)
        """,
    )
    _write(
        root / "services" / "config_service.py",
        """
        import json
        from pathlib import Path
        from lsdyna_batch_generator.core.models import AppConfig
        class ConfigService:
            def load(self, path):
                return AppConfig.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        """,
    )
    _write(
        root / "services" / "case_generator.py",
        """
        from dataclasses import dataclass
        from lsdyna_batch_generator.core.models import CaseDefinition
        class FakeFrame:
            def __init__(self, rows): self.rows = rows; self.columns = list(rows[0]) if rows else []; self.index = list(range(len(rows)))
            def to_dict(self, orient="records"): return list(self.rows)
        @dataclass
        class GenerationResult:
            cases: list
            dataframe: FakeFrame
            warnings: list
        class CaseGeneratorService:
            def generate_random(self, parameters, config):
                rows = []
                for i in range(config.sample_count):
                    rows.append({p.alias: (p.minimum or 0) + i for p in parameters})
                return GenerationResult([CaseDefinition(i + 1, row) for i, row in enumerate(rows)], FakeFrame(rows), [])
            def generate_lhs(self, parameters, config): return self.generate_random(parameters, config)
            def load_from_excel(self, parameters, excel_path): return self.generate_random(parameters, type("C", (), {"sample_count": 1})())
        """,
    )
    _write(
        root / "services" / "constraint_service.py",
        """
        from dataclasses import dataclass
        @dataclass
        class ConstraintResult:
            dataframe: object
            messages: list
        class ConstraintService:
            def apply_constraints(self, dataframe, constraints):
                return ConstraintResult(dataframe, [])
        """,
    )
    _write(
        root / "services" / "export_service.py",
        """
        from pathlib import Path
        class FakeIndex:
            def __init__(self, records): self.records = records
            def to_dict(self, orient="records"): return list(self.records)
        class ExportService:
            def preview_case_names(self, cases, config, limit=5):
                return [f"case {c.case_id}: folder={c.case_name(config.folder_template)} | file={config.file_template.format(case_name=c.case_name(config.folder_template), case_id=c.case_id, **c.values)}" for c in cases[:limit]]
            def export_cases(self, document, parameters, cases, config):
                out = Path(config.output_dir)
                out.mkdir(parents=True, exist_ok=True)
                records = []
                for case in cases:
                    name = config.file_template.format(case_name=case.case_name(config.folder_template), case_id=case.case_id, **case.values)
                    if not name.endswith(".k"): name += ".k"
                    path = out / name
                    path.write_text("\\n".join(document.lines) + "\\n", encoding="utf-8")
                    records.append({"case_id": case.case_id, "output_path": str(path), **case.values})
                (out / "case_index.csv").write_text("case_id,output_path\\n", encoding="utf-8")
                return FakeIndex(records)
        """,
    )


class CaseGeneratorIntegrationTests(unittest.TestCase):
    def _config(self, root: Path, fake_src: Path) -> LsppConfig:
        return LsppConfig(
            lsprepost_exe="lsprepost.exe",
            workspace_root=root,
            allowed_roots=(root,),
            case_generator_python=sys.executable,
            case_generator_src=fake_src,
            variable_maps=default_variable_maps(),
        )

    def test_validate_case_generator_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_src = root / "fake_src"
            _fake_casegen_package(fake_src)
            result = validate_case_generator_integration(config=self._config(root, fake_src))
            self.assertTrue(result["ok"])
            self.assertIn("ConfigService", result["available_services"])

    def test_generate_lsdyna_cases_uses_external_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_src = root / "fake_src"
            _fake_casegen_package(fake_src)
            k_file = root / "model.k"
            k_file.write_text("*KEYWORD\n*END\n", encoding="utf-8")
            output_dir = root / "cases"
            project_config = root / "project_config.json"
            project_config.write_text(
                json.dumps(
                    {
                        "k_file_path": str(k_file),
                        "parameters": [
                            {
                                "parameter_id": "p1",
                                "alias": "charge",
                                "keyword": "*MAT",
                                "instance_index": 0,
                                "block_start_line": 1,
                                "relative_line_index": 1,
                                "file_line_number": 1,
                                "field_index": 0,
                                "current_value": "1",
                                "data_type": "float",
                                "minimum": 1.0,
                                "maximum": 2.0,
                            }
                        ],
                        "generator": {"method": "random", "sample_count": 2},
                        "output": {
                            "output_dir": str(output_dir),
                            "output_mode": "flat",
                            "folder_template": "case_{case_id:03d}",
                            "file_template": "{case_name}_{charge}.k",
                            "include_index_csv": True,
                            "include_index_excel": False,
                            "copy_support_files": [],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = generate_lsdyna_cases(
                project_config_path=str(project_config),
                overwrite=False,
                config=self._config(root, fake_src),
            )

            self.assertTrue(result["ok"], result["message"])
            self.assertEqual(result["generated_count"], 2)
            self.assertTrue((output_dir / "case_index.csv").exists())
            self.assertEqual(len(list(output_dir.glob("*.k"))), 2)
            self.assertTrue(Path(result["generated_request"]).exists())


if __name__ == "__main__":
    unittest.main()

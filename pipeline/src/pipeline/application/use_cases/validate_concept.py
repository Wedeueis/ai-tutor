"""The structural attester: general conformance + schema validation for any
concept — distinct from the OKF §10 Attested-Computation executor/attester
(attest_computation.py), which attests a *run*, not a document's shape."""

from __future__ import annotations

from dataclasses import dataclass, field

import jsonschema

from pipeline.application.ports.schema_registry import SchemaRegistryPort
from pipeline.domain.concept import Concept
from pipeline.domain.conformance import ConformanceChecker, ConformanceIssue


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[ConformanceIssue] = field(default_factory=list)


class ValidateConcept:
    def __init__(
        self,
        schema_registry: SchemaRegistryPort,
        conformance_checker: ConformanceChecker | None = None,
    ) -> None:
        self._schema_registry = schema_registry
        self._conformance_checker = conformance_checker or ConformanceChecker()

    def run(self, concept: Concept) -> ValidationResult:
        report = self._conformance_checker.check(concept)
        issues = list(report.issues)

        schema = self._schema_registry.get_schema(concept.frontmatter.type)
        if schema is not None:
            validator = jsonschema.Draft202012Validator(schema)
            for error in validator.iter_errors(concept.frontmatter.to_dict()):
                issues.append(ConformanceIssue("schema", error.message))

        return ValidationResult(ok=not issues, issues=issues)

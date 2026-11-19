
"""Checks for relationship validation - is something actually a potential key?"""
import json
import unittest
from agents.investigator.contracts import Coverage, ToolResult, SourceRef
from agents.investigator.relationships import(
    validate_candidate_key,
    validate_file_sample_match,
    validate_document_association,
)

class RelationshipTests(unittest.TestCase):
    def make_result(self, row_count, null_count, distinct_count, coverage_mode="full", examined=None):
        if examined is None:
            examined = row_count
        
        return ToolResult(
            result_id="r_keys",
            component_id="c_patients",
            status="complete",
            inputs=["s_patients"],
            method="table_profile",
            parameters={},
            coverage=Coverage(
                mode=coverage_mode,
                unit="rows",
                examined=examined,
                total=row_count,
                selection="all rows" if coverage_mode == "full"
                          else "sampled rows"
            ),
            measurements={
                "row_count": row_count,
                "columns": {
                    "patient_id": {
                        "null_count": null_count,
                        "distinct_count": distinct_count
                    }
                }
            }
        )
    
    # ----- CANDIDATE KEY TESTS (validate_candidate_key) -----

    def test_supported_candidate_key(self):
        # a column that should be supported as a key
        result = self.make_result(100, 0, 100)
        relationship = validate_candidate_key(result, "patient_id")

        self.assertEqual(relationship["status"], "supported")
        self.assertEqual(relationship["relationship_type"], "candidate_key")
        self.assertEqual(relationship["evidence"]["result_id"], "r_keys")

    def test_rejected_candidate_key(self):
        # a column that should've been rejected as a key
        result = self.make_result(100, 0, 75)
        relationship = validate_candidate_key(result, "patient_id")

        self.assertEqual(relationship["status"], "rejected")

    def test_sampled_key_is_not_confirmed(self):
        # a column that only has measurements of a sample
        # therefore, should have 'insufficient_evidence' status
        result = self.make_result(
            row_count=100,
            null_count=0,
            distinct_count=100,
            coverage_mode="sample",
            examined=100
        )
        # dataset is larger than sample coverage
        result.coverage.total = 1000
        result.validate()
        relationship = validate_candidate_key(result, "patient_id")

        self.assertEqual(
            relationship["status"], "insufficient_evidence"
        )

    def test_candidate_key_missing_evidence(self):
        # checks that function does not infer uniqueness from incomplete measurements
        result = ToolResult(
            result_id="r_incomplete_stats",
            component_id="c_patients",
            status="partial",
            inputs=["s_patients"],
            method="table_profile",
            parameters={},
            coverage=Coverage(
                mode="full",
                unit="rows",
                examined=100,
                total=100,
                selection="all rows"
            ),
            measurements={
                "row_count": 100,
                "columns": {
                    "patient_id": {
                        "null_count": 0
                        # distinct_count is missing
                    }
                }
            },
            limitations=["Distinct counts were not calculated."]
        )
        relationship = validate_candidate_key(result, "patient_id")

        self.assertEqual(relationship["status"], "insufficient_evidence")

    def test_candidate_key_inconsistent_counts(self):
        # incase number of nulls or distincts > number of rows
        # SHOULD be flagged as insufficient_evidence
        result = self.make_result(
            row_count=100,
            null_count=0,
            distinct_count=120
        )
        relationship = validate_candidate_key(result, "patient_id")

        self.assertEqual(relationship["status"], "insufficient_evidence")

    # ----- FILENAME MATCHING TESTS (validate_file_sample_match) -----

    def test_matching_sample_filenames(self):
        # when filenames match
        csv = SourceRef("s_csv", "tables/patient_001.csv", "csv", 100, 1)
        image = SourceRef("s_image", "images/patient_001.png", "png", 500, 1)
        match = validate_file_sample_match(csv, image)

        self.assertEqual(match["status"], "candidate")
        self.assertEqual(match["relationship_type"], "file_sample_match")
        self.assertEqual(match["evidence"]["source_ids"], ["s_csv", "s_image"])

    def test_nonmatching_sample_filenames(self):
        # when filenames do not match
        csv = SourceRef("s_csv", "patient_001.csv", "csv", 100, 1)
        image = SourceRef("s_image", "patient_002.png", "png", 500, 1)
        match = validate_file_sample_match(csv, image)

        self.assertEqual(match["status"], "no_match")

    def test_generic_filenames_are_not_matches(self):
        # ensure generic filenames are excluded
        csv = SourceRef("s_csv", "tables/data.csv", "csv", 100, 1)
        image = SourceRef("s_image", "images/data.png", "png", 500, 1)
        match = validate_file_sample_match(csv, image)

        self.assertEqual(match["status"], "insufficient_evidence")

    def test_cannot_match_source_with_itself(self):
        # checks source id to make sure a file does not match with itself
        source = SourceRef("s_csv", "patient_001.csv", "csv", 100, 1)

        with self.assertRaises(ValueError):
            validate_file_sample_match(source, source)

    def test_matching_filenames_remain_candidates(self):
        source_a = SourceRef("s_png", "images/patient_001.png", "png", 500, 1)
        source_b = SourceRef("s_tiff", "images/patient_001.tiff", "tiff", 2000, 1)

        relationship = validate_file_sample_match(source_a, source_b)

        self.assertEqual(
            relationship["status"],
            "candidate"
        )
        self.assertIn("Matching filename stems", relationship["reason"])

    # ----- DOCUMENT-TO-SOURCE REFERENCE TESTS (validate_document_association) -----

    def test_document_references_target(self):
        # check for when a document does reference a target
        document = SourceRef(
            "s_readme", "README.md", "md", 200, 1
        )
        target = SourceRef(
            "s_patients", "tables/patients.csv", "csv", 500, 1
        )
        result = validate_document_association(
            document,
            target,
            ["tables/patients.csv", "tables/measurements.csv"]
        )

        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["relationship_type"], "documentation_association")
        self.assertEqual(result["evidence"]["target_source_id"], "s_patients")

    def test_document_does_not_reference_target(self):
        # check for when a document does NOT reference a target
        document = SourceRef("s_readme", "README.md", "md", 200, 1)
        target = SourceRef("s_image", "images/sample_001.png", "png", 500, 1)
        result = validate_document_association(
            document,
            target,
            ["tables/patients.csv", "tables/measurements.csv"]
        )

        self.assertEqual(result["status"], "no_match")

    def test_document_without_references(self):
        # when document has no references
        document = SourceRef(
            "s_readme", "README.md", "md", 200, 1
        )
        target = SourceRef(
            "s_patients", "patients.csv", "csv", 500, 1
        )
        result = validate_document_association(
            document,
            target,
            []
        )

        self.assertEqual(result["status"], "insufficient_evidence")

    def test_document_basename_is_not_enough(self):
        # when only filename is provided
        document = SourceRef("s_readme", "README.md", "md", 200, 1)
        target = SourceRef("s_patients", "tables/patients.csv", "csv", 500, 1)
        result = validate_document_association(
            document,
            target,
            ["patients.csv"]
        )

        # bare filename does not establish which path it refers to.
        self.assertEqual(result["status"], "no_match")

    def test_document_association_requires_target_reference(self):
        # associated target dataset should be in referenced_paths
        document = SourceRef("s_readme", "README.md", "md", 200, 1)
        target = SourceRef("s_measurements", "tables/measurements.csv", "csv", 1000, 1)

        relationship = validate_document_association(document, target, ["tables/patients.csv"])

        self.assertEqual(relationship["status"], "no_match")
        self.assertEqual(
            relationship["evidence"]["target_source_id"],
            "s_measurements"
        )
    
    def test_relationship_results_json_round_trip(self):
        # checking that all outputs work with JSON

        # candidate key evidence
        key_result = self.make_result(100, 0, 100)
        key_relationship = validate_candidate_key(key_result, "patient_id")

        # file/sample matching evidence
        csv = SourceRef("s_csv", "patient_001.csv", "csv", 100, 1)
        image = SourceRef("s_image", "patient_001.png", "png", 500, 1)
        file_relationship = validate_file_sample_match(csv, image)

        # documentation association evidence
        document = SourceRef("s_readme", "README.md", "md", 200, 1)
        doc_relationship = validate_document_association(document, csv, ["patient_001.csv"])

        relationships = [
            key_relationship,
            file_relationship,
            doc_relationship
        ]

        for relationship in relationships:
            with self.subTest(
                relationship=relationship["relationship_type"]
            ):
                serialized = json.dumps(
                    relationship,
                    allow_nan=False
                )
                restored = json.loads(serialized)

                self.assertEqual(restored, relationship)
                self.assertIn("relationship_type", restored)
                self.assertIn("status", restored)
                self.assertIn("evidence", restored)
                self.assertIn("reason", restored)
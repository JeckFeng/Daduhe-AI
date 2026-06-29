"""Unit tests for extraction merge logic — no external deps needed."""

from src.models import Entity, EntityExtractionResult, Relationship
from src.extraction.pipeline import merge_extraction_results


def _make_entity(name: str, etype: str, desc: str, source_id: str = "") -> Entity:
    return Entity(entity_name=name, entity_type=etype, entity_description=desc)


def _make_rel(src: str, tgt: str, keywords: str, desc: str) -> Relationship:
    return Relationship(source=src, target=tgt, keywords=keywords, description=desc)


class TestMergeEntities:
    def test_merges_same_name_keeps_longest_description(self):
        """Two entities with same name → merged into one, longest desc kept."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "混凝土结构表面的开裂缺陷"),
                ],
                relationships=[],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "短的描述"),
                ],
                relationships=[],
            ),
        ]
        merged = merge_extraction_results(results)

        assert len(merged.entities) == 1
        assert merged.entities[0].entity_description == "混凝土结构表面的开裂缺陷"

    def test_keeps_unique_entities_from_different_chunks(self):
        """Entities with different names are all kept."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "开裂缺陷"),
                ],
                relationships=[],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("渗漏", "DefectType", "渗漏缺陷"),
                ],
                relationships=[],
            ),
        ]
        merged = merge_extraction_results(results)

        assert len(merged.entities) == 2
        names = {e.entity_name for e in merged.entities}
        assert names == {"裂缝", "渗漏"}

    def test_dedup_exact_same_description(self):
        """Entities with same name AND same description → dedup to one."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "相同的描述文本"),
                ],
                relationships=[],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "相同的描述文本"),
                ],
                relationships=[],
            ),
        ]
        merged = merge_extraction_results(results)

        assert len(merged.entities) == 1

    def test_case_insensitive_entity_name_match(self):
        """Entity names match case-insensitively (handles English mixed case)."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("DL/T 2628-2023", "NormClause", "规范A条款"),
                ],
                relationships=[],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity(
                        "dl/t 2628-2023",
                        "NormClause",
                        "更长的规范描述，包含更多细节信息B",
                    ),
                ],
                relationships=[],
            ),
        ]
        merged = merge_extraction_results(results)
        assert len(merged.entities) == 1

    def test_entity_type_kept_from_longest_description(self):
        """When merging, entity_type is taken from the entry with longest description."""
        results = [
            EntityExtractionResult(
                entities=[_make_entity("裂缝", "DefectType", "短")],
                relationships=[],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "Other", "这个描述更长所以类型应该用Other")
                ],
                relationships=[],
            ),
        ]
        merged = merge_extraction_results(results)
        assert merged.entities[0].entity_type == "Other"


class TestMergeRelationships:
    def test_dedup_identical_relationships(self):
        """Same source/target/keywords → dedup to one."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "d"),
                    _make_entity("DL/T 2628", "NormClause", "d"),
                ],
                relationships=[
                    _make_rel("裂缝", "DL/T 2628", "标准", "判定标准"),
                ],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "d"),
                    _make_entity("DL/T 2628", "NormClause", "d"),
                ],
                relationships=[
                    _make_rel("裂缝", "DL/T 2628", "标准", "判定标准"),
                ],
            ),
        ]
        merged = merge_extraction_results(results)
        assert len(merged.relationships) == 1

    def test_keeps_unique_relationships(self):
        """Different relationships are all kept."""
        results = [
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "d"),
                    _make_entity("DL/T 2628", "NormClause", "d"),
                ],
                relationships=[
                    _make_rel("裂缝", "DL/T 2628", "标准", "判定标准"),
                ],
            ),
            EntityExtractionResult(
                entities=[
                    _make_entity("裂缝", "DefectType", "d"),
                    _make_entity("帷幕灌浆", "Treatment", "d"),
                ],
                relationships=[
                    _make_rel("裂缝", "帷幕灌浆", "处理措施", "灌浆处理"),
                ],
            ),
        ]
        merged = merge_extraction_results(results)
        assert len(merged.relationships) == 2

    def test_merge_same_relationship_keeps_longest_description(self):
        """Same source/target → merge, keep longest description."""
        r1 = EntityExtractionResult(
            entities=[
                _make_entity("裂缝", "DefectType", "d"),
                _make_entity("DL/T 2628", "NormClause", "d"),
            ],
            relationships=[
                _make_rel("裂缝", "DL/T 2628", "标准", "短"),
            ],
        )
        r2 = EntityExtractionResult(
            entities=[
                _make_entity("裂缝", "DefectType", "d"),
                _make_entity("DL/T 2628", "NormClause", "d"),
            ],
            relationships=[
                _make_rel("裂缝", "DL/T 2628", "标准,判定", "更长的描述内容"),
            ],
        )
        merged = merge_extraction_results([r1, r2])
        assert len(merged.relationships) == 1
        assert merged.relationships[0].description == "更长的描述内容"
        assert "标准" in merged.relationships[0].keywords

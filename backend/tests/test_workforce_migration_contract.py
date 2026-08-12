"""Contract tests for the workforce domain migration (e8a1c2d3f4b5).

This test verifies that the migration adheres to PostgreSQL compatibility requirements
and follows proper ownership strategies.
"""

import ast
import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "e8a1c2d3f4b5_workforce_domain_foundation.py"
)


def test_migration_file_exists():
    """Verify migration file exists at expected location."""
    assert MIGRATION_PATH.exists(), f"Migration file not found at {MIGRATION_PATH}"


def test_no_sqlite_uuid_generation():
    """Verify no SQLite-specific UUID generation (randomblob/hex) is used."""
    content = MIGRATION_PATH.read_text()

    # Check for SQLite-specific functions
    assert "randomblob" not in content.lower(), (
        "Found 'randomblob' - use Python uuid.uuid4() for PostgreSQL compatibility"
    )

    assert "hex(" not in content.lower() or "hex(randomblob" not in content.lower(), (
        "Found 'hex(' with randomblob - use Python uuid.uuid4() for PostgreSQL compatibility"
    )


def test_no_first_user_ownership_pattern():
    """Verify migration doesn't assign all skills to first user by created_at."""
    content = MIGRATION_PATH.read_text()

    # Look for the problematic pattern of getting first user
    re.compile(
        r"ORDER\s+BY\s+created_at\s+LIMIT\s+1.*first.*user",
        re.IGNORECASE | re.DOTALL,
    )

    # Check within a reasonable window (200 chars) around ORDER BY
    for match in re.finditer(r"ORDER\s+BY\s+created_at\s+LIMIT\s+1", content, re.IGNORECASE):
        context_start = max(0, match.start() - 100)
        context_end = min(len(content), match.end() + 100)
        context = content[context_start:context_end].lower()

        # If we're selecting from users table and assigning to first user, fail
        if "users" in context and ("first" in context or "skill" in context):
            pytest.fail(
                f"Found first-user ownership pattern at position {match.start()}. "
                "Skills should be owned by agents that reference them, not arbitrary first user."
            )


def test_no_purpose_column_in_skill_packs_select():
    """Verify skill_packs SELECT doesn't include non-existent 'purpose' column."""
    content = MIGRATION_PATH.read_text()

    # Extract SQL query strings more precisely
    sql_queries = []
    sql_queries.extend(re.findall(r'text\(\s*"""(.*?)"""\s*\)', content, re.DOTALL))
    sql_queries.extend(re.findall(r"text\(\s*'''(.*?)'''\s*\)", content, re.DOTALL))
    sql_queries.extend(re.findall(r'text\(\s*"([^"]+)"\s*\)', content, re.DOTALL))
    sql_queries.extend(re.findall(r"text\(\s*'([^']+)'\s*\)", content, re.DOTALL))

    # Check queries that involve skill_packs table
    for query in sql_queries:
        if re.search(r"FROM\s+skill_packs", query, re.IGNORECASE):
            # Extract the SELECT clause
            select_match = re.search(
                r"SELECT\s+(.*?)\s+FROM\s+skill_packs", query, re.IGNORECASE | re.DOTALL
            )
            if select_match:
                columns = select_match.group(1)
                # Check if 'purpose' appears as a column name
                if re.search(r"\bpurpose\b", columns, re.IGNORECASE):
                    raise AssertionError(
                        "Found 'purpose' column in skill_packs SELECT. "
                        "SkillPack model has no 'purpose' column - use description instead."
                    )


def test_uses_python_uuid_generation():
    """Verify migration uses Python uuid.uuid4() for ID generation."""
    content = MIGRATION_PATH.read_text()

    # Should import uuid
    assert "import uuid" in content, "Migration should import uuid module"

    # Should use uuid.uuid4()
    assert "uuid.uuid4()" in content, (
        "Migration should use uuid.uuid4() for PostgreSQL-compatible UUID generation"
    )


def test_uses_postgresql_boolean_syntax():
    """Verify boolean values use 'true'/'false' not '1'/'0'."""
    content = MIGRATION_PATH.read_text()

    # Look for SQL INSERT/UPDATE statements with boolean columns
    # Common boolean columns: is_published, is_active, enabled, requires_approval
    boolean_columns = ["is_published", "is_active", "enabled", "requires_approval"]

    # Find SQL statements
    for node in ast.walk(ast.parse(content)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value.strip()

            if "INSERT" in sql.upper() or "UPDATE" in sql.upper():
                for col in boolean_columns:
                    if col in sql:
                        # Check if we're setting it to integer 1/0 instead of boolean
                        # Pattern: column_name, value, value could be 1 or 0
                        pattern = rf"{col}['\"]?\s*,?\s*(?:VALUES|SET).*?[\(,\s]([01])[\),\s]"
                        if re.search(pattern, sql, re.IGNORECASE):
                            raise AssertionError(
                                f"Found integer (0/1) for boolean column '{col}'. "
                                "Use 'true'/'false' for PostgreSQL compatibility."
                            )


def test_has_ownership_strategy_documentation():
    """Verify migration documents the ownership strategy."""
    content = MIGRATION_PATH.read_text()

    # Should have a comment explaining ownership strategy
    doc_keywords = ["ownership", "owner", "strategy"]
    content[: content.find("def upgrade()")]

    # Check for explanation in comments or docstrings near data migration
    data_migration_section = content[content.find("# Data migrations") :]

    has_documentation = any(
        keyword in data_migration_section.lower()[:500] for keyword in doc_keywords
    )

    assert has_documentation, (
        "Migration should document ownership strategy for migrated skills. "
        "Add a comment explaining how skill ownership is determined."
    )


def test_idempotent_skill_creation():
    """Verify skill creation checks for existing records before inserting."""
    content = MIGRATION_PATH.read_text()

    # Should check for existing skills before inserting
    assert "existing_skill" in content.lower() or "SELECT id FROM skills" in content, (
        "Migration should check if skills already exist (idempotency)"
    )


def test_idempotent_tool_creation():
    """Verify tool creation checks for existing records before inserting."""
    content = MIGRATION_PATH.read_text()

    # Should check for existing tools before inserting
    assert "existing" in content.lower() and "tool_definitions" in content, (
        "Migration should check if tools already exist (idempotency)"
    )


def test_idempotent_agent_skill_assignments():
    """Verify agent_skill_assignments checks for existing records."""
    content = MIGRATION_PATH.read_text()

    # Should check for existing assignments before inserting
    assert (
        "existing_assignment" in content.lower()
        or "SELECT id FROM agent_skill_assignments" in content
    ), "Migration should check if agent_skill_assignments already exist (idempotency)"


def test_uses_current_timestamp_for_postgresql():
    """Verify uses CURRENT_TIMESTAMP instead of SQLite datetime('now')."""
    content = MIGRATION_PATH.read_text()

    # Check for SQLite-specific datetime function
    if "datetime('now')" in content:
        raise AssertionError(
            "Found datetime('now') - use CURRENT_TIMESTAMP for PostgreSQL compatibility"
        )


if __name__ == "__main__":
    # Allow running tests directly without pytest
    import sys

    test_functions = [
        test_migration_file_exists,
        test_no_sqlite_uuid_generation,
        test_no_first_user_ownership_pattern,
        test_no_purpose_column_in_skill_packs_select,
        test_uses_python_uuid_generation,
        test_uses_postgresql_boolean_syntax,
        test_has_ownership_strategy_documentation,
        test_idempotent_skill_creation,
        test_idempotent_tool_creation,
        test_idempotent_agent_skill_assignments,
        test_uses_current_timestamp_for_postgresql,
    ]

    passed = 0
    failed = 0
    errors = []

    print("Running migration contract tests...\n")

    for test_func in test_functions:
        test_name = test_func.__name__
        try:
            test_func()
            print(f"✓ {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_name}: {e}")
            failed += 1
            errors.append((test_name, str(e)))
        except Exception as e:
            print(f"✗ {test_name}: ERROR - {e}")
            failed += 1
            errors.append((test_name, f"ERROR: {e}"))

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")

    if errors:
        print("\nFailure details:")
        for test_name, error_msg in errors:
            print(f"\n{test_name}:")
            print(f"  {error_msg}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)

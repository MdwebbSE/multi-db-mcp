"""Unit tests for validate_sql_query function."""
import pytest
from db import validate_sql_query


class TestValidateSqlQuery:
    """Tests for the validate_sql_query function."""

    def test_empty_query_raises_error(self):
        """Empty query should raise ValueError."""
        with pytest.raises(ValueError, match="SQL query cannot be empty"):
            validate_sql_query("")

    def test_whitespace_only_query_raises_error(self):
        """Whitespace-only query should raise ValueError."""
        with pytest.raises(ValueError, match="SQL query cannot be empty"):
            validate_sql_query("   ")

    def test_valid_select_query(self):
        """Valid SELECT query should not raise error."""
        # Should not raise any exception
        validate_sql_query("SELECT * FROM users WHERE id = 1")
        validate_sql_query("SELECT name, email FROM users WHERE status = 'active'")
        validate_sql_query("SELECT COUNT(*) FROM orders")

    def test_valid_select_with_and_or(self):
        """Valid SELECT with AND/OR should not raise error."""
        # These are legitimate uses of AND/OR in WHERE clauses
        validate_sql_query("SELECT * FROM users WHERE status = 'active' AND role = 'admin'")
        validate_sql_query("SELECT * FROM users WHERE id = 1 OR status = 'pending'")

    def test_union_select_injection_detected(self):
        """UNION SELECT injection should be detected."""
        with pytest.raises(ValueError, match="UNION SELECT injection attempt detected"):
            validate_sql_query("SELECT * FROM users UNION SELECT * FROM admin")

    def test_union_all_select_injection_detected(self):
        """UNION ALL SELECT injection should be detected."""
        with pytest.raises(ValueError, match="UNION SELECT injection attempt detected"):
            validate_sql_query("SELECT * FROM users UNION ALL SELECT password FROM admin")

    def test_classic_sql_injection_detected(self):
        """Classic SQL injection 'OR '1'='1' should be detected."""
        with pytest.raises(ValueError, match="SQL injection attempt detected"):
            validate_sql_query("SELECT * FROM users WHERE name = '' OR '1'='1'")

    def test_numeric_or_injection_detected(self):
        """Numeric OR injection should be detected."""
        # This is caught by the tautology OR pattern
        with pytest.raises(ValueError, match="Tautology OR injection detected"):
            validate_sql_query("SELECT * FROM users WHERE id = 1 OR 1=1")

    def test_tautology_or_injection_detected(self):
        """Tautology OR injection should be detected."""
        with pytest.raises(ValueError, match="Tautology OR injection detected"):
            validate_sql_query("SELECT * FROM users WHERE id = 1 OR 1 = 1")

    def test_stacked_queries_detected(self):
        """Stacked queries should be detected."""
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; DROP TABLE users")

    def test_drop_statement_after_semicolon_detected(self):
        """DROP statement after semicolon should be detected."""
        # Caught by stacked queries check first
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; DROP TABLE users")

    def test_delete_statement_after_semicolon_detected(self):
        """DELETE statement after semicolon should be detected."""
        # Caught by stacked queries check first
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; DELETE FROM users")

    def test_insert_statement_after_semicolon_detected(self):
        """INSERT statement after semicolon should be detected."""
        # Caught by stacked queries check first
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; INSERT INTO users VALUES (1, 'test')")

    def test_update_statement_after_semicolon_detected(self):
        """UPDATE statement after semicolon should be detected."""
        # Caught by stacked queries check first
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; UPDATE users SET name = 'hacked'")

    def test_query_with_comments(self):
        """Query with comments should be validated correctly."""
        # Should not raise error - comments are stripped
        validate_sql_query("SELECT * FROM users -- comment")

    def test_query_with_block_comments(self):
        """Query with block comments should be validated correctly."""
        # Should not raise error - block comments are stripped
        validate_sql_query("SELECT * FROM users /* comment */ WHERE id = 1")

    def test_exec_statement_detected(self):
        """EXEC/EXECUTE statement should be detected."""
        # Caught by stacked queries check first
        with pytest.raises(ValueError, match="Multiple statements in a single query are not allowed"):
            validate_sql_query("SELECT * FROM users; EXEC sp_executesql")

    def test_valid_query_with_or_in_string(self):
        """Valid query with OR in string literal should not raise error."""
        # OR in a string literal is fine
        validate_sql_query("SELECT * FROM users WHERE name = 'John OR Jane'")

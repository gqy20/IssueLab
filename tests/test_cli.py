"""Tests for CLI tools."""

import json
import tempfile
from pathlib import Path

from issuelab.cli.mentions import parse_github_mentions


class TestParseMentions:
    """Tests for mention parsing."""

    def test_single_mention(self):
        """Test parsing single mention."""
        text = "@alice please review"
        mentions = parse_github_mentions(text)
        assert mentions == ["alice"]

    def test_multiple_mentions(self):
        """Test parsing multiple mentions."""
        text = "@alice @bob @charlie"
        mentions = parse_github_mentions(text)
        assert mentions == ["alice", "bob", "charlie"]

    def test_duplicate_mentions(self):
        """Test deduplication."""
        text = "@alice @bob @alice @charlie @bob"
        mentions = parse_github_mentions(text)
        assert mentions == ["alice", "bob", "charlie"]

    def test_mention_with_hyphens(self):
        """Test usernames with hyphens."""
        text = "@user-name @test-user-123"
        mentions = parse_github_mentions(text)
        assert mentions == ["user-name", "test-user-123"]

    def test_invalid_mentions(self):
        """Test invalid mention patterns."""
        text = "@-invalid @invalid- @123"
        mentions = parse_github_mentions(text)
        # 正则会匹配 @-invalid 的 invalid 和 @123 的 123
        # GitHub 的实际行为也是这样的
        assert mentions == ["invalid", "123"]

    def test_empty_text(self):
        """Test empty input."""
        assert parse_github_mentions("") == []
        assert parse_github_mentions(None) == []

    def test_no_mentions(self):
        """Test text without mentions."""
        text = "This is a normal text without any mentions"
        mentions = parse_github_mentions(text)
        assert mentions == []

    def test_mention_in_markdown(self):
        """Test mentions in markdown context."""
        text = """
        # Issue Title

        @alice can you review this?

        ```python
        # This @bob is in code, but will be matched
        print("test")
        ```

        cc @charlie
        """
        mentions = parse_github_mentions(text)
        assert "alice" in mentions
        assert "bob" in mentions
        assert "charlie" in mentions


class TestMentionsCLI:
    """Tests for mentions CLI."""

    def test_cli_csv_output(self, capsys):
        """Test CSV output format (default)."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob"])
        assert result == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == "alice,bob"

    def test_cli_json_output(self, capsys):
        """Test JSON output format."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob", "--output", "json"])
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["mentions"] == ["alice", "bob"]
        assert output["count"] == 2

    def test_cli_text_output(self, capsys):
        """Test text output format."""
        from issuelab.cli.mentions import main

        result = main(["--issue-body", "@alice @bob", "--output", "text"])
        assert result == 0

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines == ["alice", "bob"]

    def test_cli_no_input(self, capsys):
        """Test error on no input."""
        from issuelab.cli.mentions import main

        result = main([])
        assert result == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestParseAgentsArg:
    """Tests for parse_agents_arg function."""

    def test_comma_separated(self):
        """Test comma-separated format."""
        from issuelab.__main__ import parse_agents_arg

        result = parse_agents_arg("echo,test,moderator")
        assert result == ["echo", "test", "moderator"]

    def test_space_separated(self):
        """Test space-separated format."""
        from issuelab.__main__ import parse_agents_arg

        result = parse_agents_arg("echo test moderator")
        assert result == ["echo", "test", "moderator"]

    def test_json_array(self):
        """Test JSON array format."""
        from issuelab.__main__ import parse_agents_arg

        result = parse_agents_arg('["echo", "test"]')
        assert result == ["echo", "test"]

    def test_mixed_case(self):
        """Test that results are lowercased."""
        from issuelab.__main__ import parse_agents_arg

        result = parse_agents_arg("Echo,TEST,Moderator")
        assert result == ["echo", "test", "moderator"]

    def test_whitespace_handling(self):
        """Test whitespace is trimmed."""
        from issuelab.__main__ import parse_agents_arg

        result = parse_agents_arg("  echo , test , moderator  ")
        assert result == ["echo", "test", "moderator"]


class TestDispatch:
    """Tests for dispatch functionality."""

    def test_load_empty_registry(self):
        """Test loading from non-existent directory."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "non_existent"
            registry = load_registry(non_existent)
            assert registry == {}

    def test_load_valid_registry(self):
        """Test loading valid registry files."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)

            # Create test agent directory with agent.yml
            alice_dir = agents_dir / "alice"
            alice_dir.mkdir()
            config_file = alice_dir / "agent.yml"
            config_file.write_text("""
owner: alice
repository: alice/IssueLab
triggers:
  - "@alice"
enabled: true
""")

            registry = load_registry(agents_dir)
            assert "alice" in registry
            assert registry["alice"]["owner"] == "alice"
            assert registry["alice"]["repository"] == "alice/IssueLab"

    def test_load_disabled_agent(self):
        """Test that disabled agents are not loaded."""
        from issuelab.cli.dispatch import load_registry

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir)

            # Create test agent directory with agent.yml
            bob_dir = agents_dir / "bob"
            bob_dir.mkdir()
            config_file = bob_dir / "agent.yml"
            config_file.write_text("""
owner: bob
repository: bob/IssueLab
triggers:
  - "@bob"
enabled: false
""")

            registry = load_registry(agents_dir)
            assert "bob" not in registry

    def test_match_triggers(self):
        """Test trigger matching."""
        from issuelab.cli.dispatch import match_triggers

        registry = {
            "alice": {"owner": "alice", "repository": "alice/IssueLab", "triggers": ["@alice"]},
            "bob": {"owner": "bob", "repository": "bob/IssueLab", "triggers": ["@bob", "@bob-cv"]},
            "carol": {"owner": "carol", "repository": "carol/IssueLab"},
        }

        # Test direct match
        matched = match_triggers(["alice"], registry)
        assert len(matched) == 1
        assert matched[0]["owner"] == "alice"

        # Test multiple matches
        matched = match_triggers(["alice", "bob"], registry)
        assert len(matched) == 2

        # Test no match
        matched = match_triggers(["charlie"], registry)
        assert len(matched) == 0

        # Test default match
        matched = match_triggers(["carol"], registry)
        assert len(matched) == 1
        assert matched[0]["owner"] == "carol"


class TestDispatchCLI:
    """Tests for dispatch CLI mention parsing."""

    def test_parse_json_mentions(self, monkeypatch):
        """Test parsing JSON format mentions."""
        from issuelab.cli.dispatch import main

        # Mock environment
        monkeypatch.setenv("GITHUB_APP_ID", "fake_app_id")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake_private_key")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty agents directory
            agents_dir = Path(tmpdir)
            agents_dir.mkdir(exist_ok=True)

            # Should handle JSON format
            result = main(
                [
                    "--mentions",
                    '["alice", "bob"]',
                    "--agents-dir",
                    str(agents_dir),
                    "--source-repo",
                    "test/repo",
                    "--issue-number",
                    "1",
                ]
            )

            # Returns 0 even with no matches (no agents to dispatch to)
            assert result == 0

    def test_parse_csv_mentions(self, monkeypatch):
        """Test parsing CSV format mentions."""
        from issuelab.cli.dispatch import main

        # Mock environment
        monkeypatch.setenv("GITHUB_APP_ID", "fake_app_id")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake_private_key")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty agents directory
            agents_dir = Path(tmpdir)
            agents_dir.mkdir(exist_ok=True)

            # Should handle CSV format
            result = main(
                [
                    "--mentions",
                    "alice,bob",
                    "--agents-dir",
                    str(agents_dir),
                    "--source-repo",
                    "test/repo",
                    "--issue-number",
                    "1",
                ]
            )

            # Returns 0 even with no matches (no agents to dispatch to)
            assert result == 0

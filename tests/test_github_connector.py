"""Tests for github_connector.py"""
import pytest
from unittest.mock import Mock
from mcp.github_connector import GitHubConnector

@pytest.fixture
def mock_event_bus():
    bus = Mock()
    bus.emit = Mock(return_value="github-event-id-789")
    return bus

@pytest.fixture
def github_connector(mock_event_bus):
    return GitHubConnector(event_bus_module=mock_event_bus)

class TestGitHubConnectorPRMerged:
    def test_pr_merged_emits_event(self, github_connector, mock_event_bus):
        payload = {"pull_request_id": "pr-123", "pull_request_number": 42, "repository_name": "romariobc/nerve-layer", "merged_at": "2026-06-27T15:00:00Z", "merged_by": "developer"}
        event_id = github_connector.on_pr_merged(payload)
        assert event_id == "github-event-id-789"
        mock_event_bus.emit.assert_called_once()

    def test_pr_merged_payload_structure(self, github_connector, mock_event_bus):
        payload = {"pull_request_id": "pr-456", "pull_request_number": 99, "repository_name": "org/repo", "merged_at": "2026-06-27T16:00:00Z", "merged_by": "reviewer"}
        github_connector.on_pr_merged(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["name"] == "pr.merged"
        assert emitted_event["source"] == "github"

    def test_pr_merged_with_optional_fields(self, github_connector, mock_event_bus):
        payload = {"pull_request_id": "pr-789", "pull_request_number": 50, "repository_name": "my-org/my-repo", "merged_at": "2026-06-27T17:00:00Z", "merged_by": "tech-lead", "branch": "feature/new", "target_branch": "main", "title": "Add connector", "commit_count": 8, "url": "https://github.com/my-org/my-repo/pull/50"}
        github_connector.on_pr_merged(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "branch" in emitted_event["payload"]

    def test_pr_merged_auto_timestamp(self, github_connector, mock_event_bus):
        payload = {"pull_request_id": "pr-101", "pull_request_number": 10, "repository_name": "test/repo", "merged_by": "user"}
        github_connector.on_pr_merged(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "merged_at" in emitted_event["payload"]

    def test_pr_merged_different_repositories(self, github_connector, mock_event_bus):
        repos = ["romariobc/project-studio", "romariobc/context-adapter", "romariobc/nerve-layer"]
        for i, repo in enumerate(repos):
            payload = {"pull_request_id": f"pr-{i}", "pull_request_number": i + 1, "repository_name": repo, "merged_at": "2026-06-27T18:00:00Z", "merged_by": "dev"}
            github_connector.on_pr_merged(payload)
        assert mock_event_bus.emit.call_count == 3

class TestGitHubConnectorPush:
    def test_push_emits_event(self, github_connector, mock_event_bus):
        payload = {"repository_name": "romariobc/nerve-layer", "branch": "Romir/p1-github-connector", "pushed_at": "2026-06-27T19:00:00Z", "commit_count": 3}
        event_id = github_connector.on_push(payload)
        assert event_id == "github-event-id-789"

    def test_push_payload_structure(self, github_connector, mock_event_bus):
        payload = {"repository_name": "org/code", "branch": "main", "pushed_at": "2026-06-27T20:00:00Z", "commit_count": 5}
        github_connector.on_push(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["name"] == "code.pushed"
        assert emitted_event["source"] == "github"

    def test_push_with_optional_fields(self, github_connector, mock_event_bus):
        payload = {"repository_name": "team/monorepo", "branch": "feature/large", "pushed_at": "2026-06-27T21:00:00Z", "commit_count": 20, "pushed_by": "senior-dev", "commits": ["sha1", "sha2", "sha3"], "url": "https://github.com/team/monorepo/tree/feature/large", "is_default_branch": False}
        github_connector.on_push(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "pushed_by" in emitted_event["payload"]

    def test_push_to_default_branch(self, github_connector, mock_event_bus):
        payload = {"repository_name": "prod/api", "branch": "main", "pushed_at": "2026-06-27T22:00:00Z", "commit_count": 2, "is_default_branch": True}
        github_connector.on_push(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["is_default_branch"] is True

    def test_push_auto_timestamp(self, github_connector, mock_event_bus):
        payload = {"repository_name": "test/code", "branch": "develop", "commit_count": 1}
        github_connector.on_push(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert "pushed_at" in emitted_event["payload"]

    def test_push_default_commit_count(self, github_connector, mock_event_bus):
        payload = {"repository_name": "test/repo", "branch": "hotfix", "pushed_at": "2026-06-27T23:00:00Z"}
        github_connector.on_push(payload)
        emitted_event = mock_event_bus.emit.call_args[0][0]
        assert emitted_event["payload"]["commit_count"] == 1

class TestGitHubConnectorIntegration:
    def test_connector_initializes_with_event_bus(self, mock_event_bus):
        connector = GitHubConnector(event_bus_module=mock_event_bus)
        assert connector.event_bus is mock_event_bus

    def test_connector_initializes_without_event_bus(self):
        connector = GitHubConnector()
        assert connector.event_bus is not None

    def test_connector_handles_multiple_events(self, github_connector, mock_event_bus):
        pr_payload = {"pull_request_id": "pr-multi-1", "pull_request_number": 100, "repository_name": "multi/test", "merged_at": "2026-06-28T00:00:00Z", "merged_by": "user1"}
        push_payload = {"repository_name": "multi/test", "branch": "develop", "pushed_at": "2026-06-28T01:00:00Z", "commit_count": 7}
        github_connector.on_pr_merged(pr_payload)
        github_connector.on_push(push_payload)
        assert mock_event_bus.emit.call_count == 2

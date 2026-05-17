"""
Unit tests for the CLI helpers.
"""

from pathlib import Path

import main as main_module


class TestRepositorySourceHelpers:
    """Tests for CLI repository source resolution helpers."""

    def test_detects_github_repository_sources(self):
        assert main_module.is_github_repository_source('https://github.com/user/repo')
        assert main_module.is_github_repository_source('git@github.com:user/repo.git')
        assert not main_module.is_github_repository_source('/local/path/to/repo')

    def test_normalizes_github_clone_urls(self):
        assert main_module.normalize_github_clone_url('https://github.com/user/repo') == 'https://github.com/user/repo.git'
        assert main_module.normalize_github_clone_url('github.com/user/repo') == 'https://github.com/user/repo.git'
        assert main_module.normalize_github_clone_url('git@github.com:user/repo') == 'git@github.com:user/repo.git'

    def test_resolve_local_repository_path(self, tmp_path):
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()

        resolved, cleanup_required = main_module.resolve_repository_source(str(repo_dir), tmp_path)

        assert resolved == repo_dir
        assert cleanup_required is False

    def test_clone_github_repository_uses_git_clone(self, tmp_path, monkeypatch):
        captured_commands = []

        def fake_run(command, check, capture_output, text):
            captured_commands.append(command)
            clone_target = Path(command[-1])
            clone_target.mkdir(parents=True, exist_ok=True)
            (clone_target / 'sample.py').write_text('print("hello")\n', encoding='utf-8')

            class Result:
                stdout = 'cloned'
                stderr = ''

            return Result()

        monkeypatch.setattr(main_module.subprocess, 'run', fake_run)

        cloned_path = main_module.clone_github_repository('https://github.com/user/repo', tmp_path)

        assert cloned_path.exists()
        assert (cloned_path / 'sample.py').exists()
        assert captured_commands[0][:3] == ['git', 'clone', '--depth']
        assert captured_commands[0][3] == '1'
        assert captured_commands[0][4] == 'https://github.com/user/repo.git'
"""
Unit tests for the Flask application helpers.
"""

from pathlib import Path

import pytest

import app as app_module


class TestRepositorySourceHelpers:
    """Tests for repository source resolution helpers."""

    def test_detects_github_repository_sources(self):
        assert app_module.is_github_repository_source('https://github.com/user/repo')
        assert app_module.is_github_repository_source('git@github.com:user/repo.git')
        assert not app_module.is_github_repository_source('/local/path/to/repo')

    def test_normalizes_github_clone_urls(self):
        assert app_module.normalize_github_clone_url('https://github.com/user/repo') == 'https://github.com/user/repo.git'
        assert app_module.normalize_github_clone_url('github.com/user/repo') == 'https://github.com/user/repo.git'
        assert app_module.normalize_github_clone_url('git@github.com:user/repo') == 'git@github.com:user/repo.git'

    def test_resolve_local_repository_path(self, tmp_path):
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()

        resolved = app_module.resolve_repository_source(str(repo_dir), 'task-123')

        assert resolved == repo_dir

    def test_clone_github_repository_uses_git_clone(self, tmp_path, monkeypatch):
        temp_folder = tmp_path / 'temp'
        temp_folder.mkdir()
        app_module.app.config['TEMP_FOLDER'] = str(temp_folder)

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

        monkeypatch.setattr(app_module.subprocess, 'run', fake_run)

        cloned_path = app_module.clone_github_repository('https://github.com/user/repo', 'task-456')

        assert cloned_path.exists()
        assert (cloned_path / 'sample.py').exists()
        assert captured_commands[0][:3] == ['git', 'clone', '--depth']
        assert captured_commands[0][3] == '1'
        assert captured_commands[0][4] == 'https://github.com/user/repo.git'
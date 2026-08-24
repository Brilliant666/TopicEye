"""Fail-closed, request-scoped adapters for Rardar POC fact fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.rardar.schemas import ArtifactPointer, CandidateFixture, ExplosionBoardArtifact


class RardarArtifactError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _read_regular_file(path: Path, *, root: Path) -> bytes:
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RardarArtifactError("artifact_missing", f"Rardar artifact is unavailable: {path.name}") from exc
    if path.is_symlink() or resolved.is_symlink():
        raise RardarArtifactError("unsafe_artifact_path", "Rardar artifacts cannot be symbolic links")
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise RardarArtifactError("unsafe_artifact_path", "Rardar artifact escaped its fixture root")
    if not resolved.is_file():
        raise RardarArtifactError("artifact_missing", "Rardar artifact path is not a regular file")
    return resolved.read_bytes()


class RardarIntelligenceAdapter:
    """Load exactly one verified explosion-board revision per request."""

    def __init__(self, fixture_root: Path):
        self.root = fixture_root.resolve()
        self.board_root = self.root / "explosion-board"

    def load_explosion_board(self) -> ExplosionBoardArtifact:
        pointer_bytes = _read_regular_file(self.board_root / "current.json", root=self.board_root)
        try:
            pointer = ArtifactPointer.model_validate_json(pointer_bytes)
        except Exception as exc:
            raise RardarArtifactError("invalid_artifact_pointer", "Explosion pointer failed strict validation") from exc

        artifact_path = self.board_root / pointer.artifact
        artifact_bytes = _read_regular_file(artifact_path, root=self.board_root)
        actual_digest = hashlib.sha256(artifact_bytes).hexdigest()
        if actual_digest != pointer.sha256:
            raise RardarArtifactError("artifact_digest_mismatch", "Explosion artifact digest does not match pointer")
        try:
            artifact = ExplosionBoardArtifact.model_validate_json(artifact_bytes)
        except Exception as exc:
            raise RardarArtifactError(
                "invalid_explosion_artifact", "Explosion artifact failed strict validation"
            ) from exc
        if artifact.artifactRevision != pointer.artifactRevision:
            raise RardarArtifactError("artifact_revision_mismatch", "Pointer and artifact revisions differ")
        return artifact

    def load_candidate_fixture(self) -> CandidateFixture:
        fixture_bytes = _read_regular_file(self.root / "find-project-candidates.v1.json", root=self.root)
        try:
            return CandidateFixture.model_validate_json(fixture_bytes)
        except Exception as exc:
            raise RardarArtifactError(
                "invalid_candidate_fixture", "Candidate fixture failed strict validation"
            ) from exc

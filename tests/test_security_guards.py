"""
Unit tests for Platform Security Guards: SSRF, Subprocess safety, API Keys, and RBAC.
"""

from pathlib import Path
import pytest

from textora_engine.db import APIKeyRepository, MigrationRunner, ProjectRepository, SQLiteDatabase
from textora_engine.domain import Organization, Project, Role
from textora_engine.security import (
    APIKeyManager,
    PermissionError,
    SecurityError,
    SubprocessRunner,
    TenantAuthorizer,
    URLValidator,
)


def test_ssrf_validator_blocks_private_targets():
    # Localhost & loopback
    with pytest.raises(SecurityError, match="Targeting localhost is prohibited"):
        URLValidator.validate_url("http://127.0.0.1:8000/api")

    with pytest.raises(SecurityError, match="Targeting localhost is prohibited"):
        URLValidator.validate_url("http://localhost:3000/secret")

    # Cloud metadata endpoint
    with pytest.raises(SecurityError, match="SSRF blocked"):
        URLValidator.validate_url("http://169.254.169.254/latest/meta-data")

    # RFC 1918 Private networks
    with pytest.raises(SecurityError, match="SSRF blocked"):
        URLValidator.validate_url("http://10.0.0.1/admin")

    with pytest.raises(SecurityError, match="SSRF blocked"):
        URLValidator.validate_url("http://192.168.1.1/router")

    # Prohibited schemes
    with pytest.raises(SecurityError, match="Prohibited URL scheme"):
        URLValidator.validate_url("ftp://example.com/video.mp4")

    with pytest.raises(SecurityError, match="Prohibited URL scheme"):
        URLValidator.validate_url("file:///etc/passwd")

    # Embedded credentials
    with pytest.raises(SecurityError, match="embedded user credentials"):
        URLValidator.validate_url("https://user:secret@example.com/video.mp4")

    # Prohibited ports (e.g. SSH, Redis)
    with pytest.raises(SecurityError, match="Targeting port 22 is prohibited"):
        URLValidator.validate_url("http://example.com:22/payload")

    with pytest.raises(SecurityError, match="Targeting port 6379 is prohibited"):
        URLValidator.validate_url("http://example.com:6379/keys")

    # Safe redirect handler blocks redirection to private IP
    from textora_engine.security.ssrf import SafeRedirectHandler
    handler = SafeRedirectHandler()
    with pytest.raises(SecurityError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/admin")


    with pytest.raises(SecurityError, match="Prohibited URL scheme"):
        URLValidator.validate_url("javascript:alert(1)")


def test_subprocess_runner_safety():
    # Valid execution
    proc = SubprocessRunner.run_safe(["python", "-c", "print('safe execution')"])
    assert proc.returncode == 0
    assert "safe execution" in proc.stdout

    # Non-list rejected
    with pytest.raises(ValueError, match="Command must be a non-empty list"):
        SubprocessRunner.run_safe("python -c echo")

    # Non-string element rejected
    with pytest.raises(ValueError, match="All command arguments must be strings"):
        SubprocessRunner.run_safe(["python", 123])


def test_api_key_manager_generation_and_verification(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "auth_test.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_sec", name="Security Org"))
    proj_repo.create_project(Project(id="prj_sec", org_id="org_sec", name="Sec Prj"))

    key_repo = APIKeyRepository(db)

    # Generate key
    key_entity, raw_key = APIKeyManager.generate_key(
        org_id="org_sec",
        project_id="prj_sec",
        name="Ingest Key Alpha",
    )
    assert raw_key.startswith("tx_live_")
    assert key_entity.key_prefix == raw_key[:12]
    assert key_entity.key_hash != raw_key  # Must be hashed!

    # Store in DB
    key_repo.create_key(key_entity)

    # Verification with correct key
    verified = APIKeyManager.verify_key(raw_key, key_repo)
    assert verified is not None
    assert verified.id == key_entity.id

    # Verification with invalid key
    assert APIKeyManager.verify_key("tx_live_invalid_fake_key_12345", key_repo) is None
    assert APIKeyManager.verify_key("malformed_key", key_repo) is None

    # Revocation
    db.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_entity.id,))
    assert APIKeyManager.verify_key(raw_key, key_repo) is None


def test_tenant_authorizer_and_rbac():
    # Tenant isolation
    TenantAuthorizer.authorize_tenant("org_1", "org_1")
    with pytest.raises(PermissionError, match="Cross-tenant access denied"):
        TenantAuthorizer.authorize_tenant("org_1", "org_2")

    # RBAC checks
    # VIEWER
    TenantAuthorizer.check_permission(Role.VIEWER, "read:jobs")
    with pytest.raises(PermissionError, match="does not possess required permission"):
        TenantAuthorizer.check_permission(Role.VIEWER, "create:jobs")

    # MEMBER
    TenantAuthorizer.check_permission(Role.MEMBER, "create:jobs")
    with pytest.raises(PermissionError, match="does not possess required permission"):
        TenantAuthorizer.check_permission(Role.MEMBER, "manage:keys")

    # ADMIN
    TenantAuthorizer.check_permission(Role.ADMIN, "manage:keys")
    TenantAuthorizer.check_permission(Role.ADMIN, "create:jobs")

    # OWNER
    TenantAuthorizer.check_permission(Role.OWNER, "manage:org")

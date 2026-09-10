"""
API key management, secure hashing, and multi-tenant authorization for Textora Engine.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import secrets
from typing import Optional, Set, Tuple
import uuid

from textora_engine.db.repositories import APIKeyRepository
from textora_engine.domain.entities import APIKey, Role


class PermissionError(Exception):
    """Raised when an actor lacks authority to access a resource."""
    pass


class APIKeyManager:
    """Handles secure API key generation, salted hashing, and constant-time verification."""

    @classmethod
    def generate_key(
        cls,
        org_id: str,
        project_id: str,
        name: str = "Default Ingest Key",
        is_test: bool = False,
    ) -> Tuple[APIKey, str]:
        """
        Generate a new cryptographically secure API key.
        Returns: (APIKey entity for storage, raw_secret_key for one-time display)
        """
        env_tag = "test" if is_test else "live"
        secret_part = secrets.token_hex(20)  # 40 chars hex
        raw_key = f"tx_{env_tag}_{secret_part}"
        key_prefix = raw_key[:12]

        # Compute SHA-256 hash of raw key
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        key_entity = APIKey(
            id=f"key_{uuid.uuid4().hex[:12]}",
            org_id=org_id,
            project_id=project_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            created_at=datetime.now(timezone.utc),
            revoked=False,
        )

        return key_entity, raw_key

    @classmethod
    def verify_key(cls, raw_key: str, repo: APIKeyRepository) -> Optional[APIKey]:
        """
        Verify raw API key string using constant-time hash comparison.
        """
        if not raw_key or not isinstance(raw_key, str) or not raw_key.startswith("tx_"):
            return None

        computed_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_entity = repo.get_by_hash(computed_hash)

        if not key_entity:
            return None

        if key_entity.revoked:
            return None

        # Check expiration if set
        if key_entity.expires_at and key_entity.expires_at < datetime.now(timezone.utc):
            return None

        # Constant-time comparison
        if not hmac.compare_digest(computed_hash, key_entity.key_hash):
            return None

        repo.mark_used(key_entity.id)
        return key_entity


class TenantAuthorizer:
    """Enforces organizational boundaries and Role-Based Access Control."""

    ROLE_PERMISSIONS = {
        Role.VIEWER: {"read:jobs", "read:datasets", "read:projects"},
        Role.MEMBER: {"read:jobs", "read:datasets", "read:projects", "create:jobs", "cancel:jobs"},
        Role.ADMIN: {"read:jobs", "read:datasets", "read:projects", "create:jobs", "cancel:jobs", "manage:keys", "manage:projects"},
        Role.OWNER: {"read:jobs", "read:datasets", "read:projects", "create:jobs", "cancel:jobs", "manage:keys", "manage:projects", "manage:org"},
    }

    @classmethod
    def authorize_tenant(cls, actor_org_id: str, resource_org_id: str) -> None:
        """Verify that actor belongs to the organization owning the resource."""
        if actor_org_id != resource_org_id:
            raise PermissionError(f"Cross-tenant access denied: Actor org '{actor_org_id}' cannot access resource in org '{resource_org_id}'")

    @classmethod
    def check_permission(cls, role: Role, required_permission: str) -> None:
        """Verify that actor role holds the required permission."""
        perms = cls.ROLE_PERMISSIONS.get(role, set())
        if required_permission not in perms:
            raise PermissionError(f"Role '{role.value}' does not possess required permission '{required_permission}'")

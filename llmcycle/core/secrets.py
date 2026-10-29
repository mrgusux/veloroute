"""
Secret Manager Adapters
========================
Abstract SecretLoader interface + built-in adapters for loading API keys
from environment variables, AWS Secrets Manager, GCP Secret Manager,
and HashiCorp Vault.

All adapters are lazy-imported — AWS/GCP/Vault SDKs are only required
when the corresponding adapter is actually used.

Usage::

    from llmcycle.core.secrets import EnvSecretLoader, AWSSecretLoader

    # Load from environment variables (default — always available)
    loader = EnvSecretLoader()
    key = loader.load("OPENAI_API_KEYS")   # reads os.environ["OPENAI_API_KEYS"]

    # Load from AWS Secrets Manager (requires boto3)
    loader = AWSSecretLoader(region="us-east-1")
    key = loader.load("prod/openai-api-key")    # fetches the secret string

    # Use with LLMCycle
    client = LLMCycle(secret_loader=AWSSecretLoader(region="us-east-1"))
    client.add_key("openai", loader.load("prod/openai/key"))
"""
from __future__ import annotations
import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SecretLoader(ABC):
    """Abstract base class for secret source adapters."""

    @abstractmethod
    def load(self, secret_id: str) -> str:
        """
        Load and return the secret value for the given ID.

        Args:
            secret_id: Provider-specific identifier (env var name, ARN, path, etc.)

        Returns:
            The raw secret string (API key, token, etc.)

        Raises:
            SecretNotFoundError: If the secret cannot be found.
            SecretLoadError:     On SDK / network / permission errors.
        """

    def load_many(self, mapping: Dict[str, str]) -> Dict[str, str]:
        """
        Load multiple secrets.

        Args:
            mapping: {alias → secret_id} — e.g. {"openai_key": "OPENAI_API_KEYS"}

        Returns:
            {alias → secret_value}
        """
        return {alias: self.load(sid) for alias, sid in mapping.items()}


# ─── Errors ──────────────────────────────────────────────────────────────────

class SecretNotFoundError(Exception):
    def __init__(self, secret_id: str, source: str):
        super().__init__(f"Secret '{secret_id}' not found in {source}.")
        self.secret_id = secret_id
        self.source    = source


class SecretLoadError(Exception):
    def __init__(self, secret_id: str, source: str, cause: Exception):
        super().__init__(f"Failed to load secret '{secret_id}' from {source}: {cause}")
        self.secret_id = secret_id
        self.source    = source
        self.cause     = cause


# ─── Built-in adapters ───────────────────────────────────────────────────────

class EnvSecretLoader(SecretLoader):
    """
    Load secrets from environment variables (default, zero-dependency).

    Usage::

        loader = EnvSecretLoader()
        key = loader.load("OPENAI_API_KEYS")   # → os.environ["OPENAI_API_KEYS"]

        # With prefix stripping
        loader = EnvSecretLoader(prefix="PROD_")
        key = loader.load("OPENAI_API_KEYS")   # reads PROD_OPENAI_API_KEYS
    """

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    def load(self, secret_id: str) -> str:
        env_key = f"{self.prefix}{secret_id}"
        value = os.environ.get(env_key)
        if not value:
            raise SecretNotFoundError(env_key, source="environment variables")
        return value


class AWSSecretLoader(SecretLoader):
    """
    Load secrets from AWS Secrets Manager.

    Requires: pip install boto3

    Usage::

        loader = AWSSecretLoader(region="us-east-1")
        key = loader.load("prod/openai-key")
    """

    def __init__(self, region: str, profile: Optional[str] = None):
        self.region  = region
        self.profile = profile
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "AWS Secrets Manager requires boto3. Install it with: pip install boto3"
                ) from e
            session = boto3.Session(region_name=self.region, profile_name=self.profile)
            self._client = session.client("secretsmanager")
        return self._client

    def load(self, secret_id: str) -> str:
        client = self._get_client()
        try:
            response = client.get_secret_value(SecretId=secret_id)
            return response.get("SecretString") or response.get("SecretBinary", b"").decode()
        except Exception as e:
            err_name = type(e).__name__
            if "ResourceNotFoundException" in err_name or "NoSuchKey" in str(e):
                raise SecretNotFoundError(secret_id, source="AWS Secrets Manager")
            raise SecretLoadError(secret_id, source="AWS Secrets Manager", cause=e)


class GCPSecretLoader(SecretLoader):
    """
    Load secrets from GCP Secret Manager.

    Requires: pip install google-cloud-secret-manager

    Usage::

        loader = GCPSecretLoader(project_id="my-gcp-project")
        key = loader.load("openai-api-key")         # fetches latest version
        key = loader.load("openai-api-key/versions/3")  # specific version
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._client    = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import secretmanager
            except ImportError as e:
                raise ImportError(
                    "GCP Secret Manager requires google-cloud-secret-manager. "
                    "Install with: pip install google-cloud-secret-manager"
                ) from e
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def load(self, secret_id: str) -> str:
        client = self._get_client()
        # Support "secret_name/versions/N" or just "secret_name" (→ latest)
        if "/versions/" in secret_id:
            name = f"projects/{self.project_id}/secrets/{secret_id}"
        else:
            name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("utf-8")
        except Exception as e:
            if "NOT_FOUND" in str(e):
                raise SecretNotFoundError(secret_id, source="GCP Secret Manager")
            raise SecretLoadError(secret_id, source="GCP Secret Manager", cause=e)


class VaultSecretLoader(SecretLoader):
    """
    Load secrets from HashiCorp Vault (KV v1/v2 engine).

    Requires: pip install hvac

    Usage::

        loader = VaultSecretLoader(
            url="https://vault.mycompany.com",
            token="s.abc123",
            mount_point="secret",  # KV engine mount
        )
        key = loader.load("llm/openai")   # reads the 'value' field from the KV path
    """

    def __init__(
        self,
        url: str,
        token: str,
        mount_point: str = "secret",
        field: str = "value",
        kv_version: int = 2,
    ):
        self.url         = url
        self.token       = token
        self.mount_point = mount_point
        self.field       = field
        self.kv_version  = kv_version
        self._client     = None

    def _get_client(self):
        if self._client is None:
            try:
                import hvac
            except ImportError as e:
                raise ImportError(
                    "Vault requires hvac. Install with: pip install hvac"
                ) from e
            self._client = hvac.Client(url=self.url, token=self.token)
        return self._client

    def load(self, secret_id: str) -> str:
        client = self._get_client()
        try:
            if self.kv_version == 2:
                response = client.secrets.kv.v2.read_secret_version(
                    path=secret_id, mount_point=self.mount_point
                )
                data = response["data"]["data"]
            else:
                response = client.secrets.kv.read_secret(
                    path=secret_id, mount_point=self.mount_point
                )
                data = response["data"]
            if self.field not in data:
                raise KeyError(
                    f"Field '{self.field}' not found in Vault secret '{secret_id}'. "
                    f"Available fields: {list(data.keys())}"
                )
            return data[self.field]
        except KeyError:
            raise
        except Exception as e:
            if "InvalidPath" in str(e) or "404" in str(e):
                raise SecretNotFoundError(secret_id, source="HashiCorp Vault")
            raise SecretLoadError(secret_id, source="HashiCorp Vault", cause=e)

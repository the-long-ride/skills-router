"""Layer 1.2 — Registry Resolver.

Resolves package names to JSON tool manifests by querying a central pre-audited registry
or looking up local cache copies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from skills_router.config import SkillsRouterConfig

_PACKAGE_NAME_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9_\-]{0,126}[a-zA-Z0-9])?$"
)
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]{0,127}$")
_GITHUB_REF_RE = re.compile(
    r"^github:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?:@(?P<ref>[A-Za-z0-9_./-]+))?$"
)
_LOCALHOSTS = {"localhost", "127.0.0.1", "::1"}


class RegistryResolutionError(ValueError):
    """Raised when resolving a package name fails."""


class RegistryResolver:
    """Resolves local files or remote package names to manifests."""

    def __init__(self, config: SkillsRouterConfig):
        self.config = config
        Path(self.config.registry_cache_dir).mkdir(parents=True, exist_ok=True)

    def resolve(self, package_name_or_path: str) -> dict:
        """Resolve a file path or a registry package name to a manifest dict.

        Args:
            package_name_or_path: Path to local JSON or a registry package name.

        Returns:
            Parsed tool manifest dictionary.

        Raises:
            RegistryResolutionError: If package cannot be resolved or parsed.
        """
        if package_name_or_path.strip().startswith("github:"):
            return self._resolve_github(package_name_or_path.strip())

        # 1. If it exists as a local file, read and parse it.
        local_path = Path(package_name_or_path)
        if local_path.exists() and local_path.is_file():
            try:
                return self._read_json_file(local_path, source="local manifest file")
            except Exception as e:
                if isinstance(e, RegistryResolutionError):
                    raise
                raise RegistryResolutionError(
                    f"Failed to parse local manifest file: {e}"
                ) from e

        if self._looks_like_path(package_name_or_path):
            raise RegistryResolutionError(
                f"Local manifest file not found: {package_name_or_path}"
            )

        # 2. Treat as package name.
        package_name, version = self._parse_package_spec(package_name_or_path)
        if not _PACKAGE_NAME_RE.match(package_name):
            raise RegistryResolutionError(
                f"Invalid package name or path: '{package_name_or_path}'. "
                "Package names must only contain alphanumeric characters, hyphens, and underscores."
            )

        # 3. Check local cache scoped to the registry base URL.
        cache_file = self._cache_file(package_name, version)
        cached = self._read_cache(cache_file)
        if cached is not None:
            return cached

        # 4. Fetch from remote registry.
        url = self._manifest_url(package_name, version)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "skills-router-package-manager",
                },
            )
            with urllib.request.urlopen(
                req, timeout=self.config.registry_fetch_timeout_seconds
            ) as response:
                self._validate_response_headers(response, package_name)
                content = self._read_response_limited(response)
                manifest = self._decode_manifest(content, package_name)
                self._attach_resolution_meta(
                    manifest,
                    source="registry",
                    identifier=package_name,
                    version=version,
                    url=url,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RegistryResolutionError(
                    f"Package '{package_name}' not found in registry (HTTP 404)."
                ) from e
            raise RegistryResolutionError(
                f"Registry HTTP error for '{package_name}': {e.code} - {e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise RegistryResolutionError(
                f"Failed to connect to registry for '{package_name}': {e.reason}"
            ) from e
        except json.JSONDecodeError as e:
            raise RegistryResolutionError(
                f"Registry returned invalid JSON for '{package_name}': {e}"
            ) from e
        except UnicodeDecodeError as e:
            raise RegistryResolutionError(
                f"Registry returned non-UTF-8 content for '{package_name}': {e}"
            ) from e
        except Exception as e:
            if isinstance(e, RegistryResolutionError):
                raise
            raise RegistryResolutionError(
                f"Unexpected error fetching package '{package_name}': {e}"
            ) from e

        # 5. Write to cache.
        try:
            self._write_cache(cache_file, manifest)
        except Exception:
            # Failure to cache shouldn't fail the resolution
            pass

        return manifest

    @staticmethod
    def _parse_package_spec(value: str) -> tuple[str, str | None]:
        spec = value.strip()
        if "@" not in spec:
            return spec, None
        package_name, version = spec.rsplit("@", 1)
        if not version or not _VERSION_RE.match(version):
            raise RegistryResolutionError(
                f"Invalid package version in '{value}'. Use name@version."
            )
        return package_name, version

    def _resolve_github(self, spec: str) -> dict[str, Any]:
        match = _GITHUB_REF_RE.match(spec)
        if not match:
            raise RegistryResolutionError(
                "Invalid GitHub package spec. Use github:<owner>/<repo> or "
                "github:<owner>/<repo>@<ref>."
            )

        owner = match.group("owner")
        repo = match.group("repo")
        ref = match.group("ref") or "main"
        cache_file = self._github_cache_file(owner, repo, ref)
        cached = self._read_cache(cache_file)
        if cached is not None:
            return cached

        errors: list[str] = []
        for manifest_path in self.config.github_manifest_paths:
            if self._unsafe_github_manifest_path(manifest_path):
                continue
            url = (
                "https://raw.githubusercontent.com/"
                f"{owner}/{repo}/{ref}/{manifest_path}"
            )
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "skills-router-package-manager",
                    },
                )
                with urllib.request.urlopen(
                    req, timeout=self.config.registry_fetch_timeout_seconds
                ) as response:
                    self._validate_response_headers(response, spec)
                    content = self._read_response_limited(response)
                    manifest = self._decode_manifest(content, spec)
                    self._attach_resolution_meta(
                        manifest,
                        source="github",
                        identifier=f"{owner}/{repo}",
                        version=ref,
                        url=url,
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                    self._write_cache(cache_file, manifest)
                    return manifest
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    errors.append(f"{manifest_path}: HTTP {e.code}")
            except Exception as e:
                if isinstance(e, RegistryResolutionError):
                    errors.append(f"{manifest_path}: {e}")
                else:
                    errors.append(f"{manifest_path}: {type(e).__name__}: {e}")

        detail = "; ".join(errors[:3]) if errors else "no manifest path found"
        raise RegistryResolutionError(
            f"Could not resolve {spec} from GitHub ({detail})."
        )

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        stripped = value.strip()
        if not stripped:
            return False
        candidate = Path(stripped)
        return (
            candidate.is_absolute()
            or stripped.startswith((".", "~"))
            or "/" in stripped
            or "\\" in stripped
            or bool(re.match(r"^[a-zA-Z]:", stripped))
            or stripped.lower().endswith(".json")
        )

    def _manifest_url(self, package_name: str, version: str | None = None) -> str:
        base_url = self.config.registry_base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(base_url)

        if not parsed.scheme or not parsed.netloc:
            raise RegistryResolutionError(
                f"Invalid registry_base_url: '{self.config.registry_base_url}'"
            )
        if parsed.query or parsed.fragment:
            raise RegistryResolutionError(
                "registry_base_url must not include query or fragment"
            )
        if (
            self.config.registry_require_https
            and parsed.scheme != "https"
            and parsed.hostname not in _LOCALHOSTS
        ):
            raise RegistryResolutionError(
                "registry_base_url must use HTTPS unless it points to localhost"
            )

        quoted_name = urllib.parse.quote(package_name, safe="")
        if version:
            quoted_version = urllib.parse.quote(version, safe="")
            return f"{base_url}/{quoted_name}/{quoted_version}.json"
        return f"{base_url}/{quoted_name}.json"

    def _registry_cache_scope(self) -> str:
        normalized = self.config.registry_base_url.rstrip("/").lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _cache_file(self, package_name: str, version: str | None = None) -> Path:
        cache_dir = Path(self.config.registry_cache_dir) / self._registry_cache_scope()
        suffix = f"@{version}" if version else ""
        return cache_dir / f"{package_name}{suffix}.json"

    def _github_cache_file(self, owner: str, repo: str, ref: str) -> Path:
        scope = hashlib.sha256(
            f"github:{owner.lower()}/{repo.lower()}@{ref}".encode("utf-8")
        ).hexdigest()[:16]
        return Path(self.config.registry_cache_dir) / "github" / scope / "manifest.json"

    def _read_cache(self, cache_file: Path) -> dict[str, Any] | None:
        if not cache_file.exists() or not cache_file.is_file():
            return None

        ttl = self.config.registry_cache_ttl_seconds
        if ttl >= 0 and time.time() - cache_file.stat().st_mtime > ttl:
            return None

        try:
            return self._read_json_file(cache_file, source="cached registry manifest")
        except RegistryResolutionError:
            # Cache corruption should not prevent a fresh registry lookup.
            return None

    @staticmethod
    def _read_json_file(path: Path, source: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise RegistryResolutionError(f"{source} must be a JSON object")
        return data

    def _validate_response_headers(self, response, package_name: str) -> None:
        headers = getattr(response, "headers", None)
        if not headers or not hasattr(headers, "get"):
            return

        content_type = headers.get("Content-Type", "")
        if (
            isinstance(content_type, str)
            and content_type
            and "json" not in content_type.lower()
        ):
            raise RegistryResolutionError(
                f"Registry returned unsupported content type for "
                f"'{package_name}': {content_type}"
            )

        content_length = headers.get("Content-Length")
        if content_length is None:
            return
        try:
            length = int(content_length)
        except (TypeError, ValueError):
            return
        if length > self.config.registry_max_manifest_bytes:
            raise RegistryResolutionError(
                f"Registry manifest for '{package_name}' exceeds "
                f"{self.config.registry_max_manifest_bytes} bytes"
            )

    def _read_response_limited(self, response) -> bytes:
        max_bytes = self.config.registry_max_manifest_bytes
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise RegistryResolutionError(
                f"Registry manifest exceeds {max_bytes} bytes"
            )
        return content

    @staticmethod
    def _decode_manifest(content: bytes, package_name: str) -> dict[str, Any]:
        data = json.loads(content.decode("utf-8"))
        if not isinstance(data, dict):
            raise RegistryResolutionError(
                f"Registry returned a non-object manifest for '{package_name}'"
            )
        return data

    @staticmethod
    def _write_cache(cache_file: Path, manifest: dict[str, Any]) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = cache_file.with_name(f".{cache_file.name}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        try:
            os.replace(tmp_file, cache_file)
        except PermissionError:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            try:
                tmp_file.unlink()
            except OSError:
                pass

    @staticmethod
    def _unsafe_github_manifest_path(manifest_path: str) -> bool:
        parts = manifest_path.replace("\\", "/").split("/")
        return (
            not manifest_path
            or manifest_path.startswith("/")
            or ".." in parts
            or any(not part for part in parts)
        )

    @staticmethod
    def _attach_resolution_meta(
        manifest: dict[str, Any],
        source: str,
        identifier: str,
        version: str | None,
        url: str,
        sha256: str,
    ) -> None:
        meta = manifest.setdefault("layer_meta", {})
        if isinstance(meta, dict):
            meta["resolved_source"] = source
            meta["resolved_identifier"] = identifier
            if version:
                meta["resolved_version"] = version
            meta["resolved_url"] = url
            meta["resolved_sha256"] = sha256

# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/plugins/ldap_ad.py
from __future__ import annotations

import logging
import ssl as pyssl
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from thaum.types import ResolvedSecret, ServerConfig, ThaumPerson, ThaumTeam
from lookup.base import BaseLookupPlugin, BaseLookupPluginConfig

try:
    import ldap3  # type: ignore
except Exception:  # pragma: no cover
    ldap3 = None  # type: ignore


class BaseLdapConfig(BaseModel):
    """
    Shared LDAP settings used by the AD/LDAP lookup plugin.
    """

    server_uri: str = Field(..., description="e.g. ldap://dc1.example.com or ldaps://dc1.example.com")
    use_start_tls: bool = False
    base_dn: str = Field(..., description="Default search base DN for people")

    bind_dn: str
    bind_password: ResolvedSecret

    # People identity mapping
    # `lookup_id` for people is matched against this LDAP attribute.
    person_id_mode: Literal["samaccountname", "uid", "attribute"] = "samaccountname"
    person_id_attribute: Optional[str] = None  # used when person_id_mode="attribute"

    people_search_filter: str = Field(
        default="",
        description=(
            "Optional extra filter appended with AND. "
            "Examples: (objectClass=user) or (objectCategory=person)."
        ),
    )
    email_attribute: str = "mail"
    fallback_email_attributes: List[str] = Field(default_factory=lambda: ["userPrincipalName", "mail"])
    display_name_attribute: str = "displayName"

    # Group/team mapping
    # In this plugin, teams are addressed by DN (default), so team.lookup_id should be a group DN.
    group_lookup_id_mode: Literal["dn", "name"] = "dn"
    group_search_base_dn: Optional[str] = None
    group_id_attribute: str = "distinguishedName"
    group_name_attribute: str = "cn"

    group_member_attribute: str = "member"
    group_member_id_mode: Literal["dn"] = "dn"  # members come back as DNs; we resolve them via LDAP search

# -- End Class BaseLdapConfig


class LdapAdLookupPluginConfig(BaseLookupPluginConfig, BaseLdapConfig):
    # Which cache platform key should we treat as the LDAP id space?
    # If unset, the plugin resolves any `bot_plugin_name` passed to get_person_by_id(...)
    # using the configured person_id_mode.
    supported_bot_plugin_names: Optional[List[str]] = None

# -- End Class LdapAdLookupPluginConfig


class LdapAdLookupPlugin(BaseLookupPlugin):
    plugin_name = "ldap_ad"

    def __init__(self, **config: Any):
        cfg = LdapAdLookupPluginConfig(**config)
        super().__init__(
            default_team_ttl_seconds=cfg.default_team_ttl_seconds,
        )
        self.cfg = cfg

        self.logger = logging.getLogger("lookup.ldap_ad")
        if ldap3 is None:
            raise RuntimeError(
                "ldap3 is required for LdapAdLookupPlugin. Install it (pip install ldap3)."
            )

    def _connect(self):
        parsed = urlparse(self.cfg.server_uri)
        if parsed.scheme in {"ldap", "ldaps"} and parsed.hostname:
            host = parsed.hostname
            use_ssl = parsed.scheme == "ldaps"
            port = parsed.port or (636 if use_ssl else 389)
        else:
            host = self.cfg.server_uri
            use_ssl = self.cfg.server_uri.lower().startswith("ldaps://")
            port = 636 if use_ssl else 389

        tls = None
        if self.cfg.use_start_tls and hasattr(ldap3, "Tls"):
            tls = ldap3.Tls(validate=pyssl.CERT_NONE)  # type: ignore[attr-defined]

        server = ldap3.Server(host, port=port, use_ssl=use_ssl, get_info=ldap3.ALL)  # type: ignore[attr-defined]

        conn = ldap3.Connection(
            server,
            user=self.cfg.bind_dn,
            password=self.cfg.bind_password.get_secret_value(),
            auto_bind=True,
            receive_timeout=10,
            tls=tls,
        )

        if self.cfg.use_start_tls:
            try:
                conn.start_tls()
            except Exception:
                # If the server doesn't support it, let subsequent operations fail naturally.
                pass

        return conn

    def _build_person_filter(self, person_id: str) -> str:
        if self.cfg.person_id_mode == "samaccountname":
            attr = "sAMAccountName"
        elif self.cfg.person_id_mode == "uid":
            attr = "uid"
        else:
            attr = self.cfg.person_id_attribute or "sAMAccountName"

        base_filter = f"({attr}={ldap3.utils.conv.escape_filter_chars(person_id)})"  # type: ignore[attr-defined]
        extra = self.cfg.people_search_filter.strip()
        if extra:
            return f"(&{base_filter}{extra})"
        return base_filter

    def get_person_by_id(self, bot_plugin_name: str, person_id: str) -> Optional[ThaumPerson]:
        # First hit: identity cache.
        cached = super().get_person_by_id(bot_plugin_name, person_id)
        if cached is not None:
            return cached

        if self.cfg.supported_bot_plugin_names and bot_plugin_name not in self.cfg.supported_bot_plugin_names:
            return None

        # Remote lookup (LDAP/AD).
        try:
            conn = self._connect()
        except Exception as e:
            self.logger.warning("LDAP connect failed: %s", e)
            return None

        try:
            attributes = list(
                {
                    self.cfg.email_attribute,
                    self.cfg.display_name_attribute,
                    *self.cfg.fallback_email_attributes,
                }
            )
            # Find user by configured id attribute.
            search_filter = self._build_person_filter(person_id)
            ok = conn.search(
                search_base=self.cfg.base_dn,
                search_filter=search_filter,
                attributes=attributes,
                size_limit=2,
            )
            if not ok or not conn.entries:
                return None

            entry = conn.entries[0]

            def _get_attr(attr: str) -> str:
                try:
                    v = entry[attr].value
                    return "" if v is None else str(v)
                except Exception:
                    return ""

            display_name = _get_attr(self.cfg.display_name_attribute)

            email = _get_attr(self.cfg.email_attribute)
            if not email:
                for a in self.cfg.fallback_email_attributes:
                    email = _get_attr(a)
                    if email:
                        break

            if not email:
                # Still allow caching placeholder identities (better than returning None).
                email = f"{person_id}@{bot_plugin_name}.unresolved"

            fragment = ThaumPerson(
                email=email,
                display_name=display_name,
                platform_ids={bot_plugin_name: person_id},
                source_plugin=self.plugin_name,
            )
            return self.merge_person(fragment)
        except Exception as e:
            self.logger.warning("LDAP person lookup failed for %s/%s: %s", bot_plugin_name, person_id, e)
            return None
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def fetch_team_members(self, team: ThaumTeam) -> List[ThaumPerson]:
        """
        Resolve group DN -> members -> resolve each member DN -> emit ThaumPerson fragments.
        """
        if ldap3 is None:
            return []

        lookup_id = team.lookup_id or (team.team_name if self.cfg.group_lookup_id_mode == "name" else None)
        if not lookup_id:
            return []

        try:
            conn = self._connect()
        except Exception as e:
            self.logger.warning("LDAP connect failed (team lookup): %s", e)
            return []

        try:
            group_dn: Optional[str] = None
            if self.cfg.group_lookup_id_mode == "dn":
                group_dn = str(lookup_id)
            else:
                # Search for group by cn (team_name)
                base = self.cfg.group_search_base_dn or self.cfg.base_dn
                search_filter = f"({self.cfg.group_name_attribute}={ldap3.utils.conv.escape_filter_chars(str(lookup_id))})"  # type: ignore[attr-defined]
                ok = conn.search(
                    search_base=base,
                    search_filter=search_filter,
                    attributes=[self.cfg.group_id_attribute, self.cfg.group_member_attribute],
                    size_limit=2,
                )
                if not ok or not conn.entries:
                    return []
                group_dn = str(conn.entries[0].entry_dn)

            if not group_dn:
                return []

            # Read group member DNs.
            ok = conn.search(
                search_base=group_dn,
                search_filter="(objectClass=*)",
                attributes=[self.cfg.group_member_attribute],
                size_limit=1,
            )
            if not ok or not conn.entries:
                return []

            group_entry = conn.entries[0]

            member_dns: List[str] = []
            try:
                raw_members = group_entry[self.cfg.group_member_attribute].values
                for v in raw_members:
                    if v:
                        member_dns.append(str(v))
            except Exception:
                # Attribute missing => empty team.
                return []

            if not member_dns:
                return []

            # Resolve each member DN to email/displayName.
            # We do one search per DN (simple + reliable).
            people_attributes = list(
                {
                    self.cfg.email_attribute,
                    self.cfg.display_name_attribute,
                    *self.cfg.fallback_email_attributes,
                }
            )

            fragments: List[ThaumPerson] = []
            for mdn in member_dns:
                user_ok = conn.search(
                    search_base=mdn,
                    search_filter="(objectClass=*)",
                    attributes=people_attributes,
                    size_limit=1,
                )
                if not user_ok or not conn.entries:
                    continue

                entry = conn.entries[0]

                def _get_attr(attr: str) -> str:
                    try:
                        v = entry[attr].value
                        return "" if v is None else str(v)
                    except Exception:
                        return ""

                email = _get_attr(self.cfg.email_attribute)
                if not email:
                    for a in self.cfg.fallback_email_attributes:
                        email = _get_attr(a)
                        if email:
                            break

                if not email:
                    # Without email we can't merge reliably; skip.
                    continue

                display_name = _get_attr(self.cfg.display_name_attribute)

                # We don't know the original "bot plugin person_id" for DN members.
                # Cache still needs a platform id mapping; we treat the DN itself as
                # the lookup id under the LDAP platform key.
                fragments.append(
                    ThaumPerson(
                        email=email,
                        display_name=display_name,
                        platform_ids={self.plugin_name: mdn},
                        source_plugin=self.plugin_name,
                    )
                )

            return fragments
        except Exception as e:
            self.logger.warning("LDAP team member lookup failed: %s", e)
            return []
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

# -- End Class LdapAdLookupPlugin


def create_instance_lookup(config_raw: dict) -> LdapAdLookupPlugin:
    # The factory already merges [lookup] + [lookup.<plugin_name>] into one dict.
    return LdapAdLookupPlugin(**(config_raw or {}))

# -- End Function create_instance_lookup


def get_config_model():
    return LdapAdLookupPluginConfig


def maintenance_tasks_register(registry: Any, *, server_cfg: ServerConfig, config: Dict[str, Any]) -> None:
    return


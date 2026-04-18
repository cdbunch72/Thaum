# SPDX-License-Identifier: MPL-2.0
# Copyright 2026 Clinton Bunch
# lookup/plugins/ldap_ad.py
from __future__ import annotations

import json
import logging
import re
import ssl as pyssl
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator
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

    platform_ids_ldap_attribute: Optional[str] = Field(
        default=None,
        description=(
            "Optional LDAP attribute holding extra Thaum platform_ids (e.g. jira, webex). "
            "Unset = only the primary id from person_id / member DN is used. "
            "See docs/LDAP-AD-lookup.md for encodings."
        ),
    )
    platform_ids_format: str = Field(
        default="json",
        description=(
            "How platform_ids_ldap_attribute is encoded: 'json', or "
            "'multi-value-attr-delimited' with optional '(delimiter)' where delimiter is "
            "one of : / , — default ':' if omitted. Ignored when platform_ids_ldap_attribute is unset."
        ),
    )

# -- End Class BaseLdapConfig


class LdapAdLookupPluginConfig(BaseLookupPluginConfig, BaseLdapConfig):
    # Which cache platform key should we treat as the LDAP id space?
    # If unset, the plugin resolves any `bot_plugin_name` passed to get_person_by_id(...)
    # using the configured person_id_mode.
    supported_bot_plugin_names: Optional[List[str]] = None

    @model_validator(mode="after")
    def _validate_platform_ids_config(self) -> LdapAdLookupPluginConfig:
        if self.platform_ids_ldap_attribute and not str(self.platform_ids_ldap_attribute).strip():
            raise ValueError("platform_ids_ldap_attribute must be non-empty when set.")
        if self.platform_ids_ldap_attribute:
            parse_platform_ids_format(self.platform_ids_format)
        return self

# -- End Class LdapAdLookupPluginConfig


_PLATFORM_IDS_DELIM_PATTERN = re.compile(
    r"^multi-value-attr-delimited" r"(?:\(([:\/,])\))?$"
)


def parse_platform_ids_format(s: str) -> Tuple[Literal["json", "delimited"], str]:
    """
    Parse ``platform_ids_format`` into mode and delimiter (delimiter only used for delimited mode).

    Allowed: ``json``; ``multi-value-attr-delimited`` (``:``); ``multi-value-attr-delimited(:|/|,)``.
    """
    t = (s or "").strip()
    if t == "json":
        return ("json", ":")
    m = _PLATFORM_IDS_DELIM_PATTERN.match(t)
    if m:
        delim = m.group(1) or ":"
        if delim not in (":", "/", ","):
            raise ValueError(f"Invalid delimiter in platform_ids_format: {s!r}")
        return ("delimited", delim)
    raise ValueError(
        f"Invalid platform_ids_format {s!r}. Use 'json', 'multi-value-attr-delimited', "
        "or 'multi-value-attr-delimited(:)', '(/)', or '(,)'."
    )


def merge_platform_ids_from_ldap(base: Dict[str, str], extra: Dict[str, str]) -> Dict[str, str]:
    """Merge LDAP-derived platform ids into *base*; *extra* wins on duplicate keys."""
    out = dict(base)
    out.update(extra)
    return out


def iter_ldap_attribute_string_values(entry: Any, attr_name: str) -> List[str]:
    """Return string values for *attr_name* on an ldap3 Entry (multi-valued or single)."""
    try:
        a = entry[attr_name]
    except Exception:
        return []
    raw = getattr(a, "values", None)
    if raw is not None:
        return [str(x) for x in raw if x is not None and str(x).strip()]
    v = getattr(a, "value", None)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None and str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def parse_platform_ids_from_ldap_entry(
    entry: Any,
    attr_name: str,
    mode: Literal["json", "delimited"],
    delimiter: str,
    logger: logging.Logger,
) -> Dict[str, str]:
    """Parse ``platform_ids_ldap_attribute`` from a directory entry into a platform_key -> id map."""
    if not attr_name or not str(attr_name).strip():
        return {}
    values = iter_ldap_attribute_string_values(entry, attr_name)
    if not values:
        return {}

    if mode == "json":
        raw = next((x for x in values if x.strip()), "")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("platform_ids JSON parse failed for attribute %s: %s", attr_name, e)
            return {}
        if not isinstance(data, dict):
            logger.warning("platform_ids JSON for %s must be a JSON object, got %s", attr_name, type(data).__name__)
            return {}
        out: Dict[str, str] = {}
        for k, v in data.items():
            ks = str(k).strip()
            vs = str(v).strip() if v is not None else ""
            if ks and vs:
                out[ks] = vs
        return out

    # delimited
    out_d: Dict[str, str] = {}
    for line in values:
        line = line.strip()
        if not line:
            continue
        if delimiter not in line:
            logger.warning(
                "platform_ids delimited value missing delimiter %r: %s",
                delimiter,
                line[:80],
            )
            continue
        plugin, _, rest = line.partition(delimiter)
        plugin = plugin.strip()
        pid = rest.strip()
        if not plugin or not pid:
            logger.warning("platform_ids delimited value malformed: %s", line[:80])
            continue
        out_d[plugin] = pid
    return out_d


class LdapAdLookupPlugin(BaseLookupPlugin):
    plugin_name = "ldap_ad"

    def __init__(self, **config: Any):
        cfg = LdapAdLookupPluginConfig(**config)
        super().__init__(
            default_team_ttl_seconds=cfg.default_team_ttl_seconds,
        )
        self.cfg = cfg
        self._platform_ids_mode: Literal["json", "delimited"] = "json"
        self._platform_ids_delimiter = ":"
        if cfg.platform_ids_ldap_attribute:
            self._platform_ids_mode, self._platform_ids_delimiter = parse_platform_ids_format(
                cfg.platform_ids_format
            )

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

    def _person_id_attr_name(self) -> str:
        if self.cfg.person_id_mode == "samaccountname":
            return "sAMAccountName"
        if self.cfg.person_id_mode == "uid":
            return "uid"
        return self.cfg.person_id_attribute or "sAMAccountName"

    def _build_email_search_filter(self, email_key: str) -> str:
        esc = ldap3.utils.conv.escape_filter_chars(email_key)  # type: ignore[attr-defined]
        mail_f = f"({self.cfg.email_attribute}={esc})"
        parts = [mail_f]
        for a in self.cfg.fallback_email_attributes:
            if a.strip() and a != self.cfg.email_attribute:
                parts.append(f"({a.strip()}={esc})")
        combined = f"(|{''.join(parts)})"
        extra = self.cfg.people_search_filter.strip()
        if extra:
            return f"(&{combined}{extra})"
        return combined

    def _add_platform_ids_ldap_attribute(self, attrs: set) -> None:
        an = self.cfg.platform_ids_ldap_attribute
        if an and str(an).strip():
            attrs.add(str(an).strip())

    def _platform_ids_extra_from_entry(self, entry: Any) -> Dict[str, str]:
        an = self.cfg.platform_ids_ldap_attribute
        if not an or not str(an).strip():
            return {}
        return parse_platform_ids_from_ldap_entry(
            entry,
            str(an).strip(),
            self._platform_ids_mode,
            self._platform_ids_delimiter,
            self.logger,
        )

    def _person_fragment_from_ldap_entry(self, entry: Any, bot_plugin_name: str) -> Optional[ThaumPerson]:
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

        id_attr = self._person_id_attr_name()
        person_id = _get_attr(id_attr).strip()
        if not person_id:
            return None

        if not email:
            email = f"{person_id}@{bot_plugin_name}.unresolved"

        base_ids: Dict[str, str] = {bot_plugin_name: person_id}
        extra_ids = self._platform_ids_extra_from_entry(entry)
        platform_ids = merge_platform_ids_from_ldap(base_ids, extra_ids)

        return ThaumPerson(
            email=email,
            display_name=display_name,
            platform_ids=platform_ids,
            source_plugin=self.plugin_name,
        )

    def get_person_by_email(self, email: str) -> Optional[ThaumPerson]:
        key = (email or "").strip()
        if not key:
            return None
        cached = self._get_cached_person_by_email(key)
        if cached is not None:
            return cached

        try:
            conn = self._connect()
        except Exception as e:
            self.logger.warning("LDAP connect failed (get_person_by_email): %s", e)
            return None

        try:
            id_attr = self._person_id_attr_name()
            attributes = {
                self.cfg.email_attribute,
                self.cfg.display_name_attribute,
                id_attr,
                *self.cfg.fallback_email_attributes,
            }
            self._add_platform_ids_ldap_attribute(attributes)
            search_filter = self._build_email_search_filter(key)
            ok = conn.search(
                search_base=self.cfg.base_dn,
                search_filter=search_filter,
                attributes=list(attributes),
                size_limit=2,
            )
            if not ok or not conn.entries:
                return None

            entry = conn.entries[0]
            frag = self._person_fragment_from_ldap_entry(entry, self.plugin_name)
            if frag is None:
                return None
            return self.merge_person(frag)
        except Exception as e:
            self.logger.warning("LDAP get_person_by_email failed for %s: %s", key, e)
            return None
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

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
            id_attr = self._person_id_attr_name()
            attributes = {
                self.cfg.email_attribute,
                self.cfg.display_name_attribute,
                id_attr,
                *self.cfg.fallback_email_attributes,
            }
            self._add_platform_ids_ldap_attribute(attributes)
            # Find user by configured id attribute.
            search_filter = self._build_person_filter(person_id)
            ok = conn.search(
                search_base=self.cfg.base_dn,
                search_filter=search_filter,
                attributes=list(attributes),
                size_limit=2,
            )
            if not ok or not conn.entries:
                return None

            entry = conn.entries[0]
            fragment = self._person_fragment_from_ldap_entry(entry, bot_plugin_name)
            if fragment is None:
                return None
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
            people_attributes = {
                self.cfg.email_attribute,
                self.cfg.display_name_attribute,
                *self.cfg.fallback_email_attributes,
            }
            self._add_platform_ids_ldap_attribute(people_attributes)
            people_attributes_list = list(people_attributes)

            fragments: List[ThaumPerson] = []
            for mdn in member_dns:
                user_ok = conn.search(
                    search_base=mdn,
                    search_filter="(objectClass=*)",
                    attributes=people_attributes_list,
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
                base_ids = {self.plugin_name: mdn}
                extra_ids = self._platform_ids_extra_from_entry(entry)
                platform_ids = merge_platform_ids_from_ldap(base_ids, extra_ids)
                fragments.append(
                    ThaumPerson(
                        email=email,
                        display_name=display_name,
                        platform_ids=platform_ids,
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


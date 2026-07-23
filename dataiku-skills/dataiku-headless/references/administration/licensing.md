---
name: licensing
description: Inspect Dataiku DSS license validity, expiry, enabled add-ons, and user-profile capacity.
---

# Licensing

Use `get_licensing_status` to inspect instance licensing before assigning user profiles or diagnosing license-related restrictions. This is an administrator-only, read-only operation.

## Workflow

1. Inspect the default response for license validity, expiration, enabled add-ons, and profile capacity.
2. Use `direct_count` for users directly assigned to a profile. Compare `count_with_demoted_to` to `licensed_limit` to understand if a profile type can be assigned to any additional users; also take into account `over_quota`.
3. Use `include_profile_capabilities=True` only when needing to understand what Dataiku features each profile is allowed to use.
4. Treat the returned `expired` value as authoritative; `days_until_expiration` is supplemental.

## Safety Rules

- Do not expose license identifiers, licensee information, or raw license content in responses.
- Use the returned profile names when creating or updating users; do not invent profile types.

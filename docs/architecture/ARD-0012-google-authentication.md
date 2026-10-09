# ARD-0012: Google Authentication And App Sessions

Status: Retired implementation; identifier and historical decision retained.
Disposition date: 2026-10-08.

The original Google authentication implementation was archived and removed from
the active build. This entry prevents the retained identifier from implying that
Google sign-in or application sessions currently protect shared data.

The [original decision](../../evidence/deployment-2026-07-14-1412/architecture/docs/architecture/ARD-0012-google-authentication.md)
and [archived restoration plan](../archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md)
remain historical. Selective restoration belongs to
[Story #91](https://github.com/khab40/lob-arena/issues/91), with backend
authorization before sensitive shared data is exposed. The planned private
local-only saved-score mock does not establish that shared-deployment gate.

Related: [ARD-0014](ARD-0014-multiuser-platform-foundation.md),
[current status](../roadmap/CURRENT_STATUS.md).

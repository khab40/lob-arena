"""Fixed legacy evidence compatibility; no cloud, credentials or model imports."""
from copy import deepcopy
import hashlib
import json

CAMPAIGN = "transformer-confirm-c4-20261004-r1"
SCHEMA = "transformer_research_execution_v2"
SLOTS = ("seed-7", "seed-2027")
PREFIX = f"campaigns/wave1-research-20260816/development/{CAMPAIGN}/"
MANIFEST = {'schema_version': 'transformer_confirmation_compatibility_v1',
 'legacy_campaign': 'transformer-research-c4-20261003-r2',
 'source_commit': '87ce8a933c40fe825569e3de6a8699b519808c34',
 'image_digest': 'sha256:b713f1ffeb3c2ba5e4ab09dd2cdb829c6d659a915dd140a113bcabdf6c1909d9',
 'context_public_key': '381d79ac3c10d03c2e180c4fdc0a4eb075d5c27871e7cc4455cba2fc61265fe3',
 'input_inventory_sha256': 'd99876f0119c0a86e2395a7c61f4919b09506557f21b18dd8ef8e32b84dd0e23',
 'bundle_sha256': '697f29587002e8cb46f30c8942ebd1a3ac0e78701ed51e69f8aeb330431e83f3',
 'source_receipt_sha256': '9ed4852ae01c952d76f59054e3db8ad1a8dce00b4ec7a543ce5a48641d7d07ae',
 'baseline_predictions_sha256': '828e261801aa36ab55c02fbe199bbd00ce44b8cef64dd0e0a183d0f6e0913f76',
 'baseline_calibration_sha256': 'a27d88091988dc6e504e3e84d57c985f774f5865ea534882ba7fe87c6ea49e30',
 'prior': {'smoke': {'success': {'sha256': 'e4945d6d97bffee257fe964b7d2db74219a0598218afd41cf09ea823011bedc6',
                                 'size_bytes': 221,
                                 'version_id': '1'},
                     'request': {'sha256': '1aecb34fc2be6a62465a7b49f54fe1791d731df25a69d8f2be9c977090d20830'}},
           'search-64-0003': {'success': {'sha256': '242220a39a11c68147d6b52b54ed9faeb230b630c9666ddbbcedb93f7e35a900',
                                          'size_bytes': 221,
                                          'version_id': '1'},
                              'request': {'sha256': 'cfd8097ab824f9abddfef7fff957773ff78a6b44780f7d8cc3e4c8be44de3788'}},
           'search-64-001': {'success': {'sha256': '12fefd052f3e7d026430c99612b0e12ba5c7b6da34a083302bd8218fa4a4cc9a',
                                         'size_bytes': 221,
                                         'version_id': '1'},
                             'request': {'sha256': 'b8697fa036da1d1bb0e145939979882e3853d3f5321f5840b6364580f713b870'}},
           'search-128-0003': {'success': {'sha256': '32d121ca95d390c18d985e0a45ba0e6088976ac201c1b9e101d1572db83a059a',
                                           'size_bytes': 221,
                                           'version_id': '1'},
                               'request': {'sha256': 'cea6563f836b2fa44ee70d3af7659613e95c31f81ca952033c22f52d9ae4ea99'}},
           'search-128-001': {'success': {'sha256': '71e7296c9923222f6f25f6f7d09fa5b3b1317ef9a01fd66005d3c6e3083569c0',
                                          'size_bytes': 221,
                                          'version_id': '1'},
                              'request': {'sha256': '57a387ce865c1f57a60129bfefa1447372293a294a2f92cb3b70a967c0f9e197'}}}}
BASE_SOURCE = MANIFEST["source_commit"]
BASE_IMAGE_DIGEST = MANIFEST["image_digest"]
CONTEXT_PUBLIC_KEY = MANIFEST["context_public_key"]
LEGACY_PRIOR = MANIFEST["prior"]
LEGACY_PREFIX = f'campaigns/wave1-research-20260816/development/{MANIFEST["legacy_campaign"]}/'
COMPATIBILITY_SHA256 = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def is_replacement(request):
    return request.get("schema_version") == SCHEMA


def prerequisites():
    return deepcopy(LEGACY_PRIOR)


def artifact_prefix(request, slot):
    if slot == request["slot"] and slot in SLOTS:
        return PREFIX + slot + "/"
    if slot in LEGACY_PRIOR:
        return LEGACY_PREFIX + slot + "/"
    raise ValueError("confirmation artifact is outside current slot and fixed legacy inputs")


def require_reference(current, slot, success, expected_request_sha):
    """Check the immutable legacy selector before any storage read."""
    if not is_replacement(current):
        return
    if slot == current["slot"]:
        expected = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if expected_request_sha != expected:
            raise ValueError("confirmation self request differs")
    elif slot not in LEGACY_PRIOR or {"success": success, "request": {"sha256": expected_request_sha}} != LEGACY_PRIOR[slot]:
        raise ValueError("confirmation prerequisite differs from fixed legacy receipt")


def origin_matches(previous, current, slot):
    identity = current
    if is_replacement(current) and slot in LEGACY_PRIOR:
        identity = MANIFEST
    return all(previous[k] == identity[k] for k in ("source_commit", "image_digest", "context_public_key"))

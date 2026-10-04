"""Exact comparison inputs and checkpoint origin; no model or network imports."""
from copy import deepcopy

from . import research_confirmation_contract as confirmation
from .verification_spec import canonical, digest

CAMPAIGN = "transformer-compare-c4-20261004-r1"
SCHEMA = "transformer_research_execution_v3"
PREFIX = f"campaigns/wave1-research-20260816/development/{CAMPAIGN}/"
REPLACEMENT_CAMPAIGN = "transformer-compare-c4-20261004-r2"
REPLACEMENT_SCHEMA = "transformer_research_execution_v4"
REPLACEMENT_PREFIX = f"campaigns/wave1-research-20260816/development/{REPLACEMENT_CAMPAIGN}/"
REPLACEMENT_OF = {
    "job_id": "aijob-e00ma26ee5bavrb8nb",
    "request_sha256": "d5b28eb967d59700182d8003e6b08e73264a2ed06ba0e3c6cb4b94160a9b4deb",
    "proposal_sha256": "e5ef3bf3aeee9b8d9e15b24d8ea1b1288809c7183a12764d800f8c10399a0716",
    "source_commit": "b275e147257b605c8c528e7e61294a114cab7962",
    "image_digest": "sha256:5ab068aae50ef1e8dc2ff89315f5cf5cda01b20b937b48caed8194f08880d713",
    "terminal_state": "CANCELLED",
}
MANIFEST = {'schema_version': 'transformer_comparison_compatibility_v1',
 'confirmation_origin': {'source_commit': '7b88ea213b0e38b8e453e40943dd8403ded79fb4',
                         'image_digest': 'sha256:436def17c45688e764d1cf1b84100ef66f40acfe37bb42cd12ec5c63154c0952',
                         'context_public_key': '381d79ac3c10d03c2e180c4fdc0a4eb075d5c27871e7cc4455cba2fc61265fe3'},
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
                              'request': {'sha256': '57a387ce865c1f57a60129bfefa1447372293a294a2f92cb3b70a967c0f9e197'}},
           'seed-7': {'success': {'sha256': '1ed3dfc88c7039a9b4822ecedc8b1880f4efd2e2b643b3bba6d7c4cd9f051cab',
                                  'size_bytes': 221,
                                  'version_id': '1'},
                      'request': {'sha256': '98375419ad9697f2278af7a71adb42a2dd33db130e5814aa80c2dded083c90e1'}},
           'seed-2027': {'success': {'sha256': 'aae2636e24d8bf6536cd347ebb8e231c2b43d1ed62f6960275eca6d354dfe708',
                                     'size_bytes': 221,
                                     'version_id': '1'},
                         'request': {'sha256': '21891f90c63922a2f5fe36c2330e571b429b5f3c967a53772738dbb58da5a6fa'}}},
 'selected': {'slot': 'search-128-0003',
              'trial': {'batch_size': 64,
                        'learning_rate': 0.0003,
                        'max_epochs': 30,
                        'patience': 5,
                        'seed': 42,
                        'width': 128},
              'trial_sha256': 'cd7c973e11dc6706490f0aa412f774e1642ffd11b6111af5ecb3c10ddf01e7db',
              'checkpoint': {'epoch': 4,
                             'name': 'epoch-04.pt',
                             'object_name': 'search-128-0003-epoch-04.pt',
                             'sha256': 'e2cc94d8e11ad3ad644e52d5283fd958c5458717efd7cfe02ccc30f8f82e6b2b',
                             'size_bytes': 5033993,
                             'version_id': '1'},
              'bindings_sha256': 'aef0fe381453bf97e6a2fc21b9b680b3521501afe70a5e2e0b671e0685dc6dc2'}}
COMPATIBILITY_SHA256 = digest(canonical(MANIFEST))


def is_comparison(request):
    return request.get("schema_version") in (SCHEMA, REPLACEMENT_SCHEMA)


def is_replacement(request):
    return request.get("schema_version") == REPLACEMENT_SCHEMA


def prerequisites():
    return deepcopy(MANIFEST["prior"])


def artifact_prefix(request, slot):
    if slot == request["slot"] == "inference":
        return (REPLACEMENT_PREFIX if is_replacement(request) else PREFIX) + slot + "/"
    if slot in confirmation.LEGACY_PRIOR:
        return confirmation.LEGACY_PREFIX + slot + "/"
    if slot in confirmation.SLOTS:
        return confirmation.PREFIX + slot + "/"
    raise ValueError("comparison artifact is outside its fixed inputs")


def require_reference(current, slot, success, expected_request_sha):
    if slot == current["slot"] == "inference":
        if expected_request_sha != digest(canonical(current)):
            raise ValueError("comparison self request differs")
    elif {"success": success, "request": {"sha256": expected_request_sha}} != MANIFEST["prior"].get(slot):
        raise ValueError("comparison prerequisite differs from fixed receipt")


def origin_matches(previous, current, slot):
    if slot not in ("inference", *MANIFEST["prior"]):
        return False
    identity = current if slot == "inference" else (
        confirmation.MANIFEST if slot in confirmation.LEGACY_PRIOR else MANIFEST["confirmation_origin"])
    return all(previous.get(k) == identity[k] for k in ("source_commit", "image_digest", "context_public_key"))


def checkpoint_origin(request, prior, current_bindings):
    """Keep original bytes/bindings; admit only the verified seed-42 winner."""
    fixed = MANIFEST["selected"]
    previous = prior[fixed["slot"]]
    winner, original = previous["result"], previous["request"]
    if (not is_comparison(request) or previous["status"] != "verified"
            or winner["status"] != "verified" or winner["trial"] != fixed["trial"]
            or winner["trial_sha256"] != fixed["trial_sha256"]
            or winner["selected_checkpoint"] != fixed["checkpoint"]
            or digest(canonical(winner["bindings"])) != fixed["bindings_sha256"]
            or digest(canonical(original)) != MANIFEST["prior"][fixed["slot"]]["request"]["sha256"]
            or not origin_matches(original, request, fixed["slot"])):
        raise ValueError("comparison checkpoint origin differs")
    expected = {**winner["bindings"], "source_commit": request["source_commit"],
                "image_digest": request["image_digest"]}
    if canonical(current_bindings) != canonical(expected):
        raise ValueError("comparison input or normalization bindings differ")
    return {"slot": fixed["slot"], "request_sha256": digest(canonical(original)),
            "bindings": deepcopy(winner["bindings"]), "trial_sha256": fixed["trial_sha256"],
            "checkpoint": deepcopy(fixed["checkpoint"])}

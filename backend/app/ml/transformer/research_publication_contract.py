"""Dispatch explicit publication compatibility without weakening old contracts."""
from . import research_comparison_contract as comparison
from . import research_confirmation_contract as confirmation


def contract(request):
    return comparison if comparison.is_comparison(request) else confirmation


def is_compatible(request):
    return comparison.is_comparison(request) or confirmation.is_replacement(request)


def artifact_prefix(request, slot):
    return contract(request).artifact_prefix(request, slot)


def require_reference(current, slot, success, expected_request_sha):
    return contract(current).require_reference(current, slot, success, expected_request_sha)


def origin_matches(previous, current, slot):
    return contract(current).origin_matches(previous, current, slot)

"""Assemble the planned steps into one ordered signal chain per price tier.

The order is the one from the spec — Gate/NR → subtractive EQ → compression →
additive EQ → de-ess → saturation → spatial — with two additions and one
severity-driven exception, all documented below.
"""

from __future__ import annotations

from app.db.repository import PluginCatalog
from app.models.schemas import (
    PluginEntry,
    PluginRecommendation,
    Severity,
    SignalChain,
    Tier,
    VocalProfile,
)
from app.recommendation.engine import ProcessingStep, StepRole, plan

#: Canonical signal order.
#:
#: Cleanup first, because everything downstream reacts to noise. Tuning sits early,
#: on the cleaned but uncompressed signal, where pitch trackers work best. Peak
#: control goes last, as a safety net after the spatial send.
CHAIN_ORDER: tuple[StepRole, ...] = (
    StepRole.NOISE_REDUCTION,
    StepRole.GATE,
    StepRole.PITCH,
    StepRole.SUBTRACTIVE_EQ,
    StepRole.COMPRESSION,
    StepRole.ADDITIVE_EQ,
    StepRole.DE_ESS,
    StepRole.SATURATION,
    StepRole.SPATIAL,
    StepRole.LIMITER,
)


def build_chains(
    profile: VocalProfile,
    catalog: PluginCatalog,
    tiers: tuple[Tier, ...] = (Tier.FREE, Tier.MID, Tier.PREMIUM),
) -> list[SignalChain]:
    """One complete chain per tier, from the same plan."""
    steps = order_steps(plan(profile))
    return [SignalChain(tier=tier, steps=_fill(steps, catalog, tier)) for tier in tiers]


def order_steps(steps: list[ProcessingStep]) -> list[ProcessingStep]:
    """Sort the planned steps into signal order, applying the severity exception."""
    by_role = {step.role: step for step in steps}
    order = list(CHAIN_ORDER)

    de_ess = by_role.get(StepRole.DE_ESS)
    if de_ess is not None and de_ess.severity is Severity.CRITICAL:
        # A compressor fed hard esses rides the esses. With sibilance this bad, take
        # them out before the compressor sees them.
        order.remove(StepRole.DE_ESS)
        order.insert(order.index(StepRole.COMPRESSION), StepRole.DE_ESS)

    return [by_role[role] for role in order if role in by_role]


def _fill(
    steps: list[ProcessingStep], catalog: PluginCatalog, tier: Tier
) -> list[PluginRecommendation]:
    """Choose a plugin for each step at this tier, avoiding repeats within the chain."""
    used: set[str] = set()
    recommendations: list[PluginRecommendation] = []

    for step in steps:
        pick = catalog.select(
            category=step.category,
            tier=tier,
            preferred_tags=step.preferred_tags,
            excluded_tags=step.excluded_tags,
            exclude=frozenset() if step.allows_reuse else frozenset(used),
        )
        if pick is None:  # nothing in the catalog for this category at any tier
            continue

        reused = pick.plugin.name in used
        used.add(pick.plugin.name)
        recommendations.append(
            PluginRecommendation(
                plugin_name=pick.plugin.name,
                tier=pick.plugin.tier,
                category=step.category,
                suggested_settings=f"{step.label}: {step.settings_text()}",
                why=_why(step, pick.plugin, reused, pick.substituted_tier, tier),
                price=pick.plugin.price,
                purchase_url=pick.plugin.purchase_url,
            )
        )
    return recommendations


def _why(
    step: ProcessingStep,
    plugin: PluginEntry,
    reused: bool,
    substituted: bool,
    asked_tier: Tier,
) -> str:
    """Why this step exists, and why this plugin fills it."""
    parts = [step.reason_text()]
    if reused:
        parts.append(f"A second instance of {plugin.name}, doing a different job here.")
    else:
        parts.append(f"{plugin.why}.")
    if substituted:
        parts.append(
            f"Nothing in the catalog covers this at the {asked_tier.value.lower()} tier, so "
            "this is the pick regardless of tier — it is worth owning anyway."
        )
    return " ".join(part for part in parts if part)

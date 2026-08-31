# 2026-08-31 — Rardar Discover Signal Calibration and Navigation

## Goal

Consume Rardar's calibrated `trending-discover-v2` proof without duplicating
its selection policy, then make the resulting early-signal surface directly
navigable and explorable while keeping Today unchanged.

## Producer boundary

Rardar merge `deb65469c963d80cacab352dcea4cbf9b1187996` is the fact authority.
Its simple publish condition is an absolute-growth or relative-growth gate,
combined with continuous positive Observation evidence for growth stages. The
artifact records recomputable signal facts, publish reasons and aggregate
suppression reasons. TopicEye vendors that exact contract and validates its
pointer, manifest, hashes, source binding, stage/order proof, policy constants
and suppression invariants. It does not infer missing candidates or rerun the
producer gate.

V1 remains readable for rollback compatibility. V1 uses the existing complete
mechanical replay; v2 uses its versioned producer proof. Neither path performs
24-hour extrapolation, AI ranking or database writes.

## Static Serving and category contract

The immutable Discover Serving projection reuses the existing canonical
identity, positioning, capabilities and evidence. Serving v2 adds a single
deterministic category with its source mode and evidence references. Profile
facts take precedence, GitHub metadata is the fallback signal, and an explicit
`other` category represents no match. Category affects only client-side
filtering; it cannot affect selection, stage or order.

Normal collection and detail requests still perform zero GitHub calls, zero
model calls, zero raw-artifact reads and zero PostgreSQL fact writes. Today and
Discover retain independent raw and Serving pointers.

## Product behavior

- the labels are 刚刚发现, 持续升温 and 待日榜验证;
- cards expose the actual window, delta and continuity instead of a proxy 24h
  value;
- the whole card is mouse/touch and keyboard navigable, while the title and
  GitHub links keep independent legal link behavior;
- the fixed category filter is URL-backed and preserves producer order;
- the Discover detail starts with `DiscoverFactContext`, including first/latest
  observation, capture continuity, positive intervals, latest interval, next
  Observation, next Today settlement and a deterministic not-in-Today reason;
- canonical profile, opt-in AI insight and Find Project remain shared product
  capabilities, but Today rank and Today 24h facts are absent.

## Isolation and rollback

This iteration adds no table, migration, model route or credential change. It
does not change Today facts, profiles, detail behavior or UI. Publication stays
pointer-based: any adapter, profile, category, schema or activation failure
leaves the previous immutable Discover Serving active. Production activation
remains a separate task.

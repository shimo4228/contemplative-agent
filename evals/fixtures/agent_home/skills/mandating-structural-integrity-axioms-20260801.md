---
name: assume-perfect-adversarial-understanding
description: "Shift system design discussions from proving functionality or detecting failure to structurally guaranteeing impossibility."
origin: auto-extracted
---

# Mandating Structural Integrity Axioms

**Context:** When discussing complex systems, security architecture, or foundational trust models where simple verification is insufficient against sophisticated threats.

## Problem
Current threat modeling often focuses on known attack vectors (detection) or measurable failures (exfiltration). This approach fails to account for the most advanced risk: that an adversary possesses complete, perfect knowledge of the system's internal mechanisms and intended safeguards, rendering standard "transparency" or mere detection architectures irrelevant.

## Solution
Adopt a framework that forces the assumption of maximum adversarial capability. The solution mandates shifting focus from *detecting* failure to *structurally eliminating* the possibility of specific types of harm—specifically compromising authorization boundaries (trust boundary violation) or generating actionable knowledge about systemic flaws. This requires defining constraints that ensure, rather than merely report on, system impossibility in key areas.

## When to Use
RECURRING STRUCTURAL conditions:
1.  During any architectural review where the discussion shifts from "how we can prevent data leakage" to "what happens when an insider with elevated access attempts a targeted structural compromise."
2.  When analyzing or defining trust boundaries between independent components (users, assistants, models) and determining if the core vulnerability is compromised *data* versus compromised *authorization*.
3.  Any time the conversation around security mechanisms stalls at basic verification techniques; the discussion must pivot to preemptively constraining potential harm rather than accumulating knowledge of that failure.

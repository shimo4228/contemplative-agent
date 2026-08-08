---
name: mapping-systemic-dependency-failures
description: "Diagnose system failures by mapping necessary causal, temporal, or structural constraints rather than inspecting isolated components."
origin: auto-extracted
---

# Mapping Systemic Dependency Failures

**Context:** Analyzing the failure modes of complex, multi-stage, or highly coupled systems (e.g., data pipelines, software architectures, operational processes).

## Problem
The tendency to attribute failures solely to functional bugs, resource shortages, or isolated component errors, thereby missing the underlying structural flaw in how dependencies (temporal, causal, or sequential) were designed or assumed. This leads to superficial fixes that do not address the root vulnerability of the system architecture itself.

## Solution
Shift the focus from validating individual component states ("Does Component A work?") to identifying and mapping all necessary relationships between components/steps ("For Component B to succeed, does Component A *necessarily* have completed in this specific manner before time T?"). The true vulnerability is found by treating dependency connections themselves as critical components subject to failure.

## When to Use
When a reported failure suggests that data or functionality was missing or incorrect, but the system components involved all appear nominally functional. Specifically, use this skill when:
1. A workflow relies on output X from Step Y (Causal Dependency), and diagnosing why X is wrong requires tracing back through multiple non-obvious structural prerequisites.
2. An operation only yields meaningful results if a sequence of events must occur in strict temporal order, or if the start time of one action is contingent upon another having finished (Temporal Constraint).
3. The system's overall integrity relies on an assumption about data flow or state that cannot be verified by checking any single boundary check or isolated log entry (Structural/Epistemological Failure).

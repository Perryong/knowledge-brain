---
type: concept
title: "OWASP Top 10 for LLM Applications 2025"
updated: 2026-07-27
tags:
  - concept
  - security
  - owasp
  - llm
status: evergreen
confidence: high
related:
  - "[[SSDLC for AI Systems]]"
  - "[[OWASP Top 10 for LLM Applications 2025 Source]]"
  - "[[Research AI Engineer Role 2026]]"
---

# OWASP Top 10 for LLM Applications 2025

**Angle 3 (security core)** — the security risks an AI engineer designs against. Edition document dated **2024-11-17** (Source: [[OWASP Top 10 for LLM Applications 2025 Source]]). Confidence: **high**.

| ID | Risk | Note |
|---|---|---|
| LLM01 | **Prompt Injection** | #1 for the second edition running |
| LLM02 | **Sensitive Information Disclosure** | jumped 6th → 2nd in 2025 |
| LLM03 | **Supply Chain** | model weights, base images, plugins |
| LLM04 | **Data and Model Poisoning** | training/fine-tune data integrity |
| LLM05 | **Improper Output Handling** | downstream injection via unvalidated output |
| LLM06 | **Excessive Agency** | over-broad tool/permission scope in agents |
| LLM07 | **System Prompt Leakage** | new in 2025 |
| LLM08 | **Vector and Embedding Weaknesses** | RAG-store poisoning / leakage |
| LLM09 | **Misinformation** | hallucination as a security/reliability risk |
| LLM10 | **Unbounded Consumption** | DoS, cost exhaustion, model extraction (new/reworked) |

## What changed in 2025
Two new categories (system-prompt leakage, unbounded consumption), reordering by community feedback, and consolidation of overlapping entries — driven by real-world incidents and the rise of **agentic AI**. Confidence: high.

> [!gap] Item names are corroborated across multiple 2026 security write-ups; the exact LLM0x ordering should be confirmed against the downloaded OWASP PDF before use in a formal audit.

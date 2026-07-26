---
type: concept
title: "SSDLC for AI Systems"
updated: 2026-07-27
tags:
  - concept
  - security
  - ssdlc
  - cicd
  - iac
status: evergreen
confidence: medium
related:
  - "[[Research AI Engineer Role 2026]]"
  - "[[OWASP Top 10 for LLM Applications 2025]]"
  - "[[AI Governance and Compliance 2026]]"
---

# SSDLC for AI Systems

**Angle 3** — how secure SDLC, CI/CD, Git workflow, IaC, and cloud deployment change when the artifact is an AI system.

## What changes vs traditional software
- **The prompt/model is code.** CI/CD must version and test **prompts, model versions, and eval suites**, not just application code. A prompt change is a deployable behavioral change and needs a gated eval run. Confidence: medium.
- **Evals are the test suite.** Regression = eval-score drop. Observability covers token cost, latency, hallucination rate, and tool-call correctness — not just uptime. Confidence: medium.
- **Supply chain widens.** Model weights, base images, and third-party tools/plugins are dependencies with provenance risk (maps to OWASP **LLM03 Supply Chain** and **LLM04 Data/Model Poisoning**, see [[OWASP Top 10 for LLM Applications 2025]]). Confidence: high.
- **Secrets in agentic systems.** Agents that call tools/APIs need least-privilege credentials and bounded scopes — over-broad tool access is OWASP **LLM06 Excessive Agency**. Confidence: high.
- **IaC for AI workloads.** Terraform/CDK provision GPU inference endpoints, VPC isolation, IAM, and model gateways. In SG/GovTech this is a **core AI-engineer skill**, not a platform-team hand-off (Source: [[AI Engineer Demanded Skillset 2026]]). Confidence: medium.

## Compliance layer
Secure-SDLC evidence feeds governance regimes — SG [[IMDA AI Verify]] process checks, MAS guidance for financial services, and the EU AI Act (see [[AI Governance and Compliance 2026]]). Confidence: high.

> [!gap] There is no single authoritative "SSDLC-for-AI" standard yet; practice is assembled from OWASP LLM Top 10 + conventional DevSecOps + emerging LLMOps tooling. Treat framework-level claims as medium confidence.

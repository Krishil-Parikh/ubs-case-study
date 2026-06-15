
# Data Generation Manifest

This document details the prompts used to synthesize the financial security corpus. These prompts were engineered to intentionally embed **conflicts, population mismatches, and bias**, providing the necessary "adversarial noise" for the Skeptic (A8) and Applicability (A7) agents to detect and resolve.

---

## 1. Wikipedia Synthesis (Baseline Knowledge)
**Context:** Used to generate `wikipedia.md` (WK-001 to WK-100).
**Role:** Encyclopedic Baseline.
**Prompt:**
> "Act as a Wikipedia Editor specializing in FinTech. Generate 100 entries defining core banking security concepts. 
> **Focus:** Multi-Factor Authentication (MFA), FIDO Alliance standards, Real-Time Gross Settlement (RTGS), and the history of biometric sensors. 
> **Requirement:** Maintain a strictly neutral, objective tone. Cite historical dates (e.g., PSD2 implementation in 2018) and standard bodies (ISO/IEC). These entries serve as the 'Ground Truth' for term definitions in the 11-agent pipeline."

---

## 2. Research Paper Synthesis (Reliability Benchmarking)
**Context:** Used to generate `research_papers.md` (RP-001 to RP-100).
**Role:** Technical/Peer-Reviewed Evidence.
**Prompt:**
> "Act as a Technical Librarian. Generate 100 simulated abstracts for peer-reviewed papers on mobile banking security. 
> **Focus:** Statistical metrics like False Acceptance Rate (FAR), False Rejection Rate (FRR), and encryption vulnerabilities. 
> **Adversarial Requirements:** 
> 1. **Temporal Decay:** Include 15% 'Outdated' entries (pre-2021) to test if the system identifies them as obsolete compared to 2024 news.
> 2. **Applicability Mismatch:** Include 10% entries where the study population is specialized (e.g., 'Identical Twins' or 'Elderly Populations') to test the Demographic Agent (A7)."

---

## 3. News & Breach Report Synthesis (Recency Bias)
**Context:** Used to generate `news.md` (NW-001 to NW-100).
**Role:** Current Event Signals.
**Prompt:**
> "Act as a Financial Technology Journalist. Generate 100 headlines and snippets from 2023-2024. 
> **Focus:** Real-world failures: voice-auth deepfakes, SIM-swap rings, and Faster Payment fraud.
> **Adversarial Requirements:** 
> 1. Ensure a sensationalist tone to test the Reliability Agent's (A4) ability to filter emotional noise from factual metrics.
> 2. Create direct contradictions with vendor claims (e.g., News reports a breach that a vendor claims is impossible)."

---

## 4. Blog & Forum Synthesis (Anecdotal Noise)
**Context:** Used to generate `blogs_and_forums.md` (BL-001 to BL-100).
**Role:** Qualitative/Unverified Data.
**Prompt:**
> "Act as various cybersecurity forum members (Reddit/StackExchange). Generate 100 posts. 
> **Focus:** Anecdotes of 'getting scammed' and DIY 'hacker' guides to fingerprint spoofing.
> **Adversarial Requirements:** 
> 1. Include 'Overconfidence Bias' (e.g., 'Biometrics are 100% safe').
> 2. Include 'Anecdotal Fallacies' that contradict Wikipedia definitions, testing the Contradiction Agent (A6)."

---

## 5. Vendor Whitepaper Synthesis (Commercial Bias)
**Context:** Used to generate `vendor_whitepapers.md` (CM-001 to CM-100).
**Role:** Biased/Promotional Claims.
**Prompt:**
> "Act as a Marketing Director for a Security Startup. Generate 100 promotional claims for auth software.
> **Focus:** Selling 'Liveness Detection' and 'AI-Shields.'
> **Adversarial Requirements:** 
> 1. Make absolute claims (e.g., '0% False Rejection') without methodology.
> 2. These entries provide the 'Bias Trap' that the Skeptic Agent (A8) must identify and down-weight in the ERS calculation."

# `#sec-triage` excerpt

**Mara, Security:** One pattern resembles credential stuffing, especially the rotating IPs. We also have upstream IdP latency, so this may be two overlapping issues.

**Devon, SRE:** Rate-limit change helped but did not eliminate failures.

**Mara:** Treat credential stuffing as a hypothesis. I have not found account takeover or a confirmed malicious campaign. We need an Incident Commander before external classification.

**Support bot:** 27 customer tickets reference login or MFA loops.

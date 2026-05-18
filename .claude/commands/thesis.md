---
description: Evaluate a thesis against the personal knowledge base via Probe's RAG
---

Use the Probe MCP server's `evaluate_thesis` tool to judge the following claim against my personal knowledge base. Pass the entire argument string as `claim_or_id`; the tool will resolve it as a stored thesis id if it matches one, otherwise treat it as an ad-hoc claim.

Claim: $ARGUMENTS

After the tool returns, summarize the verdict, the reasoning, and quote the supporting and contradicting chunks with their source titles.

# Version Isolation Governance

SectorBreaker has a hard project-memory rule after the V2 Agent Kernel cutover
incident:

- Do not build a new Agent architecture by gradually patching the old workflow
  spine.
- Do not leave old executable workflow code reachable from production imports.
- For personal `domain_knowledge` auto-run, the production owner is the V2
  Agent Kernel: `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`.
- Historical workflow code may remain only as documentation or explicitly
  archived material that production code cannot import.
- Runtime legacy-event guards are smoke alarms only. They are not a substitute
  for deleting or isolating old paths.
- Before claiming an Agent rewrite is ready, run the real user path and inspect
  exported Markdown, not only unit tests.
- If old markers such as `Knowledge Builder`, `Document Writer`,
  `specialist_react_loop`, `EV-V1-`, `ART-V1-`, or `已使用保底` appear in a new
  personal auto-run, treat it as an architecture regression.

Future agents must read `docs/20-version-isolation-and-cutover-rules.md` before
changing Agent entrypoints, workflow definitions, or product-mode routing.


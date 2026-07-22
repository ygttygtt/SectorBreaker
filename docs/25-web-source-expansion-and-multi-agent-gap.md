# Web Source Expansion And Multi-Agent Gap Review

## Decision

SectorBreaker should keep web acquisition as replaceable layers instead of
embedding a crawler product into the Agent Kernel:

```text
SearchProvider (discover URLs)
  -> ContentExtractionProvider (read selected URLs)
  -> SourceVerificationProvider (assess evidence quality)
  -> Evidence / SourceMemory / local Hybrid RAG
```

Firecrawl is a useful addition, but it does not replace Tavily by itself. It can
serve both discovery and extraction; Tavily, Brave, Exa, Serper, or a future
SearXNG adapter can provide complementary result sets. `multi` must query
providers concurrently and merge them fairly, otherwise the first configured
provider silently dominates the source pool.

The V3 production Agent now executes the first two layers for selected search
results: `search_web` post-filters canonical hosts, extracts up to three
readable pages through the configured extraction Provider, and persists body
text plus provenance on Evidence. Source assessment remains a quality signal;
it does not verify claims.

## Firecrawl Assessment

Firecrawl exposes search, single-page scrape, site map, crawl, batch scrape,
and structured extraction. Its search endpoint can return URLs/descriptions or
also scrape result pages. SectorBreaker intentionally keeps search results
lightweight and uses the extraction provider only after the Agent selects a URL.
This preserves explicit budgets and evidence metadata.

Recommended use now:

- configure Firecrawl as `search_provider_mode=firecrawl` or as one member of
  `multi`;
- optionally select Firecrawl as the content extraction provider with the same
  API key;
- use source-pack domains or `preferred_domains` for targeted official-site
  searches;
- do not ingest an entire site automatically without a crawl/map budget,
  deduplication, robots/policy rules, and a document persistence contract.

Self-hosting is not the default recommendation. The upstream repository uses
AGPL-3.0 and its full deployment includes browser/queue infrastructure. A hosted
API or separately deployed service is easier to isolate at the provider boundary.

Primary references:

- Firecrawl repository and license: <https://github.com/firecrawl/firecrawl>
- Firecrawl v2 Search API: <https://docs.firecrawl.dev/api-reference/endpoint/search>
- Firecrawl GitHub scrape/map/crawl examples:
  <https://docs.firecrawl.dev/developer-guides/common-sites/github>

## Other Projects Considered

| Project | Best fit | Recommendation |
| --- | --- | --- |
| SearXNG | Self-hosted meta-search and source diversity | Add later as a `SearchProvider`; useful local/private fallback, but public instances are unreliable and extraction is separate. |
| Crawl4AI | Python-native browser crawling and Markdown extraction | Strong self-hosted `ContentExtractionProvider`/future site-crawl adapter; heavier than the current HTTP/Jina path. |
| Jina Reader | Low-friction URL-to-Markdown and web search | Keep current Reader extraction; consider a separate authenticated Jina Search adapter after Firecrawl evaluation. |
| Crawlee Python | Programmable durable crawling, queues, proxies, Playwright | Best when SectorBreaker needs custom monitored connectors, not as a simple general search API. |
| Apify Actors | Hosted catalog of site-specific crawlers | Consider for difficult named sites with stable Actor contracts and explicit cost/credential policy. |

References:

- SearXNG: <https://github.com/searxng/searxng>
- Crawl4AI: <https://github.com/unclecode/crawl4ai>
- Jina Reader: <https://github.com/jina-ai/reader>
- Crawlee Python: <https://github.com/apify/crawlee-python>
- Apify API: <https://docs.apify.com/api/v2>

## Dedicated Source Sites

The prior registry mixed three different states: executable connectors,
search-domain packs, and roadmap entries. Entries without required keys were
often shown as configured even when no adapter existed.

The current contract distinguishes:

- `ready_via_search`: executable through a configured SearchProvider with
  domain constraints;
- `ready`: an implemented extraction adapter is configured;
- `needs_search_provider` / `needs_configuration`: implementation exists but
  runtime configuration is missing;
- `manual_review`: intentionally human-operated;
- `planned` / `configured_but_unwired`: catalog or credential exists, but no
  production adapter executes it.

The configuration UI can load a source pack into the real search self-test.
The Agent `search_web` tool accepts `preferred_domains`, so a domain pack is an
execution constraint rather than a decorative list.

## Multi-Agent Implementation Audit

Implemented:

- one Master Agent owns State and chooses tools dynamically;
- `vault_auditor`, `researcher`, `verifier`, and `knowledge_editor` are typed,
  task-scoped Specialist roles;
- up to four independent Specialist calls run concurrently;
- role tool allowlists reject unsafe recommendations;
- Specialists cannot write files or apply ChangeSets;
- each Specialist now receives bounded active-artifact context plus local
  project retrieval results;
- structured result summaries, evidence ids, recommendations, and proposed
  change paths persist in the delegation log.

Partially implemented:

- Specialist recommendations are returned to the Master, but Specialists do
  not yet run an independent multi-turn ReAct loop;
- external search is still executed by the Master tool dispatcher rather than
  a per-Specialist budgeted dispatcher;
- findings are typed in the observation, but claim/open-question/ChangeSet
  promotion still depends on a later Master decision;
- verifier behavior lacks a deterministic claim-level corroboration and
  counterevidence acceptance gate.

Next priorities:

1. Add a bounded Specialist tool dispatcher with per-task search/retrieval
   budgets and typed observations.
2. Validate and promote Specialist findings into StateDelta or ChangeSet
   proposals without parsing prose.
3. Add delegation quality metrics: useful evidence gain, duplicate work,
   recommendation follow-through, latency, and cost.
4. Add Firecrawl map/crawl only after a site-crawl request schema, URL/page
   limits, robots/policy behavior, persistence, and acceptance tests exist.

# Evidence completeness v2

Repeated findings on separate pages previously collapsed into a single recommendation that retained only the first page's evidence. Equivalent recommendations now merge distinct rationale and evidence, preserving affected pages without duplicating identical observations. Different actions or provenance classes remain separate.

Version `free-readiness-preview-v2` also lowers short-text, missing-description and missing-schema heuristics to low-priority reviews. It calls out JavaScript-rendering limitations and removes guaranteed title/snippet character-count advice. Title guidance follows https://developers.google.com/search/docs/appearance/title-link and description guidance follows https://developers.google.com/search/docs/appearance/snippet.

Deploy the paired queryclear frontend aggregate-evidence compatibility release before this runtime release. Its bounded evidence/rationale fields support five-page aggregation. Existing cached v1 reports remain unchanged; compare report versions before attributing a changed priority to website changes.

Offline tests cover multiple pages, duplicate observations, distinct fixes with identical titles, and low-confidence heuristic severity. They are regression fixtures, not a claim of measured model accuracy. No new providers, scheduled model calls, secrets, data migrations or infrastructure changes are introduced.

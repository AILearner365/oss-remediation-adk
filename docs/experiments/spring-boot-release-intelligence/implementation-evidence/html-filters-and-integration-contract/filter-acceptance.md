# HTML filter acceptance

## Accepted behavior

- Exactly four approved tables remain; names, order, column labels and meanings
  are unchanged.
- Every one of the 34 headers has an accessible filter/sort button.
- Text menus provide search, distinct values, select/deselect all, multi-value
  selection, apply, clear, A–Z and Z–A sorting.
- Numeric columns use numeric rather than lexicographic ascending/descending
  order and support distinct-number checkbox selection.
- Multiple values within a column use OR; active columns combine using AND.
- Active filters have a visual indicator. Each table has Reset All Filters and
  an `aria-live` visible/total row count.
- Table headers remain sticky inside horizontally and vertically scrollable
  table regions. Menus are positioned within viewport edges.
- Escape, outside click, and the menu actions close the dropdown. Native
  buttons, inputs, labels and focus restoration provide keyboard operation.
- Table 4's existing release selector loads only the retained comparison rows,
  updates its two candidate headers, rebuilds distinct values, and clears stale
  filters/sorting. It never invokes Maven or a scanner.
- Cell rendering and dynamic Table 4 updates use escaped HTML or `textContent`.
  Tests include hostile dependency/advisory text.

## Security semantics

Filtering and sorting only reorder or hide existing DOM rows. They do not
recalculate ranks, totals, severities, outcomes, advisory identities, or
dependency ownership. The real source `result.json` was not copied or modified.
The behavior test confirmed the actual 3-release, 62-dependency artifact retains
its displayed security values while filtered.

## Interaction evidence

The committed `tests/js/test_sbri_filters.js` was executed against the retained
`report.html` using a disposable Node.js 22.20.0/jsdom 27.0.1 environment. It
performed actual DOM clicks, checkbox changes, search input, sorting, reset,
release selection, keyboard Escape, and outside-click events. All checks passed.

## Limitations

- Numeric equals/greater-than/less-than predicates were deliberately omitted;
  numeric distinct-value filtering and numeric sorting satisfy the bounded
  requirement without adding a second query language.
- The menu is keyboard-operable but does not implement a modal focus trap or
  spreadsheet-specific arrow-key grid navigation.
- Validation used a standards-oriented DOM implementation because no graphical
  browser was installed. Layout-specific visual checks are limited to generated
  CSS and viewport-positioning logic; functional interaction was executed.

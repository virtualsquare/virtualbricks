# Bugs

Bugs of the site found and not fixed yet, each with how it was seen. A fixed
one leaves the list.

## Documentation

- [ ] **Links to pages that aren't on the site.** The pages of the
  Documentation are those of `docs/` in `develop`, which link to each
  other; three of them aren't here yet (`vbp-format.html` since the pages
  were refreshed from `develop` 4add7e07, 12 Oct):

  | Page | `command-line.html` | `archive-protocol.html` | `vbp-format.html` |
  |---|---|---|---|
  | `config-files.html` (published) | 5, to `#control-socket` and `#windows` too | 1 | 1 |
  | `control-protocols.html` (published) | 9, to `#commands` and `#control-socket` too | 1 | 1 |

  The fix is to add `docs/command-line.html`, `docs/archive-protocol.html`
  and `docs/vbp-format.html` of `develop` as `config-files.html` was: the body unchanged, the
  `<style>` in a stylesheet beside it, the head of Pelican's metadata. The
  anchors are in `develop`'s `command-line.html`.

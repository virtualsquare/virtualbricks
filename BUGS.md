# Bugs

Bugs of the site found and not fixed yet, each with how it was seen. A fixed
one leaves the list.

## Documentation

- [ ] **Links to pages that aren't on the site.** The pages of the
  Documentation are those of `docs/` in `develop`, which link to each
  other; two of them aren't here yet:

  | Page | `command-line.html` | `archive-protocol.html` |
  |---|---|---|
  | `config-files.html` (published) | 5, to `#control-socket` and `#windows` too | 1 |
  | `control-protocols.html` (draft) | 9, to `#commands` and `#control-socket` too | 1 |

  The fix is to add `docs/command-line.html` and `docs/archive-protocol.html`
  of `develop` as `config-files.html` was: the body unchanged, the
  `<style>` in a stylesheet beside it, the head of Pelican's metadata. The
  anchors are in `develop`'s `command-line.html`.

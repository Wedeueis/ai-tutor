---
type: MOC
title: Home
description: Root map of content — curated, thematic entry point into the vault.
generated:
  by: human:wedeueis
  at: '2026-08-17T00:00:00+00:00'
---

# Home

The curated entry point into the wiki. Unlike index.md, which lists the
bundle's physical directory contents, this MOC organizes concepts by theme
through hand-picked links — the hierarchy here is a link graph, not a folder
tree (see §6 of the OKF spec).

Sub-MOCs (MOCs of MOCs) can be added under their own headings as themes
accumulate enough concepts to warrant one.

# Areas

Empty for now. The bundle was reset, and Domains are machine-derived — they
reappear as ingest classifies new concepts, and get linked here by hand once
a theme is worth navigating to.

This file is **hand-authored**, unlike everything else `pipeline` writes. It is
also, for that reason, the one thing `pipeline clear` destroys that no re-ingest
can bring back: `clear` walks the bundle deleting concepts, and a `type: MOC`
document is a concept like any other. Worth knowing before the next reset.

# CircadianIQ Architecture Notes

This file will accumulate architecture decisions as later phases are
implemented (database schema design, model design, fusion strategy,
etc.). It is intentionally minimal in Phase 1.

## Locked architecture (Phase 1)

```
SQL database
    |
Python computational pipeline
    |
SQL database
```

SQL is the authoritative source of truth. Python owns feature
engineering, ML inference, circadian state computation, DLMO fusion,
alignment calculation, contributor ranking, recommendation selection,
personalization, and safety logic.

See the top-level README.md for what Phase 1 does and does not cover.

# Quick Start: Ruhusa v0.7.0 Validation

## One-time Setup (PostgreSQL)

```bash
docker compose up -d postgres
export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"
```

(See `POSTGRES_SETUP.md` for detailed instructions)

## Run Validation

```bash
# In-memory only (fast, ~1s)
uv run pytest tests/ -v -m "not postgres"

# Full suite with PostgreSQL (~1s)
uv run pytest tests/ -v

# Stop PostgreSQL when done
docker compose down
```

## Expected Results

✓ 43 in-memory tests  
✓ 6 PostgreSQL tests  
⊘ 1 skipped (tamper detection)  

**Total: 49 PASS, 1 SKIP**

## Review Results

```bash
cat RUHUSA_V0_7_VALIDATION.md
```

## For Future Releases

1. Update version in `pyproject.toml` (change `tag = "vX.Y.Z"`)
2. Run: `docker compose up -d postgres`
3. Run: `export RUHUSA_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/ruhusa_demo"`
4. Run: `uv run pytest tests/ -v`
5. Review: `RUHUSA_V0_7_VALIDATION.md`

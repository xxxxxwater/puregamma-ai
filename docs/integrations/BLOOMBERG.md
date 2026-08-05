# Bloomberg

Bloomberg support is planned for enterprise/private deployments where the customer has appropriate licensed data access. PureGamma AI must not bypass data licensing restrictions.

Bloomberg-derived research is still research only and not financial advice.

## Configuration

```text
BLOOMBERG_ENABLED=false
BLOOMBERG_DATA_DIR=
BLOOMBERG_SFTP_HOST=
BLOOMBERG_SFTP_USER=
BLOOMBERG_SFTP_PRIVATE_KEY=
```

## Current Status

No Bloomberg backend adapter is implemented. The frontend fallback data-source page includes Bloomberg as a mock import/source requiring enterprise setup.

## Supported Deployment Pattern

Preferred enterprise model:

1. Customer exports licensed files to a controlled directory or SFTP drop.
2. PureGamma private deployment ingests those files.
3. Parser validates schema, timestamp, and license boundary.
4. Normalized data is stored with source attribution.
5. Reports include source freshness.

## Security

- Keep Bloomberg files in private enterprise environment.
- Restrict SFTP keys and data directory permissions.
- Do not expose raw licensed data in logs.
- Retain only data allowed by customer contract.

## Troubleshooting

- File missing: check export schedule and SFTP.
- Schema mismatch: quarantine file and alert admin.
- Stale import: mark Bloomberg source stale and continue without it.
- License question: stop ingestion until customer confirms usage rights.

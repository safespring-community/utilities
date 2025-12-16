# OpenStack Migration Utilities

Utilities for migrating OpenStack resources (volumes, instance snapshots) between Safespring cloud platforms (v1 to v2).

## Prerequisites

- Python 3.10+
- `qemu-img` (from qemu-utils package)
- OpenStack `clouds.yaml` configuration
- Sufficient disk space (2x the size of resources being migrated)

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# For development (includes test dependencies)
pip install -r requirements-dev.txt
```

## Configuration

Configure your OpenStack clouds in `~/.config/openstack/clouds.yaml`:

```yaml
clouds:
  v1:
    auth:
      auth_url: https://v1.example.com:5000/v3
      username: myuser
      password: mypassword
      project_name: myproject
      user_domain_name: Default
      project_domain_name: Default
    region_name: region1

  v2:
    auth:
      auth_url: https://v2.example.com:5000/v3
      username: myuser
      password: mypassword
      project_name: myproject
      user_domain_name: Default
      project_domain_name: Default
    region_name: region2
```

## Usage

### Volume Migration

```bash
# Interactive selection
python migrate.py volume v1 v2

# Migrate specific volume
python migrate.py volume v1 v2 --volume my-volume

# Migrate multiple volumes (batch mode)
python migrate.py volume v1 v2 --volume "vol1,vol2,vol3"

# Dry run to preview actions
python migrate.py volume v1 v2 --dry-run

# Skip confirmation prompts
python migrate.py volume v1 v2 --volume my-volume --yes

# Resume interrupted migration
python migrate.py volume v1 v2 --resume
```

### Snapshot/Image Migration

```bash
# Interactive selection
python migrate.py snapshot v1 v2

# Migrate specific image
python migrate.py snapshot v1 v2 --image my-snapshot

# Migrate multiple images
python migrate.py snapshot v1 v2 --image "snap1,snap2,snap3"

# Dry run
python migrate.py snapshot v1 v2 --dry-run
```

### Common Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview actions without executing |
| `--yes`, `-y` | Skip confirmation prompts |
| `--insecure` | Disable SSL certificate verification |
| `--log-file PATH` | Log file path (default: migration.log) |
| `--verbose`, `-v` | Increase verbosity (use -vv for debug) |
| `--resume` | Resume from last saved state |
| `--no-cleanup` | Keep temp files on failure |
| `--work-dir PATH` | Working directory for temp files |

### Status and Cleanup

```bash
# Show current migration state
python migrate.py status

# Clear saved migration state
python migrate.py clean
```

## Migration Scenarios

### Instance boots from image (no additional volumes)
1. Shut down the instance
2. Take an instance snapshot
3. Boot the instance back up
4. Run: `python migrate.py snapshot v1 v2 --image my-snapshot`

### Instance boots from volume
1. Shut down the instance
2. Create a volume snapshot
3. Boot the instance back up
4. Create a volume from the snapshot
5. Run: `python migrate.py volume v1 v2 --volume my-volume`

### Instance with additional data volumes
1. Shut down the instance
2. Take an instance snapshot
3. Create volume snapshots for all attached volumes
4. Boot the instance back up
5. Create volumes from all snapshots
6. Run: `python migrate.py snapshot v1 v2 --image my-snapshot`
7. Run: `python migrate.py volume v1 v2 --volume "vol1,vol2,vol3"`

## Features

- **Progress bars**: Visual progress for downloads, uploads, and conversions
- **Resume capability**: Interrupted migrations can be resumed with `--resume`
- **Batch mode**: Migrate multiple resources in one command
- **Dry run**: Preview actions before executing
- **Graceful interrupts**: Clean up on Ctrl+C
- **Retry logic**: Automatic retries with exponential backoff
- **Disk space checks**: Validates sufficient space before starting
- **Detailed logging**: Configurable verbosity with file logging

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_volume.py

# Run with coverage
pytest --cov=migration

# Run specific test
pytest tests/test_volume.py::TestMigrateSingleVolume::test_dry_run
```

## Legacy Scripts

The original shell scripts are preserved in the `legacy/` directory for reference:
- `legacy/migrate-data-vol.sh`
- `legacy/migrate-instance-snapshot.sh`
- `legacy/unset.sh`

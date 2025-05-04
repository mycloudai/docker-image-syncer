# Docker Image Sync Tool

This is an automated tool for syncing public Docker images to your private Docker registry. It uses GitHub Actions for daily scheduled execution and also supports trigger on code commits.

## Features

- 🔄 Automatically sync specified Docker images
- ⏰ Daily scheduled execution (UTC time)
- 🚀 Support manual trigger and code commit trigger
- 🔒 Secure credential storage using GitHub Secrets
- 📝 Support custom target image names
- 🖥️ Support platform architecture specification

## Configuration File Format

Create a `sync-config.yaml` file in the project root directory:

```yaml
images:
  - source: kasmweb/nginx:1.25.3
    platform: linux/arm64
  - source: postgres:15
    target: a-postgres:15
    platform: linux/amd64
  - source: allanpk716/chinesesubfinder
  - source: linuxserver/jackett
  - source: diluka/nas-tools:2.9.1
```

Field descriptions:
- `source`: Source image address (required)
- `target`: Target image name (optional, defaults to source image name)
- `platform`: Specified platform architecture (optional, defaults to current system architecture)

## Usage Steps

### 1. Fork this Repository

Click the Fork button in the upper right corner to fork the repository to your GitHub account.

### 2. Configure GitHub Secrets

Add the following Environment Secrets in your repository settings:

- `TARGET_REGISTRY`: Target Docker registry address (e.g., `registry.example.com`)
- `TARGET_NAMESPACE`: Target namespace (e.g., `myproject`)
- `REGISTRY_USERNAME`: Docker registry username
- `REGISTRY_PASSWORD`: Docker registry password

### 3. Modify Configuration File

Edit the `sync-config.yaml` file to add the list of images you need to sync.

### 4. Enable GitHub Actions

Ensure that the Actions feature is enabled in your repository. The sync task will:
- Execute automatically at 00:00 UTC daily
- Execute on each code commit
- Support manual trigger

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── sync-images.yml    # GitHub Actions workflow configuration
├── scripts/
│   └── sync.py               # Image sync script
├── sync-config.yaml          # Image sync configuration file
├── requirements.txt          # Python dependencies
└── README.md                 # This document
```

## How the Sync Script Works

1. Read the `sync-config.yaml` configuration file
2. Login to the target Docker registry
3. Iterate through the image list:
   - Pull the source image
   - Re-tag as the target image name
   - Push to the target registry
4. Record sync results

## Manual Trigger Sync

1. Go to the Actions page of the repository
2. Select the "Sync Docker Images" workflow
3. Click the "Run workflow" button
4. Select the branch and run

## Logging and Monitoring

- Sync logs can be viewed in the GitHub Actions run history
- Failed sync tasks will show a red mark on the Actions page
- It's recommended to set up GitHub notifications to receive sync failure alerts

## FAQs

### Q: How to handle private source images?
A: You can add `SOURCE_REGISTRY_USERNAME` and `SOURCE_REGISTRY_PASSWORD` in GitHub Secrets and add source registry login logic in the script.

### Q: How to modify the sync schedule?
A: Edit the cron expression in the `.github/workflows/sync-images.yml` file.

### Q: What to do if sync fails?
A: Check the Actions logs. Common causes include:
- Network issues
- Authentication failure
- Image not found
- Insufficient disk space

## Contributing

Issues and Pull Request are welcome to improve this tool!

## License

MIT License

---

## Tech Stack

- Python 3.9+
- Docker SDK for Python
- PyYAML
- GitHub Actions

## Related Links

- [Docker SDK for Python Documentation](https://docker-py.readthedocs.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

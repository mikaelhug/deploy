## "GitOps" Deployment of Docker Containers

When a change is made to your docker-fleet repository, GitHub will SSH your server and trigger the deployment script from this repository which will then look for changes and deploy them on the server.

```
$ ls /opt/
containerd  deploy  docker-fleet
```

## Installation

### On the server

```bash
cd /opt && sudo git clone https://github.com/mikaelhug/deploy.git
sudo chown -R deployer:deployer deploy
```

### On deployer user

Edit your SSH authorized_keys:

```bash
nano ~/.ssh/authorized_keys
```

Add the following line (replace `<PUBLIC_KEY>` with the actual key):

```
command="python3 /opt/deploy/deploy.py",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 <PUBLIC_KEY> github-actions-deploy
```

### Inside docker-fleet repo

Add a `sync.yml` file for webhook configuration

## GitHub Actions Workflow

To automatically deploy your containers when changes are pushed to your docker-fleet repository, create a GitHub Actions workflow:

### 1. Generate SSH Key Pair

Generate a dedicated SSH key pair for GitHub Actions (on your server or locally):

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy_key -N ""
```

### 2. Add Public Key to Server

Copy the public key to your server's authorized_keys (as shown in the installation steps above).

### 3. Add Private Key to GitHub Secrets

1. Go to your docker-fleet repository settings
2. Navigate to **Secrets and variables** → **Actions**
3. Create a new secret called `SSH_PRIVATE_KEY` and paste the contents of the private key
4. Create a secret called `SERVER_HOST` with your server's hostname/IP
5. Create a secret called `SERVER_USER` with the deployer username (e.g., `deployer`)

### 4. Create Workflow File

Create `.github/workflows/deploy.yml` in your docker-fleet repository:

```yaml
name: Sync Fleet

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Fleet Update
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: run-fleet # The command is ignored due to the SSH key lock
```

This workflow will:
- Trigger on every push to the `main` branch
- SSH into your server
- Update the docker-fleet repository
- Run the deployment script to detect and deploy changes
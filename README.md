# "GitOps" Deployment of Docker Containers
When a change is made to your docker-fleet repository, GitHub will SSH your server and trigger the deployment script from this repository which will then look for changes and deploy them on the server.

# Installation
On the server
cd /opt && sudo git clone https://github.com/mikaelhug/deploy.git
sudo chown -R deployer:docker deploy

On deployer user
nano ~/.ssh/authorized_keys
> command="/opt/deploy/deploy.py",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 <PUBLIC_KEY> github-actions-deploy
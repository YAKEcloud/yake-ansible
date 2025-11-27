# YAKE Ansible — Documentation

This repository contains Ansible roles and playbooks to prepare a Kubernetes cluster using the Gardener Operator to create Gardener clusters. The goal of this documentation is to provide a clear, practical guide for getting started, configuring and operating the automation provided in this repository.

## Table of Contents

- [Overview](#overview)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Quick start](#quick-start)
- [Playbooks and Roles](#playbooks-and-roles)
- [Secrets and credentials](#secrets-and-credentials)
- [Testing and validation](#testing-and-validation)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Overview

This repository automates the preparation of a Kubernetes host environment and the installation/configuration of the Gardener Operator so that a Gardener cluster can be provisioned. It focuses on repeatable, idempotent Ansible roles and playbooks that can run against target hosts or management nodes.

## Repository layout

- `roles/` - reusable Ansible roles (ssh, packages, docker, kubeadm, gardener-operator, etc.)
- `group_vars/` - environment-specific variables
- `docs/` - this documentation
- `/` - playbooks which will be used

## Requirements

A minimum of the following resources is required to run a productive Gardener + Managed Seed + Shoots:

- 10 routers (each cluster requires its own router)
- 10 networks (each cluster requires its own network)
- 15 security groups
- 15 floating IPs
- 1.5 TB volume storage
- 40 volumes
- 150 GB RAM
- 50 VCPUs

In addition, at least two projects are required:

- One for control plane + managed seed
- Another for shoots for testing

The following services are required:

- A load balancer service such as Octavia (currently only supported)
- A DNS service such as Designate
- If you want to use backups, an S3 service such as Openstack's Object Store, Hetzner Object Storage, or Backblaze

The rest is not as critical, but should be adjusted in case of bottlenecks. With the specifications mentioned above, the number of shoots is of course limited. If you want to build many large shoots, the resources must be adapted accordingly.

## Prerequisites

- Python 3 on control and target hosts.
- kubectl and relevant cloud CLIs installed on the machine that administers Gardener targets (if required).
- Credentials for the infrastructure provider (cloud account, service principal, or secret) used by Gardener to create target clusters.
- Sufficient privileges to create resources on target nodes and in the cloud provider.

Install commonly required management-node tooling:

```bash
sudo apt install python3-virtualenv -y # if you're on Ubuntu
virtualenv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Configuration

Variables: configure `group_vars/all.yml` and group-specific files for values such as:
  - K8s version
  - Gardener version
  - Cloud provider credentials and secrets
  - CloudProfile configurations
  - ManagedSeed configurations
  
Have a look at `all.yml.example` for a inspiration. Nevertheless you need to have a look at the `default/main.yml` at all roles.

## Quick start

1. Setup you environment.

2. Prepare the variables.

3. Run the playbook to setup the whole Gardener cluster:

```bash
ansible-playbook -i localhost, -c local site.yml (--ask-become-pass)
```
or

4. Run single steps:

```bash
ansible-playbook -i localhost, -c local kubectl-install.yml
ansible-playbook -i localhost, -c local helm-install.yml
ansible-playbook -i localhost, -c local clusterctl-install.yml
ansible-playbook -i localhost, -c local kind-install.yml
ansible-playbook -i localhost, -c local kind-cluster.yml
ansible-playbook -i localhost, -c local clusterapi-install.yml
ansible-playbook -i localhost, -c local clusterapi-cluster.yml
ansible-playbook -i localhost, -c local gardener-operator.yml
```

## Playbooks and Roles

- site.yml - will setup all in one (1) single step.
- all other playbooks - deploy what the playbook says.

Each role should include:
- `tasks/` — main tasks
- `defaults/main.yml` — sensible defaults
- `templates/` — Kubernetes manifests or config templates

## Secrets and credentials

- Never commit plain-text credentials.
- Use Ansible Vault for any secrets stored in group_vars or host_vars:
  - `ansible-vault encrypt vars/secure.yml`
  - Use `--ask-vault-pass` or `--vault-password-file` on playbook runs.
- Alternatively, integrate with HashiCorp Vault, AWS Secrets Manager, or other secret backends as a pre-step.

## Testing and validation

- Lint roles/playbooks: use `ansible-lint` and fix reported issues.
- Dry-run with `--check` where suitable:

```bash
ansible-playbook -i localhost, -c local site.yml --check
```

- Validate deployed resources with `kubectl`:

```bash
kubectl get pods -n <gardener-namespace>
kubectl describe pod <pod-name> -n <gardener-namespace>
```

## Troubleshooting

- Check Ansible verbose output: add `-vvv` to get detailed logs.
- SSH connectivity: verify key permissions and host reachability.
- Service failures: inspect systemd logs on the node (`journalctl -u <service>`).
- Kubernetes/Gardener issues: use `kubectl logs` and `kubectl describe` for troubleshooting operator/pod problems.
- Check role variable precedence: group_vars > role defaults.

## Contributing

- Create an issue to discuss larger changes before implementing.
- Submit pull requests with focused, well-documented changes and tests where applicable.
- Keep secrets out of commits.

## License

Refer to the repository `LICENSE` file for licensing details.

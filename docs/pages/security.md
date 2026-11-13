# Security

This page collects what matters for running yake-ansible in production. The variables are described in the [configuration reference](configuration.md).

## Secrets in your configuration

`group_vars/all.yml` contains OpenStack credentials, the Dex dashboard secret and, depending on your setup, certificate keys. The file is listed in `.gitignore` and stays out of the repository by default.

- Do not commit it in plain text. If you keep your configuration in git, encrypt it with [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html). The CI configuration of this repository does exactly that, see [Operations](operations.md#ci-variables-group_varsciyml).
- Back up `/var/lib/yake/` together with the configuration. It holds kubeconfigs and generated keys. The OpenStack credentials the playbook writes there have mode `0600`.

## OpenStack credentials

- Use application credentials instead of a username and password. They can be revoked without changing the password of a user.
- Use separate credentials for the garden cluster and for each managed seed, if your OpenStack projects are separated. Each managed seed has its own `openstack` block in `gardener_operator_managed_seeds`.
- If your OpenStack uses a custom CA, set `gardener_operator_openstack_cacert` instead of disabling certificate verification.

## Secrets at rest

`clusterapi_cluster_secrets_encryption_enabled` encrypts Secrets at rest in the etcd of the garden cluster. Without it, all Gardener credentials are stored in plain text in etcd and in its backups. The option is recommended, enabled in `group_vars/all.yml.example` and opt-in, because it cannot simply be disabled again. The key is generated once and stored in the Secret `<name>-encryption-config` in the management cluster and in `/var/lib/yake/encryption-key.<name>`.

!!! warning "Back up the encryption key"
    Without the key you cannot read the encrypted Secrets any more. Enabling the option rolls the control plane, and the role refuses to disable it again.

## Certificates

The shoot certificate service signs certificates for the Garden components, Dex and the seed ingress. Set `gardener_operator_shoot_cert_service_issuer_type` to:

- `acme` to use Let's Encrypt or your own ACME endpoint. This is the default.
- `ca` to use your own certificate authority, for example in air-gapped setups. Without a certificate and key, the role generates a root CA once in `/var/lib/yake/ca` and reuses it.

If you use the generated CA, keep `/var/lib/yake/ca` safe and distribute the root certificate to the clients that must trust your endpoints.

The check after the installation that the dashboard login reaches Dex validates the TLS certificate by default. Switch `gardener_operator_login_check_validate_certs` off only for tests with self-signed certificates.

## Access to Gardener

Users sign in to the dashboard through Dex.

- `gardener_operator_dex.static_passwords` holds bcrypt hashes, never plain text passwords. Static users are meant for the first access. For teams, connect your identity provider through `gardener_operator_dex.connectors`.
- `gardener_operator_garden_cluster_admin_email` is the cluster admin of the dashboard and the default member of the `seeds` project. Use a mailbox that people can control.
- Give project members the least role they need. Members are set per project in `gardener_operator_projects`.

## Network isolation

- `gardener_operator_seed_block_cidrs` is blocked in all shoot clusters by a NetworkPolicy. The default blocks the metadata service `169.254.169.254/32`, so workloads in shoots cannot reach OpenStack instance metadata. Add more CIDRs that shoots must not reach, for example internal management networks.
- The endpoints that are reachable from outside OpenStack, such as the Kubernetes API, the Istio ingress gateway and the per-shoot load balancers, are listed in [Networking](networking.md#ports). Compare them with your firewall rules.
- If you use a proxy (`gardener_operator_proxy_host`), a NetworkPolicy allows the traffic from the managed seeds to it.

## Updates

Only the newest Gardener version is maintained, so upgrade regularly. See [Releases](releases.md) for the versioning and [Operations](operations.md#upgrading) for the upgrade steps.

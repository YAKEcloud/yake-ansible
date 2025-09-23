# yake-ansible

At the moment we only support Openstack as infrastructure and for DNS. Get in contact with us, if you need another Cloud.
But it is possible to write your own cloudprofiles for AWS, Azure, or GCP (we have already implemented the extensions for this as an option).

## Installation

```bash
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Usage

```bash
ansible-playbook -i localhost, -c local site.yml
```

### Single steps

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

### Accessing the Cluster API cluster

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl get nodes
```

### Accessing the Garden cluster

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
./.local/yake-kubectl get nodes
```

### Patch/Upgrade
If you want to patch/upgrade your gardener, just run the playbook once again and set the variable `gardener_operator_version` to the next version you like. Your gardener will be patched/upgraded to this version.

### Managed Seed Terminal
If you want to use the web terminal for shoots running on a managed seed, you need to add a certificate and a secret there.

Use the Gardener dashboard to access the shoot that acts as a managed seed.

Once you have access, you can add the following to the cluster (please adapt it to your infrastructure):

```bash
kubectl apply -f - <<EOF
apiVersion: cert.gardener.cloud/v1alpha1
kind: Certificate
metadata:
  annotations:
    cert.gardener.cloud/class: garden
    cert.gardener.cloud/dnsrecord-class: garden
    cert.gardener.cloud/dnsrecord-provider-type: openstack-designate
    cert.gardener.cloud/dnsrecord-secret-ref: openstack-cloud
  name: seed-ingress
  namespace: garden
spec:
  commonName: "*.<SEED_PROJECT>.<GARDENER_URL>"
  issuerRef:
    name: default-issuer
    namespace: garden
  secretRef:
    name: seed-ingress-certificate
    namespace: garden
---
apiVersion: v1
kind: Secret
metadata:
  labels:
    gardener.cloud/role: controlplane-cert
  name: seed-ingress-certificate
  namespace: garden
type: Opaque
EOF
```

You should then be able to access all shoots running on the managed seed via the terminal.

### Cleanup

```bash
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
./.local/yake-kubectl delete cluster garden
./.local/yake-kind delete cluster --name clusterapi
docker rm -f $(docker ps -qa)
sudo rm -rf /var/lib/yake/
```

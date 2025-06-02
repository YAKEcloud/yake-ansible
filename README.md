# yake-ansible

## Installation

```
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Usage

Configure all.yml to your needs:
```
cp group_vars/all.yml.example group_vars/all.yml
```
Run the playbook:
```
ansible-playbook -i localhost, -c local site.yml
```

### Single steps

```
ansible-playbook -i localhost, -c local kubectl-install.yml
ansible-playbook -i localhost, -c local helm-install.yml
ansible-playbook -i localhost, -c local clusterctl-install.yml
ansible-playbook -i localhost, -c local kind-install.yml
ansible-playbook -i localhost, -c local kind-cluster.yml
ansible-playbook -i localhost, -c local clusterapi-install.yml
ansible-playbook -i localhost, -c local clusterapi-cluster.yml
ansible-playbook -i localhost, -c local flux-install.yml
ansible-playbook -i localhost, -c local ingress-nginx-install.yml
ansible-playbook -i localhost, -c local cert-manager-install.yml
ansible-playbook -i localhost, -c local keycloak-install.yml
```

### Accessing the Cluster API cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
yake-kubectl get nodes
```

### Accessing the Garden cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
yake-kubectl get nodes
```

### Cleanup

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
yake-kubectl delete cluster garden
yake-kind delete cluster --name clusterapi
```

# yake-ansible

## Installation

```
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy install -f -r requirements.yml
```

## Usage

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
```

### Accessing the Cluster API cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
kubectl get nodes
```

### Accessing the Garden cluster

```
export KUBECONFIG=/var/lib/yake/kubeconfig.garden
kubectl get nodes
```

### Cleanup

```
export KUBECONFIG=/var/lib/yake/kubeconfig.clusterapi
kubectl delete cluster garden
kind delete cluster --name clusterapi
```

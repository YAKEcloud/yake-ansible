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
ansible-playbook -i localhost, -c local clusterctl-install.yml
ansible-playbook -i localhost, -c local kind-install.yml
ansible-playbook -i localhost, -c local kind-cluster.yml
ansible-playbook -i localhost, -c local clusterapi-install.yml
ansible-playbook -i localhost, -c local clusterapi-cluster.yml
```

### Accessing the workload cluster

```
kubectl get cluster
clusterctl describe cluster yake
kubectl get kubeadmcontrolplane
clusterctl get kubeconfig yake
```

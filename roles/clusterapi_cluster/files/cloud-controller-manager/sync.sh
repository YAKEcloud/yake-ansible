#!/usr/bin/env bash

VERSION=v1.31.2

for file in cloud-controller-manager-role-bindings.yaml cloud-controller-manager-roles.yaml openstack-cloud-controller-manager-ds.yaml; do
    curl -o $file https://raw.githubusercontent.com/kubernetes/cloud-provider-openstack/refs/tags/$VERSION/manifests/controller-manager/$file
done

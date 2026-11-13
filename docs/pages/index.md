---
title: Yet another Kubernetes Engine (now in Ansible)
hide:
  - navigation
  - toc
---

<div class="yake-hero" markdown>

# Yet another Kubernetes Engine (now in Ansible)

**Gardener on OpenStack, from zero to a working landscape.**

[Get started](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/YAKEcloud/yake-ansible){ .md-button }

![YAKE overview](assets/overview-light.svg#only-light){ .yake-overview }
![YAKE overview](assets/overview-dark.svg#only-dark){ .yake-overview }

</div>

yake-ansible automates the deployment of a Gardener-based Kubernetes platform on OpenStack. It provisions a management cluster, initializes Cluster API with the OpenStack provider, creates a dedicated garden cluster, and installs the Gardener Operator with cloud profiles, managed seeds, and all required extensions.

The result is a fully operational Gardener installation that can manage Kubernetes shoot clusters across one or more OpenStack tenants.

<div class="grid cards yake-cards" markdown>

-   **Easy bootstrapping**

    ---

    One playbook takes you from an empty OpenStack tenant to a running Gardener landscape.

-   **Declarative configuration**

    ---

    The whole setup is described by Ansible variables in your inventory. Changes are tracked in git and documented by the configuration itself.

-   **Easy updates**

    ---

    Gardener, Cluster API and all extensions are versioned and tested together, so upgrades stay a routine task.

</div>

## A project by ALASCA

<div class="yake-alasca" markdown>

<div markdown>

In January 2024, YAKE found its new home at [ALASCA](https://alasca.cloud/), a non-profit organisation for the development of operational, open cloud infrastructures. ALASCA's mission revolves around open source tools that enable and simplify the development and operation of customised cloud infrastructures.

Besides the practical development work, ALASCA also acts as a provider of knowledge on these topics, for example with the ALASCA Tech Talks. With a strong, motivated community and the combined expertise of its members, ALASCA drives digital sovereignty in Germany and Europe, also in collaboration with other open source initiatives.

</div>

<div markdown>

[![ALASCA](assets/logo-alasca.png#only-light){ width="300" }](https://alasca.cloud/)
[![ALASCA](assets/logo-alasca_dark.png#only-dark){ width="300" }](https://alasca.cloud/)

</div>

</div>

## Support

When you build your productive Gardener environment on YAKE, you also get support from the engineers at [23 Technologies](https://23technologies.cloud). From simple configuration questions to advanced Gardener operations, we are by your side.

## Legacy: YAKE with Flux

The previous, Flux-based YAKE installer and its documentation live on in the [YAKEcloud/yake](https://github.com/YAKEcloud/yake) repository.

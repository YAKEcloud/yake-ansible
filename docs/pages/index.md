---
title: Yet another Kubernetes Engine (now in Ansible)
hide:
  - navigation
  - toc
---

<div class="yake-hero" markdown>

# Yet another Kubernetes Engine (now in Ansible)

**Gardener on OpenStack, from zero to a working landscape.**

[Get started](requirements.md){ .md-button .md-button--primary }
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

<div class="yake-alasca" markdown>

<div markdown>

## A project by ALASCA

In January 2024, YAKE found its new home at [ALASCA](https://alasca.cloud/), a non-profit organisation for the development of operational, open cloud infrastructures. ALASCA builds open source tools that make it easier to run customised cloud infrastructures, shares its knowledge, for example in the ALASCA Tech Talks, and drives digital sovereignty in Germany and Europe together with a strong community.

[Visit alasca.cloud](https://alasca.cloud/){ .md-button }

</div>

<div markdown>

[![ALASCA](assets/ALASCA-Logo-black-claim-EN.svg#only-light){ width="400" }![ALASCA](assets/ALASCA-Logo-white-claim-EN.svg#only-dark){ width="400" }](https://alasca.cloud/)

</div>

</div>

<div class="grid cards yake-cards yake-cards--two" markdown>

-   **Support**

    ---

    When you build your productive Gardener environment on YAKE, you also get support from the engineers at [23 Technologies](https://23technologies.cloud). From simple configuration questions to advanced Gardener operations, we are by your side.

-   **Legacy: YAKE with Flux**

    ---

    The previous, Flux-based YAKE installer and its documentation live on in the [YAKEcloud/yake](https://github.com/YAKEcloud/yake) repository.

</div>

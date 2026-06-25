# Local Infra Collection

This Ansible collection (`local.infra`) manages the local server infrastructure and services for the Catstar project.

## Structure

* **Plugins:** Custom filter plugins (e.g., Nginx configurations/blocks).
* **Roles:** Modular deployment and provisioning roles:
  * `common`: Core system settings, swappiness, and shell environments.
  * `nginx`: High-performance Nginx web server configurations.
  * `ssl`: SSL certificate deployments.
  * `v2ray`: Network routing and tunnel daemons.

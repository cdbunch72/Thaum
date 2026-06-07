# Cloud deployment quickstarts

Cloud deploy documentation and example artifacts (Dockerfile, CI workflows, Azure provisioning guides) live in the **[Thaum Cloud](https://gemstone-software-dev.github.io/thaum-cloud/)** template repository—not in this upstream tree.

| Resource | Link |
|----------|------|
| **Documentation hub** | https://gemstone-software-dev.github.io/thaum-cloud/ |
| **Azure Container Apps quickstart** | https://gemstone-software-dev.github.io/thaum-cloud/quickstart/azure/quickstart_aca.html |
| **Template repository** | https://github.com/gemstone-software-dev/thaum-cloud |

Fork or copy **thaum-cloud** for org-specific `thaum.toml`, Dockerfile, and GitHub Actions. Upstream Thaum publishes **cloud-neutral** container images (`thaum`, `thaum-external-db`); see the main [README](../../README.md) “Container images (CI)”.

For **Kubernetes** (any cluster), use the in-repo guide: [quickstart/kubernetes/README.md](../kubernetes/README.md).

## See also

- [Deployment quickstarts index](../../docs/deployment-quickstarts.md)
- [Thaum quickstart index](../QUICKSTART.md)

// DASH-004 addition - Client Software page "Update" action.
//
// Wires the per-row Update button to the EXISTING deployment creation
// endpoint (DEPLOY-001, POST /api/admin/deployments). No new deployment
// mechanism is introduced here - this only sends the same request shape
// backend/schemas/deployment.py::DeploymentCreateRequest already expects,
// using the same CSRF cookie/header convention as dashboard.js.
//
// Relies on the global `readCookie()` helper defined in dashboard.js,
// which is loaded before this script (see base.html).

document.addEventListener("DOMContentLoaded", () => {
    const alertBox = document.getElementById("updateAlert");

    function showAlert(message, isError) {
        if (!alertBox) {
            return;
        }
        alertBox.textContent = message;
        alertBox.classList.remove("d-none", "alert-success", "alert-danger");
        alertBox.classList.add(isError ? "alert-danger" : "alert-success");
    }

    document.querySelectorAll(".update-btn").forEach((button) => {
        button.addEventListener("click", async () => {
            const clientId = button.dataset.clientId;
            const repositoryPackageId = button.dataset.repositoryPackageId;
            const softwareName = button.dataset.softwareName;
            const approvedVersion = button.dataset.approvedVersion;

            const confirmed = window.confirm(
                `Deploy ${softwareName} ${approvedVersion} to this client?`
            );
            if (!confirmed) {
                return;
            }

            const originalText = button.textContent;
            button.disabled = true;
            button.textContent = "Deploying...";

            try {
                const response = await fetch("/api/admin/deployments", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": readCookie("csrf_token") || "",
                    },
                    body: JSON.stringify({
                        repository_package_id: repositoryPackageId,
                        client_ids: [clientId],
                    }),
                });

                const payload = await response.json().catch(() => null);

                if (!response.ok) {
                    const message =
                        (payload && (payload.message || payload.detail)) ||
                        (response.status === 409
                            ? "This client already has an active deployment in progress."
                            : `Unable to start deployment (HTTP ${response.status}).`);
                    throw new Error(message);
                }

                showAlert(`Deployment for ${softwareName} ${approvedVersion} queued successfully.`, false);
                button.textContent = "Queued";
                // Left disabled: the server is now the source of truth for
                // this client's active-deployment state (DeploymentClientActiveError,
                // 409). A page reload reflects the current status accurately.
            } catch (error) {
                showAlert(error.message || "Unable to start deployment.", true);
                button.disabled = false;
                button.textContent = originalText;
            }
        });
    });
});
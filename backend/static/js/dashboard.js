// DASH-001 - Dashboard JavaScript.
//
// Wires the navbar "Log out" button to the already-existing
// POST /api/admin/logout endpoint (AUTH-001).
//
// Also provides the administrator-facing client provisioning workflow:
// POST /api/admin/keys -> display provisioning key -> generate the
// PowerShell registration command.
//
// No new authentication or registration logic is introduced here.
// The existing backend provisioning and registration endpoints remain
// responsible for those operations.

function readCookie(name) {
    const match = document.cookie.match(
        new RegExp("(?:^|; )" + name + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : null;
}

document.addEventListener("DOMContentLoaded", () => {

    // ---------------------------------------------------------------
    // Administrator logout
    // ---------------------------------------------------------------

    const logoutButton = document.getElementById("logoutButton");

    if (logoutButton) {
        logoutButton.addEventListener("click", async () => {
            try {
                await fetch("/api/admin/logout", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRF-Token": readCookie("csrf_token") || "",
                    },
                });
            } finally {
                window.location.href = "/login";
            }
        });
    }

    // ---------------------------------------------------------------
    // Client provisioning
    // ---------------------------------------------------------------
    const hostname = document.getElementById("clientHostname").value.trim();

    const generateButton = document.getElementById(
        "generateProvisioningKeyBtn"
    );

    if (!generateButton) {
        return;
    }

    const provisioningInitialState = document.getElementById(
        "provisioningInitialState"
    );

    const provisioningResult = document.getElementById(
        "provisioningResult"
    );

    const provisioningKeyInput = document.getElementById(
        "provisioningKey"
    );

    const registrationCommand = document.getElementById(
        "registrationCommand"
    );

    const provisioningError = document.getElementById(
        "provisioningError"
    );

    const copyProvisioningKeyButton = document.getElementById(
        "copyProvisioningKeyBtn"
    );

    const copyRegistrationCommandButton = document.getElementById(
        "copyRegistrationCommandBtn"
    );

    const copySuccess = document.getElementById("copySuccess");

    // Generate a new administrator-issued provisioning credential.
    generateButton.addEventListener("click", async () => {
        generateButton.disabled = true;
        generateButton.textContent = "Generating...";

        provisioningError.classList.add("d-none");
        provisioningError.textContent = "";

        try {
            const response = await fetch("/api/admin/keys", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRF-Token": readCookie("csrf_token") || "",
                    "Content-Type": "application/json",
                },
            });

            const payload = await response.json().catch(() => null);

            if (!response.ok) {
                const message =
                    payload?.message ||
                    payload?.detail ||
                    `Unable to generate provisioning key (HTTP ${response.status}).`;

                throw new Error(message);
            }

            const apiKey = payload?.data?.api_key;

            if (!apiKey) {
                throw new Error(
                    "The server did not return a provisioning key."
                );
            }

            // Display the generated provisioning credential.
            provisioningKeyInput.value = apiKey;

            // Build the command using the server the administrator is
            // currently accessing. This avoids hardcoding the server IP.
            const serverUrl = window.location.origin;
            const hostname = document.getElementById("clientHostname").value.trim();

            if (!hostname) {
                provisioningError.textContent = "Please enter a hostname.";
                provisioningError.classList.remove("d-none");
                return;
            }

            const command = [
                `$env:AGENT_API_KEY="${apiKey}"`,
                `$env:AGENT_SERVER_URL="${serverUrl}"`,
                `$env:AGENT_HOSTNAME="${hostname}"`,
                "python -m agent.main",
            ].join("\n");

            registrationCommand.value = command;

            provisioningInitialState.classList.add("d-none");
            provisioningResult.classList.remove("d-none");

        } catch (error) {
            provisioningError.textContent =
                error.message || "Unable to generate provisioning key.";

            provisioningError.classList.remove("d-none");

        } finally {
            generateButton.disabled = false;
            generateButton.textContent = "Generate Provisioning Key";
        }
    });

    // Copy only the provisioning key.
    if (copyProvisioningKeyButton) {
        copyProvisioningKeyButton.addEventListener("click", async () => {
            const key = provisioningKeyInput.value;

            if (!key) {
                return;
            }

            try {
                await navigator.clipboard.writeText(key);

                copyProvisioningKeyButton.textContent = "Copied";

                setTimeout(() => {
                    copyProvisioningKeyButton.textContent = "Copy";
                }, 1500);

            } catch (error) {
                provisioningKeyInput.select();
                document.execCommand("copy");
            }
        });
    }

    // Copy the complete PowerShell registration command.
    if (copyRegistrationCommandButton) {
        copyRegistrationCommandButton.addEventListener(
            "click",
            async () => {
                const command = registrationCommand.value;

                if (!command) {
                    return;
                }

                try {
                    await navigator.clipboard.writeText(command);

                    copyRegistrationCommandButton.textContent =
                        "Copied";

                    if (copySuccess) {
                        copySuccess.classList.remove("d-none");

                        setTimeout(() => {
                            copySuccess.classList.add("d-none");
                        }, 2000);
                    }

                    setTimeout(() => {
                        copyRegistrationCommandButton.textContent =
                            "Copy Command";
                    }, 1500);

                } catch (error) {
                    registrationCommand.select();
                    document.execCommand("copy");

                    copyRegistrationCommandButton.textContent =
                        "Copied";

                    setTimeout(() => {
                        copyRegistrationCommandButton.textContent =
                            "Copy Command";
                    }, 1500);
                }
            }
        );
    }

    // Reset the modal whenever it is closed so the next registration
    // starts from a clean state.
    const registerModal = document.getElementById(
        "registerClientModal"
    );

    if (registerModal) {
        registerModal.addEventListener("hidden.bs.modal", () => {
            provisioningInitialState.classList.remove("d-none");
            provisioningResult.classList.add("d-none");

            provisioningKeyInput.value = "";
            registrationCommand.value = "";

            provisioningError.classList.add("d-none");
            provisioningError.textContent = "";

            if (copySuccess) {
                copySuccess.classList.add("d-none");
            }
        });
    }
});
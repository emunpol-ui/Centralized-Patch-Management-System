// DASH-001 - minimal dashboard JavaScript.
//
// Wires the navbar "Log out" button to the already-existing
// POST /api/admin/logout endpoint (AUTH-001). No new authentication
// logic is introduced here.

function readCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
}

document.addEventListener("DOMContentLoaded", () => {
    const logoutButton = document.getElementById("logoutButton");
    if (!logoutButton) {
        return;
    }

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
});

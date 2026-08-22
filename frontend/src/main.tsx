import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/400.css";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./index.css";
import { clearDevServiceWorkers } from "./app/devServiceWorker";
import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";

async function mountApp() {
    if (await clearDevServiceWorkers()) {
        window.location.reload();
        return;
    }

    ReactDOM.createRoot(document.getElementById("root")!).render(
        <React.StrictMode>
            <AppProviders>
                <AppRouter />
            </AppProviders>
        </React.StrictMode>,
    );
}

void mountApp();

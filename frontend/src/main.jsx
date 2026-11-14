import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { BrowserRouter } from "react-router-dom";
import "bootstrap/dist/css/bootstrap.min.css";
import "@fontsource/press-start-2p/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import store from "./store";
import "./index.css";
import "./theme.css"; // the student and company themes; must come after index.css

// Provider       = gives every component access to the Redux store (src/store)
// BrowserRouter  = lets the address bar change without reloading the page
// AuthProvider   = checks the stored login at start-up and signs out on a 401
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Provider store={store}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </Provider>
  </React.StrictMode>
);

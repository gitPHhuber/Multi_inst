import React from "react";
import ReactDOM from "react-dom/client";
import "./app.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import DevicePage from "./components/DevicePage";

document.documentElement.dataset.theme = "dark";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/device/:uid" element={<DevicePage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

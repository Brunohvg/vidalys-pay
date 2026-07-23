"use strict";

window.addEventListener("load", function () {
  const mount = document.getElementById("swagger-ui");
  if (!mount || typeof window.SwaggerUIBundle !== "function") return;

  window.SwaggerUIBundle({
    url: mount.dataset.schemaUrl,
    dom_id: "#swagger-ui",
    deepLinking: true,
    displayRequestDuration: true,
    persistAuthorization: false,
    tryItOutEnabled: false,
  });
});

(function () {
  "use strict";

  // Dashboard quick actions link to #add-member / #issue-loan: open that form.
  if (window.location.hash) {
    var target = document.getElementById(window.location.hash.slice(1));
    if (target && target.tagName === "DETAILS") {
      target.open = true;
    }
  }

  // Ask before destructive or bulk actions, like the desktop app's confirmation dialogs.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });

  // Live "Paying now" total on the payment form.
  document.querySelectorAll("form[data-payment-form]").forEach(function (form) {
    var parts = form.querySelectorAll("[data-payment-part]");
    var output = form.querySelector("[data-payment-total]");
    if (!output) {
      return;
    }
    var formatter = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
    function update() {
      var total = 0;
      parts.forEach(function (input) {
        var value = parseFloat(input.value);
        if (!isNaN(value) && value > 0) {
          total += value;
        }
      });
      output.textContent = "Paying now: " + formatter.format(total);
    }
    parts.forEach(function (input) {
      input.addEventListener("input", update);
    });
    update();
  });

  // Reports page: point each report link at the selected period.
  document.querySelectorAll("form[data-report-form]").forEach(function (form) {
    var select = form.querySelector("[data-report-period]");
    var links = form.querySelectorAll("[data-report-link]");
    function update() {
      links.forEach(function (link) {
        link.href = link.getAttribute("data-report-link").replace(/\/0\./, "/" + select.value + ".");
      });
    }
    select.addEventListener("change", update);
    update();
  });
})();

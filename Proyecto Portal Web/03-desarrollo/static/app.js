document.addEventListener("click", (event) => {
  const dismiss = event.target.closest("[data-dismiss-flash]");
  if (dismiss) {
    const flash = dismiss.closest(".flash");
    if (flash) {
      flash.remove();
    }
    return;
  }

  const confirmTrigger = event.target.closest("[data-confirm]");
  if (confirmTrigger) {
    const message = confirmTrigger.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  }
});

(function () {
  "use strict";

  const nav = document.querySelector(".nav");
  const onScroll = () => {
    if (!nav) {
      return;
    }
    nav.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const revealNodes = document.querySelectorAll(
    ".section-head, .feature-rail, .steps, .finale",
  );
  revealNodes.forEach((node) => node.classList.add("reveal"));

  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.16 },
    );
    revealNodes.forEach((node) => io.observe(node));
  } else {
    revealNodes.forEach((node) => node.classList.add("is-visible"));
  }
})();
